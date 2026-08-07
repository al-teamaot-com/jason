#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(os.environ.get("JASON_REPO_ROOT", Path(__file__).resolve().parents[2]))
ROADMAP_PATH = REPO_ROOT / "07-Roadmap" / "Jason-Roadmap-Status.json"
HOST = os.environ.get("JASON_STATUS_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_STATUS_PORT", "9464"))


def _metric_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _tcp_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_running(container_name: str) -> bool:
    try:
        completed = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and completed.stdout.strip().lower() == "true"


def _roadmap() -> dict:
    if not ROADMAP_PATH.exists():
        return {"milestones": []}
    return json.loads(ROADMAP_PATH.read_text(encoding="utf-8"))


def render_metrics() -> str:
    roadmap = _roadmap()
    milestones = roadmap.get("milestones", [])
    status_counts: dict[str, int] = {}
    for item in milestones:
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    complete = status_counts.get("complete", 0)
    total = len(milestones)
    completion = (complete / total * 100.0) if total else 0.0

    lines = [
        "# HELP jason_roadmap_completion_percent Percentage of tracked Jason milestones complete.",
        "# TYPE jason_roadmap_completion_percent gauge",
        f"jason_roadmap_completion_percent {completion:.2f}",
        "# HELP jason_roadmap_milestones Count of Jason roadmap milestones by status.",
        "# TYPE jason_roadmap_milestones gauge",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f'jason_roadmap_milestones{{status="{_metric_escape(status)}"}} {count}')

    lines.extend([
        "# HELP jason_roadmap_item_info Jason roadmap milestone metadata.",
        "# TYPE jason_roadmap_item_info gauge",
    ])
    for item in milestones:
        labels = {
            "milestone": str(item.get("id", "unknown")),
            "title": str(item.get("title", "")),
            "status": str(item.get("status", "unknown")),
            "phase": str(item.get("phase", "")),
        }
        label_text = ",".join(f'{key}="{_metric_escape(value)}"' for key, value in labels.items())
        lines.append(f"jason_roadmap_item_info{{{label_text}}} 1")

    component_health = {
        "openbao": 1 if _docker_running("openbao") and _tcp_open("127.0.0.1", 8200) else 0,
        "openclaw_gateway": 1 if _docker_running("openclaw-openclaw-gateway-1") and _tcp_open("127.0.0.1", 3978) else 0,
        "local_llm": 1 if _tcp_open("127.0.0.1", 11434) else 0,
        "autotask_readonly": 1 if (REPO_ROOT / "implementation" / "connectors" / "autotask").exists() else 0,
    }
    lines.extend([
        "# HELP jason_component_health Jason component health or readiness indicator.",
        "# TYPE jason_component_health gauge",
    ])
    for component, health in component_health.items():
        lines.append(f'jason_component_health{{component="{component}"}} {health}')

    lines.extend([
        "# HELP jason_status_exporter_build_info Jason status exporter metadata.",
        "# TYPE jason_status_exporter_build_info gauge",
        'jason_status_exporter_build_info{version="1"} 1',
    ])
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
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Jason status exporter listening on {HOST}:{PORT}", flush=True)
    while True:
        server.handle_request()
        time.sleep(0)
