"""Create and deliver exactly reviewed universal plans through existing trust ports.

Issuance is not approval. Live requester grants are required before a card exists;
recipient policy is intersected with live approver grants for every bounded step.
Only server-owned immutable request material is retained, under explicit policy.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from typing import Any, Callable
from uuid import uuid4

from connectors.src.jason_connectors.approval_requests import ApprovalRequest, ApprovalPresentation
from kernel.capabilities import CapabilityLifecycle
from kernel.identity_authority import AuthorityOutcome, AuthorityRequest, PermissionMode
from orchestrator.approval_delivery import ApprovalDeliveryReceipt, ApprovalRequestDeliveryCoordinator
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.contracts import OrchestrationRequest
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from orchestrator.teams_plan_request_repository import plan_fingerprint, request_material

_RISK={'low':0,'medium':1,'high':2,'critical':3}


@dataclass(frozen=True,slots=True)
class ExistingTeamsApprovalDelivery:
    """Reuse the existing configured gateway sender, never a second Teams client."""
    gateway_url: str
    token_file: Any
    bindings: Any
    sender_factory: Any = None
    clock: Callable[[],datetime] = lambda:datetime.now(timezone.utc)

    def deliver(self, request: ApprovalRequest) -> ApprovalDeliveryReceipt:
        from .playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
        factory=self.sender_factory or TeamsGatewayPlaybookApprovalSender
        sender=factory(gateway_url=self.gateway_url,token_file=self.token_file,
            bindings=self.bindings,owner_identity_ids=request.authorized_approver_ids)
        message_ids=sender.send(request)
        if not message_ids or len(message_ids)!=len(request.authorized_approver_ids):
            raise RuntimeError('approval delivery did not confirm every selected recipient')
        return ApprovalDeliveryReceipt('microsoft_teams',','.join(message_ids),self.clock())


@dataclass(frozen=True,slots=True)
class UniversalPlanIssuer:
    handler: Any
    policy: Any
    authority: Any
    capabilities: Any
    bindings: Any
    delivery: Any
    clock: Callable[[],datetime] = lambda:datetime.now(timezone.utc)
    approval_id_factory: Callable[[],str] = lambda:'planapproval-'+uuid4().hex

    def submit_plan(self, *, requests: tuple[OrchestrationRequest,...], identity,
                    title: str, summary: str, production: bool,
                    ttl_seconds: int = 1800) -> dict:
        if not 1<=len(requests)<=32:
            raise ValueError('approval plan requires one to 32 explicit steps')
        now=self.clock()
        if now.tzinfo is None or type(production) is not bool:
            raise ValueError('approval plan requires explicit production classification and aware time')
        if (not isinstance(title,str) or not 1<=len(title)<=180
                or not isinstance(summary,str) or not 1<=len(summary)<=1200):
            raise ValueError('bounded approval title and summary required')
        if identity.authentication_assurance!='botframework-authenticated':
            raise PermissionError('authenticated Teams requester required')
        binding=self.bindings.find(microsoft_tenant_id=identity.microsoft_tenant_id,
                                   microsoft_object_id=identity.microsoft_object_id)
        first=requests[0]
        if binding is None or binding.status!='active' or binding.jason_identity_id!=first.principal_id:
            raise PermissionError('requester does not match active Teams identity binding')
        policy=self.policy.for_organization(first.organization_id)
        if not policy['request_retention_allowed']:
            raise PermissionError('approval policy has not authorized request-material retention')
        if production and not policy['production_allowed']:
            raise PermissionError('production work is outside configured approval policy')
        if type(ttl_seconds) is not int or not 60<=ttl_seconds<=policy['max_ttl_seconds']:
            raise PermissionError('approval lifetime exceeds configured policy')
        pinned=[]
        eligible=None
        for request in requests:
            if request.principal_id!=first.principal_id or request.organization_id!=first.organization_id:
                raise PermissionError('approval plan cannot mix requesters or organizations')
            cap=self.capabilities.get_current(capability_name=request.capability_name,allow_pilot=True)
            if cap.lifecycle_status not in {CapabilityLifecycle.ACTIVE,CapabilityLifecycle.PILOT}:
                raise PermissionError('approval plan capability is not executable')
            if request.capability_version is not None and request.capability_version!=cap.version:
                raise PermissionError('approval proposal uses stale capability version')
            if request.requested_mode not in cap.permitted_execution_modes:
                raise PermissionError('execution strategy is outside registered capability contract')
            risk=cap.risk_level.value
            if risk not in _RISK or _RISK[risk]>policy['max_risk']:
                raise PermissionError('registered capability risk exceeds approval policy')
            decision=self.authority.evaluate(AuthorityRequest(
                request_id=request.execution_id,correlation_id=request.correlation_id,
                principal_id=request.principal_id,organization_id=request.organization_id,
                client_id=request.client_id,capability=request.capability_name,
                requested_mode=PermissionMode(request.permission_mode),
                authentication_assurance=identity.authentication_assurance))
            if decision.outcome not in {AuthorityOutcome.ALLOWED,AuthorityOutcome.APPROVAL_REQUIRED}:
                raise PermissionError('requester lacks authority for reviewed plan step')
            # Explicit versioned retention policy allows the minimum reviewed material;
            # request_material rejects embedded credentials rather than retaining them.
            normalized=replace(request,capability_version=cap.version,risk=risk,
                authority_allowed=False,approval_present=False,authority_context_id=None,approval_id=None,
                allow_pilot_capability=cap.lifecycle_status is CapabilityLifecycle.PILOT,
                allow_pilot_provider=cap.lifecycle_status is CapabilityLifecycle.PILOT,
                data_handling=replace(request.data_handling,retention_allowed=True),
                idempotency_key=(request.idempotency_key or ('plan-'+request.execution_id)
                                 if cap.idempotency_key_required else request.idempotency_key))
            request_material(normalized)
            pinned.append(normalized)
            candidates=set(self.policy.candidates(organization_id=request.organization_id,
                capability=request.capability_name,requester_id=request.principal_id))
            candidates={actor for actor in candidates if self.handler.service.teams_flow.approval_service.authority.can_approve(
                approver_identity_id=actor,organization_id=request.organization_id,client_id=request.client_id,
                capability=request.capability_name,requested_mode=request.permission_mode)}
            eligible=candidates if eligible is None else eligible & candidates
        if not eligible:
            raise PermissionError('no configured approver has current authority for every plan step')
        # Resolve every recipient before creating/sending anything: no cross-tenant
        # routing based on an email string or a client-editable card field.
        for actor in eligible:
            recipient=self.bindings.find_active_by_jason_identity(jason_identity_id=actor)
            if recipient is None or recipient.status!='active' or recipient.microsoft_tenant_id!=identity.microsoft_tenant_id:
                raise PermissionError('approver delivery binding is unavailable or outside request tenant')
        pinned=tuple(pinned)
        first=pinned[0]
        approval_id=self.approval_id_factory()
        if not approval_id.startswith('planapproval-') or len(approval_id)>256:
            raise ValueError('bounded universal approval identifier required')
        scope=ApprovedPlanScope('plan-'+approval_id,first.organization_id,self.policy.digest(),
            frozenset(r.capability_name for r in pinned),
            frozenset(r.client_id for r in pinned if r.client_id is not None),
            max(_RISK[r.risk] for r in pinned),production,now+timedelta(seconds=ttl_seconds))
        fingerprint=plan_fingerprint(pinned,scope)
        proposal=ServerOwnedPlanProposal(approval_id,first.organization_id,first.client_id,
            first.principal_id,first.capability_name,fingerprint,scope)
        # Evidence on the card describes exact reviewed parameters, bounded/redacted
        # before retention. No capability selection or target parameters come back in
        # the approval response; the original server-owned manifest is authoritative.
        facts=[('Plan fingerprint',fingerprint),('Steps',str(len(pinned))),
               ('Highest risk',max(pinned,key=lambda r:_RISK[r.risk]).risk),
               ('Production','Yes' if production else 'No')]
        for index,request in enumerate(pinned,1):
            detail=json.dumps(request.arguments,sort_keys=True,separators=(',',':'),ensure_ascii=False)
            if len(detail)>600:
                raise ValueError('reviewed step parameters exceed card review bound; attach an approved immutable evidence artifact')
            facts.append((f'Step {index}',request.capability_name+'@'+request.capability_version+' '+detail))
        # Match the reviewed protected-release V2 lane: every universal plan
        # approval binds its Teams click to an unguessable, one-use issued card.
        # Callback verification is independently enforced before any grant.
        card_challenge = secrets.token_hex(24)
        pending=ApprovalRequest(approval_id,first.execution_id,first.correlation_id,
            first.organization_id,first.client_id,first.principal_id,first.capability_name,
            first.permission_mode,now,scope.expires_at,tuple(sorted(eligible)),
            presentation=ApprovalPresentation(title,summary,tuple(facts)),
            metadata={
                'plan_fingerprint':fingerprint,'plan_id':scope.plan_id,
                'policy_digest':scope.policy_digest,
                'card_instance_challenge':card_challenge,
                'card_instance_challenge_sha256':hashlib.sha256(
                    card_challenge.encode('ascii')).hexdigest(),
            })
        self.handler.requests.store(proposal,pinned,now=now)
        self.handler.proposals.store(proposal)
        self.handler.requests.record_progress(approval_id,state='awaiting_approval',now=now)
        coordinator=ApprovalRequestDeliveryCoordinator(self.handler.service.teams_flow.approval_service,
            self.handler.service.teams_flow.audit,self.delivery)
        try:
            receipt=coordinator.create_and_deliver(pending,now=now)
        except Exception as exc:
            # A partial/unknown delivery is observable and not automatically resent.
            # A valid delivered card can still be decided safely; callback revalidates.
            self.handler.requests.record_progress(approval_id,state='blocked',now=self.clock(),
                reason_code='approval_delivery_'+type(exc).__name__)
            raise
        return {'approval_id':approval_id,'status':'awaiting_approval','delivered':True,
                'delivery_reference':receipt.channel_reference_id,'plan_fingerprint':fingerprint}
