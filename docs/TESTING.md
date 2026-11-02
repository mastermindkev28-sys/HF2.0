# Test log

## Automated (every change)
`cd backend && .venv/bin/python -m pytest -q`: workflow graph checks for every engine and mode, camera
prompt building, model detection, and the full studio pipeline (queue → progress → download → thumbnail →
library, plus variation, extend, stitch, interpolation, characters, honest errors for offline backends
and missing models). Pipeline tests use `tests/fake_comfy.py`, a ComfyUI test double that renders an
FFmpeg test pattern. It is not AI and is never used by the app.

## Real generation runs
Recorded here with hardware, settings and wall-clock time as they're run. Nothing below is estimated.

| Date | Backend | Engine | Mode | Settings | Time | Result |
|---|---|---|---|---|---|---|
| 2026-11-02 | User's MacBook Pro (Intel i7-1068NG7, 32 GB, CPU only), ComfyUI v0.7.0 + PyTorch 2.2.2 | LTX-Video 2B distilled 0.9.8 | t2v (direct ComfyUI API, same node graph as the studio) | 320×192, 9 frames @ 24 fps, 8 steps, cfg 1, seed 42 | 78.6 s total, cold model load; sampling 27.8 s (~3 s/step); peak RAM 15.8 GB | ✅ Fox walking through snow between pines, verified by inspecting a frame |

### Intel Mac notes learned from that run
- ComfyUI ≥ 0.8.0 needs PyTorch 2.4 (`torch.library.custom_op`), so Intel Macs are pinned to v0.7.0.
- `transformers` 5.x needs PyTorch ≥ 2.6, so it's pinned to 4.51.3.
- PyTorch 2.2 lacks `torch.compiler.is_compiling`; `custom_nodes/torch22_compat.py` provides it.
- `comfy-angle`, `comfy-kitchen` and `comfy-aimdo` are skipped (no Intel-Mac builds, optional for v0.7.0).
- FFmpeg comes from the imageio-ffmpeg wheel on PyPI (no ffprobe; the studio falls back to parsing `ffmpeg -i`).
