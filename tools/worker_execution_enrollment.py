"""Release-managed, fail-closed diagnostic enrollment for Jason workers.

This DOES NOT grant autonomous shell or activate a worker role.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Callable

ENV_NAME = "JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID"
LINUX_SHELL_UID = "bc7c4531-6869-4658-b1d6-7639a477045e"
UID_PATTERN = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


class WorkerEnrollmentError(ValueError):
    pass


def approved_diagnostic_uid(repo: Path) -> str:
    """Return the exact UID only for a reviewed, versioned diagnostic binding."""
    path = repo / "config" / "worker-execution-enrollment.json"
    if not path.exists():
        return ""
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise WorkerEnrollmentError("enrollment policy must be an object")
    allowed = {
        "schema_version", "status", "role_id", "target_name",
        "device_uid", "device_class", "component_uid", "approval_mode",
        "issue_number", "authorization", "limitations",
    }
    if set(policy) != allowed:
        raise WorkerEnrollmentError("enrollment policy has missing or unknown keys")
    if (policy["schema_version"] != "1.0"
            or policy["status"] != "approved_diagnostic_transport_only"
            or policy["role_id"] != "jason-development-worker"
            or policy["device_class"] != "Server"
            or policy["component_uid"] != LINUX_SHELL_UID
            or policy["approval_mode"] != "per_run"
            or policy["issue_number"] != 1459):
        raise WorkerEnrollmentError("enrollment authority/scope mismatch")
    uid = str(policy["device_uid"])
    if not UID_PATTERN.fullmatch(uid):
        raise WorkerEnrollmentError("invalid exact Datto device identity")
    manifest = json.loads(
        (repo / "config" / "worker-roles" / "jason-development-worker-v1.json").read_text(encoding="utf-8")
    )
    acceptance = manifest.get("acceptance") or {}
    if (manifest.get("role_id") != policy["role_id"]
            or manifest.get("lifecycle") != "approved_for_engineering_not_activated"
            or acceptance.get("first_target") != policy["target_name"]
            or acceptance.get("datto_uid") != uid
            or acceptance.get("status") != "pending"
            or acceptance.get("excluded_production_host") == policy["target_name"]):
        raise WorkerEnrollmentError("enrollment does not match pending worker-role contract")
    return uid


def live_diagnostic_uid(output: Callable[[list[str]], str]) -> str:
    """Read both Docker planes; reject missing, duplicate, or divergent scope."""
    values = []
    present = []
    for container in ("jason-runtime", "jason-mcp-pilot"):
        entries = json.loads(output([
            "docker", "inspect", container, "--format", "{{json .Config.Env}}",
        ]))
        if not isinstance(entries, list):
            raise WorkerEnrollmentError("container environment invalid")
        matching = [value.partition("=")[2] for value in entries
                    if isinstance(value, str) and value.startswith(ENV_NAME + "=")]
        if len(matching) > 1:
            raise WorkerEnrollmentError("worker enrollment environment missing or duplicated")
        values.append(matching[0] if matching else "")
        present.append(bool(matching))
    # The pre-enrollment runtime image may omit the field entirely while
    # MCP explicitly records an empty value. Both mean *no* enrollment.
    # Require at least one explicit empty value so a missing integration in
    # both planes cannot silently masquerade as a valid disabled policy.
    if not any(present):
        raise WorkerEnrollmentError("worker enrollment environment missing or duplicated")
    if values[0] != values[1]:
        if not all(present):
            raise WorkerEnrollmentError("worker enrollment environment missing or duplicated")
        raise WorkerEnrollmentError("MCP/runtime worker enrollment differs")
    return values[0]
