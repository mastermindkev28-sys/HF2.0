"""HIGGS Studio API + static UI server.

Run:  uvicorn app.main:app --port 7860   (from backend/), or use scripts/start.sh
"""
from __future__ import annotations

import logging
import platform
import random
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, media, prompting
from .camera import CAMERA_MOVES, build_prompt
from .comfy import ComfyClient, ComfyError
from .config import (ASSETS_DIR, CHARACTERS_DIR, DATA_DIR, FRONTEND_DIR, OUTPUTS_DIR, THUMBS_DIR, load_settings,
                     save_settings)
from .engines import ENGINES, UPSCALER, get_engine, installed_from_object_info
from .hardware import local_hardware
from .jobs import JobManager, backend_by_id, delete_generation_files, resolve_input_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
jobs = JobManager()

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi", ".gif"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await jobs.start()
    yield
    await jobs.stop()


app = FastAPI(title="HIGGS Studio", lifespan=lifespan)


@app.exception_handler(ComfyError)
async def comfy_error(_, exc: ComfyError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPError)
async def http_error(_, exc: httpx.HTTPError):
    return JSONResponse(status_code=502, content={"detail": f"Backend unreachable: {type(exc).__name__}. "
                                                            "Check that ComfyUI is running and the address in Settings is right."})


# ---------------------------------------------------------------- basics
@app.get("/api/health")
async def health():
    return {"ok": True, "data_dir": str(DATA_DIR), "ffmpeg": media.ffmpeg_bin(), "queue_current": jobs.current}


@app.get("/api/hardware")
async def hardware():
    return local_hardware()


@app.get("/api/engines")
async def engines():
    return {"engines": [e.info() for e in ENGINES.values()],
            "camera_moves": [{"id": k, "label": v["label"], "text": v["text"]} for k, v in CAMERA_MOVES.items()],
            "upscaler": UPSCALER.__dict__}


@app.get("/api/settings")
async def get_settings():
    return load_settings()


class SettingsIn(BaseModel):
    backends: list[dict[str, Any]] | None = None
    active_backend: str | None = None
    ollama_url: str | None = None
    ollama_model: str | None = None
    ffmpeg_path: str | None = None


@app.put("/api/settings")
async def put_settings(body: SettingsIn):
    s = load_settings()
    for k, v in body.model_dump(exclude_none=True).items():
        s[k] = v
    for b in s["backends"]:
        b["url"] = (b.get("url") or "").strip().rstrip("/")
        b.setdefault("token", "")
    if s["active_backend"] not in {b["id"] for b in s["backends"]}:
        s["active_backend"] = s["backends"][0]["id"]
    return save_settings(s)


# ---------------------------------------------------------------- backends + models
async def _backend_status(b: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"id": b["id"], "name": b["name"], "url": b.get("url", ""), "online": False}
    if not b.get("url"):
        out["error"] = "No address set."
        return out
    client = ComfyClient(b["url"], b.get("token", ""), timeout=20)
    try:
        stats = await client.system_stats()
    except Exception as e:  # noqa: BLE001
        out["error"] = _short_err(e)
        return out
    out["online"] = True
    out["system"] = stats.get("system", {})
    out["devices"] = stats.get("devices", [])
    try:
        q = await client.queue()
        out["queue"] = {"running": len(q.get("queue_running", [])), "pending": len(q.get("queue_pending", []))}
    except Exception:  # noqa: BLE001
        pass
    try:
        info = await client.object_info()
        installed = installed_from_object_info(info)
        out["installed_files"] = installed
        out["engines"] = {}
        for e in ENGINES.values():
            if e.catalog_only:
                continue
            res = e.resolve_files(installed)
            out["engines"][e.id] = {"installed": all(res.values()),
                                    "missing": [f for f, hit in res.items() if hit is None]}
        names = [UPSCALER.filename, *UPSCALER.alternatives]
        out["upscaler_installed"] = any(n in installed.get("upscale_models", []) for n in names)
        out["nodes_ok"] = all(n in info for n in ("CreateVideo", "SaveVideo", "Wan22ImageToVideoLatent", "LTXVConditioning"))
    except Exception as e:  # noqa: BLE001
        out["error"] = _short_err(e)
    try:
        out["bridge"] = await client.bridge("info")
    except Exception:  # noqa: BLE001
        out["bridge"] = None
    return out


def _short_err(e: Exception) -> str:
    if isinstance(e, httpx.ConnectError):
        return "Not reachable (is ComfyUI running?)"
    if isinstance(e, httpx.TimeoutException):
        return "Timed out"
    return str(e)[:300] or type(e).__name__


@app.get("/api/backends/status")
async def backends_status(backend_id: str | None = None):
    s = load_settings()
    bs = [b for b in s["backends"] if backend_id in (None, b["id"])]
    return {"active": s["active_backend"], "backends": [await _backend_status(b) for b in bs]}


class TestIn(BaseModel):
    url: str
    token: str = ""


@app.post("/api/backends/test")
async def backends_test(body: TestIn):
    return await _backend_status({"id": "test", "name": "test", "url": body.url.strip().rstrip("/"), "token": body.token})


class InstallIn(BaseModel):
    engine_id: str
    backend_id: str


@app.post("/api/models/install")
async def install_model(body: InstallIn):
    b = backend_by_id(body.backend_id)
    client = ComfyClient(b["url"], b.get("token", ""))
    files = [UPSCALER] if body.engine_id == "upscaler" else get_engine(body.engine_id).files
    if not files:
        raise HTTPException(400, "This model is listed for reference only and can't be installed on your backends.")
    installed = installed_from_object_info(await client.object_info())
    started = []
    for f in files:
        if any(n in installed.get(f.folder, []) for n in [f.filename, *f.alternatives]):
            continue
        await client.bridge("download", "POST", {"url": f.url, "folder": f.folder, "filename": f.filename})
        started.append(f.filename)
    return {"started": started}


@app.get("/api/models/downloads")
async def model_downloads(backend_id: str):
    b = backend_by_id(backend_id)
    return await ComfyClient(b["url"], b.get("token", "")).bridge("downloads")


@app.post("/api/models/remove")
async def remove_model(body: InstallIn):
    b = backend_by_id(body.backend_id)
    client = ComfyClient(b["url"], b.get("token", ""))
    files = [UPSCALER] if body.engine_id == "upscaler" else get_engine(body.engine_id).files
    # don't delete files another engine still needs
    others = {f.filename for e in ENGINES.values() if e.id != body.engine_id for f in e.files}
    removed = []
    for f in files:
        if f.filename in others:
            continue
        r = await client.bridge("delete", "POST", {"folder": f.folder, "filename": f.filename})
        if r.get("deleted"):
            removed.append(f.filename)
    return {"removed": removed}


# ---------------------------------------------------------------- prompts
class EnhanceIn(BaseModel):
    prompt: str


@app.post("/api/enhance")
async def enhance(body: EnhanceIn):
    if not body.prompt.strip():
        raise HTTPException(400, "Write a prompt first.")
    return await prompting.enhance(body.prompt)


@app.get("/api/ollama/models")
async def ollama_models():
    return {"models": await prompting.ollama_models()}


# ---------------------------------------------------------------- generation
class GenerateIn(BaseModel):
    mode: str = Field(pattern="^(t2v|i2v|v2v)$")
    engine: str
    backend_id: str | None = None
    prompt: str = ""
    negative: str | None = None
    aspect: str = "16:9"
    resolution: str | None = None
    duration_s: float = 3
    fps: int | None = None
    steps: int | None = None
    cfg: float | None = None
    seed: int = -1
    camera: list[str] = []
    camera_intensity: int = 3
    motion_prompt: str = ""
    motion_intensity: int | None = None
    image: str | None = None
    video: str | None = None
    denoise: float | None = None
    character_id: str | None = None
    extra: dict[str, Any] = {}
    parent_id: str | None = None
    finish_1080p: bool = False


def _create_job(body: GenerateIn) -> dict[str, Any]:
    engine = get_engine(body.engine)
    if engine.catalog_only:
        raise HTTPException(400, f"{engine.name} can't run on your current backends.")
    if body.mode not in engine.modes:
        raise HTTPException(400, f"{engine.name} doesn't support this mode.")
    character_desc = ""
    image = body.image
    if body.character_id:
        ch = db.get_character(body.character_id)
        if not ch:
            raise HTTPException(404, "Character not found.")
        character_desc = ch.get("description") or ""
        if body.mode == "i2v" and not image and ch["images"]:
            image = f"character:{ch['id']}/{ch['images'][0]}"
    if body.mode == "i2v" and not image:
        raise HTTPException(400, "Add an image (or pick a character with a reference image).")
    if body.mode == "v2v" and not body.video:
        raise HTTPException(400, "Add a source video.")
    if body.mode == "t2v" and not body.prompt.strip():
        raise HTTPException(400, "Write a prompt.")
    seed = body.seed if body.seed >= 0 else random.randint(0, 2**31 - 1)
    final_prompt = build_prompt(body.prompt or "", body.camera, body.camera_intensity, body.motion_prompt,
                                body.motion_intensity if body.mode == "i2v" else None, character_desc)
    d = engine.defaults
    params = {
        "aspect": body.aspect, "resolution": body.resolution or d["resolution"], "duration_s": body.duration_s,
        "fps": body.fps or d["fps"], "steps": body.steps or d["steps"],
        "cfg": body.cfg if body.cfg is not None else d["cfg"], "seed": seed, "camera": body.camera,
        "camera_intensity": body.camera_intensity, "motion_prompt": body.motion_prompt,
        "motion_intensity": body.motion_intensity, "image": image, "video": body.video,
        "denoise": body.denoise if body.denoise is not None else d.get("denoise"), "extra": body.extra,
        "finish_1080p": body.finish_1080p,
    }
    w, h = engine.dims(params["aspect"], params["resolution"])
    params["width"], params["height"] = w, h
    params["frames"] = engine.frames(params["duration_s"], params["fps"])
    negative = body.negative if body.negative is not None else d.get("negative", "")
    return db.create_generation(
        mode=body.mode, engine=engine.id, backend_id=body.backend_id or load_settings()["active_backend"],
        prompt=body.prompt, final_prompt=final_prompt, negative_prompt=negative, params=params,
        parent_id=body.parent_id, character_id=body.character_id,
    )


@app.post("/api/generate")
async def generate(body: GenerateIn):
    g = _create_job(body)
    await jobs.enqueue(g["id"])
    return g


class ShotIn(BaseModel):
    prompt: str
    duration_s: float = 5
    camera: list[str] = []


class LongIn(BaseModel):
    engine: str = "wan22_ti2v_5b"
    backend_id: str | None = None
    shots: list[ShotIn]
    negative: str | None = None
    aspect: str = "9:16"
    resolution: str | None = None
    fps: int | None = None
    steps: int | None = None
    cfg: float | None = None
    seed: int = -1
    camera_intensity: int = 3
    image: str | None = None
    character_id: str | None = None
    finish_1080p: bool = False


MAX_LONG_S = 60


@app.post("/api/generate/long")
async def generate_long(body: LongIn):
    """15-60 s videos: shots are generated one after another, each continuing from the last frame of the previous."""
    engine = get_engine(body.engine)
    if engine.catalog_only or "i2v" not in engine.modes:
        raise HTTPException(400, f"{engine.name} can't make long videos (needs image-to-video).")
    shots = [s for s in body.shots if s.prompt.strip()]
    if not shots:
        raise HTTPException(400, "Add at least one shot with a prompt.")
    d = engine.defaults
    fps = body.fps or d["fps"]
    max_shot = engine.max_frames / fps
    for s in shots:
        s.duration_s = max(1.0, min(float(s.duration_s), max_shot))
    total = sum(s.duration_s for s in shots)
    if total > MAX_LONG_S:
        raise HTTPException(400, f"Total length is {total:.0f}s; the limit is {MAX_LONG_S}s.")
    character_desc, image = "", body.image
    if body.character_id:
        ch = db.get_character(body.character_id)
        if not ch:
            raise HTTPException(404, "Character not found.")
        character_desc = ch.get("description") or ""
        if not image and ch["images"]:
            image = f"character:{ch['id']}/{ch['images'][0]}"
    seed = body.seed if body.seed >= 0 else random.randint(0, 2**31 - 1000)
    shot_params = [{"prompt": s.prompt, "duration_s": s.duration_s, "camera": s.camera,
                    "final_prompt": build_prompt(s.prompt, s.camera, body.camera_intensity, character_desc=character_desc)}
                   for s in shots]
    resolution = body.resolution or d["resolution"]
    w, h = engine.dims(body.aspect, resolution)
    params = {"aspect": body.aspect, "resolution": resolution, "fps": fps, "steps": body.steps or d["steps"],
              "cfg": body.cfg if body.cfg is not None else d["cfg"], "seed": seed, "shots": shot_params,
              "camera_intensity": body.camera_intensity, "image": image, "finish_1080p": body.finish_1080p,
              "width": w, "height": h, "duration_s": total, "extra": {}}
    summary = " → ".join(s.prompt.strip() for s in shots)
    g = db.create_generation(mode="long", engine=engine.id, backend_id=body.backend_id or load_settings()["active_backend"],
                             prompt=summary, final_prompt=" | ".join(sp["final_prompt"] for sp in shot_params),
                             negative_prompt=body.negative if body.negative is not None else d.get("negative", ""),
                             params=params, character_id=body.character_id)
    await jobs.enqueue(g["id"])
    return g


@app.get("/api/generations")
async def generations(limit: int = 200):
    return {"generations": db.list_generations(limit)}


@app.get("/api/generations/{gid}")
async def generation(gid: str):
    g = db.get_generation(gid)
    if not g:
        raise HTTPException(404, "Not found")
    return g


@app.get("/api/generations/{gid}/workflow")
async def generation_workflow(gid: str):
    p = OUTPUTS_DIR / f"{gid}.workflow.json"
    if not p.exists():
        raise HTTPException(404, "No workflow stored")
    return FileResponse(p, media_type="application/json")


@app.delete("/api/generations/{gid}")
async def delete_generation(gid: str):
    g = db.get_generation(gid)
    if not g:
        raise HTTPException(404, "Not found")
    jobs.cancel(gid)
    delete_generation_files(g)
    db.delete_generation(gid)
    return {"ok": True}


@app.post("/api/generations/{gid}/cancel")
async def cancel_generation(gid: str):
    jobs.cancel(gid)
    return {"ok": True}


class SavedIn(BaseModel):
    saved: bool


@app.post("/api/generations/{gid}/saved")
async def save_generation(gid: str, body: SavedIn):
    db.update_generation(gid, saved=int(body.saved))
    return db.get_generation(gid)


class RegenIn(BaseModel):
    variation: bool = False


@app.post("/api/generations/{gid}/regenerate")
async def regenerate(gid: str, body: RegenIn):
    g = db.get_generation(gid)
    if not g:
        raise HTTPException(404, "Not found")
    if g["mode"] not in ("t2v", "i2v", "v2v"):
        raise HTTPException(400, "Only generations can be regenerated.")
    p = g["params"]
    req = GenerateIn(mode=g["mode"], engine=g["engine"], backend_id=load_settings()["active_backend"],
                     prompt=g["prompt"], negative=g["negative_prompt"], aspect=p["aspect"], resolution=p["resolution"],
                     duration_s=p["duration_s"], fps=p["fps"], steps=p["steps"], cfg=p["cfg"],
                     seed=-1 if body.variation else p["seed"], camera=p.get("camera", []),
                     camera_intensity=p.get("camera_intensity", 3), motion_prompt=p.get("motion_prompt", ""),
                     motion_intensity=p.get("motion_intensity"), image=p.get("image"), video=p.get("video"),
                     denoise=p.get("denoise"), character_id=g.get("character_id"), extra=p.get("extra", {}),
                     parent_id=gid, finish_1080p=bool(p.get("finish_1080p")))
    new = _create_job(req)
    await jobs.enqueue(new["id"])
    return new


class ExtendIn(BaseModel):
    prompt: str | None = None
    duration_s: float | None = None


@app.post("/api/generations/{gid}/extend")
async def extend(gid: str, body: ExtendIn):
    g = db.get_generation(gid)
    if not g or g["status"] != "done":
        raise HTTPException(400, "Only finished videos can be extended.")
    engine_id = g["engine"] if g["engine"] in ENGINES and "i2v" in ENGINES[g["engine"]].modes else "wan22_ti2v_5b"
    p = dict(g["params"]) if isinstance(g["params"], dict) else {}
    engine = get_engine(engine_id)
    p.setdefault("aspect", "16:9")
    p.setdefault("resolution", engine.defaults["resolution"])
    p.setdefault("fps", engine.defaults["fps"])
    p.setdefault("steps", engine.defaults["steps"])
    p.setdefault("cfg", engine.defaults["cfg"])
    p["duration_s"] = body.duration_s or p.get("duration_s", 3)
    p["seed"] = random.randint(0, 2**31 - 1)
    p["source_id"] = gid
    prompt = body.prompt or g["prompt"]
    new = db.create_generation(mode="extend", engine=engine_id, backend_id=load_settings()["active_backend"],
                               prompt=prompt, final_prompt=build_prompt(prompt, p.get("camera", []), p.get("camera_intensity", 3)),
                               negative_prompt=g.get("negative_prompt"), params=p, parent_id=gid,
                               character_id=g.get("character_id"))
    await jobs.enqueue(new["id"])
    return new


class ToolIn(BaseModel):
    source: str | None = None
    sources: list[str] = []
    target_fps: int = 48
    factor: int = 2
    target: str | None = None


@app.post("/api/tools/{tool}")
async def run_tool(tool: str, body: ToolIn):
    if tool not in ("interpolate", "upscale_basic", "upscale_ai", "stitch"):
        raise HTTPException(404, "Unknown tool")
    if tool == "stitch" and len(body.sources) < 2:
        raise HTTPException(400, "Pick at least two clips to stitch.")
    if tool != "stitch" and not body.source:
        raise HTTPException(400, "Pick a source video.")
    if tool != "upscale_ai" and not media.ffmpeg_bin():
        raise HTTPException(400, "FFmpeg is not installed. Run scripts/install.sh.")
    label = {"interpolate": f"Frame interpolation to {body.target_fps} fps", "upscale_basic": f"Upscale x{body.factor} (Lanczos)",
             "upscale_ai": "AI upscale to 1080p (Real-ESRGAN)" if body.target == "1080p" else "AI upscale x2 (Real-ESRGAN)", "stitch": f"Stitched {len(body.sources)} clips"}[tool]
    parent = (body.source or (body.sources[0] if body.sources else "")).partition(":")[2] or None
    g = db.create_generation(mode=tool, engine="realesrgan" if tool == "upscale_ai" else "ffmpeg",
                             backend_id=load_settings()["active_backend"], prompt=label, final_prompt=label,
                             params=body.model_dump(), parent_id=parent if body.source else None)
    await jobs.enqueue(g["id"])
    return g


# ---------------------------------------------------------------- assets
async def _store_upload(up: UploadFile, dest_dir: Path, stem: str) -> Path:
    ext = Path(up.filename or "").suffix.lower()
    if ext not in IMAGE_EXT | VIDEO_EXT:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Use an image (png/jpg/webp) or video (mp4/mov/webm).")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}{ext}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(up.file, fh)
    return dest


@app.post("/api/assets")
async def upload_asset(file: UploadFile = File(...)):
    stem = db.new_id()
    dest = await _store_upload(file, ASSETS_DIR, stem)
    kind = "image" if dest.suffix in IMAGE_EXT else "video"
    info = await media.probe(dest)
    if kind == "video":
        try:
            await media.thumbnail(dest, THUMBS_DIR / f"asset_{stem}.jpg")
        except media.MediaError:
            pass
    return db.create_asset(kind, dest.name, file.filename or dest.name, info.get("width"), info.get("height"),
                           info.get("duration_s") if kind == "video" else None)


@app.get("/api/assets")
async def assets(kind: str | None = None):
    return {"assets": db.list_assets(kind)}


@app.delete("/api/assets/{aid}")
async def delete_asset(aid: str):
    a = db.get_asset(aid)
    if not a:
        raise HTTPException(404, "Not found")
    (ASSETS_DIR / a["filename"]).unlink(missing_ok=True)
    (THUMBS_DIR / f"asset_{Path(a['filename']).stem}.jpg").unlink(missing_ok=True)
    db.delete_asset(aid)
    return {"ok": True}


# ---------------------------------------------------------------- characters
@app.get("/api/characters")
async def characters():
    return {"characters": db.list_characters()}


@app.post("/api/characters")
async def create_character(name: str = Form(...), description: str = Form(""), files: list[UploadFile] = File(default=[])):
    cid = db.new_id()
    names = []
    for i, f in enumerate(files):
        p = await _store_upload(f, CHARACTERS_DIR / cid, f"ref{i}")
        if p.suffix not in IMAGE_EXT:
            p.unlink()
            raise HTTPException(400, "Character references must be images.")
        names.append(p.name)
    return db.create_character(name, description, names, cid=cid)


@app.put("/api/characters/{cid}")
async def update_character(cid: str, name: str = Form(None), description: str = Form(None),
                           files: list[UploadFile] = File(default=[])):
    ch = db.get_character(cid)
    if not ch:
        raise HTTPException(404, "Not found")
    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if files:
        images = list(ch["images"])
        for f in files:
            p = await _store_upload(f, CHARACTERS_DIR / cid, f"ref{db.new_id()[:6]}")
            images.append(p.name)
        fields["images"] = images
    if fields:
        db.update_character(cid, **fields)
    return db.get_character(cid)


class FromGenIn(BaseModel):
    generation_id: str
    name: str
    description: str = ""


@app.post("/api/characters/from-generation")
async def character_from_generation(body: FromGenIn):
    """Saves a frame of a generated video as a character reference."""
    src = resolve_input_path(f"generation:{body.generation_id}")
    g = db.get_generation(body.generation_id)
    cid = db.new_id()
    dest = CHARACTERS_DIR / cid / "ref0.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        await media.thumbnail(src, dest, width=1280)
    except media.MediaError as e:
        raise HTTPException(400, f"Couldn't extract a frame: {e}") from e
    desc = body.description or (g["prompt"] if g else "")
    return db.create_character(body.name, desc, [dest.name], cid=cid)


@app.delete("/api/characters/{cid}")
async def delete_character(cid: str):
    shutil.rmtree(CHARACTERS_DIR / cid, ignore_errors=True)
    db.delete_character(cid)
    return {"ok": True}


@app.delete("/api/characters/{cid}/images/{fname}")
async def delete_character_image(cid: str, fname: str):
    ch = db.get_character(cid)
    if not ch:
        raise HTTPException(404, "Not found")
    (CHARACTERS_DIR / cid / Path(fname).name).unlink(missing_ok=True)
    db.update_character(cid, images=[i for i in ch["images"] if i != fname])
    return db.get_character(cid)


# ---------------------------------------------------------------- files + UI
app.mount("/files/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
app.mount("/files/thumbs", StaticFiles(directory=THUMBS_DIR), name="thumbs")
app.mount("/files/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/files/characters", StaticFiles(directory=CHARACTERS_DIR), name="characters")


@app.get("/api/system")
async def system():
    return {"platform": platform.platform(), "python": platform.python_version()}


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
else:
    @app.get("/")
    async def no_ui():
        return JSONResponse({"detail": "The interface isn't built yet. Run scripts/install.sh."}, status_code=503)
