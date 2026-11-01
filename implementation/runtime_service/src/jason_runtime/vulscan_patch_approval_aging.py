"""Deterministic VulScan patch approval aging decisions (no provider actions).

All inputs are authoritative, pre-normalized facts supplied by governed readers.
This module neither fetches Microsoft data nor sends Teams messages.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class PatchApprovalObservation:
    kb: str
    release_date: date | None
    observed_date: date
    policy_id: str
    client_id: str
    device_id: str
    approval_state: str
    source_verified: bool
    intentional_deferral: bool = False
    superseded: bool = False
    actively_exploited: bool = False
    exploitation_verified: bool = False


@dataclass(frozen=True)
class ApprovalNoticeDecision:
    patch: str
    policy_id: str
    stage: str
    age_days: int | None
    affected_clients: int
    affected_devices: int
    idempotency_key: str
    reason: str


def evaluate_approval_aging(
    observations: Iterable[PatchApprovalObservation],
) -> tuple[ApprovalNoticeDecision, ...]:
    """Return grouped notification *intent*, never send authorization.

    Group by KB AND approval policy. Reject contradictory release-date facts.
    Days 0-15 are the normal grace period; day 16 first notice, day 21
    follow-up. Actively exploited findings require an immediate *review*,
    not an automatic approval or installation.
    """
    groups: dict[tuple[str, str], list[PatchApprovalObservation]] = {}
    for item in observations:
        kb = item.kb.strip().upper()
        if not kb.startswith("KB") or not kb[2:].isdigit() or not item.policy_id:
            raise ValueError("Invalid patch or approval policy identity")
        groups.setdefault((kb, item.policy_id), []).append(item)

    results = []
    for (kb, policy), items in sorted(groups.items()):
        if any(not x.source_verified or x.release_date is None for x in items):
            stage, age, reason = "evidence_exception", None, "Release date or authoritative source unavailable"
        elif len({x.release_date for x in items}) != 1 or len({x.observed_date for x in items}) != 1:
            stage, age, reason = "evidence_exception", None, "Contradictory patch release/observation dates"
        else:
            age = (items[0].observed_date - items[0].release_date).days
            if age < 0:
                stage, reason = "evidence_exception", "Patch release date is in the future"
            else:
                pending = [x for x in items if x.approval_state.upper() == "NOT_APPROVED"
                           and not x.intentional_deferral and not x.superseded]
                if not pending:
                    stage, reason = "none", "No outstanding unapproved applicability"
                elif any(x.actively_exploited and x.exploitation_verified for x in pending):
                    stage, reason = "urgent_review", "Verified actively exploited vulnerability requires review"
                elif age >= 21:
                    stage, reason = "day21_escalation", "Approval outstanding beyond 21 days"
                elif age >= 16:
                    stage, reason = "day16_notice", "Approval outstanding beyond 15-day review window"
                else:
                    stage, reason = "none", "Within normal 15-day review window"
        outstanding = [x for x in items if x.approval_state.upper() == "NOT_APPROVED"
                       and not x.intentional_deferral and not x.superseded]
        if stage == "none":
            continue
        # Scoped counts must never infer a company/device from a bare ticket count.
        clients = {x.client_id for x in outstanding}
        devices = {(x.client_id, x.device_id) for x in outstanding}
        results.append(ApprovalNoticeDecision(
            patch=kb, policy_id=policy, stage=stage, age_days=age,
            affected_clients=len(clients), affected_devices=len(devices),
            idempotency_key=f"vulscan-aging:v2:{kb}:{policy}:{stage}",
            reason=reason,
        ))
    return tuple(results)
