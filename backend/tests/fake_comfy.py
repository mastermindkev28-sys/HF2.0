"""TEST DOUBLE ONLY: a tiny stand-in for the ComfyUI API, used by the automated tests
to exercise the studio's queue/progress/download/library pipeline in CI without
a GPU. It renders an FFmpeg test pattern, not AI video. Never used by the app.
"""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, WebSocket
from fastapi.responses import FileResponse

app = FastAPI()
OUT = Path(tempfile.mkdtemp(prefix="fakecomfy_"))
HISTORY: dict[str, dict] = {}
SOCKETS: dict[str, WebSocket] = {}
KNOWN = {"UNETLoader", "CLIPLoader", "VAELoader", "ModelSamplingSD3", "CLIPTextEncode", "Wan22ImageToVideoLatent",
         "KSampler", "VAEDecode", "CreateVideo", "SaveVideo", "LoadImage", "LoadVideo", "GetVideoComponents",
         "ImageFromBatch", "ImageScale", "VAEEncode", "CheckpointLoaderSimple", "LTXVConditioning",
         "EmptyLTXVLatentVideo", "LTXVImgToVideo", "LTXVScheduler", "KSamplerSelect", "SamplerCustom",
         "SplitSigmasDenoise", "UpscaleModelLoader", "ImageUpscaleWithModel"}
SUBMITTED: list[dict] = []


@app.get("/system_stats")
async def stats():
    return {"system": {"os": "test"}, "devices": [{"name": "cpu", "type": "cpu", "vram_total": 0, "vram_free": 0}]}


@app.get("/object_info")
async def object_info():
    return {
        "UNETLoader": {"input": {"required": {"unet_name": [["wan2.2_ti2v_5B_fp16.safetensors"]]}}},
        "CLIPLoader": {"input": {"required": {"clip_name": [["umt5_xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors"]]}}},
        "VAELoader": {"input": {"required": {"vae_name": ["COMBO", {"options": ["wan2.2_vae.safetensors"]}]}}},
        "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["ltxv-2b-0.9.8-distilled.safetensors"]]}}},
        "UpscaleModelLoader": {"input": {"required": {"model_name": [[]]}}},
        **{k: {} for k in KNOWN if k not in ("UNETLoader", "CLIPLoader", "VAELoader", "CheckpointLoaderSimple", "UpscaleModelLoader")},
    }


@app.get("/queue")
async def queue():
    return {"queue_running": [], "queue_pending": []}


@app.post("/upload/image")
async def upload(image: UploadFile = File(...), overwrite: str = Form("true"), type: str = Form("input")):
    (OUT / image.filename).write_bytes(await image.read())
    return {"name": image.filename, "subfolder": "", "type": "input"}


@app.post("/prompt")
async def prompt(body: dict):
    wf = body["prompt"]
    bad = [n["class_type"] for n in wf.values() if n["class_type"] not in KNOWN]
    if bad:
        return {"error": {"message": f"unknown nodes {bad}"}, "node_errors": {}}, 400
    SUBMITTED.append(wf)
    pid = uuid.uuid4().hex
    asyncio.create_task(_execute(pid, wf, body.get("client_id")))
    return {"prompt_id": pid, "number": 1, "node_errors": {}}


async def _execute(pid: str, wf: dict, client_id: str | None):
    ws = SOCKETS.get(client_id or "")

    async def send(t, d):
        if ws:
            try:
                await ws.send_json({"type": t, "data": {**d, "prompt_id": pid}})
            except Exception:
                pass
    await send("execution_start", {})
    sampler = next(k for k, v in wf.items() if v["class_type"] in ("KSampler", "SamplerCustom", "ImageUpscaleWithModel"))
    await send("executing", {"node": sampler})
    for i in range(1, 6):
        await asyncio.sleep(0.1)
        await send("progress", {"value": i, "max": 5, "node": sampler})
    name = f"higgs_{pid[:8]}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x192:rate=24", "-t", "1",
                    "-pix_fmt", "yuv420p", str(OUT / name)], check=True)
    HISTORY[pid] = {"status": {"status_str": "success", "completed": True, "messages": []},
                    "outputs": {"99": {"images": [{"filename": name, "subfolder": "", "type": "output"}], "animated": [True]}}}
    await send("executing", {"node": None})


@app.get("/history/{pid}")
async def history(pid: str):
    return {pid: HISTORY[pid]} if pid in HISTORY else {}


@app.get("/view")
async def view(filename: str, subfolder: str = "", type: str = "output"):
    return FileResponse(OUT / filename)


@app.post("/interrupt")
async def interrupt():
    return {}


@app.websocket("/ws")
async def ws(websocket: WebSocket, clientId: str = ""):
    await websocket.accept()
    SOCKETS[clientId] = websocket
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        SOCKETS.pop(clientId, None)
