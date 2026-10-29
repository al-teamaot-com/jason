"""Compose the read-only Windows time-source shadow maintenance service."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

from autonomous_remediation.autonomous_principal import AutonomousPrincipal, AutonomousRequestFactory
from autonomous_remediation.playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore

from autonomous_remediation.playbook_document import validate_playbook_document

from .autonomy_shadow_runtime import GovernedAutonomyReadPort
from .windows_time_json_shadow_evidence import (
    SQLiteWindowsTimeJsonShadowState,
    WindowsTimeJsonShadowEvidence,
)
from .windows_time_source_shadow import (
    SQLiteWindowsTimeSourceShadowState,
    WindowsTimeSourceShadowMaintenance,
)


def build_windows_time_json_shadow_observer(
    *,
    reads: GovernedAutonomyReadPort,
    document_path: Path,
    state_db: Path,
):
    """Load an exact disabled candidate into an isolated local shadow state.

    The document resides in immutable container-image source, not an
    interactive staging store. An invalid, unexpected or executable document
    blocks opt-in startup; it cannot downgrade to an arbitrary JSON version.
    """
    path = Path(document_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    document = validate_playbook_document(payload, known_capabilities=set())
    if document.playbook_id != "windows_time_source" or document.version != "0.1.0-jsonpreview":
        raise ValueError("JSON_TIME_SHADOW_EXACT_VERSION_REQUIRED")
    observer = WindowsTimeJsonShadowEvidence(reads=reads, document=document)
    state = SQLiteWindowsTimeJsonShadowState(Path(state_db))
    return observer, state


def build_windows_time_source_shadow_maintenance(
    *,
    enabled: bool,
    identity_authority,
    capabilities,
    approvals,
    execution_ledger,
    orchestrator,
    state_db: Path,
    promotion_db: Path,
    cadence_minutes: int = 15,
    json_shadow_enabled: bool = False,
    json_document_path: Path | None = None,
    json_state_db: Path | None = None,
    json_shadow_allowed_site_uids: frozenset[str] = frozenset(),
    json_shadow_max_alerts_per_tick: int = 25,
    audit=None,
):
    if not enabled:
        if json_shadow_enabled:
            raise ValueError("JSON shadow requires existing Windows Time shadow")
        return None

    promotion_store = SQLitePlaybookAutonomyApprovalStore(promotion_db)
    request_factory = AutonomousRequestFactory(
        principal=AutonomousPrincipal(),
        authority=identity_authority,
        capabilities=capabilities,
        approvals=approvals,
        execution_ledger=execution_ledger,
        promotion_store=promotion_store,
    )
    reads = GovernedAutonomyReadPort(
        request_factory=request_factory,
        orchestrator=orchestrator,
        policy_id="windows-time-source-shadow-read-v1",
    )
    json_shadow = None
    json_shadow_state = None
    if json_shadow_enabled:
        if json_document_path is None or json_state_db is None:
            raise ValueError("JSON_TIME_SHADOW_EXACT_PATHS_REQUIRED")
        json_shadow, json_shadow_state = build_windows_time_json_shadow_observer(
            reads=reads,
            document_path=Path(json_document_path),
            state_db=Path(json_state_db),
        )
    return WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=SQLiteWindowsTimeSourceShadowState(state_db),
        cadence=timedelta(minutes=int(cadence_minutes)),
        audit=audit,
        json_shadow=json_shadow,
        json_shadow_state=json_shadow_state,
        json_shadow_allowed_site_uids=json_shadow_allowed_site_uids,
        json_shadow_max_alerts_per_tick=json_shadow_max_alerts_per_tick,
    )
