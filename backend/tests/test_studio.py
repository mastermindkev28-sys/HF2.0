"""Automated tests. Real AI generation is tested on a real ComfyUI backend (see docs/TESTING.md);
these check workflow construction and the studio pipeline against the fake_comfy test double."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

os.environ["HIGGS_DATA_DIR"] = tempfile.mkdtemp(prefix="higgs_test_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.camera import build_prompt  # noqa: E402
from app.engines import ENGINES, GenRequest, installed_from_object_info  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def fake_comfy():
    from tests import fake_comfy as fc
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(fc.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}", fc
    server.should_exit = True


def test_dims_and_frames():
    wan = ENGINES["wan22_ti2v_5b"]
    assert wan.dims("16:9", "720p") == (1280, 704)
    assert wan.dims("9:16", "480p") == (480, 832)
    w, h = wan.dims("1:1", "480p")
    assert w == h and w % 32 == 0
    assert (wan.frames(5, 24) - 1) % 4 == 0 and wan.frames(5, 24) == 121
    ltx = ENGINES["ltxv_2b_distilled"]
    assert (ltx.frames(3, 24) - 1) % 8 == 0
    assert ltx.frames(60, 24) == 257


@pytest.mark.parametrize("eid", ["wan22_ti2v_5b", "ltxv_2b_distilled"])
@pytest.mark.parametrize("mode", ["t2v", "i2v", "v2v"])
def test_workflows_are_connected(eid, mode):
    e = ENGINES[eid]
    files = {f.filename: f.filename for f in e.files}
    wf = e.build(GenRequest(mode=mode, prompt="p", negative="n", aspect="16:9", resolution=e.defaults["resolution"],
                            duration_s=2, fps=24, steps=8, cfg=1, seed=5, image="i.png", video="v.mp4"), files)
    ids = set(wf)
    for nid, node in wf.items():
        for v in node["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in ids, f"{eid}/{mode}: node {nid} links to missing {v[0]}"
    types = [n["class_type"] for n in wf.values()]
    assert types[-1] == "SaveVideo"
    if mode == "i2v":
        assert "LoadImage" in types
    if mode == "v2v":
        assert "LoadVideo" in types and "VAEEncode" in types


def test_camera_prompt():
    p = build_prompt("a fox in snow", ["dolly_in", "orbit"], 4)
    assert "dolly-in" in p and "orbiting" in p and "dynamic" in p
    assert "tripod" in build_prompt("x", ["static", "pan_left"], 3)


def test_installed_parsing_both_formats():
    info = {"UNETLoader": {"input": {"required": {"unet_name": [["a.safetensors"]]}}},
            "VAELoader": {"input": {"required": {"vae_name": ["COMBO", {"options": ["v.safetensors"]}]}}}}
    inst = installed_from_object_info(info)
    assert inst["diffusion_models"] == ["a.safetensors"] and inst["vae"] == ["v.safetensors"]


def test_full_pipeline(fake_comfy):
    url, fc = fake_comfy
    from app.main import app
    with TestClient(app) as c:
        s = c.get("/api/settings").json()
        s["backends"][0]["url"] = url
        assert c.put("/api/settings", json=s).status_code == 200
        st = c.get("/api/backends/status?backend_id=local").json()["backends"][0]
        assert st["online"] and st["engines"]["wan22_ti2v_5b"]["installed"]

        g = c.post("/api/generate", json={"mode": "t2v", "engine": "wan22_ti2v_5b", "prompt": "a red fox",
                                          "camera": ["dolly_in"], "duration_s": 2}).json()
        g = _wait(c, g["id"])
        assert g["status"] == "done", g
        assert g["output_file"] and g["thumb_file"]
        assert "dolly-in" in g["final_prompt"]
        assert c.get(f"/files/outputs/{g['output_file']}").status_code == 200
        assert c.get(f"/api/generations/{g['id']}/workflow").status_code == 200

        # image to video with an uploaded asset
        img = Path(os.environ["HIGGS_DATA_DIR"]) / "test.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64", "-frames:v", "1", str(img)], check=True)
        a = c.post("/api/assets", files={"file": ("test.png", img.read_bytes(), "image/png")}).json()
        g2 = _wait(c, c.post("/api/generate", json={"mode": "i2v", "engine": "ltxv_2b_distilled", "image": f"asset:{a['id']}",
                                                     "prompt": "", "motion_intensity": 2}).json()["id"])
        assert g2["status"] == "done", g2
        assert fc.SUBMITTED[-1][next(k for k, v in fc.SUBMITTED[-1].items() if v["class_type"] == "LoadImage")]["inputs"]["image"].startswith("higgs_")

        # variation, extend, stitch, interpolate
        v = _wait(c, c.post(f"/api/generations/{g['id']}/regenerate", json={"variation": True}).json()["id"])
        assert v["status"] == "done" and v["params"]["seed"] != g["params"]["seed"]
        e = _wait(c, c.post(f"/api/generations/{g['id']}/extend", json={}).json()["id"])
        assert e["status"] == "done" and e["duration_s"] > g["duration_s"]
        st2 = _wait(c, c.post("/api/tools/stitch", json={"sources": [f"generation:{g['id']}", f"generation:{v['id']}"]}).json()["id"])
        assert st2["status"] == "done"
        it = _wait(c, c.post("/api/tools/interpolate", json={"source": f"generation:{g['id']}", "target_fps": 48}).json()["id"])
        assert it["status"] == "done", it

        # missing model -> honest error, no fake output
        up = _wait(c, c.post("/api/tools/upscale_ai", json={"source": f"generation:{g['id']}"}).json()["id"])
        assert up["status"] == "error" and "not installed" in up["error"]

        # characters
        ch = c.post("/api/characters/from-generation", json={"generation_id": g["id"], "name": "Fox"}).json()
        assert ch["images"]
        g3 = _wait(c, c.post("/api/generate", json={"mode": "i2v", "engine": "wan22_ti2v_5b", "character_id": ch["id"], "prompt": "runs"}).json()["id"])
        assert g3["status"] == "done" and g3["params"]["image"].startswith("character:")

        assert c.delete(f"/api/generations/{g['id']}").status_code == 200
        assert c.get(f"/api/generations/{g['id']}").status_code == 404


def test_offline_backend_reports_error():
    from app.main import app
    with TestClient(app) as c:
        s = c.get("/api/settings").json()
        s["backends"].append({"id": "dead", "name": "dead", "url": "http://127.0.0.1:9", "token": "", "kind": "remote"})
        c.put("/api/settings", json=s)
        g = _wait(c, c.post("/api/generate", json={"mode": "t2v", "engine": "ltxv_2b_distilled", "prompt": "x", "backend_id": "dead"}).json()["id"])
        assert g["status"] == "error" and "reach" in g["error"]


def _wait(c, gid, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        g = c.get(f"/api/generations/{gid}").json()
        if g["status"] in ("done", "error", "cancelled"):
            return g
        time.sleep(0.2)
    raise TimeoutError(gid)
