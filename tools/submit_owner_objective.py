#!/usr/bin/env python3
"""Request/status a supported objective through the installed local issuer."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import stat
from uuid import uuid4

SOCKET = Path("/var/lib/jason/openclaw/owner-objective/issuer.sock")


def request(message, *, path=SOCKET):
    if os.geteuid() != 1000:
        raise PermissionError("Run as Jason's registered local workload user")
    parent, meta = path.parent.lstat(), path.lstat()
    if (path.parent.is_symlink() or parent.st_uid != 1000 or stat.S_IMODE(parent.st_mode) != 0o700
            or not stat.S_ISSOCK(meta.st_mode) or meta.st_uid != 1000
            or stat.S_IMODE(meta.st_mode) != 0o600):
        raise PermissionError("Installed objective issuer identity could not be verified")
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(360)
        connection.connect(str(path))
        connection.sendall(json.dumps(message, allow_nan=False).encode() + b"\n")
        with connection.makefile("rb") as stream:
            raw = stream.readline(4097)
    if len(raw) > 4096 or not raw.endswith(b"\n"):
        raise PermissionError("Bounded objective issuer response required")
    result = json.loads(raw)
    if result.get("status") != "accepted":
        raise PermissionError("Objective admission denied: " + str(result.get("reason", "unknown")))
    return result["result"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", choices=["documentation-publisher"], default="documentation-publisher")
    parser.add_argument("--request-id", help="Retain/reuse this 32-character ID for retries")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status and args.request_id is None:
        parser.error("--status requires --request-id")
    request_id = args.request_id or uuid4().hex
    if re.fullmatch(r"[0-9a-f]{32}", request_id) is None:
        parser.error("--request-id must contain exactly 32 lowercase hexadecimal characters")
    # Print before contacting the issuer: a transport loss never loses the retry ID.
    print("OBJECTIVE_REQUEST_ID=" + request_id, flush=True)
    message = {"operation": "status" if args.status else "submit", "request_id": request_id}
    if not args.status:
        message["template_id"] = args.template
    print(json.dumps(request(message), sort_keys=True))


if __name__ == "__main__":
    main()
