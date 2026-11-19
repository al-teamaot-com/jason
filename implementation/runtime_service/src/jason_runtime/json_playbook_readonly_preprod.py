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


def build_json_readonly_preprod_pilot(
    *,
    enabled: bool,
    isolated_root: Path,
    client_id: str,
    request_factory,
    orchestrator,
    clock,
):
    """Construct a read-only pilot from a separately staged preprod draft.

    No runtime auto-discovery, production configuration, or provider execution
    occurs during construction. A caller must explicitly pass a private
    isolated_root that already contains the staged pilot registry. Production
    registry sharing or active playbook loading is rejected.
    """
    if not enabled:
        return None
    root = Path(isolated_root)
    if (not root.is_absolute() or root.is_symlink() or
            not root.is_dir() or root.parent.is_symlink() or
            not str(client_id).strip()):
        raise JsonShadowBoundaryError("PREPROD_ROOT_OR_CLIENT_NOT_VERIFIED")
    # Explicit opt-in path cannot be the protected deployed JSON registry.
    # All paths are constructed within this directory; neither caller nor
    # playbook JSON can choose a provider or production registry address.
    file = root / "isolated-json-playbooks.sqlite3"
    if not file.is_file() or file.is_symlink():
        raise JsonShadowBoundaryError("ISOLATED_PREPROD_REGISTRY_MISSING")
    registry = SQLitePlaybookRegistry(file, read_only=True)
    try:
        stored = registry.get(PILOT_ID, PILOT_VERSION)
        if stored.state != "draft":
            raise JsonShadowBoundaryError("PREPROD_PILOT_MUST_REMAIN_DRAFT")
        doc = stored.document
        if doc.fingerprint != PILOT_FINGERPRINT:
            raise JsonShadowBoundaryError("PREPROD_PILOT_FINGERPRINT_CHANGED")
        if doc.autonomy_activation != "shadow" or (
            doc.payload.get("scope", {}).get("direct_provider_access") is not False
        ):
            raise JsonShadowBoundaryError("PREPROD_PILOT_BOUNDARY_CHANGED")
        if set(doc.capabilities) != PILOT_READS:
            raise JsonShadowBoundaryError("PREPROD_PILOT_READ_SCOPE_CHANGED")
        if registry.active(PILOT_ID) is not None:
            raise JsonShadowBoundaryError("PREPROD_REGISTRY_HAS_ACTIVE_PILOT")
    finally:
        registry.close()
    # A separately governed service identity supplies current Observe
    # authorization for each read. No session/user identity impersonation.
    reads = GovernedAutonomyReadPort(
        request_factory=request_factory,
        orchestrator=orchestrator,
        client_id=str(client_id),
        policy_id="json-migration-readonly-preprod-v1",
    )
    state = SQLiteJsonShadowState(root / "isolated-json-shadow-state.sqlite3")
    return GovernedJsonShadowIntegration(
        document=doc, state=state,
        read_port=reads, read_capabilities=PILOT_READS,
        normalize=lambda capability, result, facts: reduce_daily_drmm_alert(
            capability, result, facts, at=clock()),
        clock=clock,
    )
