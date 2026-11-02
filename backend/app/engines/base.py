"""Model adapter interface.

An engine knows: which weight files it needs (and where to download them for
free), which modes it really supports, sensible defaults, and how to turn a
generation request into a ComfyUI API workflow. Adding a new engine = adding one
module that subclasses Engine and registering it in engines/__init__.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4}


@dataclass
class ModelFile:
    filename: str
    folder: str           # ComfyUI models sub-folder: diffusion_models, text_encoders, vae, checkpoints, upscale_models
    url: str              # free direct download (Hugging Face)
    size_gb: float
    alternatives: list[str] = field(default_factory=list)  # other filenames that also work


@dataclass
class Resolution:
    id: str
    label: str
    pixels: int           # target area; width/height are derived per aspect ratio
    note: str = ""


@dataclass
class GenRequest:
    mode: str                         # t2v | i2v | v2v
    prompt: str                       # final prompt (camera/character text already merged)
    negative: str
    aspect: str
    resolution: str
    duration_s: float
    fps: int
    steps: int
    cfg: float
    seed: int
    image: str | None = None          # file name inside ComfyUI input/ (after upload)
    video: str | None = None
    denoise: float = 1.0              # v2v strength: lower keeps more of the source
    extra: dict[str, Any] = field(default_factory=dict)


class Graph:
    """Small helper that builds ComfyUI API-format JSON."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self._n = 0

    def add(self, class_type: str, **inputs: Any) -> "Ref":
        self._n += 1
        nid = str(self._n)
        self.nodes[nid] = {"class_type": class_type, "inputs": {k: (v.out(0) if isinstance(v, Ref) else v)
                                                                for k, v in inputs.items() if v is not None}}
        return Ref(nid)


class Ref:
    def __init__(self, nid: str):
        self.nid = nid

    def out(self, i: int) -> list[Any]:
        return [self.nid, i]

    def __getitem__(self, i: int) -> list[Any]:
        return self.out(i)


class Engine:
    id: str = ""
    name: str = ""
    family: str = ""
    description: str = ""
    license: str = ""
    homepage: str = ""
    modes: tuple[str, ...] = ()
    min_vram_gb: float = 0
    recommended_vram_gb: float = 0
    runs_on_cpu: bool = False
    cpu_note: str = ""
    files: list[ModelFile] = []
    resolutions: list[Resolution] = []
    fps_options: tuple[int, ...] = (24,)
    max_frames: int = 121
    frame_multiple: int = 4           # frames must equal multiple*n + 1
    size_multiple: int = 32
    defaults: dict[str, Any] = {}
    catalog_only: bool = False        # listed for information; no workflow on current hardware
    supports_negative: bool = True

    # ---------- shared helpers ----------
    def dims(self, aspect: str, resolution: str) -> tuple[int, int]:
        res = next((r for r in self.resolutions if r.id == resolution), self.resolutions[0])
        a = ASPECTS.get(aspect, 16 / 9)
        w = math.sqrt(res.pixels * a)
        h = w / a
        m = self.size_multiple
        return max(m, int(round(w / m)) * m), max(m, int(round(h / m)) * m)

    def frames(self, duration_s: float, fps: int) -> int:
        m = self.frame_multiple
        target = max(1, int(round(duration_s * fps)))
        n = max(1, round((target - 1) / m))
        return min(m * n + 1, self.max_frames)

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "family": self.family, "description": self.description,
            "license": self.license, "homepage": self.homepage, "modes": list(self.modes),
            "min_vram_gb": self.min_vram_gb, "recommended_vram_gb": self.recommended_vram_gb,
            "runs_on_cpu": self.runs_on_cpu, "cpu_note": self.cpu_note,
            "files": [f.__dict__ for f in self.files],
            "total_size_gb": round(sum(f.size_gb for f in self.files), 1),
            "resolutions": [r.__dict__ for r in self.resolutions], "fps_options": list(self.fps_options),
            "max_frames": self.max_frames, "frame_multiple": self.frame_multiple,
            "defaults": self.defaults, "catalog_only": self.catalog_only,
            "supports_negative": self.supports_negative,
        }

    def resolve_files(self, installed: dict[str, list[str]]) -> dict[str, str | None]:
        """Maps each needed file to the name actually present on the backend (or None)."""
        out: dict[str, str | None] = {}
        for f in self.files:
            present = installed.get(f.folder, [])
            names = [f.filename, *f.alternatives]
            hit = next((n for n in names if n in present), None)
            if hit is None:  # tolerate files placed in sub-folders
                hit = next((p for p in present for n in names if p.endswith("/" + n)), None)
            out[f.filename] = hit
        return out

    def build(self, req: GenRequest, files: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError
