"""Async client for the ComfyUI HTTP + websocket API.

Works the same for ComfyUI on this computer and ComfyUI in the Kaggle notebook
(reached via a tunnel URL). If the backend has a token, it is sent as a Bearer
header; the HIGGS bridge node on the ComfyUI side checks it.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlencode

import httpx
import websockets


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, url: str, token: str = "", timeout: float = 30.0):
        if not url:
            raise ComfyError("No ComfyUI address set for this backend. Add it in Settings.")
        self.url = url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex

    # -- helpers --
    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.url, headers=self.headers, timeout=timeout or self.timeout,
                                 follow_redirects=True)

    async def _get(self, path: str, **params: Any) -> Any:
        async with self._client() as c:
            r = await c.get(path, params=params or None)
            if r.status_code == 401:
                raise ComfyError("The ComfyUI backend rejected the access token. Check it in Settings.")
            r.raise_for_status()
            return r.json()

    # -- info --
    async def system_stats(self) -> dict[str, Any]:
        return await self._get("/system_stats")

    async def object_info(self, node: str | None = None) -> dict[str, Any]:
        return await self._get(f"/object_info/{node}" if node else "/object_info")

    async def queue(self) -> dict[str, Any]:
        return await self._get("/queue")

    async def history(self, prompt_id: str) -> dict[str, Any]:
        return await self._get(f"/history/{prompt_id}")

    async def bridge(self, path: str, method: str = "GET", payload: dict | None = None) -> Any:
        """Calls the HIGGS bridge custom node (model manager + hardware info)."""
        async with self._client() as c:
            r = await c.request(method, f"/higgs/{path}", json=payload)
            if r.status_code == 404:
                raise ComfyError("The HIGGS bridge node is not installed on this ComfyUI backend "
                                 "(custom_nodes/higgs_bridge). Run the installer or the Kaggle notebook again.")
            if r.status_code == 401:
                raise ComfyError("The ComfyUI backend rejected the access token. Check it in Settings.")
            r.raise_for_status()
            return r.json()

    # -- files --
    async def upload_file(self, path: Path, name: str | None = None) -> str:
        """Uploads an image or video into ComfyUI's input folder; returns the stored name."""
        async with self._client(timeout=600) as c:
            with path.open("rb") as fh:
                r = await c.post("/upload/image", files={"image": (name or path.name, fh)},
                                 data={"overwrite": "true", "type": "input"})
            r.raise_for_status()
            data = r.json()
            sub = data.get("subfolder") or ""
            return f"{sub}/{data['name']}" if sub else data["name"]

    async def download(self, filename: str, subfolder: str, ftype: str, dest: Path) -> Path:
        params = urlencode({"filename": filename, "subfolder": subfolder, "type": ftype})
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with self._client(timeout=600) as c:
            async with c.stream("GET", f"/view?{params}") as r:
                r.raise_for_status()
                with dest.open("wb") as fh:
                    async for chunk in r.aiter_bytes(1 << 20):
                        fh.write(chunk)
        return dest

    # -- execution --
    async def submit(self, workflow: dict[str, Any]) -> str:
        async with self._client() as c:
            r = await c.post("/prompt", json={"prompt": workflow, "client_id": self.client_id})
            if r.status_code >= 400:
                try:
                    detail = r.json()
                except Exception:
                    detail = r.text
                raise ComfyError(f"ComfyUI rejected the workflow: {_summarize_error(detail)}")
            return r.json()["prompt_id"]

    async def interrupt(self) -> None:
        async with self._client() as c:
            await c.post("/interrupt")

    async def delete_from_queue(self, prompt_id: str) -> None:
        async with self._client() as c:
            await c.post("/queue", json={"delete": [prompt_id]})

    def ws_url(self) -> str:
        base = self.url.replace("https://", "wss://").replace("http://", "ws://")
        q = {"clientId": self.client_id}
        if self.token:
            q["token"] = self.token
        return f"{base}/ws?{urlencode(q)}"

    async def run(self, workflow: dict[str, Any], on_progress: Callable[[float, str], Any],
                  cancel: asyncio.Event | None = None) -> dict[str, Any]:
        """Submit a workflow and wait for it to finish. Returns its history entry."""
        prompt_id = None
        try:
            ws = await websockets.connect(self.ws_url(), max_size=None, open_timeout=20,
                                          additional_headers=self.headers)
        except Exception:
            ws = None  # fall back to polling /history
        try:
            prompt_id = await self.submit(workflow)
            on_progress(0.0, "Queued on backend")
            if ws is not None:
                await self._follow_ws(ws, prompt_id, workflow, on_progress, cancel)
            entry = await self._poll_history(prompt_id, on_progress, cancel)
            return {"prompt_id": prompt_id, **entry}
        finally:
            if ws is not None:
                await ws.close()

    async def _follow_ws(self, ws, prompt_id, workflow, on_progress, cancel) -> None:
        total_nodes = max(len(workflow), 1)
        done_nodes: set[str] = set()
        current = ""
        while True:
            if cancel is not None and cancel.is_set():
                await self.interrupt()
                raise asyncio.CancelledError
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                # check if it already finished while we were not looking
                h = await self.history(prompt_id)
                if prompt_id in h:
                    return
                continue
            except websockets.ConnectionClosed:
                return
            if isinstance(raw, bytes):
                continue  # binary preview frames
            msg = json.loads(raw)
            mtype, data = msg.get("type"), msg.get("data", {})
            if data.get("prompt_id") not in (None, prompt_id):
                continue
            if mtype == "execution_start":
                on_progress(0.01, "Starting")
            elif mtype == "execution_cached":
                done_nodes.update(data.get("nodes", []))
            elif mtype == "executing":
                node = data.get("node")
                if node is None:
                    return
                if current:
                    done_nodes.add(current)
                current = node
                cls = workflow.get(node, {}).get("class_type", node)
                on_progress(min(0.99, len(done_nodes) / total_nodes * 0.3), _friendly(cls))
            elif mtype == "progress":
                v, m = data.get("value", 0), max(data.get("max", 1), 1)
                cls = workflow.get(current, {}).get("class_type", "")
                if "Sampler" in cls or cls.startswith("KSampler"):
                    on_progress(0.3 + 0.65 * v / m, f"Generating · step {v}/{m}")
                else:
                    on_progress(None, f"{_friendly(cls)} {v}/{m}")  # type: ignore[arg-type]
            elif mtype == "execution_error":
                raise ComfyError(f"{data.get('node_type', 'A node')} failed: {data.get('exception_message', '').strip()}")
            elif mtype == "execution_interrupted":
                raise ComfyError("Generation was interrupted on the backend.")
            elif mtype == "execution_success":
                return

    async def _poll_history(self, prompt_id, on_progress, cancel) -> dict[str, Any]:
        while True:
            if cancel is not None and cancel.is_set():
                await self.interrupt()
                raise asyncio.CancelledError
            h = await self.history(prompt_id)
            if prompt_id in h:
                entry = h[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    for m in status.get("messages", []):
                        if m[0] == "execution_error":
                            d = m[1]
                            raise ComfyError(f"{d.get('node_type', 'A node')} failed: {d.get('exception_message', '').strip()}")
                    raise ComfyError("Generation failed on the backend.")
                return entry
            await asyncio.sleep(2)


def pick_output(entry: dict[str, Any]) -> dict[str, str] | None:
    """Finds the main video (or image) file in a history entry."""
    files: list[dict[str, str]] = []
    for node_out in entry.get("outputs", {}).values():
        for key in ("videos", "gifs", "images", "video"):
            for f in node_out.get(key, []) or []:
                if isinstance(f, dict) and "filename" in f:
                    files.append(f)
    if not files:
        return None
    vids = [f for f in files if f["filename"].lower().endswith((".mp4", ".webm", ".mov", ".mkv"))]
    anim = [f for f in files if f["filename"].lower().endswith((".webp", ".gif"))]
    out = [f for f in (vids or anim or files) if f.get("type", "output") == "output"] or (vids or anim or files)
    return out[-1]


_FRIENDLY = {
    "UNETLoader": "Loading video model",
    "CheckpointLoaderSimple": "Loading video model",
    "CLIPLoader": "Loading text encoder",
    "VAELoader": "Loading VAE",
    "CLIPTextEncode": "Encoding prompt",
    "VAEDecode": "Decoding frames",
    "VAEDecodeTiled": "Decoding frames",
    "VAEEncode": "Encoding source video",
    "CreateVideo": "Assembling video",
    "SaveVideo": "Saving video",
    "LoadImage": "Loading image",
    "LoadVideo": "Loading video",
}


def _friendly(cls: str) -> str:
    return _FRIENDLY.get(cls, cls)


def _summarize_error(detail: Any) -> str:
    if isinstance(detail, dict):
        err = detail.get("error", {})
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        parts = [msg]
        for node_id, ne in (detail.get("node_errors") or {}).items():
            for e in ne.get("errors", []):
                parts.append(f"node {node_id} ({ne.get('class_type')}): {e.get('message')} {e.get('details', '')}".strip())
        return "; ".join(p for p in parts if p)
    return str(detail)[:500]
