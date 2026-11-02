"""Prompt enhancement without paid APIs.

1. If a local Ollama server is running (free, https://ollama.com) and a model is
   chosen in Settings, it rewrites the prompt with a video-specific instruction.
2. Otherwise a built-in, rule-based enhancer adds structure (shot, lighting, lens,
   quality cues) that Wan/LTX respond well to. It is labelled "built-in" in the UI.
"""
from __future__ import annotations

import re

import httpx

from .config import load_settings

SYSTEM = (
    "You rewrite short ideas into a single detailed prompt for an AI text-to-video model. "
    "Describe, in one paragraph of 60-120 words: the subject and its appearance, the action over time, "
    "the setting, lighting, color palette, camera framing and movement, and the visual style. "
    "Use concrete visual language, present tense, no lists, no quotation marks, no preamble. "
    "Keep every detail the user gave. Output only the prompt."
)

STYLE_HINTS = [
    (r"\b(product|bottle|watch|shoe|perfume|phone|packshot)\b",
     "studio product shot, softbox lighting, clean reflections, seamless backdrop, crisp detail"),
    (r"\b(portrait|woman|man|girl|boy|face|person|character)\b",
     "natural skin texture, expressive eyes, soft key light with gentle rim light, 85mm lens, shallow depth of field"),
    (r"\b(landscape|mountain|ocean|forest|desert|city|street|sky|sunset|sunrise)\b",
     "wide establishing shot, atmospheric depth, volumetric light, rich natural colors"),
    (r"\b(night|neon|cyberpunk|rain)\b",
     "moody night lighting, neon reflections on wet surfaces, high contrast"),
    (r"\b(anime|cartoon|illustration|pixar|3d render)\b",
     "consistent stylized rendering, clean line work, vibrant palette"),
]


def builtin_enhance(prompt: str) -> str:
    p = prompt.strip().rstrip(".")
    if not p:
        return p
    extras = [hint for pat, hint in STYLE_HINTS if re.search(pat, p, re.I)]
    if not extras:
        extras.append("cinematic composition, natural motion, balanced lighting")
    extras.append("cinematic, highly detailed, smooth realistic motion, film grain, professional color grading")
    return f"{p}. " + ". ".join(extras) + "."


async def ollama_models() -> list[str]:
    s = load_settings()
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{s['ollama_url'].rstrip('/')}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


async def enhance(prompt: str) -> dict[str, str]:
    s = load_settings()
    model = s.get("ollama_model") or ""
    if model:
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(f"{s['ollama_url'].rstrip('/')}/api/generate",
                                 json={"model": model, "system": SYSTEM, "prompt": prompt, "stream": False,
                                       "options": {"temperature": 0.7}})
                r.raise_for_status()
                text = r.json().get("response", "").strip().strip('"')
                if text:
                    return {"prompt": text, "method": f"ollama:{model}"}
        except Exception as e:  # fall through to the built-in enhancer, but say why
            return {"prompt": builtin_enhance(prompt), "method": "built-in",
                    "note": f"Ollama unavailable ({type(e).__name__}); used the built-in enhancer."}
    return {"prompt": builtin_enhance(prompt), "method": "built-in"}
