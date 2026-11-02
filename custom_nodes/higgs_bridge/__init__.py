"""HIGGS Studio bridge for ComfyUI.

Adds a few HTTP routes to ComfyUI so the studio can manage models on any backend
(this computer or the Kaggle notebook) and see hardware usage:

  GET  /higgs/info        hardware, VRAM/RAM usage, free disk, versions
  POST /higgs/download    {url, folder, filename}  -> downloads into ComfyUI/models/<folder>
  GET  /higgs/downloads   progress of downloads
  POST /higgs/delete      {folder, filename}

If the environment variable HIGGS_TOKEN is set, every ComfyUI request must carry
"Authorization: Bearer <token>" (or ?token=<token>). The Kaggle notebook sets this
so a public tunnel URL can't be used by anyone else.

Adds no graph nodes.
"""
from __future__ import annotations

import os
import shutil
import ssl
import threading
import time
import urllib.request
from pathlib import Path

import folder_paths
from aiohttp import web
from server import PromptServer

NODE_CLASS_MAPPINGS: dict = {}
NODE_DISPLAY_NAME_MAPPINGS: dict = {}
WEB_DIRECTORY = None

ALLOWED_FOLDERS = {"diffusion_models", "text_encoders", "vae", "checkpoints", "upscale_models", "loras", "clip_vision"}
ALLOWED_HOSTS = ("https://huggingface.co/", "https://github.com/")
_downloads: dict[str, dict] = {}


def _ssl_context() -> ssl.SSLContext:
    """python.org Python on macOS ships without system CA certificates, which makes every HTTPS download fail
    with CERTIFICATE_VERIFY_FAILED. Use certifi's CA bundle when it's available."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()
_lock = threading.Lock()

routes = PromptServer.instance.routes
TOKEN = os.environ.get("HIGGS_TOKEN", "").strip()


# ------------------------------------------------------------------ auth
if TOKEN:
    @web.middleware
    async def _higgs_auth(request: web.Request, handler):
        if request.method == "OPTIONS":
            return await handler(request)
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {TOKEN}" or request.query.get("token") == TOKEN:
            return await handler(request)
        return web.json_response({"error": "unauthorized"}, status=401)

    try:
        PromptServer.instance.app.middlewares.insert(0, _higgs_auth)
        print("[higgs_bridge] token auth enabled")
    except RuntimeError as e:  # app already frozen (very old/new ComfyUI)
        print(f"[higgs_bridge] WARNING could not enable token auth: {e}")


# ------------------------------------------------------------------ helpers
def _folder_dir(folder: str) -> Path:
    if folder not in ALLOWED_FOLDERS:
        raise ValueError(f"folder '{folder}' not allowed")
    paths = folder_paths.get_folder_paths(folder)
    if not paths:
        raise ValueError(f"ComfyUI has no path for '{folder}'")
    p = Path(paths[0])
    p.mkdir(parents=True, exist_ok=True)
    return p


def _download(key: str, url: str, dest: Path) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    headers = {"User-Agent": "higgs-studio/1.0"}
    hf_token = os.environ.get("HF_TOKEN")
    if hf_token and url.startswith("https://huggingface.co/"):
        headers["Authorization"] = f"Bearer {hf_token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as r, part.open("wb") as fh:
            total = int(r.headers.get("Content-Length") or 0)
            with _lock:
                _downloads[key]["total"] = total
            done, t0 = 0, time.time()
            while True:
                chunk = r.read(1 << 22)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                with _lock:
                    d = _downloads[key]
                    d["done"] = done
                    d["speed_mb_s"] = round(done / max(time.time() - t0, 0.01) / 2**20, 1)
                    if d.get("cancel"):
                        raise RuntimeError("cancelled")
        part.replace(dest)
        with _lock:
            _downloads[key]["status"] = "done"
    except Exception as e:  # noqa: BLE001
        part.unlink(missing_ok=True)
        with _lock:
            _downloads[key]["status"] = "error"
            _downloads[key]["error"] = str(e)


# ------------------------------------------------------------------ routes
@routes.get("/higgs/info")
async def higgs_info(request):
    info: dict = {"bridge_version": 1, "auth": bool(TOKEN)}
    try:
        import torch
        info["torch"] = torch.__version__
        if torch.cuda.is_available():
            i = torch.cuda.current_device()
            free, total = torch.cuda.mem_get_info(i)
            info["gpu"] = {"name": torch.cuda.get_device_name(i), "vram_total_gb": round(total / 2**30, 1),
                           "vram_used_gb": round((total - free) / 2**30, 1), "count": torch.cuda.device_count()}
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["gpu"] = {"name": "Apple Metal (MPS)"}
        else:
            info["gpu"] = None
    except Exception as e:  # noqa: BLE001
        info["torch_error"] = str(e)
    try:
        import psutil
        vm = psutil.virtual_memory()
        info["ram_total_gb"] = round(vm.total / 2**30, 1)
        info["ram_used_gb"] = round((vm.total - vm.available) / 2**30, 1)
    except Exception:  # noqa: BLE001
        pass
    models_dir = Path(folder_paths.models_dir)
    du = shutil.disk_usage(models_dir)
    info["disk_free_gb"] = round(du.free / 2**30, 1)
    info["models_dir"] = str(models_dir)
    return web.json_response(info)


@routes.post("/higgs/download")
async def higgs_download(request):
    body = await request.json()
    url, folder, filename = body.get("url", ""), body.get("folder", ""), Path(body.get("filename", "")).name
    if not url.startswith(ALLOWED_HOSTS) or not filename:
        return web.json_response({"error": "only Hugging Face / GitHub downloads are allowed"}, status=400)
    try:
        dest = _folder_dir(folder) / filename
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    key = f"{folder}/{filename}"
    with _lock:
        cur = _downloads.get(key)
        if cur and cur["status"] == "running":
            return web.json_response({"key": key, "status": "running"})
        if dest.exists():
            _downloads[key] = {"key": key, "status": "done", "done": dest.stat().st_size, "total": dest.stat().st_size}
            return web.json_response({"key": key, "status": "done"})
        _downloads[key] = {"key": key, "status": "running", "done": 0, "total": 0, "url": url, "started": time.time()}
    threading.Thread(target=_download, args=(key, url, dest), daemon=True).start()
    return web.json_response({"key": key, "status": "running"})


@routes.get("/higgs/downloads")
async def higgs_downloads(request):
    with _lock:
        return web.json_response({"downloads": list(_downloads.values())})


@routes.post("/higgs/delete")
async def higgs_delete(request):
    body = await request.json()
    try:
        path = _folder_dir(body.get("folder", "")) / Path(body.get("filename", "")).name
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    if path.exists():
        path.unlink()
        return web.json_response({"deleted": True})
    return web.json_response({"deleted": False})
