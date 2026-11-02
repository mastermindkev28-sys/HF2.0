"""Tiny SQLite layer. One file (data/studio.db), no server."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

from .config import DB_PATH

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    status TEXT NOT NULL,            -- queued | running | done | error | cancelled
    mode TEXT NOT NULL,              -- t2v | i2v | v2v | extend
    engine TEXT NOT NULL,
    backend_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    final_prompt TEXT,
    negative_prompt TEXT,
    params TEXT NOT NULL,            -- JSON
    progress REAL DEFAULT 0,
    progress_text TEXT,
    error TEXT,
    comfy_prompt_id TEXT,
    output_file TEXT,
    thumb_file TEXT,
    duration_s REAL,
    elapsed_s REAL,
    parent_id TEXT,
    character_id TEXT,
    saved INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    images TEXT NOT NULL             -- JSON list of filenames in data/characters/<id>/
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,              -- image | video
    filename TEXT NOT NULL,
    original_name TEXT,
    width INTEGER,
    height INTEGER,
    duration_s REAL
);
"""


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.conn = c
    return c


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    for k in ("params", "images"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d


# ---------- generations ----------

def create_generation(**fields: Any) -> dict[str, Any]:
    now = time.time()
    gid = new_id()
    fields = {**fields, "id": gid, "created_at": now, "updated_at": now, "status": "queued"}
    fields["params"] = json.dumps(fields.get("params", {}))
    cols = ",".join(fields)
    qs = ",".join("?" for _ in fields)
    c = conn()
    c.execute(f"INSERT INTO generations ({cols}) VALUES ({qs})", list(fields.values()))
    c.commit()
    return get_generation(gid)  # type: ignore[return-value]


def update_generation(gid: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = time.time()
    if "params" in fields and not isinstance(fields["params"], str):
        fields["params"] = json.dumps(fields["params"])
    sets = ",".join(f"{k}=?" for k in fields)
    c = conn()
    c.execute(f"UPDATE generations SET {sets} WHERE id=?", [*fields.values(), gid])
    c.commit()


def get_generation(gid: str) -> dict[str, Any] | None:
    return row_to_dict(conn().execute("SELECT * FROM generations WHERE id=?", (gid,)).fetchone())


def list_generations(limit: int = 200, status: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM generations"
    args: list[Any] = []
    if status:
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    return [row_to_dict(r) for r in conn().execute(q, args).fetchall()]  # type: ignore[misc]


def delete_generation(gid: str) -> None:
    c = conn()
    c.execute("DELETE FROM generations WHERE id=?", (gid,))
    c.commit()


# ---------- characters ----------

def create_character(name: str, description: str, images: list[str], cid: str | None = None) -> dict[str, Any]:
    cid = cid or new_id()
    c = conn()
    c.execute(
        "INSERT INTO characters (id, created_at, name, description, images) VALUES (?,?,?,?,?)",
        (cid, time.time(), name, description, json.dumps(images)),
    )
    c.commit()
    return get_character(cid)  # type: ignore[return-value]


def update_character(cid: str, **fields: Any) -> None:
    if "images" in fields:
        fields["images"] = json.dumps(fields["images"])
    sets = ",".join(f"{k}=?" for k in fields)
    c = conn()
    c.execute(f"UPDATE characters SET {sets} WHERE id=?", [*fields.values(), cid])
    c.commit()


def get_character(cid: str) -> dict[str, Any] | None:
    return row_to_dict(conn().execute("SELECT * FROM characters WHERE id=?", (cid,)).fetchone())


def list_characters() -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in conn().execute("SELECT * FROM characters ORDER BY created_at DESC")]  # type: ignore[misc]


def delete_character(cid: str) -> None:
    c = conn()
    c.execute("DELETE FROM characters WHERE id=?", (cid,))
    c.commit()


# ---------- assets ----------

def create_asset(kind: str, filename: str, original_name: str, width: int | None, height: int | None,
                 duration_s: float | None) -> dict[str, Any]:
    aid = new_id()
    c = conn()
    c.execute(
        "INSERT INTO assets (id, created_at, kind, filename, original_name, width, height, duration_s) VALUES (?,?,?,?,?,?,?,?)",
        (aid, time.time(), kind, filename, original_name, width, height, duration_s),
    )
    c.commit()
    return get_asset(aid)  # type: ignore[return-value]


def get_asset(aid: str) -> dict[str, Any] | None:
    return row_to_dict(conn().execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone())


def list_assets(kind: str | None = None) -> list[dict[str, Any]]:
    if kind:
        rows = conn().execute("SELECT * FROM assets WHERE kind=? ORDER BY created_at DESC", (kind,))
    else:
        rows = conn().execute("SELECT * FROM assets ORDER BY created_at DESC")
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]


def delete_asset(aid: str) -> None:
    c = conn()
    c.execute("DELETE FROM assets WHERE id=?", (aid,))
    c.commit()
