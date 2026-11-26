"""Local workload admission for reviewed templates, never an approval endpoint."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import struct
import threading

MAXIMUM = 4096


def dispatch(app, message, *, peer_uid):
    if peer_uid != 1000 or not isinstance(message, dict):
        raise PermissionError("OBJECTIVE_LOCAL_WORKLOAD_REQUIRED")
    if message.get("operation") == "submit" and set(message) == {"operation", "template_id", "request_id"}:
        return app.submit_registered(template_id=message["template_id"], request_id=message["request_id"])
    if message.get("operation") == "status" and set(message) == {"operation", "request_id"}:
        return app.submission_status(request_id=message["request_id"])
    raise PermissionError("OBJECTIVE_REGISTERED_OPERATION_REQUIRED")


def start_issuer(app, path: Path):
    if os.geteuid() != 1000:
        raise PermissionError("OBJECTIVE_COMPONENT_UID_REQUIRED")
    parent = path.parent.lstat()
    if path.parent.is_symlink() or parent.st_uid != 1000 or stat.S_IMODE(parent.st_mode) != 0o700:
        raise PermissionError("OBJECTIVE_ISSUER_DIRECTORY_IDENTITY")
    if os.path.lexists(path):
        meta = path.lstat()
        if not stat.S_ISSOCK(meta.st_mode) or meta.st_uid != 1000 or stat.S_IMODE(meta.st_mode) != 0o600:
            raise PermissionError("OBJECTIVE_ISSUER_SOCKET_IDENTITY")
        # Never replace an active listener. Only a verified stale socket left
        # by this same component may be removed during container restart.
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.connect(str(path))
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise PermissionError("OBJECTIVE_ISSUER_ALREADY_RUNNING")

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(360)
            try:
                _, uid, _ = struct.unpack("3i", self.connection.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                raw = self.rfile.readline(MAXIMUM + 1)
                if not raw.endswith(b"\n") or len(raw) > MAXIMUM:
                    raise ValueError("bounded local request required")
                result = dispatch(app, json.loads(raw), peer_uid=uid)
                response = {"status": "accepted", "result": result}
            except Exception as exc:
                # No private record, exception message, token or signed callback
                # is reflected to this workload requester.
                response = {"status": "denied", "reason": type(exc).__name__}
            self.wfile.write(json.dumps(response, allow_nan=False).encode() + b"\n")

    server = socketserver.UnixStreamServer(str(path), Handler)
    path.chmod(0o600)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
