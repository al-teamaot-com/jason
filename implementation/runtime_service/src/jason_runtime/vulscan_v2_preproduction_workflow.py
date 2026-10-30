"""Dormant VulScan V2 orchestration: governed reads -> policy -> existing Teams outbox.

Not registered in production composition. A separately accepted owner promotion
must be supplied by the caller; environment flags never grant send authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Callable, Mapping

from .vulscan_governed_patch_source import (
    VerifiedPatchTarget, collect_governed_patch_observations,
    VulscanPatchEvidenceError,
)
from .vulscan_owner_disposition_evidence import VerifiedPatchReviewDisposition
from .vulscan_microsoft_release_evidence import (
    GovernedMicrosoftReleaseRecord, normalize_governed_microsoft_release,
)
from .vulscan_patch_approval_notification import (
    PreparedPatchNotification, prepare_patch_notifications,
    verify_notification_against_fresh_evidence,
)


@dataclass(frozen=True, slots=True)
class VerifiedVulscanTargetInventory:
    """The inventory provider must prove completeness across its scoped policies."""
    targets: tuple[VerifiedPatchTarget, ...]
    full_scope_verified: bool
    source_reference: str


@dataclass(frozen=True, slots=True)
class VulscanV2BatchResult:
    mode: str
    candidate_count: int
    enqueued_count: int
    reason: str


@dataclass
class VulscanV2PreproductionWorkflow:
    """Wire existing read-only capability ports, not direct provider integrations.

    Inventory and Microsoft release source ports are not yet backed by
    production-approved automatic providers. Thus this workflow is safe to use
    with controlled/preproduction fixtures, but not production-eligible.
    """
    store: Any
    inventory_reader: Callable[[], VerifiedVulscanTargetInventory]
    patch_read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
    microsoft_release_reader: Callable[[str], GovernedMicrosoftReleaseRecord]
    # A separately governed, full-scope review-decision reader is mandatory
    # before patch-status evidence can become an owner reminder. Never assume
    # that missing approval notes mean "not deferred".
    review_disposition_read: Callable[[VerifiedPatchTarget], VerifiedPatchReviewDisposition] | None = None
    # Checked against exact durable playbook promotion + recipient/send grant.
    activation_verified: Callable[[], bool] | None = None

    def snapshot(self, *, now: datetime) -> tuple[
        tuple[Any, ...], Mapping[str, Any]]:
        if now.tzinfo is None:
            raise VulscanPatchEvidenceError("V2 snapshot requires timezone-aware time")
        inventory = self.inventory_reader()
        if (not isinstance(inventory, VerifiedVulscanTargetInventory)
                or inventory.full_scope_verified is not True
                or not isinstance(inventory.source_reference, str)
                or not inventory.source_reference.strip()):
            raise VulscanPatchEvidenceError("complete governed patch-policy inventory unavailable")
        targets = inventory.targets
        if not targets:
            return (), {}
        if self.review_disposition_read is None:
            raise VulscanPatchEvidenceError(
                "complete governed owner disposition source unavailable")
        requested_kbs = {item.kb.strip().upper() for item in targets}
        metadata = {}
        for kb in sorted(requested_kbs):
            record = self.microsoft_release_reader(kb)
            metadata[kb] = normalize_governed_microsoft_release(
                record, expected_kb=kb)
        observations = collect_governed_patch_observations(
            targets=targets, metadata_by_kb=metadata,
            read=self.patch_read, now=now,
            review_disposition_read=self.review_disposition_read)
        return observations, metadata

    def evaluate_once(self, *, now: datetime, enqueue: bool = False) -> VulscanV2BatchResult:
        """Read-only shadow is default. Enqueue requires exact authority proof.

        Never send directly here. The separate auxiliary outbox drain must
        independently re-read current facts immediately before Teams delivery.
        """
        if enqueue and (self.activation_verified is None
                        or self.activation_verified() is not True):
            raise PermissionError("V2 notification promotion/recipient authority absent")
        observations, metadata = self.snapshot(now=now)
        notices = prepare_patch_notifications(observations, metadata, now=now)
        if not enqueue:
            return VulscanV2BatchResult(
                "shadow", len(notices), 0, "no provider writes or Teams delivery")
        count = 0
        for notice in notices:
            self.store.queue_patch_approval_notification(notification=notice, now=now)
            count += 1
        return VulscanV2BatchResult(
            "queued", len(notices), count, "durable shared Teams outbox only")

    def verify_current(self, notification: PreparedPatchNotification, *, now: datetime) -> bool:
        """This must be invoked by the outbox drain before each provider send."""
        if self.activation_verified is None or self.activation_verified() is not True:
            return False
        observations, metadata = self.snapshot(now=now)
        return verify_notification_against_fresh_evidence(
            notification, observations, metadata, now=now)


@dataclass
class VulscanV2ShadowMaintenance:
    """Opt-in auxiliary cadence; not registered by default in runtime composition.

    The default execution path is always read-only shadow. Activation and
    persistent Teams send authority belong to separately promoted composition.
    """
    workflow: VulscanV2PreproductionWorkflow
    interval_seconds: int = 24 * 60 * 60
    monotonic: Callable[[], float] = time.monotonic
    current_time: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    _next_due: float = 0.0

    def __post_init__(self) -> None:
        if int(self.interval_seconds) < 60 * 60:
            raise ValueError("VulScan V2 evaluation frequency cannot exceed hourly")

    def tick(self) -> VulscanV2BatchResult | None:
        now_monotonic = self.monotonic()
        if now_monotonic < self._next_due:
            return None
        self._next_due = now_monotonic + self.interval_seconds
        return self.workflow.evaluate_once(now=self.current_time(), enqueue=False)
