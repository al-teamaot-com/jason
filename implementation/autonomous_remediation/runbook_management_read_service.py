"""Independently supervised, read-only Stage D runbook snapshot service.

Uses the ONE existing SQLite registry. No provider client, execution worker,
new signer, approval policy or mutable configuration endpoint exists here.
The already authenticated MCP control plane remains responsible for approved
stage/activate/retire operations until the governed write handoff is released.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import struct
from typing import Any

from .playbook_store import SQLitePlaybookRegistry

_MAX_REQUEST = 1024
_MAX_RESPONSE = 1_000_000


class RunbookReadServiceDenied(RuntimeError):
    pass


def snapshot(registry_path: Path, *, include_documents: bool = False) -> dict[str, Any]:
    """Read a coherent, validated registry snapshot without schema migration."""
    store = SQLitePlaybookRegistry(registry_path, read_only=True)
    try:
        generation, active = store.audited_read_only_snapshot()
        rows = []
        for item in active:
            doc = item.document
            row = {
                "playbook_id": doc.playbook_id,
                "version": doc.version,
                "fingerprint": doc.fingerprint,
                "capabilities": list(doc.capabilities),
                "activation": doc.autonomy_activation,
            }
            if include_documents:
                row["definition"] = json.loads(doc.canonical_json)
            rows.append(row)
        result = {
            "status": "healthy",
            "schema_version": 1,
            "registry_generation": generation,
            "active_count": len(rows),
            "active": rows,
            "provider_calls": False,
            "execution_authority": False,
            "configuration_mutations": False,
        }
        if len(json.dumps(result, separators=(",", ":")).encode()) > _MAX_RESPONSE:
            raise RunbookReadServiceDenied("RUNBOOK_SNAPSHOT_RESPONSE_TOO_LARGE")
        return result
    finally:
        store.close()


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        # Only the existing Jason service UID may inspect configs locally.
        raw = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _, peer_uid, _ = struct.unpack("3i", raw)
        if peer_uid != os.geteuid():
            return
        try:
            line = self.rfile.readline(_MAX_REQUEST + 1)
            if not line or len(line) > _MAX_REQUEST or not line.endswith(b"\n"):
                raise RunbookReadServiceDenied("RUNBOOK_READ_REQUEST_INVALID")
            request = json.loads(line)
            if not isinstance(request, dict) or set(request) != {"operation"}:
                raise RunbookReadServiceDenied("RUNBOOK_READ_REQUEST_INVALID")
            operation = request["operation"]
            if operation not in ("status", "snapshot"):
                raise RunbookReadServiceDenied("RUNBOOK_READ_ONLY_OPERATION_REQUIRED")
            answer = snapshot(self.server.registry_path,
                              include_documents=operation == "snapshot")
        except (ValueError, KeyError, RuntimeError, OSError, TypeError) as exc:
            answer = {"status": "rejected", "error_code": str(exc)[:160]}
        self.wfile.write(json.dumps(answer, sort_keys=True).encode() + b"\n")


class _Server(socketserver.UnixStreamServer):
    allow_reuse_address = False
    def __init__(self, path: Path, registry_path: Path):
        directory = path.parent
        try:
            meta = directory.lstat()
        except OSError as exc:
            raise RunbookReadServiceDenied("RUNBOOK_SOCKET_DIRECTORY_UNAVAILABLE") from exc
        if (path.exists() or path.is_symlink() or directory.is_symlink()
            or not stat.S_ISDIR(meta.st_mode) or meta.st_uid != os.geteuid()
            or stat.S_IMODE(meta.st_mode) != 0o700):
            raise RunbookReadServiceDenied("RUNBOOK_SOCKET_DIRECTORY_UNTRUSTED")
        self.registry_path = registry_path
        old_mask = os.umask(0o077)
        try:
            super().__init__(str(path), _Handler)
        finally:
            os.umask(old_mask)
        os.chmod(path, 0o600)
        self._socket_inode = path.stat().st_ino
        self._socket_path = path

    def server_close(self) -> None:
        super().server_close()
        try:
            meta = self._socket_path.lstat()
            if stat.S_ISSOCK(meta.st_mode) and meta.st_ino == self._socket_inode:
                self._socket_path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage D read-only runbook service")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--socket", type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    # Always fail closed on unusable or untrusted registry, before socket bind.
    if args.once:
        print(json.dumps(snapshot(args.registry), sort_keys=True))
        return 0
    if args.socket is None or not args.socket.is_absolute():
        raise RunbookReadServiceDenied("RUNBOOK_SOCKET_ABSOLUTE_PATH_REQUIRED")
    # Keep a read-only connection without an open transaction so writers
    # cannot remove the live WAL sidecars. Requests still take fresh snapshots.
    anchor = SQLitePlaybookRegistry(args.registry, read_only=True)
    try:
        anchor.audited_read_only_snapshot()
        status = snapshot(args.registry)
        with _Server(args.socket, args.registry) as server:
            print("RUNBOOK_MANAGEMENT_READ_SERVICE=READY generation="
                  + str(status["registry_generation"]), flush=True)
            server.serve_forever(poll_interval=0.2)
    finally:
        anchor.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
