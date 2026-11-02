from __future__ import annotations

from typing import Any

from .base import Engine, GenRequest, Graph, ModelFile
from .ltxv import HunyuanVideo, LTXVideo2B
from .wan22 import Wan22A14B, Wan22TI2V5B

ENGINES: dict[str, Engine] = {e.id: e for e in (Wan22TI2V5B(), LTXVideo2B(), Wan22A14B(), HunyuanVideo())}

# Extra (non-generation) model used by the AI upscale tool. Real-ESRGAN, BSD-3.
UPSCALER = ModelFile("RealESRGAN_x2.pth", "upscale_models",
                     "https://huggingface.co/ai-forever/Real-ESRGAN/resolve/main/RealESRGAN_x2.pth", 0.07,
                     alternatives=["RealESRGAN_x2plus.pth", "RealESRGAN_x4plus.pth", "4x-UltraSharp.pth"])

# object_info node/input pairs that list the files present in each models folder
FOLDER_PROBES = {
    "diffusion_models": ("UNETLoader", "unet_name"),
    "text_encoders": ("CLIPLoader", "clip_name"),
    "vae": ("VAELoader", "vae_name"),
    "checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
    "upscale_models": ("UpscaleModelLoader", "model_name"),
}


def get_engine(engine_id: str) -> Engine:
    if engine_id not in ENGINES:
        raise KeyError(f"Unknown engine '{engine_id}'")
    return ENGINES[engine_id]


def installed_from_object_info(info: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for folder, (node, inp) in FOLDER_PROBES.items():
        try:
            spec = info[node]["input"]["required"][inp]
            choices = spec[0]
            if isinstance(choices, str) and len(spec) > 1 and isinstance(spec[1], dict):  # newer "COMBO" format
                choices = spec[1].get("options", [])
            out[folder] = list(choices) if isinstance(choices, list) else []
        except (KeyError, IndexError, TypeError):
            out[folder] = []
    return out


def upscale_workflow(video_name: str, model_name: str, fps: float) -> dict[str, Any]:
    g = Graph()
    src = g.add("LoadVideo", file=video_name)
    comps = g.add("GetVideoComponents", video=src)
    up_model = g.add("UpscaleModelLoader", model_name=model_name)
    up = g.add("ImageUpscaleWithModel", upscale_model=up_model, image=comps.out(0))
    video = g.add("CreateVideo", images=up, fps=float(fps))
    g.add("SaveVideo", video=video, filename_prefix="higgs/upscaled", format="mp4", codec="h264")
    return g.nodes


__all__ = ["ENGINES", "UPSCALER", "Engine", "GenRequest", "get_engine", "installed_from_object_info",
           "upscale_workflow", "FOLDER_PROBES"]
