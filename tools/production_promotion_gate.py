from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import AbstractSet, Any, Mapping


@dataclass(frozen=True, slots=True)
class ProductionPromotionDecision:
    allowed: bool
    plan_sha256: str
    reason_codes: tuple[str, ...]


def canonical_plan_bytes(plan: Mapping[str, Any]) -> bytes:
    return json.dumps(
        plan,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def promotion_plan_sha256(plan: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_plan_bytes(plan)).hexdigest()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError:
        return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def evaluate_production_promotion(
    *,
    plan: Mapping[str, Any],
    approval: Mapping[str, Any] | None,
    trusted_owner_principals: AbstractSet[str],
    now: datetime | None = None,
) -> ProductionPromotionDecision:
    """Validate exact-plan Owner approval for a Production promotion.

    This validates deterministic binding and approval invariants only.
    The caller must obtain the approval from Jason's trusted approval authority
    and atomically reserve or consume it before material mutation.
    Caller-supplied files or booleans are not authority.
    """

    digest = promotion_plan_sha256(plan)
    reasons: list[str] = []

    if plan.get("target_environment") != "production":
        reasons.append("TARGET_NOT_PRODUCTION")

    promotion_id = plan.get("promotion_id")
    if not isinstance(promotion_id, str) or not promotion_id.strip():
        reasons.append("PROMOTION_ID_MISSING")

    blockers = plan.get("blockers")
    if not isinstance(blockers, list):
        reasons.append("BLOCKERS_INVALID")
    elif blockers:
        reasons.append("UNRESOLVED_BLOCKERS")

    if approval is None:
        reasons.append("OWNER_APPROVAL_MISSING")
        return ProductionPromotionDecision(False, digest, tuple(reasons))

    if approval.get("target_environment") != "production":
        reasons.append("APPROVAL_TARGET_MISMATCH")
    if approval.get("promotion_id") != promotion_id:
        reasons.append("APPROVAL_PROMOTION_MISMATCH")
    if approval.get("plan_sha256") != digest:
        reasons.append("APPROVAL_PLAN_MISMATCH")
    if approval.get("decision") != "approved":
        reasons.append("APPROVAL_DECISION_INVALID")
    if approval.get("approver_authority") != "owner":
        reasons.append("APPROVER_NOT_OWNER")

    principal = approval.get("approver_principal_id")
    if not isinstance(principal, str) or principal not in trusted_owner_principals:
        reasons.append("APPROVER_NOT_TRUSTED")

    if approval.get("state") != "approved":
        reasons.append("APPROVAL_NOT_AVAILABLE")

    authority_record_id = approval.get("authority_record_id")
    if not isinstance(authority_record_id, str) or not authority_record_id.strip():
        reasons.append("AUTHORITY_RECORD_MISSING")

    approved_at = _parse_datetime(approval.get("approved_at"))
    expires_at = _parse_datetime(approval.get("expires_at"))
    if approved_at is None:
        reasons.append("APPROVED_AT_INVALID")
    if expires_at is None:
        reasons.append("EXPIRES_AT_INVALID")

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if approved_at is not None and approved_at > current:
        reasons.append("APPROVAL_FROM_FUTURE")
    if expires_at is not None and expires_at <= current:
        reasons.append("APPROVAL_EXPIRED")
    if approved_at is not None and expires_at is not None and expires_at <= approved_at:
        reasons.append("APPROVAL_WINDOW_INVALID")

    return ProductionPromotionDecision(not reasons, digest, tuple(reasons))
