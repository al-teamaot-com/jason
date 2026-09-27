#!/usr/bin/env python3
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import time

STATE = Path(os.getenv("JASON_GRAFANA_ASSURANCE_STATE", "/var/lib/jason/observability/grafana-assurance.json"))
HOST = os.getenv("JASON_GRAFANA_ASSURANCE_HOST", "0.0.0.0")
PORT = int(os.getenv("JASON_GRAFANA_ASSURANCE_PORT", "9473"))


def esc(value: object) -> str:
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def render() -> str:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        status = str(data.get("status", "NOT_PROVEN"))
        summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
        ts = STATE.stat().st_mtime
        revision = str(data.get("source_revision", "unknown"))
    except Exception:
        status, summary, ts, revision = "NOT_PROVEN", {}, 0.0, "unknown"
    lines = [
        "# HELP jason_grafana_configuration_assurance Whether Grafana configuration assurance currently passes.",
        "# TYPE jason_grafana_configuration_assurance gauge",
        f"jason_grafana_configuration_assurance {1 if status == 'PASS' else 0}",
        "# HELP jason_grafana_configuration_drift Whether deterministic Grafana configuration drift is present.",
        "# TYPE jason_grafana_configuration_drift gauge",
        f"jason_grafana_configuration_drift {1 if status == 'DRIFTED' else 0}",
        "# HELP jason_grafana_configuration_not_proven Whether Grafana assurance lacks sufficient evidence.",
        "# TYPE jason_grafana_configuration_not_proven gauge",
        f"jason_grafana_configuration_not_proven {1 if status == 'NOT_PROVEN' else 0}",
        "# HELP jason_grafana_assurance_timestamp_seconds Timestamp of the latest Grafana assurance report.",
        "# TYPE jason_grafana_assurance_timestamp_seconds gauge",
        f"jason_grafana_assurance_timestamp_seconds {ts:.0f}",
        "# HELP jason_grafana_required_dashboards Number of repository-declared required Grafana dashboards.",
        "# TYPE jason_grafana_required_dashboards gauge",
        f"jason_grafana_required_dashboards {int(summary.get('required_dashboards', 0) or 0)}",
        "# HELP jason_grafana_dashboard_inventory_pass Number of required dashboards verified through Grafana API.",
        "# TYPE jason_grafana_dashboard_inventory_pass gauge",
        f"jason_grafana_dashboard_inventory_pass {int(summary.get('grafana_dashboards_pass', 0) or 0)}",
        "# HELP jason_grafana_dashboard_source_files_pass Number of required dashboard source files matching declared hashes.",
        "# TYPE jason_grafana_dashboard_source_files_pass gauge",
        f"jason_grafana_dashboard_source_files_pass {int(summary.get('source_files_pass', 0) or 0)}",
        "# HELP jason_grafana_metric_dependencies_pass Number of declared dashboard metric dependencies currently satisfied.",
        "# TYPE jason_grafana_metric_dependencies_pass gauge",
        f"jason_grafana_metric_dependencies_pass {int(summary.get('metric_dependencies_pass', 0) or 0)}",
        "# HELP jason_observability_release_info Immutable observability release currently checked.",
        "# TYPE jason_observability_release_info gauge",
        f'jason_observability_release_info{{source_revision="{esc(revision)}"}} 1',
    ]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            body = render().encode()
            self.send_response(200); self.send_header("Content-Type", "text/plain; version=0.0.4"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/health":
            body = b"ok\n"; self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *_args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
