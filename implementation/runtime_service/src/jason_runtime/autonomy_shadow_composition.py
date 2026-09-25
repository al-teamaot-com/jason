"""Compose the disabled-by-default autonomous queue shadow runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from autonomous_remediation.attention_scheduler import AutonomyConfig
from autonomous_remediation.autonomous_principal import (
    AutonomousPrincipal,
    AutonomousRequestFactory,
)
from autonomous_remediation.autotask_queue_source import (
    AutotaskQueueDiscoveryConfig,
    AutotaskQueueSource,
)
from autonomous_remediation.catalog_classifier import CatalogPlaybookClassifier
from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from autonomous_remediation.playbook_catalog import PlaybookCatalog
from autonomous_remediation.shadow_assessment import ShadowQueueAssessor
from kernel.capabilities import CapabilityRegistryService
from kernel.identity_authority import IdentityAuthorityService
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger

from .autonomy_shadow_runtime import (
    GovernedAutonomyReadPort,
    ShadowAutonomyMaintenance,
    SQLiteShadowAssessmentStore,
)


def build_autonomy_shadow_maintenance(
    *,
    enabled: bool,
    identity_authority: IdentityAuthorityService,
    capabilities: CapabilityRegistryService,
    approvals,
    execution_ledger: SQLiteGovernedExecutionLedger,
    orchestrator,
    shadow_db: Path,
    promotion_db: Path,
    playbook_registry: Path,
    owned_autotask_resource_ids: Iterable[int] = (),
    max_active_work_items: int = 2,
    interval_seconds: int = 1800,
    failure_retry_seconds: int = 300,
):
    """Build read-only shadow autonomy or return None with no side effects."""

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
    )
    queue_source = AutotaskQueueSource(
        reads=reads,
        config=AutotaskQueueDiscoveryConfig(
            owned_resource_ids=tuple(owned_autotask_resource_ids),
        ),
    )
    catalog = PlaybookCatalog.load(playbook_registry)
    classifier = CatalogPlaybookClassifier(
        catalog,
        promotion_store=promotion_store,
    )
    assessor = ShadowQueueAssessor(
        config=AutonomyConfig(max_active_work_items),
        queue_source=queue_source,
        classifier=classifier,
    )
    store = SQLiteShadowAssessmentStore(shadow_db)
    return ShadowAutonomyMaintenance(
        assessor=assessor,
        store=store,
        interval_seconds=interval_seconds,
        failure_retry_seconds=failure_retry_seconds,
    )
