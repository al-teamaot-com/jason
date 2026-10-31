from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import PMV2Store


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_snapshot(*, store: PMV2Store, destination: Path,
                    config_path: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    db_target = destination / "pm-v2.sqlite3"
    config_target = destination / "pm-v2-config.json"

    with store.connect() as source:
        target = sqlite3.connect(db_target)
        try:
            source.backup(target)
        finally:
            target.close()
    os.chmod(db_target, 0o600)

    config_bytes = config_path.read_bytes()
    config_target.write_bytes(config_bytes)
    os.chmod(config_target, 0o600)

    manifest = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": {
            "name": db_target.name,
            "sha256": _sha256(db_target),
            "size": db_target.stat().st_size,
        },
        "config": {
            "name": config_target.name,
            "sha256": _sha256(config_target),
            "size": config_target.stat().st_size,
        },
    }
    path = destination / "manifest.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)
    return manifest


def verify_snapshot(snapshot_dir: Path) -> dict[str, Any]:
    manifest_path = snapshot_dir / "manifest.json"
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ValueError("unsupported PM V2 snapshot manifest")
    for key in ("database", "config"):
        item = value.get(key)
        if not isinstance(item, dict):
            raise ValueError(f"snapshot {key} entry missing")
        path = snapshot_dir / str(item.get("name") or "")
        if not path.is_file():
            raise ValueError(f"snapshot {key} file missing")
        if _sha256(path) != item.get("sha256") or path.stat().st_size != item.get("size"):
            raise ValueError(f"snapshot {key} integrity mismatch")
    db = snapshot_dir / value["database"]["name"]
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("snapshot SQLite integrity check failed")
    finally:
        conn.close()
    return value


def restore_snapshot(*, snapshot_dir: Path, database_path: Path,
                     config_destination: Path) -> dict[str, Any]:
    manifest = verify_snapshot(snapshot_dir)
    database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    sources = (
        (snapshot_dir / manifest["database"]["name"], database_path),
        (snapshot_dir / manifest["config"]["name"], config_destination),
    )
    for source, target in sources:
        fd, name = tempfile.mkstemp(prefix=".pm-v2-restore-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(source.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(name, 0o600)
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return manifest
