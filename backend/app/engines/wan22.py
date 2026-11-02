"""Wan 2.2 TI2V-5B (Alibaba Wan team, Apache-2.0).

One 5B model does both text-to-video and image-to-video at up to 1280x704, 24 fps.
Runs on a 16 GB GPU (e.g. the free Kaggle T4/P100) with ComfyUI's automatic
offloading. Not practical on a CPU.

Workflow mirrors ComfyUI's official "Wan 2.2 5B video generation" template:
UNETLoader + CLIPLoader(type=wan) + VAELoader(wan2.2_vae) -> ModelSamplingSD3(shift=8)
-> Wan22ImageToVideoLatent -> KSampler(uni_pc/simple) -> VAEDecode -> CreateVideo -> SaveVideo.
"""
from __future__ import annotations

from typing import Any

from .base import Engine, GenRequest, Graph, ModelFile, Resolution

HF = "https://huggingface.co"

WAN_NEGATIVE = ("oversaturated, overexposed, static, blurry details, subtitles, text, watermark, painting, "
                "still image, overall gray, worst quality, low quality, JPEG artifacts, ugly, deformed, "
                "extra fingers, poorly drawn hands, poorly drawn face, disfigured, malformed limbs, "
                "fused fingers, motionless frame, cluttered background, three legs, many people in the background, "
                "walking backwards")


class Wan22TI2V5B(Engine):
    id = "wan22_ti2v_5b"
    name = "Wan 2.2 TI2V 5B"
    family = "Wan 2.2"
    description = ("Primary engine. Open-weight 5B text+image-to-video model from the Wan 2.2 family. "
                   "Strong prompt following and motion, 24 fps, up to ~5 s per clip.")
    license = "Apache-2.0"
    homepage = "https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B"
    modes = ("t2v", "i2v", "v2v")
    min_vram_gb = 12
    recommended_vram_gb = 16
    runs_on_cpu = False
    cpu_note = "Technically loads in 32 GB RAM but takes hours per clip on a laptop CPU; use the Kaggle GPU backend."
    files = [
        ModelFile("wan2.2_ti2v_5B_fp16.safetensors", "diffusion_models",
                  f"{HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", 10.0),
        ModelFile("umt5_xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders",
                  f"{HF}/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", 6.7),
        ModelFile("wan2.2_vae.safetensors", "vae",
                  f"{HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors", 1.4),
    ]
    resolutions = [
        Resolution("480p", "480p (fast)", 832 * 480, "Good for drafts. ~4x faster than 720p."),
        Resolution("576p", "576p", 1024 * 576),
        Resolution("720p", "720p (native)", 1280 * 704, "Native resolution; slowest."),
    ]
    fps_options = (16, 24)
    max_frames = 121
    frame_multiple = 4
    size_multiple = 32
    defaults = {"steps": 20, "cfg": 5.0, "fps": 24, "duration_s": 3, "resolution": "480p",
                "negative": WAN_NEGATIVE, "shift": 8.0, "sampler": "uni_pc", "scheduler": "simple", "denoise": 0.65}

    def build(self, req: GenRequest, files: dict[str, str]) -> dict[str, Any]:
        g = Graph()
        w, h = self.dims(req.aspect, req.resolution)
        length = self.frames(req.duration_s, req.fps)
        unet = g.add("UNETLoader", unet_name=files["wan2.2_ti2v_5B_fp16.safetensors"], weight_dtype="default")
        clip = g.add("CLIPLoader", clip_name=files["umt5_xxl_fp8_e4m3fn_scaled.safetensors"], type="wan", device="default")
        vae = g.add("VAELoader", vae_name=files["wan2.2_vae.safetensors"])
        model = g.add("ModelSamplingSD3", model=unet, shift=float(req.extra.get("shift", self.defaults["shift"])))
        pos = g.add("CLIPTextEncode", text=req.prompt, clip=clip)
        neg = g.add("CLIPTextEncode", text=req.negative or "", clip=clip)
        denoise = 1.0

        if req.mode == "v2v":
            if not req.video:
                raise ValueError("Video-to-video needs a source video.")
            src = g.add("LoadVideo", file=req.video)
            comps = g.add("GetVideoComponents", video=src)
            clip_frames = g.add("ImageFromBatch", image=comps.out(0), batch_index=0, length=length)
            scaled = g.add("ImageScale", image=clip_frames, upscale_method="lanczos", width=w, height=h, crop="center")
            latent = g.add("VAEEncode", pixels=scaled, vae=vae)
            denoise = float(req.denoise)
        else:
            start = None
            if req.mode == "i2v":
                if not req.image:
                    raise ValueError("Image-to-video needs an image.")
                start = g.add("LoadImage", image=req.image)
            latent = g.add("Wan22ImageToVideoLatent", vae=vae, width=w, height=h, length=length, batch_size=1,
                           start_image=start.out(0) if start else None)

        sampled = g.add("KSampler", model=model, seed=int(req.seed), steps=int(req.steps), cfg=float(req.cfg),
                        sampler_name=req.extra.get("sampler", self.defaults["sampler"]),
                        scheduler=req.extra.get("scheduler", self.defaults["scheduler"]),
                        positive=pos, negative=neg, latent_image=latent, denoise=denoise)
        frames = g.add("VAEDecode", samples=sampled, vae=vae)
        video = g.add("CreateVideo", images=frames, fps=float(req.fps))
        g.add("SaveVideo", video=video, filename_prefix="higgs/wan22", format="mp4", codec="h264")
        return g.nodes


class Wan22A14B(Engine):
    id = "wan22_a14b"
    name = "Wan 2.2 A14B (T2V / I2V)"
    family = "Wan 2.2"
    description = ("The flagship 14B mixture-of-experts Wan 2.2 models. Best quality in the family, "
                   "but needs a 24 GB+ NVIDIA GPU (or heavy quantization on 16 GB). Listed for when you "
                   "add a stronger GPU backend.")
    license = "Apache-2.0"
    homepage = "https://huggingface.co/Wan-AI/Wan2.2-T2V-A14B"
    modes = ("t2v", "i2v")
    min_vram_gb = 24
    recommended_vram_gb = 48
    catalog_only = True
    cpu_note = "Not feasible on CPU."
    files = []
    resolutions = [Resolution("720p", "720p", 1280 * 720)]
