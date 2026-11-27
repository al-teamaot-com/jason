"""Resolve contact Supervisor emails through existing governed read/binding ports.

The contact relationship routes a request; it does not grant authority. Every
candidate must independently exist in the current approved approver set.
"""
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Callable, Mapping

from .procurement_supervisor_policy import money


@dataclass(frozen=True)
class SupervisorContactRoute:
    approvers: tuple[str, ...]
    evidence_digest: str
    reason: str


def resolve_supervisor_contacts(*, requester_id: str, requester_contact: Mapping[str, Any],
        amount: Decimal, fallback_id: str, allowed_approvers: frozenset[str],
        lookup_contact: Callable[[str], Mapping[str, Any] | None],
        resolve_identity: Callable[[str], str | None],
        udf: Callable[[Mapping[str, Any], str], Any], max_depth: int = 20) -> SupervisorContactRoute:
    if fallback_id == requester_id or fallback_id not in allowed_approvers:
        raise PermissionError("no distinct authorized fallback approver")
    required = money(amount)
    company_id = requester_contact.get("companyID")
    if company_id is None:
        raise PermissionError("requester contact company is unknown")
    visited = {requester_contact.get("id")}
    chain = []
    evidence = []
    current = requester_contact
    reason = "supervisor_chain"
    for _ in range(max_depth):
        email = str(udf(current, "Supervisor") or "").strip().casefold()
        if not email:
            reason = "supervisor_missing"
            break
        if email.count("@") != 1 or any(c.isspace() for c in email):
            reason = "supervisor_email_invalid"
            break
        contact = lookup_contact(email)
        if (not contact or contact.get("companyID") != company_id
                or contact.get("isActive") not in (True, 1)
                or str(contact.get("emailAddress") or "").strip().casefold() != email):
            reason = "supervisor_unavailable_or_ambiguous"
            break
        contact_id = contact.get("id")
        if not contact_id or contact_id in visited:
            reason = "supervisor_cycle"
            break
        visited.add(contact_id)
        identity = resolve_identity(email)
        try:
            limit = money(udf(contact, "Spending limit"))
        except ValueError:
            limit = None
        evidence.append({"contact_id": contact_id, "identity": identity,
                         "limit": str(limit) if limit is not None else None})
        if (identity in allowed_approvers and identity not in (requester_id, fallback_id)
                and identity not in chain and limit is not None and required <= limit):
            chain.append(identity)
        current = contact
    else:
        reason = "supervisor_depth_exceeded"
    # Loop/ambiguous relationships cannot silently choose an intermediate user.
    if reason in {"supervisor_cycle", "supervisor_depth_exceeded",
                  "supervisor_unavailable_or_ambiguous", "supervisor_email_invalid"}:
        chain = []
    chain.append(fallback_id)
    fingerprint = sha256(json.dumps({"requester": requester_id, "company": company_id,
        "amount": str(required), "chain": chain, "evidence": evidence, "reason": reason},
        sort_keys=True).encode()).hexdigest()
    return SupervisorContactRoute(tuple(chain), fingerprint, reason)
