"""LTX-Video 2B distilled (Lightricks, LTXV open-weights license).

The lightest serious open video model: a distilled 2B DiT that needs only ~8 steps.
It is the only engine that is usable (slowly) on a CPU-only computer, and it is
fast on the free Kaggle GPU.

Workflow follows ComfyUI's core LTXV nodes:
CheckpointLoaderSimple (model+vae) + CLIPLoader(type=ltxv, T5-XXL) -> CLIPTextEncode
-> LTXVConditioning(frame_rate) -> EmptyLTXVLatentVideo | LTXVImgToVideo
-> LTXVScheduler -> SamplerCustom(euler) -> VAEDecode -> CreateVideo -> SaveVideo.
"""
from __future__ import annotations

from typing import Any

from .base import Engine, GenRequest, Graph, ModelFile, Resolution

HF = "https://huggingface.co"

LTX_NEGATIVE = "worst quality, inconsistent motion, blurry, jittery, distorted, watermark, text, deformed"


class LTXVideo2B(Engine):
    id = "ltxv_2b_distilled"
    name = "LTX-Video 2B distilled"
    family = "LTX Video"
    description = ("Fast, lightweight engine. ~8 sampling steps, 24 fps, up to ~10 s. Lower fidelity than Wan 2.2, "
                   "but the only model that runs on this Mac's CPU, and very quick on the Kaggle GPU.")
    license = "LTXV Open Weights License (free for personal use)"
    homepage = "https://huggingface.co/Lightricks/LTX-Video"
    modes = ("t2v", "i2v", "v2v")
    min_vram_gb = 6
    recommended_vram_gb = 12
    runs_on_cpu = True
    cpu_note = "Runs on CPU at low resolution (e.g. 512x320, 2-3 s). Expect tens of minutes per clip on a 4-core laptop."
    files = [
        ModelFile("ltxv-2b-0.9.8-distilled.safetensors", "checkpoints",
                  f"{HF}/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled.safetensors", 6.3,
                  alternatives=["ltxv-2b-0.9.6-distilled-04-25.safetensors"]),
        ModelFile("t5xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders",
                  f"{HF}/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors", 5.2,
                  alternatives=["t5xxl_fp8_e4m3fn.safetensors", "t5xxl_fp16.safetensors"]),
    ]
    resolutions = [
        Resolution("320p", "320p (CPU-friendly)", 512 * 320, "The practical size on a CPU-only computer."),
        Resolution("512p", "512p (native)", 768 * 512),
        Resolution("704p", "704p", 1216 * 704, "GPU only."),
    ]
    fps_options = (24, 25, 30)
    max_frames = 257
    frame_multiple = 8
    size_multiple = 32
    defaults = {"steps": 8, "cfg": 1.0, "fps": 24, "duration_s": 3, "resolution": "512p",
                "negative": LTX_NEGATIVE, "i2v_strength": 1.0, "denoise": 0.6}

    def build(self, req: GenRequest, files: dict[str, str]) -> dict[str, Any]:
        g = Graph()
        w, h = self.dims(req.aspect, req.resolution)
        length = self.frames(req.duration_s, req.fps)
        ckpt = g.add("CheckpointLoaderSimple", ckpt_name=files["ltxv-2b-0.9.8-distilled.safetensors"])
        clip = g.add("CLIPLoader", clip_name=files["t5xxl_fp8_e4m3fn_scaled.safetensors"], type="ltxv", device="default")
        model, vae = ckpt.out(0), ckpt.out(2)
        pos = g.add("CLIPTextEncode", text=req.prompt, clip=clip)
        neg = g.add("CLIPTextEncode", text=req.negative or "", clip=clip)

        if req.mode == "i2v":
            if not req.image:
                raise ValueError("Image-to-video needs an image.")
            img = g.add("LoadImage", image=req.image)
            i2v = g.add("LTXVImgToVideo", positive=pos, negative=neg, vae=vae, image=img.out(0), width=w, height=h,
                        length=length, batch_size=1, strength=float(req.extra.get("i2v_strength", 1.0)))
            pos_c, neg_c, latent = i2v.out(0), i2v.out(1), i2v.out(2)
        elif req.mode == "v2v":
            if not req.video:
                raise ValueError("Video-to-video needs a source video.")
            src = g.add("LoadVideo", file=req.video)
            comps = g.add("GetVideoComponents", video=src)
            clip_frames = g.add("ImageFromBatch", image=comps.out(0), batch_index=0, length=length)
            scaled = g.add("ImageScale", image=clip_frames, upscale_method="lanczos", width=w, height=h, crop="center")
            latent = g.add("VAEEncode", pixels=scaled, vae=vae).out(0)
            pos_c, neg_c = pos.out(0), neg.out(0)
        else:
            latent = g.add("EmptyLTXVLatentVideo", width=w, height=h, length=length, batch_size=1).out(0)
            pos_c, neg_c = pos.out(0), neg.out(0)

        cond = g.add("LTXVConditioning", positive=pos_c, negative=neg_c, frame_rate=float(req.fps))
        sigmas = g.add("LTXVScheduler", steps=int(req.steps), max_shift=2.05, base_shift=0.95, stretch=True,
                       terminal=0.1, latent=latent)
        sig = sigmas.out(0)
        if req.mode == "v2v":
            split = g.add("SplitSigmasDenoise", sigmas=sig, denoise=float(req.denoise))
            sig = split.out(1)
        sampler = g.add("KSamplerSelect", sampler_name="euler")
        sampled = g.add("SamplerCustom", model=model, add_noise=True, noise_seed=int(req.seed), cfg=float(req.cfg),
                        positive=cond.out(0), negative=cond.out(1), sampler=sampler, sigmas=sig, latent_image=latent)
        frames = g.add("VAEDecode", samples=sampled.out(0), vae=vae)
        video = g.add("CreateVideo", images=frames, fps=float(req.fps))
        g.add("SaveVideo", video=video, filename_prefix="higgs/ltxv", format="mp4", codec="h264")
        return g.nodes


class HunyuanVideo(Engine):
    id = "hunyuan_video"
    name = "HunyuanVideo / HunyuanVideo 1.5"
    family = "HunyuanVideo"
    description = ("Tencent's open video models. High quality, but heavy: the 13B original needs 24 GB+ VRAM; "
                   "1.5 (8.3B) needs ~14 GB+ with offloading and its license excludes the EU, UK and South Korea. "
                   "Listed for a future stronger GPU backend.")
    license = "Tencent Hunyuan Community License"
    homepage = "https://huggingface.co/tencent/HunyuanVideo-1.5"
    modes = ("t2v", "i2v")
    min_vram_gb = 16
    recommended_vram_gb = 24
    catalog_only = True
    cpu_note = "Not feasible on CPU."
    files = []
    resolutions = [Resolution("720p", "720p", 1280 * 720)]
