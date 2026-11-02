"""FFmpeg helpers: thumbnails, probing, extend/stitch, frame interpolation, basic upscale."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .config import RUNTIME_DIR, load_settings


def _find(binary: str) -> str | None:
    s = load_settings()
    custom = s.get("ffmpeg_path") or ""
    if custom:
        cand = Path(custom).expanduser()
        if cand.is_dir():
            cand = cand / binary
        elif binary == "ffprobe":
            cand = cand.with_name("ffprobe")
        if cand.exists():
            return str(cand)
    for cand in (RUNTIME_DIR / "bin" / binary, Path(os.environ.get("HIGGS_FFMPEG_DIR", "/nonexistent")) / binary):
        if cand.exists():
            return str(cand)
    return shutil.which(binary)


def ffmpeg_bin() -> str | None:
    return _find("ffmpeg")


def ffprobe_bin() -> str | None:
    return _find("ffprobe")


class MediaError(RuntimeError):
    pass


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise MediaError(err.decode(errors="ignore")[-800:])
    return out.decode(errors="ignore")


def _need_ffmpeg() -> str:
    b = ffmpeg_bin()
    if not b:
        raise MediaError("FFmpeg is not installed. Run scripts/install.sh (it downloads a standalone copy).")
    return b


async def probe(path: Path) -> dict[str, Any]:
    fp = ffprobe_bin()
    if not fp:
        return {}
    out = await _run(fp, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path))
    data = json.loads(out)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    fps = None
    if v.get("avg_frame_rate") and v["avg_frame_rate"] != "0/0":
        n, d = v["avg_frame_rate"].split("/")
        fps = float(n) / float(d) if float(d) else None
    dur = data.get("format", {}).get("duration")
    return {"width": v.get("width"), "height": v.get("height"), "fps": fps,
            "duration_s": float(dur) if dur not in (None, "N/A") else None,
            "frames": int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None}


async def thumbnail(video: Path, dest: Path, width: int = 480) -> Path:
    ff = _need_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if video.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        await _run(ff, "-y", "-v", "error", "-i", str(video), "-vf", f"scale={width}:-2", str(dest))
    else:
        await _run(ff, "-y", "-v", "error", "-ss", "0.3", "-i", str(video), "-frames:v", "1",
                   "-vf", f"scale={width}:-2", str(dest))
    return dest


async def last_frame(video: Path, dest: Path) -> Path:
    ff = _need_ffmpeg()
    await _run(ff, "-y", "-v", "error", "-sseof", "-0.1", "-i", str(video), "-frames:v", "1", "-update", "1", str(dest))
    if not dest.exists():  # very short clips: take the last decodable frame
        await _run(ff, "-y", "-v", "error", "-i", str(video), "-vf", "reverse", "-frames:v", "1", str(dest))
    return dest


async def concat(videos: list[Path], dest: Path, drop_first_frame_of_rest: bool = True, fps: float | None = None) -> Path:
    """Joins clips end to end (re-encoded so differing sizes still work)."""
    ff = _need_ffmpeg()
    if not videos:
        raise MediaError("Nothing to stitch.")
    first = await probe(videos[0])
    w, h = first.get("width") or 832, first.get("height") or 480
    fps = fps or first.get("fps") or 24
    inputs: list[str] = []
    chains = []
    for i, v in enumerate(videos):
        inputs += ["-i", str(v)]
        trim = ",trim=start_frame=1,setpts=PTS-STARTPTS" if (i > 0 and drop_first_frame_of_rest) else ""
        chains.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                      f"fps={fps},format=yuv420p{trim}[v{i}]")
    filt = ";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(len(videos))) + f"concat=n={len(videos)}:v=1:a=0[out]"
    await _run(ff, "-y", "-v", "error", *inputs, "-filter_complex", filt, "-map", "[out]",
               "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-movflags", "+faststart", str(dest))
    return dest


async def interpolate(video: Path, dest: Path, target_fps: int) -> Path:
    """Motion-compensated frame interpolation (FFmpeg minterpolate; classical, not AI)."""
    ff = _need_ffmpeg()
    await _run(ff, "-y", "-v", "error", "-i", str(video), "-vf",
               f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
               "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest))
    return dest


async def upscale_basic(video: Path, dest: Path, factor: int = 2) -> Path:
    """Lanczos resize + light sharpening (fast, non-AI)."""
    ff = _need_ffmpeg()
    await _run(ff, "-y", "-v", "error", "-i", str(video), "-vf",
               f"scale=iw*{factor}:ih*{factor}:flags=lanczos,unsharp=5:5:0.6",
               "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest))
    return dest


async def to_mp4(src: Path, dest: Path) -> Path:
    """Normalizes any output (webp/webm/mov) to a widely playable H.264 MP4."""
    ff = _need_ffmpeg()
    await _run(ff, "-y", "-v", "error", "-i", str(src), "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
               "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-movflags", "+faststart", str(dest))
    return dest
