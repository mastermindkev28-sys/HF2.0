"""Paths and persistent settings for HIGGS Studio.

Everything the studio stores lives under one data directory on your own disk
(default: <repo>/data, override with HIGGS_DATA_DIR).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("HIGGS_DATA_DIR", REPO_ROOT / "data")).expanduser().resolve()
OUTPUTS_DIR = DATA_DIR / "outputs"
THUMBS_DIR = DATA_DIR / "thumbnails"
ASSETS_DIR = DATA_DIR / "assets"
CHARACTERS_DIR = DATA_DIR / "characters"
DB_PATH = DATA_DIR / "studio.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
FRONTEND_DIR = REPO_ROOT / "frontend" / "out"
RUNTIME_DIR = Path(os.environ.get("HIGGS_RUNTIME_DIR", REPO_ROOT.parent / "runtime")).expanduser()

for _d in (DATA_DIR, OUTPUTS_DIR, THUMBS_DIR, ASSETS_DIR, CHARACTERS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS: dict[str, Any] = {
    # A backend is any ComfyUI server reachable over HTTP. "local" is ComfyUI on this
    # computer; "kaggle" is the free Kaggle GPU notebook (its URL changes every session).
    "backends": [
        {"id": "local", "name": "This computer (ComfyUI)", "url": "http://127.0.0.1:8188", "token": "", "kind": "local"},
        {"id": "kaggle", "name": "Kaggle free GPU", "url": "", "token": "", "kind": "remote"},
    ],
    "active_backend": "local",
    # Optional free local LLM for prompt enhancement (https://ollama.com). Never a paid API.
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "",
    "ffmpeg_path": "",
}

_lock = threading.Lock()


def load_settings() -> dict[str, Any]:
    with _lock:
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text())
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        merged = {**DEFAULT_SETTINGS, **data}
        # make sure default backends always exist
        ids = {b["id"] for b in merged["backends"]}
        for b in DEFAULT_SETTINGS["backends"]:
            if b["id"] not in ids:
                merged["backends"].append(dict(b))
        return merged


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(SETTINGS_PATH)
    return data


def active_backend(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    s = settings or load_settings()
    for b in s["backends"]:
        if b["id"] == s["active_backend"]:
            return b
    return s["backends"][0]
