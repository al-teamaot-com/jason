"""Fail-closed autonomy gate for Jason playbooks."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AutonomyGateResult:
    allowed: bool
    reason: str


def source_sha256(path: Path | str) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def evaluate_autonomous_playbook(
    registry: Mapping[str, Any],
    *,
    playbook_id: str,
    playbook_version: str,
    source_hash: str,
    capability: str,
    target_count: int = 1,
) -> AutonomyGateResult:
    """Authorize standing autonomy only when every explicit gate matches."""
    global_policy = registry.get("autonomy")
    if not isinstance(global_policy, Mapping):
        return AutonomyGateResult(False, "global_autonomy_policy_missing")
    if global_policy.get("global_enabled") is not True:
        return AutonomyGateResult(False, "global_autonomy_disabled")
    if str(global_policy.get("default", "deny")) != "deny":
        return AutonomyGateResult(False, "global_default_must_deny")

    entries = registry.get("playbooks")
    if not isinstance(entries, list):
        return AutonomyGateResult(False, "playbook_registry_invalid")
    playbook = next((x for x in entries if isinstance(x, Mapping) and x.get("id") == playbook_id), None)
    if playbook is None:
        return AutonomyGateResult(False, "playbook_not_registered")
    if playbook.get("enabled") is not True:
        return AutonomyGateResult(False, "playbook_disabled")
    if str(playbook.get("version", "")) != playbook_version:
        return AutonomyGateResult(False, "playbook_version_mismatch")

    policy = playbook.get("autonomy")
    if not isinstance(policy, Mapping):
        return AutonomyGateResult(False, "playbook_autonomy_policy_missing")
    if policy.get("mode") != "approved_autonomous":
        return AutonomyGateResult(False, "playbook_not_approved_autonomous")
    if policy.get("approval_status") != "approved":
        return AutonomyGateResult(False, "playbook_autonomy_not_approved")
    if policy.get("approved_version") != playbook_version:
        return AutonomyGateResult(False, "approved_version_mismatch")
    if not source_hash or policy.get("approved_source_sha256") != source_hash:
        return AutonomyGateResult(False, "approved_source_hash_mismatch")
    if not str(policy.get("approved_by") or "").strip():
        return AutonomyGateResult(False, "autonomy_approver_missing")
    if not str(policy.get("approved_at") or "").strip():
        return AutonomyGateResult(False, "autonomy_approval_time_missing")

    allowed_capabilities = policy.get("allowed_capabilities")
    if not isinstance(allowed_capabilities, list) or capability not in allowed_capabilities:
        return AutonomyGateResult(False, "capability_not_in_playbook_autonomy_scope")
    maximum_targets = policy.get("maximum_targets", 0)
    if not isinstance(maximum_targets, int) or maximum_targets < 1:
        return AutonomyGateResult(False, "invalid_maximum_targets")
    if target_count < 1 or target_count > maximum_targets:
        return AutonomyGateResult(False, "target_count_exceeds_playbook_scope")

    return AutonomyGateResult(True, "approved_autonomous_playbook")
