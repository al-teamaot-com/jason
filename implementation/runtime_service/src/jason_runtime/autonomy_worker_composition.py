"""Compose the disabled-by-default production autonomous ticket worker."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from autonomous_remediation.autonomous_principal import (
    AutonomousPrincipal,
    AutonomousRequestFactory,
)
from autonomous_remediation.autotask_queue_source import (
    AutotaskQueueDiscoveryConfig,
    AutotaskQueueSource,
)
from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from autonomous_remediation.targeted_recheck import SQLiteTargetedWakeStore
from kernel.capabilities import CapabilityRegistryService
from kernel.identity_authority import IdentityAuthorityService
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger

from .autonomy_shadow_runtime import GovernedAutonomyReadPort
from .autonomy_targeted_wake_runtime import (
    CompositeAutonomyMaintenance,
    TargetedWakeMaintenance,
)
from .autonomy_worker_runtime import (
    GovernedAutonomyActionPort,
    OperationalAutonomyMaintenance,
    SQLiteOperationalWorkStore,
)


def build_autonomy_worker_maintenance(
    *,
    enabled: bool,
    identity_authority: IdentityAuthorityService,
    capabilities: CapabilityRegistryService,
    approvals,
    execution_ledger: SQLiteGovernedExecutionLedger,
    orchestrator,
    work_db: Path,
    promotion_db: Path,
    targeted_wake_db: Path,
    owned_autotask_resource_ids: Iterable[int] = (),
    max_active_work_items: int = 2,
    interval_seconds: int = 60,
    targeted_wake_retry_seconds: int = 300,
    audit=None,
    completion_notifier=None,
):
    """Build the production worker or return None without side effects."""

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
        policy_id="autonomous-worker-read-v1",
    )
    queue_source = AutotaskQueueSource(
        reads=reads,
        config=AutotaskQueueDiscoveryConfig(
            owned_queue_labels=("Jason",),
            discovery_queue_labels=(
                "Help Desk I",
                "Help Desk II",
                "Monitoring Alert",
            ),
            owned_status_labels=(
                "New",
                "In Progress",
                "Updated by Email",
                "Updated by Email - Client",
                "Updated by AOT",
                "Emergency",
                "Waiting Device Access",
            ),
            discovery_status_labels=("New", "Emergency"),
            owned_resource_ids=tuple(owned_autotask_resource_ids),
            allow_assigned_discovery=False,
            assessment_include_assigned=True,
            use_open_status_search=True,
        ),
    )
    actions = GovernedAutonomyActionPort(
        request_factory=request_factory,
        orchestrator=orchestrator,
        promotion_store=promotion_store,
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=queue_source,
        reads=reads,
        actions=actions,
        store=SQLiteOperationalWorkStore(work_db),
        promotion_store=promotion_store,
        max_active_work_items=max_active_work_items,
        interval_seconds=interval_seconds,
        audit=audit,
        completion_notifier=completion_notifier,
    )
    targeted_reads = GovernedAutonomyReadPort(
        request_factory=request_factory,
        orchestrator=orchestrator,
        policy_id="autonomous-targeted-read-v1",
    )
    targeted = TargetedWakeMaintenance(
        store=SQLiteTargetedWakeStore(targeted_wake_db),
        reads=targeted_reads,
        queue_attention=worker,
        retry_seconds=targeted_wake_retry_seconds,
    )
    return CompositeAutonomyMaintenance(targeted, worker)
