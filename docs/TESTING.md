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
| 2026-11-02 | Same Mac, through the studio app (start.sh, local backend) | LTX-Video 2B distilled | t2v | "512p" 16:9 → 832×480, 49 frames (2.0 s) @ 24 fps, 8 steps, tracking camera | 1188.6 s (~20 min); ~75–125 s/step, slowed by a game and Chrome using the CPU; ~12–13 GB RAM | ✅ Fox in snow between pines, golden backlight, soft background |
| 2026-11-02 | Same | LTX-Video 2B distilled | i2v (uploaded frame) | 320p → 544×288, 25 frames (1 s), "gentle wind, subtle motion" | 340.5 s (~5.7 min); peak 18.3 GB RAM | ✅ First frame matches the input; subject stays consistent |
| 2026-11-02 | Same | Real-ESRGAN x2 | model install via Explore Models | 67 MB | 25 MB/s | ✅ certifi fix verified (was CERTIFICATE_VERIFY_FAILED) |

### Intel Mac notes learned from that run
- ComfyUI ≥ 0.8.0 needs PyTorch 2.4 (`torch.library.custom_op`), so Intel Macs are pinned to v0.7.0.
- `transformers` 5.x needs PyTorch ≥ 2.6, so it's pinned to 4.51.3.
- PyTorch 2.2 lacks `torch.compiler.is_compiling`; `custom_nodes/torch22_compat.py` provides it.
- `comfy-angle`, `comfy-kitchen` and `comfy-aimdo` are skipped (no Intel-Mac builds, optional for v0.7.0).
- FFmpeg comes from the imageio-ffmpeg wheel on PyPI (no ffprobe; the studio falls back to parsing `ffmpeg -i`).
