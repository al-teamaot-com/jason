from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .store import PMV2Store, utcnow


ALLOWED_ACTIONS = frozenset({"priority", "pause", "resume", "cancel"})


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".pm-v2-control-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def publish_status_snapshot(*, store: PMV2Store, path: Path) -> dict[str, Any]:
    assignments = store.list_assignments()
    components = store.component_snapshot()
    nodes = store.node_snapshot()
    payload = {
        "schema_version": "1.0",
        "generated_at": utcnow(),
        "summary": {
            "assignment_count": len(assignments),
            "runnable_count": sum(1 for row in assignments if row.runnable),
            "blocked_count": sum(
                1 for row in assignments
                if row.state in {"blocked", "validation_pending"}
            ),
            "running_count": sum(1 for row in assignments if row.state == "running"),
        },
        "assignments": [
            {
                "assignment_id": row.assignment_id,
                "title": row.title,
                "priority": row.priority,
                "state": row.state,
                "completion_percent": row.completion_percent,
                "blocked_reason": row.blocked_reason,
            }
            for row in assignments[:100]
        ],
        "components": components,
        "nodes": nodes,
    }
    _atomic_json(path, payload)
    return payload


def consume_control_requests(
    *,
    store: PMV2Store,
    inbox: Path,
    results: Path,
) -> dict[str, int]:
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    results.mkdir(parents=True, exist_ok=True, mode=0o700)
    applied = rejected = skipped = 0
    for path in sorted(inbox.glob("*.json"), key=lambda item: item.stat().st_mtime):
        result_path = results / path.name
        request: dict[str, Any] = {}
        if result_path.exists():
            skipped += 1
            continue
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(request, dict) or request.get("schema_version") != "1.0":
                raise ValueError("invalid PM V2 control request schema")
            request_id = str(request.get("request_id") or "").strip()
            principal = str(request.get("principal_id") or "").strip()
            organization = str(request.get("organization_id") or "").strip()
            assignment_id = str(request.get("assignment_id") or "").strip()
            action = str(request.get("action") or "").strip().casefold()
            source = str(request.get("source") or "")
            if (
                not request_id or not principal or not organization
                or not assignment_id or action not in ALLOWED_ACTIONS
            ):
                raise ValueError("PM V2 control request is incomplete")
            if source != "governed_runtime_authenticated_request":
                raise PermissionError("PM V2 control request source is not governed runtime")
            priority = request.get("priority")
            result = store.apply_owner_control(
                assignment_id=assignment_id,
                action=action,
                principal_id=principal,
                request_id=request_id,
                priority=priority,
            )
            payload = {
                "schema_version": "1.0",
                "request_id": request_id,
                "status": "applied",
                "result": result,
                "completed_at": utcnow(),
            }
            applied += 1
        except Exception as exc:
            payload = {
                "schema_version": "1.0",
                "request_id": str(
                    request.get("request_id") if isinstance(request, dict) else ""
                ),
                "status": "rejected",
                "error": f"{type(exc).__name__}:{str(exc)[:240]}",
                "completed_at": utcnow(),
            }
            rejected += 1
        _atomic_json(result_path, payload)
    return {"applied": applied, "rejected": rejected, "skipped": skipped}
