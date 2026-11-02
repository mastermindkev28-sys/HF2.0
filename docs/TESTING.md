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
