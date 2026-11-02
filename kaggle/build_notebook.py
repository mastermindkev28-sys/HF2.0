"""Builds kaggle/higgs_studio_kaggle.ipynb (embeds the HIGGS bridge node so the repo can stay private).

    python kaggle/build_notebook.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = (ROOT / "custom_nodes" / "higgs_bridge" / "__init__.py").read_text()


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


cells = [
    md("""
# HIGGS Studio · free Kaggle GPU backend

This notebook turns a free Kaggle GPU into the generation engine for your HIGGS Studio on your Mac.

**One-time setup**
1. Kaggle account with a verified phone number (needed for GPU + internet).
2. In the right sidebar: **Session options → Accelerator → GPU T4 x2**, and **Internet → On**.

**Every session**
1. Click **Run All**.
2. Wait for the last cell to print an address like `https://something.trycloudflare.com` and an access token.
3. In HIGGS Studio → **Settings → Kaggle free GPU**, paste both, click **Test**, then **Save**.
4. Generate. Leave this tab open; stop the session when you're done to save GPU hours.

**Limits (Kaggle's, not ours):** about 30 GPU hours per week, sessions end after at most 12 hours, and an idle session may be stopped. Model files (~30 GB) are re-downloaded each session, which takes a few minutes on Kaggle's network.
"""),
    md("## 1 · Settings"),
    code("""
# Which engines to download this session (True/False)
INSTALL_WAN22_5B = True     # Wan 2.2 TI2V 5B: best quality you can run here (~18 GB)
INSTALL_LTXV_2B  = True     # LTX-Video 2B distilled: fast drafts (~11.5 GB)
INSTALL_UPSCALER = True     # Real-ESRGAN x2 for AI upscaling (70 MB)

COMFY_DIR  = "/kaggle/temp/ComfyUI" if __import__("os").path.isdir("/kaggle/temp") else "/tmp/ComfyUI"
"""),
    md("## 2 · Check the GPU"),
    code("""
import subprocess, torch
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"], capture_output=True, text=True).stdout)
assert torch.cuda.is_available(), "No GPU. Set Session options -> Accelerator -> GPU T4 x2 and restart."
print("torch", torch.__version__, "| CUDA", torch.version.cuda, "|", torch.cuda.get_device_name(0))
"""),
    md("## 3 · Install ComfyUI (keeps Kaggle's CUDA PyTorch)"),
    code("""
import os, subprocess, sys
if not os.path.isdir(COMFY_DIR):
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/comfyanonymous/ComfyUI", COMFY_DIR], check=True)
req = [l for l in open(f"{COMFY_DIR}/requirements.txt").read().splitlines()
       if l.strip() and not l.startswith("#") and not l.split("=")[0].split(">")[0].split("<")[0].strip() in ("torch", "torchvision", "torchaudio")]
open("/tmp/comfy_req.txt", "w").write("\\n".join(req))
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "/tmp/comfy_req.txt", "hf_transfer", "huggingface_hub"], check=True)
print("ComfyUI ready at", COMFY_DIR)
"""),
    md("## 4 · Install the HIGGS bridge (model manager + access token)"),
    code("bridge_src = " + json.dumps(BRIDGE) + """
os.makedirs(f"{COMFY_DIR}/custom_nodes/higgs_bridge", exist_ok=True)
open(f"{COMFY_DIR}/custom_nodes/higgs_bridge/__init__.py", "w").write(bridge_src)
print("bridge installed")
"""),
    md("## 5 · Download models (free, from Hugging Face)"),
    code("""
import os
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
from huggingface_hub import hf_hub_download
M = f"{COMFY_DIR}/models"
def get(repo, path, folder):
    dest = f"{M}/{folder}"
    os.makedirs(dest, exist_ok=True)
    name = path.split("/")[-1]
    if os.path.exists(f"{dest}/{name}"):
        print("have", name); return
    p = hf_hub_download(repo, path, local_dir="/tmp/hf_dl")
    os.replace(p, f"{dest}/{name}")
    print("downloaded", name)

if INSTALL_WAN22_5B:
    get("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", "diffusion_models")
    get("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/vae/wan2.2_vae.safetensors", "vae")
    get("Comfy-Org/Wan_2.1_ComfyUI_repackaged", "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders")
if INSTALL_LTXV_2B:
    get("Lightricks/LTX-Video", "ltxv-2b-0.9.8-distilled.safetensors", "checkpoints")
    get("comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders")
if INSTALL_UPSCALER:
    get("ai-forever/Real-ESRGAN", "RealESRGAN_x2.pth", "upscale_models")
"""),
    md("## 6 · Start ComfyUI + a free Cloudflare tunnel\nThe access token stops anyone else who sees the address from using your GPU."),
    code("""
import os, re, secrets, subprocess, time, urllib.request
TOKEN = secrets.token_urlsafe(18)
env = dict(os.environ, HIGGS_TOKEN=TOKEN)
log = open("/tmp/comfy.log", "w")
comfy = subprocess.Popen(["python", "main.py", "--listen", "127.0.0.1", "--port", "8188", "--preview-method", "none"],
                         cwd=COMFY_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
for _ in range(180):
    try:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8188/system_stats", headers={"Authorization": f"Bearer {TOKEN}"}), timeout=2)
        break
    except Exception:
        time.sleep(2)
else:
    print(open("/tmp/comfy.log").read()[-3000:]); raise SystemExit("ComfyUI did not start")
print("ComfyUI is running")

if not os.path.exists("/tmp/cloudflared"):
    urllib.request.urlretrieve("https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", "/tmp/cloudflared")
    os.chmod("/tmp/cloudflared", 0o755)
tlog = open("/tmp/tunnel.log", "w")
tunnel = subprocess.Popen(["/tmp/cloudflared", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8188"], stdout=tlog, stderr=subprocess.STDOUT)
URL = None
for _ in range(60):
    m = re.search(r"https://[a-z0-9-]+\\.trycloudflare\\.com", open("/tmp/tunnel.log").read())
    if m:
        URL = m.group(0); break
    time.sleep(1)
print("\\n" + "=" * 70)
print("  Paste these into HIGGS Studio -> Settings -> Kaggle free GPU")
print("  Address:", URL)
print("  Token:  ", TOKEN)
print("=" * 70)
"""),
    md("## 7 · Keep alive\nLeave this running while you generate. Stop it (■) and end the session when you're done."),
    code("""
import time, json, urllib.request
while True:
    try:
        r = urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8188/queue", headers={"Authorization": f"Bearer {TOKEN}"}), timeout=5)
        q = json.loads(r.read())
        print(time.strftime("%H:%M:%S"), "running", len(q["queue_running"]), "waiting", len(q["queue_pending"]), "| address", URL, flush=True)
    except Exception as e:
        print("ComfyUI not responding:", e); print(open("/tmp/comfy.log").read()[-2000:])
    if comfy.poll() is not None:
        print(open("/tmp/comfy.log").read()[-3000:]); break
    time.sleep(60)
"""),
]

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                   "language_info": {"name": "python"},
                                   "kaggle": {"accelerator": "nvidiaTeslaT4", "isInternetEnabled": True, "isGpuEnabled": True}},
      "nbformat": 4, "nbformat_minor": 5}
out = ROOT / "kaggle" / "higgs_studio_kaggle.ipynb"
out.write_text(json.dumps(nb, indent=1))
print("wrote", out)
