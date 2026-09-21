#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SUPPORT = Path(os.environ.get("JASON_SUPPORT_LIST_PATH", "/var/lib/jason/openclaw/work-items/SUPPORT.md"))
TODO = Path(os.environ.get("JASON_TODO_LIST_PATH", "/var/lib/jason/openclaw/work-items/TODO.md"))
HOST = os.environ.get("JASON_WORK_ITEM_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_WORK_ITEM_EXPORTER_PORT", "9479"))


def esc(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def support_items() -> list[dict[str, str]]:
    if not SUPPORT.exists():
        return []
    out = []
    for line in SUPPORT.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| SUPPORT-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        out.append({"id": cells[0], "priority": cells[1], "status": cells[2], "title": cells[3]})
    return out


def todo_items() -> list[dict[str, str]]:
    if not TODO.exists():
        return []
    out = []
    current: dict[str, str] | None = None
    for line in TODO.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^###\s+(TODO-[^\s]+)\s+—\s+(.+)$", line.strip())
        if match:
            if current:
                out.append(current)
            current = {"id": match.group(1), "title": match.group(2), "priority": "", "status": ""}
            continue
        if current is None:
            continue
        if line.startswith("- **Priority:**"):
            current["priority"] = line.split("**Priority:**", 1)[1].strip()
        elif line.startswith("- **Status:**"):
            current["status"] = line.split("**Status:**", 1)[1].strip()
    if current:
        out.append(current)
    return out


def render_metrics() -> str:
    support = support_items()
    todo = todo_items()
    lines = [
        "# HELP jason_work_items_total Project Jason Support and TODO work items.",
        "# TYPE jason_work_items_total gauge",
        f'jason_work_items_total{{list="support"}} {len(support)}',
        f'jason_work_items_total{{list="todo"}} {len(todo)}',
        "# HELP jason_work_item_info Secret-safe work item metadata.",
        "# TYPE jason_work_item_info gauge",
    ]
    for list_name, rows in (("support", support), ("todo", todo)):
        for row in rows:
            labels = {
                "list": list_name,
                "item_id": row.get("id", ""),
                "priority": row.get("priority", ""),
                "status": row.get("status", ""),
                "title": row.get("title", ""),
            }
            lines.append(
                "jason_work_item_info{"
                + ",".join(f'{key}="{esc(value)}"' for key, value in labels.items())
                + "} 1"
            )
    lines.extend([
        "# HELP jason_work_item_exporter_build_info Work item exporter metadata.",
        "# TYPE jason_work_item_exporter_build_info gauge",
        'jason_work_item_exporter_build_info{version="1"} 1',
    ])
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/metrics"):
            self.send_response(404)
            self.end_headers()
            return
        body = render_metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    HTTPServer((HOST, PORT), Handler).serve_forever()
