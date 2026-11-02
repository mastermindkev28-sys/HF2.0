"""Background job queue: sends workflows to ComfyUI, tracks progress, stores results locally."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import traceback
from pathlib import Path
from typing import Any

from . import db, media
from .comfy import ComfyClient, ComfyError, pick_output
from .config import ASSETS_DIR, CHARACTERS_DIR, OUTPUTS_DIR, THUMBS_DIR, load_settings
from .engines import UPSCALER, GenRequest, get_engine, installed_from_object_info, upscale_workflow

log = logging.getLogger("higgs.jobs")


def backend_by_id(backend_id: str) -> dict[str, Any]:
    s = load_settings()
    for b in s["backends"]:
        if b["id"] == backend_id:
            return b
    raise ComfyError(f"Backend '{backend_id}' no longer exists. Pick one in Settings.")


def client_for(backend_id: str) -> ComfyClient:
    b = backend_by_id(backend_id)
    return ComfyClient(b["url"], b.get("token", ""))


def resolve_input_path(ref: str) -> Path:
    """Inputs are referenced as 'asset:<id>', 'character:<id>/<file>' or 'generation:<id>'."""
    kind, _, rest = ref.partition(":")
    if kind == "asset":
        a = db.get_asset(rest)
        if not a:
            raise FileNotFoundError("That uploaded file was deleted.")
        return ASSETS_DIR / a["filename"]
    if kind == "character":
        cid, _, fname = rest.partition("/")
        return CHARACTERS_DIR / cid / fname
    if kind == "generation":
        g = db.get_generation(rest)
        if not g or not g.get("output_file"):
            raise FileNotFoundError("That generation has no output file.")
        return OUTPUTS_DIR / g["output_file"]
    raise ValueError(f"Unknown input reference '{ref}'")


class JobManager:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] | None = None
        self.cancels: dict[str, asyncio.Event] = {}
        self.worker: asyncio.Task | None = None
        self.current: str | None = None

    async def start(self) -> None:
        self.queue = asyncio.Queue()
        for g in db.list_generations(limit=1000, status="running"):
            db.update_generation(g["id"], status="error", error="The studio was closed while this was running.")
        for g in reversed(db.list_generations(limit=1000, status="queued")):
            await self.queue.put(g["id"])
        self.worker = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.worker:
            self.worker.cancel()

    async def enqueue(self, gid: str) -> None:
        assert self.queue is not None, "job manager not started"
        await self.queue.put(gid)

    def cancel(self, gid: str) -> None:
        g = db.get_generation(gid)
        if g and g["status"] == "queued":
            db.update_generation(gid, status="cancelled", progress_text="Cancelled")
        ev = self.cancels.get(gid)
        if ev:
            ev.set()

    async def _loop(self) -> None:
        while True:
            gid = await self.queue.get()
            g = db.get_generation(gid)
            if not g or g["status"] != "queued":
                continue
            self.current = gid
            self.cancels[gid] = asyncio.Event()
            started = time.time()
            db.update_generation(gid, status="running", progress=0, progress_text="Preparing")
            try:
                await self._process(g)
                db.update_generation(gid, status="done", progress=1, progress_text="Done",
                                     elapsed_s=round(time.time() - started, 1))
            except asyncio.CancelledError:
                db.update_generation(gid, status="cancelled", progress_text="Cancelled",
                                     elapsed_s=round(time.time() - started, 1))
            except Exception as e:  # report every failure honestly in the UI
                log.error("job %s failed: %s", gid, traceback.format_exc())
                db.update_generation(gid, status="error", error=_humanize(e),
                                     elapsed_s=round(time.time() - started, 1))
            finally:
                self.cancels.pop(gid, None)
                self.current = None

    # ------------------------------------------------------------------
    def _progress_cb(self, gid: str):
        last = {"t": 0.0, "p": 0.0}

        def cb(p: float | None, text: str) -> None:
            now = time.time()
            if p is not None:
                last["p"] = p
            if now - last["t"] > 0.5 or (p is not None and p >= 0.99):
                last["t"] = now
                db.update_generation(gid, progress=round(last["p"], 4), progress_text=text)
        return cb

    async def _process(self, g: dict[str, Any]) -> None:
        mode = g["mode"]
        if mode in ("t2v", "i2v", "v2v"):
            await self._generate(g)
        elif mode == "extend":
            await self._extend(g)
        elif mode in ("interpolate", "upscale_basic", "stitch"):
            await self._ffmpeg_tool(g)
        elif mode == "upscale_ai":
            await self._upscale_ai(g)
        else:
            raise ValueError(f"Unknown mode {mode}")

    async def _check_files(self, client: ComfyClient, engine) -> dict[str, str]:
        info = await client.object_info()
        installed = installed_from_object_info(info)
        resolved = engine.resolve_files(installed)
        missing = [f for f, hit in resolved.items() if hit is None]
        if missing:
            raise ComfyError(f"{engine.name} is not installed on this backend. Missing: {', '.join(missing)}. "
                             f"Install it from Explore Models.")
        return resolved  # type: ignore[return-value]

    async def _run_engine(self, g: dict[str, Any], mode: str, image_path: Path | None,
                          video_path: Path | None, out_name: str) -> Path:
        p = g["params"]
        engine = get_engine(g["engine"])
        if engine.catalog_only:
            raise ComfyError(f"{engine.name} can't run on your current backends (needs ~{engine.min_vram_gb} GB VRAM).")
        if mode not in engine.modes:
            raise ComfyError(f"{engine.name} does not support {mode}.")
        client = client_for(g["backend_id"])
        cb = self._progress_cb(g["id"])
        cb(0.0, "Checking models on backend")
        files = await self._check_files(client, engine)
        image_name = video_name = None
        if image_path is not None:
            cb(0.0, "Uploading image")
            image_name = await client.upload_file(image_path, f"higgs_{g['id']}{image_path.suffix}")
        if video_path is not None:
            cb(0.0, "Uploading video")
            video_name = await client.upload_file(video_path, f"higgs_{g['id']}{video_path.suffix}")
        req = GenRequest(
            mode=mode, prompt=g["final_prompt"] or g["prompt"], negative=g.get("negative_prompt") or "",
            aspect=p.get("aspect", "16:9"), resolution=p.get("resolution") or engine.defaults["resolution"],
            duration_s=float(p.get("duration_s", engine.defaults["duration_s"])), fps=int(p.get("fps", engine.defaults["fps"])),
            steps=int(p.get("steps", engine.defaults["steps"])), cfg=float(p.get("cfg", engine.defaults["cfg"])),
            seed=int(p.get("seed", 0)), image=image_name, video=video_name,
            denoise=float(p.get("denoise", engine.defaults.get("denoise", 0.6))), extra=p.get("extra", {}),
        )
        workflow = engine.build(req, files)
        (OUTPUTS_DIR / f"{out_name}.workflow.json").write_text(json.dumps(workflow, indent=2))
        result = await client.run(workflow, cb, self.cancels.get(g["id"]))
        db.update_generation(g["id"], comfy_prompt_id=result.get("prompt_id"))
        out = pick_output(result)
        if not out:
            raise ComfyError("The backend finished but returned no video file.")
        cb(0.97, "Downloading result")
        raw = OUTPUTS_DIR / f"{out_name}.raw{Path(out['filename']).suffix}"
        await client.download(out["filename"], out.get("subfolder", ""), out.get("type", "output"), raw)
        final = OUTPUTS_DIR / f"{out_name}.mp4"
        if raw.suffix.lower() == ".mp4":
            raw.replace(final)
        else:
            await media.to_mp4(raw, final)
            raw.unlink(missing_ok=True)
        return final

    async def _finish(self, gid: str, video: Path) -> None:
        thumb = THUMBS_DIR / f"{gid}.jpg"
        try:
            await media.thumbnail(video, thumb)
            thumb_name = thumb.name
        except media.MediaError:
            thumb_name = None
        info = await media.probe(video)
        db.update_generation(gid, output_file=video.name, thumb_file=thumb_name, duration_s=info.get("duration_s"))

    async def _generate(self, g: dict[str, Any]) -> None:
        p = g["params"]
        image = resolve_input_path(p["image"]) if g["mode"] == "i2v" else None
        video = resolve_input_path(p["video"]) if g["mode"] == "v2v" else None
        if p.get("finish_1080p"):  # check before spending GPU time on the generation
            installed = installed_from_object_info(await client_for(g["backend_id"]).object_info())
            if not any(n in installed.get("upscale_models", []) for n in [UPSCALER.filename, *UPSCALER.alternatives]):
                raise ComfyError("“Finish in 1080p” needs the Real-ESRGAN upscaler on this backend. Install it from Explore Models.")
        out = await self._run_engine(g, g["mode"], image, video, g["id"])
        if p.get("finish_1080p"):
            out = await self._to_1080p(g, out)
        await self._finish(g["id"], out)

    async def _to_1080p(self, g: dict[str, Any], src: Path) -> Path:
        """Real-ESRGAN x2 on the backend, then an exact 1080p frame (1920x1080, 1080x1920, ...) with FFmpeg."""
        cb = self._progress_cb(g["id"])
        cb(0.975, "Upscaling to 1080p (Real-ESRGAN)")
        up = OUTPUTS_DIR / f"{g['id']}.x2.mp4"
        await self._ai_upscale_file(g, src, up, report=False)
        final = OUTPUTS_DIR / f"{g['id']}.1080p.mp4"
        await media.fit_1080(up, final, g["params"].get("aspect", "16:9"))
        up.unlink(missing_ok=True)
        if src != final:
            src.unlink(missing_ok=True)
        return final

    async def _extend(self, g: dict[str, Any]) -> None:
        """Real extension: the source clip's last frame seeds an image-to-video continuation, then both are joined."""
        p = g["params"]
        src = resolve_input_path(f"generation:{p['source_id']}")
        cb = self._progress_cb(g["id"])
        cb(0.0, "Extracting last frame")
        frame = OUTPUTS_DIR / f"{g['id']}.lastframe.png"
        await media.last_frame(src, frame)
        cont = await self._run_engine(g, "i2v", frame, None, f"{g['id']}.cont")
        cb(0.98, "Stitching")
        final = OUTPUTS_DIR / f"{g['id']}.mp4"
        await media.concat([src, cont], final)
        frame.unlink(missing_ok=True)
        await self._finish(g["id"], final)

    async def _ffmpeg_tool(self, g: dict[str, Any]) -> None:
        p = g["params"]
        cb = self._progress_cb(g["id"])
        final = OUTPUTS_DIR / f"{g['id']}.mp4"
        if g["mode"] == "interpolate":
            cb(0.1, "Interpolating frames (FFmpeg)")
            await media.interpolate(resolve_input_path(p["source"]), final, int(p.get("target_fps", 48)))
        elif g["mode"] == "upscale_basic":
            cb(0.1, "Upscaling (FFmpeg Lanczos)")
            await media.upscale_basic(resolve_input_path(p["source"]), final, int(p.get("factor", 2)))
        elif g["mode"] == "stitch":
            cb(0.1, "Stitching clips")
            await media.concat([resolve_input_path(s) for s in p["sources"]], final, drop_first_frame_of_rest=False)
        await self._finish(g["id"], final)

    async def _ai_upscale_file(self, g: dict[str, Any], src: Path, dest: Path, report: bool = True) -> Path:
        client = client_for(g["backend_id"])
        cb = self._progress_cb(g["id"])
        if report:
            cb(0.0, "Checking upscaler on backend")
        installed = installed_from_object_info(await client.object_info())
        names = [UPSCALER.filename, *UPSCALER.alternatives]
        model = next((n for n in names if n in installed.get("upscale_models", [])), None)
        if not model:
            raise ComfyError("The Real-ESRGAN upscaler is not installed on this backend. Install it from Explore Models.")
        info = await media.probe(src)
        name = await client.upload_file(src, f"higgs_{g['id']}_up{src.suffix}")
        wf = upscale_workflow(name, model, info.get("fps") or 24)
        result = await client.run(wf, cb if report else (lambda *_: None), self.cancels.get(g["id"]))
        out = pick_output(result)
        if not out:
            raise ComfyError("The upscaler returned no file.")
        await client.download(out["filename"], out.get("subfolder", ""), out.get("type", "output"), dest)
        return dest

    async def _upscale_ai(self, g: dict[str, Any]) -> None:
        p = g["params"]
        src = resolve_input_path(p["source"])
        final = OUTPUTS_DIR / f"{g['id']}.mp4"
        if p.get("target") == "1080p":
            up = OUTPUTS_DIR / f"{g['id']}.x2.mp4"
            await self._ai_upscale_file(g, src, up)
            self._progress_cb(g["id"])(0.98, "Fitting to 1080p")
            info = await media.probe(src)
            w, h = info.get("width") or 16, info.get("height") or 9
            await media.fit_1080(up, final, aspect_from_size(w, h))
            up.unlink(missing_ok=True)
        else:
            await self._ai_upscale_file(g, src, final)
        await self._finish(g["id"], final)


def aspect_from_size(w: int, h: int) -> str:
    r = w / h
    return min({"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4}.items(), key=lambda kv: abs(kv[1] - r))[0]


def _humanize(e: Exception) -> str:
    import httpx
    if isinstance(e, httpx.ConnectError):
        return ("Couldn't reach the ComfyUI backend. Is it running? (Local: start it with the launcher. "
                "Kaggle: start the notebook and paste its new address in Settings.)")
    if isinstance(e, httpx.HTTPStatusError):
        return f"Backend returned HTTP {e.response.status_code} for {e.request.url.path}."
    if isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout)):
        return "The backend stopped responding (timeout)."
    msg = str(e) or type(e).__name__
    if "out of memory" in msg.lower() or "OutOfMemory" in msg:
        msg += " — Try a lower resolution or shorter duration."
    return msg


def delete_generation_files(g: dict[str, Any]) -> None:
    for name in (g.get("output_file"), f"{g['id']}.workflow.json", f"{g['id']}.mp4", f"{g['id']}.1080p.mp4", f"{g['id']}.cont.mp4", f"{g['id']}.cont.workflow.json"):
        if name:
            (OUTPUTS_DIR / name).unlink(missing_ok=True)
    if g.get("thumb_file"):
        (THUMBS_DIR / g["thumb_file"]).unlink(missing_ok=True)


def copy_to(src: Path, dest_dir: Path, name: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    shutil.copyfile(src, dest)
    return dest
