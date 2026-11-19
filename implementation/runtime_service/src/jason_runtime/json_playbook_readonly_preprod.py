"""Explicitly isolated PMv4 JSON read-only pilot composition.

This is an opt-in source-only constructor for preproduction. It does not join
the Ticket Core maintenance loop, load production JSON versions, install units,
execute provider writes, or provide a second runbook interpreter or registry.
The existing immutable JSON registry is opened mode=ro; the existing governed
Observe port handles identity/authority with Central Orchestrator.
"""
from __future__ import annotations

from pathlib import Path

from autonomous_remediation.json_shadow_facts import reduce_daily_drmm_alert
from autonomous_remediation.json_shadow_integration import (
    GovernedJsonShadowIntegration, SQLiteJsonShadowState,
    JsonShadowBoundaryError,
)
from autonomous_remediation.playbook_store import SQLitePlaybookRegistry

from .autonomy_shadow_runtime import GovernedAutonomyReadPort


PILOT_ID = "drmm_recent_alert_readonly_shadow_pilot"
PILOT_VERSION = "0.1.0"
PILOT_FINGERPRINT = "0b537a13c70339e35f3d49a73f9c02689aa472b2f6e5d095ba7fc64bf270ef06"
PILOT_READS = frozenset({
    "management.alert.search",
    "endpoint.device.read",
    "endpoint.security.status.read",
    "endpoint.security.detection.search",
})


def build_json_readonly_preprod_candidate(
    *,
    enabled: bool,
    isolated_root: Path,
    client_id: str,
    request_factory,
    orchestrator,
    clock,
    playbook_id: str,
    version: str,
    expected_fingerprint: str,
    allowed_read_capabilities: frozenset[str],
    normalize,
    state_file_name: str = "isolated-json-shadow-state.sqlite3",
):
    """Open one explicitly fingerprinted isolated draft via the existing registry.

    Unlike a production dispatcher this makes no scheduling or execution
    decision and cannot activate any version. The capability allowlist is
    supplied by reviewed source (not by JSON) and must match exactly.
    """
    if not enabled:
        return None
    root = Path(isolated_root)
    if (not root.is_absolute() or root.is_symlink() or
            not root.is_dir() or root.parent.is_symlink() or
            not str(client_id).strip()):
        raise JsonShadowBoundaryError("PREPROD_ROOT_OR_CLIENT_NOT_VERIFIED")
    if (not playbook_id or not version or
            not isinstance(expected_fingerprint, str) or
            len(expected_fingerprint) != 64 or
            not isinstance(allowed_read_capabilities, frozenset) or
            not allowed_read_capabilities or
            not all(isinstance(x, str) and x.strip()
                    for x in allowed_read_capabilities)):
        raise JsonShadowBoundaryError("PREPROD_EXACT_SOURCE_BINDING_REQUIRED")
    if (not state_file_name or
            not state_file_name.endswith(".sqlite3") or
            Path(state_file_name).name != state_file_name):
        raise JsonShadowBoundaryError("PREPROD_STATE_PATH_OUT_OF_SCOPE")
    file = root / "isolated-json-playbooks.sqlite3"
    if not file.is_file() or file.is_symlink():
        raise JsonShadowBoundaryError("ISOLATED_PREPROD_REGISTRY_MISSING")
    registry = SQLitePlaybookRegistry(file, read_only=True)
    try:
        stored = registry.get(playbook_id, version)
        if stored.state != "draft":
            raise JsonShadowBoundaryError("PREPROD_PILOT_MUST_REMAIN_DRAFT")
        doc = stored.document
        if doc.fingerprint != expected_fingerprint:
            raise JsonShadowBoundaryError("PREPROD_PILOT_FINGERPRINT_CHANGED")
        if doc.autonomy_activation != "shadow" or (
            doc.payload.get("scope", {}).get("direct_provider_access") is not False
        ):
            raise JsonShadowBoundaryError("PREPROD_PILOT_BOUNDARY_CHANGED")
        if set(doc.capabilities) != allowed_read_capabilities:
            raise JsonShadowBoundaryError("PREPROD_PILOT_READ_SCOPE_CHANGED")
        if any(
            step.get("type") not in {
                "diagnostic", "verification", "decision",
                "complete", "human_review", "escalate", "wait"
            } for step in doc.payload["steps"]
        ):
            raise JsonShadowBoundaryError("PREPROD_PILOT_MUTATION_STEP_FORBIDDEN")
        if registry.active_snapshot()[1]:
            raise JsonShadowBoundaryError("PREPROD_REGISTRY_ACTIVE_VERSION_FORBIDDEN")
    finally:
        registry.close()
    reads = GovernedAutonomyReadPort(
        request_factory=request_factory,
        orchestrator=orchestrator,
        client_id=str(client_id),
        policy_id="json-migration-readonly-preprod-v1",
    )
    state = SQLiteJsonShadowState(root / state_file_name)
    return GovernedJsonShadowIntegration(
        document=doc,
        state=state,
        read_port=reads,
        read_capabilities=allowed_read_capabilities,
        normalize=normalize,
        clock=clock,
    )


def build_json_readonly_preprod_pilot(
    *,
    enabled: bool,
    isolated_root: Path,
    client_id: str,
    request_factory,
    orchestrator,
    clock,
):
    """Backwards-compatible governed DRMM read-only pilot composition."""
    return build_json_readonly_preprod_candidate(
        enabled=enabled,
        isolated_root=isolated_root,
        client_id=client_id,
        request_factory=request_factory,
        orchestrator=orchestrator,
        clock=clock,
        playbook_id=PILOT_ID,
        version=PILOT_VERSION,
        expected_fingerprint=PILOT_FINGERPRINT,
        allowed_read_capabilities=PILOT_READS,
        normalize=lambda capability, result, facts: reduce_daily_drmm_alert(
            capability, result, facts, at=clock()),
    )
