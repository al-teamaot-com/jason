#!/usr/bin/env python3
"""One-way bounded CCC config migration, after exact-sha owner review."""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

LEGACY_SOURCE = "/home/al/projects/jason"
MANAGED_SOURCE = "/home/al/.local/lib/jason/engineering-worker-source"


def migrate_legacy_source(path: Path) -> bool:
    """Preserve nondefault operator sources; reject symlinks and unsafe modes."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode) != 0o600:
            raise PermissionError("CCC configuration is not a private regular file")
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as handle:
            document = json.load(handle)
        if not isinstance(document, dict):
            raise ValueError("CCC configuration must be an object")
        if document.get("repository_root") != LEGACY_SOURCE:
            return False
        document["repository_root"] = MANAGED_SOURCE
        encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
        temp_fd, temp_path = tempfile.mkstemp(prefix=".ccc-source-", dir=path.parent)
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
                os.fchown(handle.fileno(), meta.st_uid, meta.st_gid)
                os.fchmod(handle.fileno(), 0o600)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        return True
    finally:
        os.close(fd)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    updated = migrate_legacy_source(args.config)
    print("CCC_SOURCE_CONFIG_MIGRATION=" + ("MIGRATED" if updated else "UNCHANGED"))
