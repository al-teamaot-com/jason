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

    def review_material(self) -> dict:
        """Canonical immutable Owner-facing facts; never sourced from card fields."""
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
        return payload

    @property
    def fingerprint(self) -> str:
        """Stable digest of every reviewed fact, including the ordered steps."""
        return hashlib.sha256(json.dumps(
            self.review_material(), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
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


def issue_proved_objective_step(
    *, objective: BoundedObjective, ledger: PlanGrantLedger,
    signed_parent: dict, signing_key: object, pinned_public_key: object,
    action_index: int, observed: dict, at: datetime,
    verified_prior_steps: frozenset[int] = frozenset(),
) -> dict:
    """Source-only bridge: ONE existing authenticated human decision -> step.

    This can only be connected to a trusted existing Owner issuer after its
    authenticated Entra plan/consent record and current signer identity have
    been independently verified. It does not publish a production root job.
    The caller must get observed facts from privileged source/CI/root readback.
    """
    from kernel.pmv4_plan_child_proof import (
        issue_derived_step_proof, verify_authenticated_owner_objective,
    )
    from kernel.signed_owner_release import canonical, public_key_sha256
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if not isinstance(signing_key, Ed25519PrivateKey):
        raise PermissionError("native trusted Owner signer required")
    if public_key_sha256(signing_key.public_key()) != public_key_sha256(pinned_public_key):
        raise PermissionError("Owner signer differs from independently pinned trust")
    parent = verify_authenticated_owner_objective(
        signed_parent, objective=objective,
        pinned_public_key=pinned_public_key, at=at, ledger=ledger,
    )
    require_objective_step_sequence(
        action_index=action_index, verified_prior_steps=verified_prior_steps,
        total_steps=len(objective.actions),
    )
    if not isinstance(observed, dict) or set(observed) != {
        "candidate_sha", "rollback_sha", "freeze_sha256", "hold_sha256",
        "scope_sha256", "artifact_sha256",
    }:
        raise PermissionError("complete native observed effects required")
    require_objective_step_conformance(
        ledger=ledger, objective=objective,
        approved_fingerprint=parent["parent_plan_fingerprint"],
        action_index=action_index,
        observed_candidate_sha=observed["candidate_sha"],
        observed_rollback_sha=observed["rollback_sha"],
        observed_freeze_sha256=observed["freeze_sha256"],
        observed_hold_sha256=observed["hold_sha256"],
        observed_scope_sha256=observed["scope_sha256"],
        observed_artifact_sha256=observed["artifact_sha256"],
        now=at,
    )
    action = objective.actions[action_index]
    return issue_derived_step_proof(
        private_key=signing_key, verified_owner_oid=parent["owner_oid"],
        parent_plan_id=objective.plan_id,
        parent_approval_id=parent["parent_approval_id"],
        parent_plan_fingerprint=objective.fingerprint,
        parent_authenticated_decision_sha256=hashlib.sha256(
            canonical(signed_parent)).hexdigest(),
        parent_plan_expires_at=objective.expires_at,
        policy_digest=objective.policy_digest,
        step_index=action_index, action=action.capability,
        candidate_sha=objective.candidate_sha,
        rollback_sha=objective.rollback_sha,
        scope_sha256=action.scope_sha256,
        artifact_sha256=action.artifact_sha256,
        freeze_sha256=objective.freeze_sha256,
        hold_sha256=objective.hold_sha256, at=at,
    )


def verify_proved_objective_step(
    *, objective: BoundedObjective, ledger: PlanGrantLedger,
    signed_parent: dict, signed_step: dict, pinned_public_key: object,
    action_index: int, observed: dict, at: datetime,
    consumed_step_claims: frozenset[str] = frozenset(),
    verified_prior_steps: frozenset[int] = frozenset(),
) -> dict:
    """Read-only root gate adapter: NO release execution or claim consumption.

    The future native root caller must independently gather observed facts,
    enforce protected release locks/CCC/CI/health and atomically reserve the
    returned one-use step claim before any mutation. A stored approval cannot
    stand in for these independent gates.
    """
    from kernel.pmv4_plan_child_proof import (
        verify_authenticated_owner_objective, verify_derived_step_proof,
    )
    from kernel.signed_owner_release import canonical

    parent = verify_authenticated_owner_objective(
        signed_parent, objective=objective,
        pinned_public_key=pinned_public_key, at=at, ledger=ledger,
    )
    require_objective_step_sequence(
        action_index=action_index, verified_prior_steps=verified_prior_steps,
        total_steps=len(objective.actions),
    )
    if not isinstance(observed, dict) or set(observed) != {
        "candidate_sha", "rollback_sha", "freeze_sha256", "hold_sha256",
        "scope_sha256", "artifact_sha256",
    }:
        raise PermissionError("root independently observed complete stage effects required")
    require_objective_step_conformance(
        ledger=ledger, objective=objective,
        approved_fingerprint=parent["parent_plan_fingerprint"],
        action_index=action_index,
        observed_candidate_sha=observed["candidate_sha"],
        observed_rollback_sha=observed["rollback_sha"],
        observed_freeze_sha256=observed["freeze_sha256"],
        observed_hold_sha256=observed["hold_sha256"],
        observed_scope_sha256=observed["scope_sha256"],
        observed_artifact_sha256=observed["artifact_sha256"],
        now=at,
    )
    action = objective.actions[action_index]
    expected = {
        "tenant_id": parent["tenant_id"],
        "owner_oid": parent["owner_oid"],
        "owner_principal": parent["owner_principal"],
        "organization_id": parent["organization_id"],
        "parent_plan_id": objective.plan_id,
        "parent_approval_id": parent["parent_approval_id"],
        "parent_plan_fingerprint": objective.fingerprint,
        "parent_authenticated_decision_sha256": hashlib.sha256(
            canonical(signed_parent)).hexdigest(),
        "parent_plan_expires_at": objective.expires_at.isoformat(),
        "policy_digest": objective.policy_digest,
        "step_index": action_index,
        "action": action.capability,
        "candidate_sha": observed["candidate_sha"],
        "rollback_sha": observed["rollback_sha"],
        "scope_sha256": observed["scope_sha256"],
        "artifact_sha256": observed["artifact_sha256"],
        "freeze_sha256": observed["freeze_sha256"],
        "hold_sha256": observed["hold_sha256"],
    }
    return verify_derived_step_proof(
        signed_step, pinned_public_key=pinned_public_key,
        expected=expected, at=at, consumed_step_claims=consumed_step_claims,
    )


def require_objective_step_sequence(
    *, action_index: int, verified_prior_steps: frozenset[int],
    total_steps: int,
) -> None:
    """Caller must source prior completions from the existing ROOT journal.

    Do not accept prior-step IDs supplied from a chat, Teams card, API body,
    model output, or unprivileged workboard. A pure sequence result is never
    evidence that the prior step succeeded or an approval to execute the next.
    """
    if (type(action_index) is not int
            or type(total_steps) is not int
            or not 0 <= action_index < total_steps
            or not isinstance(verified_prior_steps, frozenset)
            or any(type(x) is not int for x in verified_prior_steps)
            or verified_prior_steps != frozenset(range(action_index))):
        raise PermissionError("verified root journal sequential completion required")
