#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(os.environ.get("JASON_REPO_ROOT", Path(__file__).resolve().parents[2]))
REGISTRY_PATH = Path(os.environ.get("JASON_PROMPT_REGISTRY_PATH", REPO_ROOT / "implementation" / "orchestrator" / "prompt_registry.json"))
HOST = os.environ.get("JASON_PROMPT_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_PROMPT_EXPORTER_PORT", "9471"))


def _escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _load_registry(path: Path | None = None) -> dict:
    selected = path or REGISTRY_PATH
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"prompts": []}
    return payload if isinstance(payload, dict) else {"prompts": []}


def _eval_prompt_text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _eval_prompt_text(node.left) + _eval_prompt_text(node.right)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "strip"
        and not node.args
        and not node.keywords
    ):
        return _eval_prompt_text(node.func.value).strip()
    raise ValueError("prompt expression is not a supported static string")


def _source_prompt_text(source_path: str, symbol: str) -> str | None:
    path = REPO_ROOT / source_path
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if symbol in names:
                try:
                    return _eval_prompt_text(node.value)
                except ValueError:
                    return None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == symbol:
            try:
                return _eval_prompt_text(node.value)
            except ValueError:
                return None
    return None


def _hash_matches(item: dict) -> int:
    content = _source_prompt_text(str(item.get("source_path", "")), str(item.get("source_symbol", "")))
    if content is None:
        return 0
    observed = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return 1 if observed == str(item.get("content_sha256", "")) else 0


def render_metrics(*, registry_path: Path | None = None) -> str:
    registry = _load_registry(registry_path)
    prompts = [item for item in registry.get("prompts", []) if isinstance(item, dict)]
    lines = [
        "# HELP jason_ai_prompt_registry_entries Number of registered material AI prompts.",
        "# TYPE jason_ai_prompt_registry_entries gauge",
        f"jason_ai_prompt_registry_entries {len(prompts)}",
        "# HELP jason_ai_prompt_info Secret-safe metadata for registered material AI prompts. Prompt content is never exported.",
        "# TYPE jason_ai_prompt_info gauge",
        "# HELP jason_ai_prompt_source_hash_match Whether registered prompt content hash matches current source text.",
        "# TYPE jason_ai_prompt_source_hash_match gauge",
        "# HELP jason_ai_prompt_invocation_telemetry_available Whether per-prompt runtime invocation telemetry is currently instrumented.",
        "# TYPE jason_ai_prompt_invocation_telemetry_available gauge",
    ]
    telemetry_available = 1
    for item in prompts:
        prompt_id = str(item.get("prompt_id", "unknown"))
        hash_value = str(item.get("content_sha256", ""))
        labels = {
            "prompt_id": prompt_id,
            "name": str(item.get("name", "")),
            "version": str(item.get("version", "")),
            "lifecycle": str(item.get("lifecycle", "unknown")),
            "surface": str(item.get("surface", "unknown")),
            "model_profile": str(item.get("model_profile", "unknown")),
            "risk": str(item.get("risk", "unknown")),
            "structured_output": "true" if item.get("structured_output") is True else "false",
            "tool_access": "true" if item.get("tool_access") is True else "false",
            "source_path": str(item.get("source_path", "")),
            "source_symbol": str(item.get("source_symbol", "")),
            "content_hash": hash_value[:12],
            "owner": str(item.get("owner", "")),
        }
        label_text = ",".join(f'{key}="{_escape(value)}"' for key, value in labels.items())
        lines.append(f"jason_ai_prompt_info{{{label_text}}} 1")
        lines.append(f'jason_ai_prompt_source_hash_match{{prompt_id="{_escape(prompt_id)}"}} {_hash_matches(item)}')
        if str(item.get("invocation_telemetry", "")) != "instrumented":
            telemetry_available = 0
    lines.append(f"jason_ai_prompt_invocation_telemetry_available {telemetry_available}")
    lines.extend([
        "# HELP jason_ai_prompt_exporter_build_info Jason AI prompt registry exporter metadata.",
        "# TYPE jason_ai_prompt_exporter_build_info gauge",
        'jason_ai_prompt_exporter_build_info{version="1"} 1',
    ])
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/metrics"):
            self.send_response(404); self.end_headers(); return
        payload = render_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers(); self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    HTTPServer((HOST, PORT), Handler).serve_forever()
