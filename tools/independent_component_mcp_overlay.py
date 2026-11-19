#!/usr/bin/env python3
"""Source-only, reproducible MCP endpoint overlay onto an exact deployed baseline.

This program DOES NOT modify a running container, host secrets, root policy,
production files, or Docker. An independently governed build must verify that
its base image ID matches BASE_IMAGE_ID before building this staged context.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

APPROVED_ENDPOINT_SOURCE_SHA = "675b99e73c33c228a8531c2797eb3db53c399ad8"
BASE_IMAGE_ID = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
BASE_SERVER_SHA256 = "a2d69adc40c9537046652fecd5c1bd111a8e6ac30f89829c9b0f11c637532d80"
BASE_IMAGE_TAG = "jason-mcp:base-pinned-b2f74bf15135"
IMPORT_ANCHOR = "from jason_mcp.release_approval_request import queue_release_approval_request\n"
NEW_IMPORT = "from jason_mcp.independent_component_release_approval import queue_component_release_approval\n"
ENDPOINT_ANCHOR = "\n@mcp.tool()\ndef authorize_pmv4_shadow_release("
ENDPOINT_START = "\n@mcp.tool()\ndef approve_independent_component_release("
MODULE_PATH = "implementation/mcp_service/src/jason_mcp/independent_component_release_approval.py"
SERVER_PATH = "implementation/mcp_service/src/jason_mcp/server.py"
ROOT = Path("/home/al/.local/share/jason")


class MCPOverlayDenied(PermissionError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(repo: Path, commit: str, path: str) -> bytes:
    if commit != APPROVED_ENDPOINT_SOURCE_SHA:
        raise MCPOverlayDenied("MCP_OVERLAY_SOURCE_SHA_NOT_REVIEWED")
    result = subprocess.run(
        ["git", "-C", str(repo), "show", commit + ":" + path],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise MCPOverlayDenied("MCP_OVERLAY_SOURCE_BLOB_MISSING")
    return result.stdout


def exact_patch(baseline: bytes, reviewed_server: bytes) -> bytes:
    if sha(baseline) != BASE_SERVER_SHA256:
        raise MCPOverlayDenied("MCP_OVERLAY_LIVE_SERVER_HASH_MISMATCH")
    old = baseline.decode("utf-8", errors="strict")
    new = reviewed_server.decode("utf-8", errors="strict")
    if (old.count(IMPORT_ANCHOR) != 1 or
        old.count(ENDPOINT_ANCHOR) != 1 or
        NEW_IMPORT in old or
        ENDPOINT_START in old or
        new.count(NEW_IMPORT) != 1 or
        new.count(ENDPOINT_START) != 1 or
        new.count(ENDPOINT_ANCHOR) != 1):
        raise MCPOverlayDenied("MCP_OVERLAY_ANCHOR_CONFLICT")
    segment = new[new.index(ENDPOINT_START):new.index(ENDPOINT_ANCHOR, new.index(ENDPOINT_START))]
    if not segment.startswith(ENDPOINT_START) or "queue_component_release_approval(" not in segment:
        raise MCPOverlayDenied("MCP_OVERLAY_ENDPOINT_UNREVIEWED")
    result = old.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT)
    result = result.replace(ENDPOINT_ANCHOR, segment + ENDPOINT_ANCHOR)
    if (result.replace(IMPORT_ANCHOR + NEW_IMPORT, IMPORT_ANCHOR)
            .replace(segment + ENDPOINT_ANCHOR, ENDPOINT_ANCHOR) != old):
        raise MCPOverlayDenied("MCP_OVERLAY_UNRELATED_CODE_CHANGED")
    compile(result, "<reviewed-mcp-overlay>", "exec")
    return result.encode("utf-8")


def staged_files(repo: Path, baseline: Path) -> dict[str, bytes]:
    approved = git_blob(repo, APPROVED_ENDPOINT_SOURCE_SHA, SERVER_PATH)
    module = git_blob(repo, APPROVED_ENDPOINT_SOURCE_SHA, MODULE_PATH)
    patched = exact_patch(baseline.read_bytes(), approved)
    compile(module, "<approved-component-approval-module>", "exec")
    dockerfile = (
        "ARG BASE_IMAGE=" + BASE_IMAGE_TAG + "\n"
        "FROM ${BASE_IMAGE}\n"
        "USER root\n"
        "COPY server.py /usr/local/lib/python3.12/site-packages/jason_mcp/server.py\n"
        "COPY independent_component_release_approval.py /usr/local/lib/python3.12/site-packages/jason_mcp/independent_component_release_approval.py\n"
        "RUN chmod 0444 /usr/local/lib/python3.12/site-packages/jason_mcp/server.py /usr/local/lib/python3.12/site-packages/jason_mcp/independent_component_release_approval.py\n"
        "USER 1000:1000\n"
    ).encode()
    return {
        "server.py": patched,
        "independent_component_release_approval.py": module,
        "Dockerfile": dockerfile,
    }


def safe_destination(path: Path) -> Path:
    p = Path(path)
    if (not p.is_absolute() or p.is_symlink() or
        ".." in p.parts or p == ROOT or ROOT not in p.parents):
        raise MCPOverlayDenied("MCP_OVERLAY_DESTINATION_UNSAFE")
    if p.exists() and not p.is_dir():
        raise MCPOverlayDenied("MCP_OVERLAY_DESTINATION_UNSAFE")
    return p


def stage(repo: Path, baseline: Path, destination: Path, *, verify_only: bool) -> dict:
    destination = safe_destination(destination)
    if baseline.is_symlink() or not baseline.is_file():
        raise MCPOverlayDenied("MCP_OVERLAY_BASELINE_UNAVAILABLE")
    files = staged_files(repo, baseline)
    expected = {
        "schema_version": "1.0",
        "status": "source_only_not_deployed",
        "reviewed_source_sha": APPROVED_ENDPOINT_SOURCE_SHA,
        "base_image_id": BASE_IMAGE_ID,
        "base_server_sha256": BASE_SERVER_SHA256,
        "files": {name: sha(content) for name, content in sorted(files.items())},
        "production_mutations": False,
    }
    manifest = (json.dumps(expected, sort_keys=True, indent=2) + "\n").encode()
    files["source-overlay.json"] = manifest
    if not verify_only:
        destination.mkdir(mode=0o700, parents=False, exist_ok=True)
        if destination.stat().st_mode & 0o077:
            raise MCPOverlayDenied("MCP_OVERLAY_DESTINATION_PERMISSIONS")
        for name, data in files.items():
            p = destination / name
            if not p.exists():
                fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             getattr(os, "O_NOFOLLOW", 0), 0o400)
                with os.fdopen(fd, "wb") as out:
                    out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
    if not destination.is_dir() or {p.name for p in destination.iterdir()} != set(files):
        raise MCPOverlayDenied("MCP_OVERLAY_STAGING_INCOMPLETE")
    for name, data in files.items():
        p = destination / name
        if (p.is_symlink() or not p.is_file() or p.stat().st_mode & 0o077 or
                p.read_bytes() != data):
            raise MCPOverlayDenied("MCP_OVERLAY_STAGED_BYTES_DRIFTED")
    return {
        "status": "verified",
        "reviewed_source_sha": APPROVED_ENDPOINT_SOURCE_SHA,
        "base_image_id": BASE_IMAGE_ID,
        "base_server_sha256": BASE_SERVER_SHA256,
        "patched_server_sha256": sha(files["server.py"]),
        "overlay_manifest_sha256": sha(manifest),
        "destination": str(destination),
        "production_installed": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("prepare", "verify"))
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--baseline-server", type=Path, required=True)
    ap.add_argument("--destination", type=Path, required=True)
    args = ap.parse_args()
    try:
        print(json.dumps(stage(args.repo, args.baseline_server, args.destination,
                               verify_only=args.command == "verify"), sort_keys=True))
    except (MCPOverlayDenied, OSError, UnicodeError, ValueError) as exc:
        print("DENIED: " + str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
