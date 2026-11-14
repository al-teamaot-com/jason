"""PMv4 single-human-decision *conformance* adapter (source-only).

Reuses the existing universal plan grant ledger. Never issues approvals, signs
sub-actions, bypasses a root gate, or executes a production release. All current
PMv3 exact-action production requirements remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from .approval_plan_grants import PlanGrantLedger
from .approval_plan_scope import ProposedPlanStep

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class ObjectiveAction:
    """One reviewed, independently guarded step of an immutable objective."""

    capability: str
    component: str
    scope_sha256: str
    artifact_sha256: str
    risk: int

    def __post_init__(self) -> None:
        if (not self.capability.strip() or not self.component.strip()
                or not _HEX_64.fullmatch(self.scope_sha256)
                or not _HEX_64.fullmatch(self.artifact_sha256)
                or type(self.risk) is not int or not 0 <= self.risk <= 3):
            raise ValueError("invalid bounded objective action")


@dataclass(frozen=True, slots=True)
class BoundedObjective:
    """Server-owned review manifest: one decision, ordered exact release steps."""

    plan_id: str
    organization_id: str
    policy_digest: str
    candidate_sha: str
    rollback_sha: str
    freeze_sha256: str
    hold_sha256: str
    actions: tuple[ObjectiveAction, ...]
    expires_at: datetime

    def __post_init__(self) -> None:
        if (not self.plan_id or not self.organization_id
                or not _HEX_64.fullmatch(self.policy_digest)
                or not _SHA.fullmatch(self.candidate_sha)
                or not _SHA.fullmatch(self.rollback_sha)
                or not _HEX_64.fullmatch(self.freeze_sha256)
                or not _HEX_64.fullmatch(self.hold_sha256)
                or not 1 <= len(self.actions) <= 12
                or self.expires_at.tzinfo is None):
            raise ValueError("invalid bounded objective manifest")
        caps = [a.capability for a in self.actions]
        if len(caps) != len(set(caps)):
            raise ValueError("duplicate capability in reviewed objective")

    @property
    def fingerprint(self) -> str:
        """Stable digest of all Owner-reviewed fields, including step ORDER."""
        payload = {
            "schema_version": "1.0",
            "plan_id": self.plan_id,
            "organization_id": self.organization_id,
            "policy_digest": self.policy_digest,
            "candidate_sha": self.candidate_sha,
            "rollback_sha": self.rollback_sha,
            "freeze_sha256": self.freeze_sha256,
            "hold_sha256": self.hold_sha256,
            "actions": [
                {
                    "capability": a.capability,
                    "component": a.component,
                    "scope_sha256": a.scope_sha256,
                    "artifact_sha256": a.artifact_sha256,
                    "risk": a.risk,
                }
                for a in self.actions
            ],
            "expires_at": self.expires_at.isoformat(),
        }
        return hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")).hexdigest()


def require_objective_step_conformance(
    *, ledger: PlanGrantLedger, objective: BoundedObjective,
    approved_fingerprint: str, action_index: int,
    observed_candidate_sha: str, observed_rollback_sha: str,
    observed_freeze_sha256: str, observed_hold_sha256: str,
    observed_scope_sha256: str, observed_artifact_sha256: str,
    now: datetime,
) -> str:
    """Deny any drift; return the step name for *read-only assessment only*.

    Trusted host root/controller must obtain all 'observed' values from its
    native authoritative readback, NOT from a caller-provided payload.
    An affirmative result is never an executable grant. The existing Release
    Manager must separately verify signed Owner proof, source, freshness,
    root lock, independent acceptance, idempotency and rollback.
    """
    if type(action_index) is not int or not 0 <= action_index < len(objective.actions):
        raise PermissionError("action index is outside reviewed objective")
    if now.tzinfo is None:
        raise ValueError("current time must be timezone-aware")
    if now.astimezone(timezone.utc) >= objective.expires_at.astimezone(timezone.utc):
        raise PermissionError("reviewed objective authorization expired")
    if approved_fingerprint != objective.fingerprint:
        raise PermissionError("reviewed objective material changed")
    if (observed_candidate_sha != objective.candidate_sha
            or observed_rollback_sha != objective.rollback_sha
            or observed_freeze_sha256 != objective.freeze_sha256
            or observed_hold_sha256 != objective.hold_sha256):
        raise PermissionError("release candidate or production control drift")
    action = objective.actions[action_index]
    if (observed_scope_sha256 != action.scope_sha256
            or observed_artifact_sha256 != action.artifact_sha256):
        raise PermissionError("reviewed action effect or artifact changed")
    ledger.require_grant(
        ProposedPlanStep(
            objective.plan_id, objective.organization_id,
            objective.policy_digest, action.capability, None, action.risk, True,
        ),
        plan_fingerprint=approved_fingerprint, now=now,
    )
    return action.capability
