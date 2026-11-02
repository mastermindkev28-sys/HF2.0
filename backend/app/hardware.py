"""Detects this computer's hardware and says honestly what it can run locally."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
from functools import lru_cache
from typing import Any

import psutil

from .config import DATA_DIR


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


@lru_cache(maxsize=1)
def _gpus() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    sysname = platform.system()
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        for line in out.strip().splitlines():
            name, mem = [x.strip() for x in line.split(",")[:2]]
            gpus.append({"name": name, "vram_gb": round(float(mem) / 1024, 1), "vendor": "NVIDIA", "cuda": True})
    if sysname == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType", "-json"])
        try:
            for d in json.loads(out).get("SPDisplaysDataType", []):
                vram = d.get("spdisplays_vram") or d.get("spdisplays_vram_shared") or ""
                gpus.append({"name": d.get("sppci_model", "GPU"), "vram": vram,
                             "vendor": d.get("spdisplays_vendor", ""), "cuda": False,
                             "apple_silicon": platform.machine() == "arm64"})
        except json.JSONDecodeError:
            pass
    elif sysname == "Linux" and not gpus and shutil.which("lspci"):
        for line in _run(["lspci"]).splitlines():
            if any(k in line for k in ("VGA", "3D controller", "Display")):
                gpus.append({"name": line.split(":", 2)[-1].strip(), "cuda": False})
    elif sysname == "Windows" and not gpus:
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"])
        gpus += [{"name": n.strip(), "cuda": False} for n in out.splitlines() if n.strip()]
    return gpus


def local_hardware() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(DATA_DIR)
    gpus = _gpus()
    cuda_vram = max((g.get("vram_gb", 0) for g in gpus if g.get("cuda")), default=0)
    apple = platform.system() == "Darwin" and platform.machine() == "arm64"
    ram_gb = round(vm.total / 2**30, 1)
    if cuda_vram >= 24:
        verdict = "Strong NVIDIA GPU: Wan 2.2 5B and LTX run locally at full quality; Wan 2.2 14B is possible."
        local = ["wan22_ti2v_5b", "ltxv_2b_distilled"]
    elif cuda_vram >= 12:
        verdict = "NVIDIA GPU: Wan 2.2 5B and LTX run locally."
        local = ["wan22_ti2v_5b", "ltxv_2b_distilled"]
    elif cuda_vram >= 6:
        verdict = "Small NVIDIA GPU: LTX 2B runs locally; Wan 2.2 5B only with heavy offloading."
        local = ["ltxv_2b_distilled"]
    elif apple and ram_gb >= 32:
        verdict = "Apple Silicon: LTX 2B and Wan 2.2 5B run via Metal (slower than NVIDIA)."
        local = ["ltxv_2b_distilled", "wan22_ti2v_5b"]
    else:
        verdict = ("No GPU usable for AI video. Local generation is CPU-only: LTX 2B at low resolution, "
                   "tens of minutes per short clip. Use the free Kaggle GPU backend for real quality.")
        local = ["ltxv_2b_distilled"] if ram_gb >= 16 else []
    return {
        "os": f"{platform.system()} {platform.mac_ver()[0] or platform.release()}", "arch": platform.machine(),
        "cpu": platform.processor() or platform.machine(), "cores": psutil.cpu_count(logical=False),
        "threads": psutil.cpu_count(), "ram_gb": ram_gb, "ram_used_pct": vm.percent,
        "disk_free_gb": round(du.free / 2**30), "disk_total_gb": round(du.total / 2**30), "gpus": gpus,
        "verdict": verdict, "local_engines": local,
    }
