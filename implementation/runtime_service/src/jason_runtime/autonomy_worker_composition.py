"""Compose the disabled-by-default production autonomous ticket worker."""

from __future__ import annotations

import os
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
from .ticket_split_runtime import SQLiteTicketSplitStore, TicketSplitExecutor
from .client_information_requests import (
    ClientQuestionWorkflow,
    SQLiteClientQuestionLedger,
    client_question_profile_enabled,
)
from .autonomy_targeted_wake_runtime import (
    CompositeAutonomyMaintenance,
    TargetedWakeMaintenance,
)
from .autonomy_worker_runtime import (
    GovernedAutonomyActionPort,
    OperationalAutonomyMaintenance,
    SQLiteOperationalWorkStore,
    CLIENT_QUESTION_SCOPE,
)


# Narrow, source-reviewed pilot only. No note or ticket update is permitted
# until an independent durable owner promotion is recorded for each playbook.
TRIAGE_NOTE_PILOT_TICKET_IDS = (143305, 143272)


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
    ticket_splitter = TicketSplitExecutor(
        actions=actions,
        store=SQLiteTicketSplitStore(work_db.with_name("ticket-split.sqlite3")),
    )
    # New authority is enabled only through its separate reviewed profile.
    contact_reads = (
        GovernedAutonomyReadPort(
            request_factory=request_factory,
            orchestrator=orchestrator,
            policy_id="autonomous-ticket-contact-context-read-v1",
        )
        if os.getenv("JASON_TICKET_CONTACT_CONTEXT_PROFILE", "") == "approved-v1"
        else None
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=queue_source,
        reads=reads,
        contact_reads=contact_reads,
        actions=actions,
        store=SQLiteOperationalWorkStore(work_db),
        promotion_store=promotion_store,
        max_active_work_items=max_active_work_items,
        triage_note_pilot_ticket_ids=TRIAGE_NOTE_PILOT_TICKET_IDS,
        interval_seconds=interval_seconds,
        audit=audit,
        completion_notifier=completion_notifier,
        ticket_splitter=ticket_splitter,
    )
    # No new send authority is created by constructing the worker. A separate
    # exact activation profile plus durable owner-promoted playbook scope are
    # both required, and the existing Autotask connector independently checks
    # recipients and exact approved message bodies.
    if client_question_profile_enabled():
        question_reads = GovernedAutonomyReadPort(
            request_factory=request_factory,
            orchestrator=orchestrator,
            policy_id="autonomous-client-question-read-v1",
        )
        worker.client_questions = ClientQuestionWorkflow(
            reads=question_reads, actions=actions,
            ledger=SQLiteClientQuestionLedger(
                work_db.with_name("client-questions.sqlite3")
            ),
            scope=CLIENT_QUESTION_SCOPE,
            scope_is_promoted=lambda: worker._scope_is_promoted(CLIENT_QUESTION_SCOPE),
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
