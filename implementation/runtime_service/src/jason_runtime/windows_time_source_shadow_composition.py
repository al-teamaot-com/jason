"""Compose the read-only Windows time-source shadow maintenance service."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from autonomous_remediation.autonomous_principal import AutonomousPrincipal, AutonomousRequestFactory
from autonomous_remediation.playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore

from .autonomy_shadow_runtime import GovernedAutonomyReadPort
from .windows_time_source_shadow import (
    SQLiteWindowsTimeSourceShadowState,
    WindowsTimeSourceShadowMaintenance,
)


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
    audit=None,
):
    if not enabled:
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
    return WindowsTimeSourceShadowMaintenance(
        reads=reads,
        state=SQLiteWindowsTimeSourceShadowState(state_db),
        cadence=timedelta(minutes=int(cadence_minutes)),
        audit=audit,
    )
