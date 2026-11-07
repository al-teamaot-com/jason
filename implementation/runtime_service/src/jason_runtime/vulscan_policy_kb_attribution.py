"""Prove KB-specific decisions for assigned Datto patch policies.

A device's effective installStatus does NOT identify which of its assigned
global/site policies blocked an update; device overrides may also apply.
Only an independent, complete, governed source can attest causal policy/KB
decisions. Missing attribution is not a reason to invent policy impact.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Collection
import re

_UID = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_KB = re.compile(r"^KB[0-9]{5,9}$")
_STATES = frozenset({"NOT_APPROVED", "APPROVED_PENDING", "NOT_APPLICABLE"})
_MAX_AGE = timedelta(minutes=15)


class PolicyKBAttributionUnavailable(ValueError):
    """Provider-specific policy causation could not be established."""


@dataclass(frozen=True, slots=True)
class VerifiedPolicyKBAttribution:
    kb: str
    client_id: str
    site_uid: str
    device_uid: str
    # Complete and explicit decision for every assigned policy, not just a
    # list of policy assignments or an aggregate device installStatus.
    policy_states: tuple[tuple[str, str], ...]
    source_reference: str
    observed_at: datetime
    full_scope_verified: bool


def verified_unapproved_policy_ids(
    evidence: Any, *, kb: str, client_id: str, site_uid: str,
    device_uid: str, assigned_policy_ids: Collection[str], now: datetime,
) -> tuple[str, ...]:
    """Fail closed unless each assigned policy has an exact current KB status."""
    if not isinstance(evidence, VerifiedPolicyKBAttribution):
        raise PolicyKBAttributionUnavailable("governed per-policy KB evidence missing")
    if (evidence.kb != kb or evidence.client_id != client_id
            or evidence.site_uid != site_uid
            or evidence.device_uid != device_uid
            or not _KB.fullmatch(kb)):
        raise PolicyKBAttributionUnavailable("per-policy KB source identity mismatch")
    if (evidence.full_scope_verified is not True
            or not isinstance(evidence.source_reference, str)
            or not 0 < len(evidence.source_reference.strip()) <= 250):
        raise PolicyKBAttributionUnavailable("per-policy KB source not complete")
    if (not isinstance(evidence.observed_at, datetime)
            or evidence.observed_at.tzinfo is None or now.tzinfo is None):
        raise PolicyKBAttributionUnavailable("per-policy KB evidence clock unavailable")
    age = now - evidence.observed_at
    if age < timedelta(0) or age > _MAX_AGE:
        raise PolicyKBAttributionUnavailable("per-policy KB source is stale or future dated")

    if (not isinstance(evidence.policy_states, tuple)
            or not 0 < len(evidence.policy_states) <= 200
            or not all(isinstance(x, tuple) and len(x) == 2
                       and isinstance(x[0], str) and isinstance(x[1], str)
                       and _UID.fullmatch(x[0]) and x[1] in _STATES
                       for x in evidence.policy_states)):
        raise PolicyKBAttributionUnavailable("per-policy KB decision set invalid")
    ids = [pair[0] for pair in evidence.policy_states]
    if len(ids) != len(set(ids)):
        raise PolicyKBAttributionUnavailable("duplicate per-policy KB decision")
    assigned = set(assigned_policy_ids)
    if not assigned or set(ids) != assigned:
        raise PolicyKBAttributionUnavailable("per-policy KB decision coverage incomplete")
    unapproved = tuple(sorted(
        policy_id for policy_id, state in evidence.policy_states
        if state == "NOT_APPROVED"
    ))
    if not unapproved:
        # Aggregate NOT_APPROVED can originate at the device override layer.
        # Until its identity is attested, no policy can be blamed for it.
        raise PolicyKBAttributionUnavailable(
            "effective NOT_APPROVED patch has no verified policy attribution")
    return unapproved
