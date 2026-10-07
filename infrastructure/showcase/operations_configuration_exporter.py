#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SHOWCASE_DIR = Path(__file__).resolve().parent
if str(SHOWCASE_DIR) not in sys.path:
    sys.path.insert(0, str(SHOWCASE_DIR))

from operations_configuration_metrics import render_metrics as render_operations_metrics

HOST = os.environ.get("JASON_OPERATIONS_CONFIGURATION_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_OPERATIONS_CONFIGURATION_PORT", "9477"))
REPO_ROOT = Path(os.environ.get("JASON_REPO_ROOT", "/opt/jason/current"))
RELEASE_MANAGER_RECORDS_DIR = Path(
    os.environ.get(
        "JASON_RELEASE_MANAGER_RECORDS_DIR",
        "/var/lib/jason/openclaw/release-manager/records",
    )
)


def runtime_environment() -> dict[str, str]:
    """Return only explicitly allowlisted runtime configuration values."""
    try:
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                "jason-runtime",
                "--format",
                "{{json .Config.Env}}",
            ],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if completed.returncode != 0:
        return {}
    try:
        values = json.loads(completed.stdout)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(values, list):
        return {}
    allowed = {"JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS"}
    result: dict[str, str] = {}
    for raw in values:
        if not isinstance(raw, str) or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        if key in allowed:
            result[key] = value
    return result


def render_metrics() -> str:
    lines = render_operations_metrics(
        REPO_ROOT,
        RELEASE_MANAGER_RECORDS_DIR,
        runtime_environment(),
    )
    lines.extend(
        [
            "# HELP jason_operations_configuration_exporter_build_info Jason Control Panel operations/configuration exporter metadata.",
            "# TYPE jason_operations_configuration_exporter_build_info gauge",
            'jason_operations_configuration_exporter_build_info{version="1"} 1',
        ]
    )
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/metrics"):
            self.send_response(404)
            self.end_headers()
            return
        payload = render_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Jason operations/configuration exporter listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()
