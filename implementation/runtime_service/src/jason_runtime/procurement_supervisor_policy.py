"""Versioned supervisor thresholds for the existing procurement Teams approver.

Not an approval engine: the canonical ApprovalRequestService remains the only
actor allowed to issue/consume a procurement Approve or Deny receipt. Config
alone grants no spending authority or provider mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


class SupervisorPolicyError(ValueError):
    pass


PURCHASE_TYPES = frozenset({'it', 'copy_print', 'other'})


def money(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise SupervisorPolicyError('monetary amount must be an exact decimal')
    try:
        amount=Decimal(str(value))
    except InvalidOperation as exc:
        raise SupervisorPolicyError('invalid monetary amount') from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise SupervisorPolicyError('money requires nonnegative cents and finite value')
    return amount.quantize(Decimal('0.01'))


def identity(value: Any) -> str:
    if not isinstance(value,str) or not value.strip() or len(value)>160 or value!=value.strip():
        raise SupervisorPolicyError('invalid canonical identity reference')
    return value


@dataclass(frozen=True,slots=True)
class SpendingRule:
    requester_id: str | None
    role: str | None
    purchase_type: str
    maximum_without_approval: Decimal
    designated_supervisor_ids: tuple[str,...]
    escalation_owner_ids: tuple[str,...]
    ttl_minutes: int


@dataclass(frozen=True,slots=True)
class SpendingDecision:
    requires_approval: bool
    threshold: Decimal
    approver_ids: tuple[str,...]
    policy_digest: str
    rule_key: str
    reason: str
    fallback_approver_ids: tuple[str,...]
    ttl_minutes: int


@dataclass(frozen=True,slots=True)
class SupervisorSpendingPolicy:
    rules: tuple[SpendingRule,...]
    canonical_digest: str
    policy_version: str
    role_memberships: tuple[tuple[str,tuple[str,...]],...]

    @classmethod
    def load(cls, path: Path) -> 'SupervisorSpendingPolicy':
        return cls.from_mapping(json.loads(path.read_text(encoding='utf-8')))

    @classmethod
    def from_mapping(cls, raw: Mapping[str,Any]) -> 'SupervisorSpendingPolicy':
        if (not isinstance(raw,dict) or set(raw)!={'schema_version','policy_version','rules','role_memberships'}
                or raw['schema_version']!='1.0'
                or not isinstance(raw['policy_version'],str)
                or not raw['policy_version'].strip()
                or not isinstance(raw['rules'],list)):
            raise SupervisorPolicyError('reviewed supervisor policy v1 required')
        memberships=raw['role_memberships']
        if not isinstance(memberships,dict):
            raise SupervisorPolicyError('reviewed role membership mapping required')
        configured=[]
        for role,users in memberships.items():
            role=identity(role)
            if not isinstance(users,list) or not users:
                raise SupervisorPolicyError('roles require explicitly bound identities')
            resolved=tuple(identity(user) for user in users)
            if len(set(resolved))!=len(resolved):
                raise SupervisorPolicyError('duplicate role member')
            configured.append((role,resolved))
        result=[]; keys=set()
        for row in raw['rules']:
            expected={'requester_id','role','purchase_type','maximum_without_approval',
                      'designated_supervisor_ids','escalation_owner_ids','ttl_minutes'}
            if not isinstance(row,dict) or set(row)!=expected:
                raise SupervisorPolicyError('supervisor rule has unreviewed fields')
            requester=identity(row['requester_id']) if row['requester_id'] is not None else None
            role=identity(row['role']) if row['role'] is not None else None
            if (requester is None)==(role is None):
                raise SupervisorPolicyError('rule must select exactly one requester or role')
            purchase_type=row['purchase_type']
            if purchase_type not in PURCHASE_TYPES:
                raise SupervisorPolicyError('unknown purchase type is not granted authority')
            supervisors=row['designated_supervisor_ids'];owners=row['escalation_owner_ids']
            if (not isinstance(supervisors,list) or not isinstance(owners,list)
                    or not supervisors or not owners):
                raise SupervisorPolicyError('explicit supervisor and escalation identities required')
            targets=tuple(identity(x) for x in supervisors)
            fallback=tuple(identity(x) for x in owners)
            if len(set(targets+fallback))!=len(targets+fallback):
                raise SupervisorPolicyError('duplicate supervisors or fallback identities')
            ttl=row['ttl_minutes']
            if type(ttl) is not int or not 5<=ttl<=1440:
                raise SupervisorPolicyError('approval timeout outside reviewed bounds')
            key=(requester or '',role or '',purchase_type)
            if key in keys:
                raise SupervisorPolicyError('ambiguous rule for requester, role and purchase type')
            keys.add(key)
            result.append(SpendingRule(requester_id=requester,role=role,purchase_type=purchase_type,
                maximum_without_approval=money(row['maximum_without_approval']),
                designated_supervisor_ids=targets,escalation_owner_ids=fallback,ttl_minutes=ttl))
        digest=sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        return cls(tuple(result),digest,raw['policy_version'],tuple(sorted(configured)))

    def roles_for(self, requester_id: str) -> tuple[str,...]:
        requester_id=identity(requester_id)
        return tuple(role for role,members in self.role_memberships if requester_id in members)

    def decide_from_reviewed_identities(self, *, requester_id: str, purchase_type: str,
            amount: Decimal, autotask_contact_udf_limit: Decimal) -> SpendingDecision:
        # Roles are resolved only from reviewed canonical Jason identities.
        # Untrusted Teams card selections may never grant additional spending.
        return self.decide(requester_id=requester_id,
            authoritative_roles=self.roles_for(requester_id),
            purchase_type=purchase_type, amount=amount,
            autotask_udf_limit=autotask_contact_udf_limit)

    @property
    def allowed_approver_ids(self) -> frozenset[str]:
        return frozenset(x for r in self.rules for x in r.designated_supervisor_ids+r.escalation_owner_ids)

    def decide(self, *, requester_id: str, authoritative_roles: tuple[str,...],
            purchase_type: str, amount: Decimal, autotask_udf_limit: Decimal) -> SpendingDecision:
        requester_id=identity(requester_id)
        if purchase_type not in PURCHASE_TYPES:
            raise SupervisorPolicyError('unknown purchase type requires manual review')
        if any(identity(role)!=role for role in authoritative_roles):
            raise SupervisorPolicyError('invalid authenticated role')
        amount=money(amount);udf=money(autotask_udf_limit)
        matched=[r for r in self.rules if r.purchase_type==purchase_type and
                 (r.requester_id==requester_id or (r.role is not None and r.role in authoritative_roles))]
        individual=[r for r in matched if r.requester_id==requester_id]
        if individual:matched=individual
        if len(matched)!=1:
            raise SupervisorPolicyError('missing or ambiguous supervisor authority; Human Review required')
        selected=matched[0]
        threshold=min(udf,selected.maximum_without_approval)
        requires=amount>threshold
        supervisors=tuple(s for s in selected.designated_supervisor_ids if s!=requester_id)
        owners=tuple(s for s in selected.escalation_owner_ids if s!=requester_id)
        if requires and not supervisors:
            raise SupervisorPolicyError('requester is the only configured supervisor; no self approval')
        if requires and not owners:
            raise SupervisorPolicyError('no distinct fallback approver')
        return SpendingDecision(requires,threshold,supervisors if requires else (),
            self.canonical_digest,(selected.requester_id or selected.role or '')+':'+purchase_type,
            'supervisor_required' if requires else 'within_delegated_spending_authority',
            owners if requires else (),selected.ttl_minutes)

    def revalidate(self, *, digest: str) -> None:
        if not isinstance(digest,str) or digest!=self.canonical_digest:
            raise PermissionError('supervisor policy changed; previous approval invalid')


def require_signed_purchase_approval(*, service: Any, approval_id: str,
                                     submission: Mapping[str, Any]) -> Any:
    """Reusable, canonical signed Teams approval receipt guard for PO/parts.

    The same immutable ApprovalRequestService used for production-style cards
    is required. A bare approval ID or local record cannot grant write access.
    """
    from connectors.src.jason_connectors.approval_requests import ApprovalRequestStatus
    if not approval_id or service is None:
        raise PermissionError('canonical signed Teams purchase approval required')
    repository = service.repository
    request = repository.get(approval_id)
    fetch = getattr(repository,'accepted_decision',None)
    receipt = fetch(approval_id) if callable(fetch) else None
    if (request is None or request.status is not ApprovalRequestStatus.APPROVED
            or request.capability != 'procurement.submission.execute'
            or request.organization_id != 'aot' or request.client_id is not None
            or request.requested_mode != 'purchase'
            or request.requested_by != submission.get('requester_principal_id')
            or request.metadata.get('submission_id') != submission.get('submission_id')
            or request.metadata.get('submission_digest') != submission.get('digest')
            or request.metadata.get('supervisor_policy_digest')
                != str(submission.get('supervisor_policy_digest') or 'owner-udf-only')
            or receipt is None or receipt.status != 'approved'
            or receipt.decided_by == request.requested_by
            or receipt.decided_by not in request.authorized_approver_ids
            or receipt.channel != 'microsoft_teams'
            or not receipt.authentication_evidence_hash):
        raise PermissionError('canonical signed Teams purchase approval receipt not verified')
    return receipt
