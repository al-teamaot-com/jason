"""VulScan V2 approval-aging notification presentation and governed Teams adapter.

There is deliberately no HTTP/Teams transport, patch write, or approval grant here.
The caller provides trusted governed observations and verified vendor metadata.
The existing JasonTeamsCommunicationService remains the only Teams sender.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .vulscan_patch_approval_aging import ApprovalNoticeDecision, PatchApprovalObservation, evaluate_approval_aging

_KB = re.compile(r"^KB[0-9]{5,9}$")
_ALLOWED_STAGES = {"day16_notice", "day21_escalation", "urgent_review"}
_STAGES = ("urgent_review", "day21_escalation", "day16_notice")
_MAX_SUMMARY = 420
_MAX_KNOWN_ISSUES = 340


def verified_microsoft_kb_url(kb: str, url: str) -> bool:
    """Allow only a verified, exact Microsoft KB article URL.

    The actual document retrieval and Microsoft source verification are the
    responsibility of an approved read connector, not this presentation layer.
    """
    if not isinstance(url, str) or len(url) > 1000 or not _KB.fullmatch(kb):
        return False
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if (parsed.scheme != "https" or host not in
                {"support.microsoft.com", "learn.microsoft.com"}
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443) or parsed.fragment):
            return False
        # A KB mismatch cannot produce a plausible-looking link.
        return re.search(r"(?<!\d)" + kb[2:] + r"(?!\d)", parsed.path, re.I) is not None
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class MicrosoftKBMetadata:
    kb: str
    release_date: date
    title: str
    summary: str
    url: str | None
    source_checked_at: datetime
    source_verified: bool
    known_issues: str | None = None
    # Recorded only; a revision is not a new original release date.
    revision_date: date | None = None


@dataclass(frozen=True, slots=True)
class PreparedPatchNotification:
    kb: str
    stage: str
    released: date
    age_days: int
    policy_ids: tuple[str, ...]
    affected_clients: int
    affected_devices: int
    idempotency_key: str
    text: str


def _bounded_plain(value: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("expected verified Microsoft text")
    # Prevent a vendor page from injecting extra faux Teams fields or actions.
    return " ".join(value.split())[:maximum]


def prepare_patch_notifications(
    observations: Iterable[PatchApprovalObservation],
    metadata_by_kb: Mapping[str, MicrosoftKBMetadata],
    *,
    now: datetime,
) -> tuple[PreparedPatchNotification, ...]:
    """One message per KB/event, with per-policy evaluation kept intact.

    Any evidence conflict for one KB fails closed for that KB. Missing metadata
    becomes an evidence exception in the evaluator, not a fabricated message.
    """
    if now.tzinfo is None:
        raise ValueError("UTC-aware evaluation time required")
    observations = tuple(observations)
    decisions = evaluate_approval_aging(observations)
    by_kb: dict[str, list[ApprovalNoticeDecision]] = {}
    for decision in decisions:
        by_kb.setdefault(decision.patch, []).append(decision)
    notices: list[PreparedPatchNotification] = []

    for kb, policies in sorted(by_kb.items()):
        # If one policy has unknown release evidence, do not imply the KB-wide
        # summary is complete. Surface it to the evidence exception tracker.
        if any(p.stage == "evidence_exception" for p in policies):
            continue
        present = {p.stage for p in policies}
        selected = next((s for s in _STAGES if s in present), None)
        if selected is None:
            continue
        meta = metadata_by_kb.get(kb)
        if meta is None or not meta.source_verified or meta.kb.upper() != kb:
            continue
        if (meta.source_checked_at.tzinfo is None
                or meta.source_checked_at > now
                or now - meta.source_checked_at > timedelta(days=7)):
            continue
        matching = [o for o in observations if o.kb.strip().upper() == kb]
        # All patch-state evidence must have been observed on today's
        # AOT-local evaluation date. Stale or future snapshots cannot trigger.
        local_today = now.astimezone(ZoneInfo("America/New_York")).date()
        if any(o.observed_date != local_today for o in matching):
            continue
        release_dates = {o.release_date for o in matching}
        if release_dates != {meta.release_date}:
            continue
        ages = {p.age_days for p in policies}
        if len(ages) != 1 or None in ages or next(iter(ages)) < 0:
            continue
        age = next(iter(ages))
        if not _KB.fullmatch(kb) or not _bounded_plain(meta.title, 200):
            continue
        active = [o for o in matching if o.approval_state.upper() == "NOT_APPROVED"
                  and not o.intentional_deferral and not o.superseded]
        clients = {o.client_id for o in active}
        devices = {(o.client_id, o.device_id) for o in active}
        policy_ids = tuple(sorted({o.policy_id for o in active}))
        if not policy_ids or not clients or not devices:
            continue
        summary = _bounded_plain(meta.summary, _MAX_SUMMARY)
        known = _bounded_plain(meta.known_issues, _MAX_KNOWN_ISSUES) if meta.known_issues else ""
        url = meta.url if meta.url and verified_microsoft_kb_url(kb, meta.url) else None
        kind = {
            "day16_notice": "Patch Approval Review",
            "day21_escalation": "Patch Approval Follow-Up",
            "urgent_review": "Urgent Patch Security Review",
        }[selected]
        text = (
            f"Jason - {kind}\n"
            f"Patch: {kb} - {_bounded_plain(meta.title, 180)}\n"
            f"Microsoft release date: {meta.release_date.isoformat()}\n"
            f"Days since release: {age}\n"
            f"Effective endpoint status: NOT_APPROVED; assigned patch policy references: {len(policy_ids)}\n"
            f"Affected clients: {len(clients)}; devices: {len(devices)}\n"
            f"Description (Microsoft): {summary or 'Verified description unavailable'}\n"
            f"Known issues: {known or 'No verified known-issue summary available'}\n"
            f"Microsoft KB: {url or 'Official KB article not verified'}\n"
            "ACTION REQUIRED: Review the patch and approve or record an intentional "
            "deferral through the existing governed patch-management process. "
            "This message does not approve or install the update."
        )
        # Stable across daily scan and count changes, distinct for new releases.
        fingerprint = f"v2|{kb}|{meta.release_date.isoformat()}|{selected}"
        event_key = "vulscan-aging-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:40]
        notices.append(PreparedPatchNotification(
            kb=kb, stage=selected, released=meta.release_date, age_days=age,
            policy_ids=policy_ids, affected_clients=len(clients),
            affected_devices=len(devices), idempotency_key=event_key, text=text,
        ))
    return tuple(notices)


def verify_notification_against_fresh_evidence(
    notification: PreparedPatchNotification,
    observations: Iterable[PatchApprovalObservation],
    metadata_by_kb: Mapping[str, MicrosoftKBMetadata],
    *,
    now: datetime,
) -> bool:
    """Fail closed if a governed re-read no longer supports this exact event.

    Real integrations must obtain these facts through the authorized per-client
    provider read and official Microsoft evidence source before calling here.
    No direct source access or cross-client expansion is performed in this module.
    """
    latest = prepare_patch_notifications(observations, metadata_by_kb, now=now)
    return any(
        candidate.idempotency_key == notification.idempotency_key
        and candidate.kb == notification.kb
        and candidate.stage == notification.stage
        and candidate.released == notification.released
        and candidate.policy_ids == notification.policy_ids
        and candidate.affected_clients == notification.affected_clients
        and candidate.affected_devices == notification.affected_devices
        and candidate.text == notification.text
        for candidate in latest
    )


@dataclass
class CanonicalPatchTeamsNotifier:
    """Authorized sender adapter; no second Teams implementation or approval.

    The caller must supply the *verified* owner identity bound by the existing
    AOT Teams identity store, plus a workflow authority grant and audience
    policy already configured in JasonTeamsCommunicationService.
    """
    communication_service: Any
    owner_identity_id: str
    organization_id: str = "aot"
    sender_identity_id: str = "jason-autonomy-worker"

    def send_prepared(self, notification: PreparedPatchNotification) -> Mapping[str, Any]:
        if notification.stage not in _ALLOWED_STAGES:
            raise PermissionError("unsupported patch notification stage")
        from communication.audience.models import AudienceType, MessagePurpose
        from .teams_communication_service import TeamsCommunicationRequest
        request = TeamsCommunicationRequest(
            workflow="vulscan_patch_approval_aging",
            communication_id=notification.idempotency_key,
            correlation_id=notification.idempotency_key,
            sender_identity_id=self.sender_identity_id,
            recipient_identity_id=self.owner_identity_id,
            organization_id=self.organization_id,
            client_id=None,
            audience_type=AudienceType.SERVICE_MANAGER,
            purpose=MessagePurpose.OPERATIONAL,
            kind="notification",
            text=notification.text,
            card=None,
            approval_id=None,
        )
        receipt = self.communication_service.send(request)
        if not receipt.message_id:
            raise RuntimeError("canonical Teams service returned no message reference")
        return {
            "message_id": receipt.message_id,
            "message_id_synthetic": receipt.message_id_synthetic,
            "delivery_state": receipt.delivery_state,
        }
