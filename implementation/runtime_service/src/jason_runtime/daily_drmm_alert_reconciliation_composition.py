"""Compose the daily recent-DRMM-alert reconciliation maintenance service."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from autonomous_remediation.autonomous_principal import AutonomousPrincipal, AutonomousRequestFactory
from autonomous_remediation.playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore

from .autonomy_shadow_runtime import GovernedAutonomyReadPort
from .autonomy_worker_runtime import GovernedAutonomyActionPort
from .daily_drmm_alert_reconciliation import (
    DailyDrmmAlertReconciliationMaintenance,
    SQLiteDailyAlertReconciliationState,
)


def build_daily_drmm_alert_reconciliation_maintenance(
    *,
    enabled: bool,
    identity_authority,
    capabilities,
    approvals,
    execution_ledger,
    orchestrator,
    state_db: Path,
    promotion_db: Path,
    lookback_hours: int = 24,
    cadence_hours: int = 24,
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
        policy_id="drmm-recent-alert-reconciliation-read-v1",
    )
    actions = GovernedAutonomyActionPort(
        request_factory=request_factory,
        orchestrator=orchestrator,
        promotion_store=promotion_store,
    )
    return DailyDrmmAlertReconciliationMaintenance(
        reads=reads,
        actions=actions,
        state=SQLiteDailyAlertReconciliationState(state_db),
        lookback=timedelta(hours=int(lookback_hours)),
        cadence=timedelta(hours=int(cadence_hours)),
        audit=audit,
    )
