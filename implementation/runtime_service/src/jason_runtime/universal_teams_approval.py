"""Universal plan callback over Jason's authenticated Teams gateway (ADR-009).

A signed gateway envelope is transport evidence, not a Microsoft OAuth token and
not execution authority. It is independently reverified here, then rebound to
active Jason identity/authority records. Card fields never supply stored scope.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from connectors.microsoft_graph.teams_approval_ingress import VerifiedMicrosoftPrincipal
from connectors.src.jason_connectors.approval_requests import ApprovalDecision, ApprovalResponse
from jason_openclaw.conversation_ingress import OpenClawTeamsConversationEnvelope
from orchestrator.teams_plan_approval_service import UniversalTeamsPlanApprovalService


@dataclass(frozen=True, slots=True)
class SignedTeamsApprovalEvidenceVerifier:
    authenticator: Any
    allowed_machine_identities: frozenset[str]
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    max_age_seconds: int = 120
    max_clock_skew_seconds: int = 60
    allowed_approval_prefixes: tuple[str, ...] = ("planapproval-",)
    allowed_selection_keys: frozenset[str] = frozenset()

    def parse(self, token: str) -> tuple[str, OpenClawTeamsConversationEnvelope]:
        if not isinstance(token, str) or len(token.encode('utf-8')) > 65536:
            raise PermissionError('bounded signed Teams approval evidence required')
        try:
            raw = json.loads(token)
            if not isinstance(raw, dict):
                raise ValueError('envelope must be an object')
            machine = self.authenticator.authenticate(raw)
            if machine not in self.allowed_machine_identities:
                raise PermissionError('unregistered Teams approval gateway')
            parsed = OpenClawTeamsConversationEnvelope.from_mapping(raw)
        except Exception as exc:
            raise PermissionError('Teams approval signature or envelope is invalid') from exc
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('approval evidence clock must be timezone-aware')
        age = (now - parsed.issued_at).total_seconds()
        if (age < -self.max_clock_skew_seconds or age > self.max_age_seconds
                or parsed.expires_at <= parsed.issued_at or now >= parsed.expires_at):
            raise PermissionError('Teams approval evidence expired or not yet valid')
        if (parsed.approval_submit is None or not any(
                parsed.approval_submit.approval_id.startswith(prefix)
                for prefix in self.allowed_approval_prefixes
        )):
            raise PermissionError('signed approval interaction is outside the configured route')
        if (set(parsed.approval_submit.selections) - self.allowed_selection_keys
                or parsed.documents):
            raise PermissionError('signed approval response contains unreviewed card data')
        return machine, parsed

    def verify(self, token: str) -> VerifiedMicrosoftPrincipal:
        import hashlib
        from jason_openclaw.signed_transport import canonical_signed_payload
        machine, parsed = self.parse(token)
        evidence_hash=hashlib.sha256(canonical_signed_payload(json.loads(token))).hexdigest()
        return VerifiedMicrosoftPrincipal(
            tenant_id=parsed.microsoft_tenant_id, object_id=parsed.microsoft_object_id,
            subject=parsed.microsoft_object_id, audience='jason-runtime:teams-approval',
            issuer='jason-registered-teams-gateway:' + machine,
            # Preserve the exact verified gateway assurance. Never invent MFA/JWT claims.
            authentication_assurance=parsed.authentication_assurance,
            authentication_evidence_hash=evidence_hash,
        )


@dataclass(frozen=True, slots=True)
class RuntimeTeamsApprovalIngress:
    """Rebind cryptographically verified gateway identity to live Jason records."""
    bindings: Any
    identities: Any

    def accept_verified_interaction(self, *, principal: VerifiedMicrosoftPrincipal,
            payload: Mapping[str, str], decided_at: datetime) -> ApprovalResponse:
        principal.validate()
        binding = self.bindings.find(microsoft_tenant_id=principal.tenant_id,
                                     microsoft_object_id=principal.object_id)
        if binding is None or binding.status != 'active':
            raise PermissionError('Teams approver has no active Jason binding')
        identity = self.identities.get(binding.jason_identity_id)
        if identity is None or identity.status != 'active':
            raise PermissionError('Teams approver identity is inactive or absent')
        if identity.organization_id != payload.get('organization_id'):
            raise PermissionError('Teams approver organization mismatch')
        return ApprovalResponse(
            approval_id=payload['approval_id'], organization_id=identity.organization_id,
            approver_identity_id=identity.identity_id,
            decision=ApprovalDecision(payload['decision']), decided_at=decided_at,
            channel='microsoft_teams', channel_response_id=payload['channel_response_id'],
            authentication_evidence_hash=principal.authentication_evidence_hash,
        )


@dataclass(frozen=True, slots=True)
class UniversalTeamsApprovalInteractionFlow:
    """Runtime mapping response contract, not a raw dataclass or arbitrary callback."""
    service: UniversalTeamsPlanApprovalService
    evidence_verifier: SignedTeamsApprovalEvidenceVerifier
    proposals: Any
    requests: Any
    continuation: Any | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    plan_runner: Any | None = None
    issuer: Any | None = None

    def request_approval(self, *, request, identity):
        if self.issuer is None:
            raise RuntimeError('universal approval issuance is not composed')
        return self.issuer.submit_plan(requests=(request,),identity=identity,
            title='Approval required: '+request.capability_name,
            summary='Review the exact action and target below. One decision covers this bounded plan only.',
            production=request.permission_mode not in {'observe','recommend'},ttl_seconds=1800)

    def handle(self, *, approval_id: str, decision: str,
            microsoft_tenant_id: str, microsoft_object_id: str,
            conversation_id: str, channel_response_id: str, decided_at: datetime,
            selections: Mapping[str, str] | None = None,
            signed_envelope: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if signed_envelope is None or selections:
            raise PermissionError('original signed approval evidence required; plan selections are immutable')
        token = json.dumps(dict(signed_envelope), ensure_ascii=False, separators=(',', ':'))
        _, parsed = self.evidence_verifier.parse(token)
        interaction = parsed.approval_submit
        if (interaction.approval_id != approval_id or interaction.decision != decision
                or parsed.microsoft_tenant_id != microsoft_tenant_id
                or parsed.microsoft_object_id != microsoft_object_id
                or parsed.conversation_id != conversation_id
                or interaction.channel_response_id != channel_response_id
                or parsed.issued_at != decided_at):
            raise PermissionError('approval callback does not match signed Teams evidence')
        original = self.requests.require(approval_id)
        proposal = self.proposals.require(approval_id)
        now = self.clock()
        # Require exact immutable, server-owned request fingerprint before consumption.
        self.requests.verify_proposal(proposal)
        principal = self.evidence_verifier.verify(token)
        response = self.service.teams_flow.ingress.accept_verified_interaction(
            principal=principal, payload={'approval_id': approval_id, 'decision': decision,
                'organization_id': original.organization_id, 'channel_response_id': channel_response_id},
            decided_at=now)
        if response.approver_identity_id == original.principal_id:
            raise PermissionError('requester cannot approve their own universal plan')
        # The human must be authorized for every reviewed step, not just the first.
        for step in self.requests.steps(approval_id):
            if not self.service.teams_flow.approval_service.authority.can_approve(
                    approver_identity_id=response.approver_identity_id,
                    organization_id=step.organization_id, client_id=step.client_id,
                    capability=step.capability_name, requested_mode=step.permission_mode):
                raise PermissionError('approver lacks current authority for a reviewed plan step')
        # Store the actual non-bearer signed decision as well as its digest, so a
        # restarted worker re-verifies cryptography instead of trusting an audit label.
        self.requests.store_transport_evidence(principal.authentication_evidence_hash, signed_envelope)
        result = self.service.handle_response(
            token=token, payload={'approval_id': approval_id, 'decision': decision,
                'organization_id': original.organization_id,
                'channel_response_id': channel_response_id},
            original_request=original, proposal=proposal, decided_at=now, now=now,
        )
        accepted = result.accepted_approval
        if accepted.status != 'approved':
            text = ('Changes requested. The plan was not executed.'
                    if accepted.status == 'changes_requested' else 'Denied. The plan was not executed.')
            return {'status': 'completed', 'approval_id': approval_id,
                    'approval_status': accepted.status, 'executed': False, 'reply': {'text': text}}
        if self.plan_runner is not None:
            self.requests.record_progress(approval_id,state='approved',now=now)
            # 'completed' is the existing interaction envelope contract, not
            # provider completion. Keep a distinct queued plan state so deployed
            # gateways finalize the decision without a coupled gateway rollout.
            progress = self.requests.progress(approval_id)
            plan_status = progress['state']
            messages = {
                'approved': 'Approval recorded. Jason has queued the reviewed plan for execution.',
                'running': 'Approval recorded. Jason is executing the reviewed plan.',
                'completed': 'Approval recorded. The reviewed plan has completed successfully.',
                'blocked': 'Approval recorded. The reviewed plan is blocked; Jason recorded the reason.',
                'indeterminate': 'Approval recorded. An execution outcome needs review; Jason will not repeat it without verification.',
                'denied': 'Approval recorded. Current execution controls denied the reviewed plan.',
            }
            if plan_status not in messages:
                raise RuntimeError('approved plan execution state is not recognized')
            # A worker may finish before this callback acknowledges the vote.
            # Report its observed durable state, not a fabricated queued status.
            return {'status': 'completed', 'approval_id': approval_id,
                    'approval_status': 'approved',
                    'plan_status': 'queued' if plan_status == 'approved' else plan_status,
                    'executed': plan_status == 'completed',
                    'reply': {'text': messages[plan_status]}}
        if self.continuation is None:
            return {'status': 'approved', 'approval_id': approval_id, 'executed': False,
                    'reply': {'text': 'Approval recorded. Execution has not started.'}}
        execution = self.continuation.execute(
            approval_id=approval_id, approved_by=accepted.decided_by,
            request=replace(result.resumed_request, approval_id=approval_id),
            channel=accepted.channel, channel_reference_id=accepted.channel_response_id,
        )
        status = execution.status.value
        return {'status': 'completed' if status == 'succeeded' else 'blocked',
                'approval_id': approval_id, 'approval_status': 'approved',
                'executed': status == 'succeeded', 'execution_id': execution.execution_id,
                'reply': {'text': 'Approved action completed.' if status == 'succeeded'
                          else 'Approval recorded. Execution did not complete; Jason recorded the blocker.'}}


@dataclass(frozen=True, slots=True)
class UniversalApprovalPolicyFile:
    """Versioned routing constraints, always subordinate to live JKD-001 grants."""
    path: Any

    def document(self) -> dict:
        from pathlib import Path
        raw = Path(self.path).read_bytes()
        if len(raw) > 65536:
            raise ValueError('approval policy exceeds bounded configuration size')
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get('schema_version') != '1.0'
                or not isinstance(data.get('organizations'), dict)):
            raise ValueError('invalid universal approval policy')
        return data

    def digest(self) -> str:
        import hashlib
        return hashlib.sha256(json.dumps(self.document(), sort_keys=True, separators=(',', ':'),
                                          allow_nan=False).encode()).hexdigest()

    def for_organization(self, organization_id: str) -> dict:
        value = self.document()['organizations'].get(organization_id)
        if not isinstance(value, dict):
            raise PermissionError('no approval policy for organization')
        if (not isinstance(value.get('role_members'), dict)
                or not isinstance(value.get('capability_roles'), dict)
                or type(value.get('max_risk')) is not int
                or value['max_risk'] not in range(4)
                or type(value.get('production_allowed')) is not bool
                or type(value.get('request_retention_allowed')) is not bool
                or type(value.get('max_ttl_seconds')) is not int
                or not 60 <= value['max_ttl_seconds'] <= 86400):
            raise ValueError('approval policy must explicitly constrain roles, risk, retention and lifetime')
        for mapping in ('role_members', 'capability_roles'):
            for key, members in value[mapping].items():
                if not isinstance(key, str) or not key or not isinstance(members, list) or not members:
                    raise ValueError('approval roles must contain explicit nonempty identities')
                if any(not isinstance(m, str) or not m for m in members):
                    raise ValueError('invalid approval role member')
        disabled = value.get('disabled_principals', [])
        if not isinstance(disabled, list) or any(not isinstance(p,str) for p in disabled):
            raise ValueError('invalid disabled approval principal list')
        return value

    def candidates(self, *, organization_id: str, capability: str, requester_id: str) -> tuple[str, ...]:
        from orchestrator.approval_role_routing import TenantApprovalPolicy, route_approval_candidates
        value = self.for_organization(organization_id)
        policy = TenantApprovalPolicy(organization_id,
            {k:frozenset(v) for k,v in value['role_members'].items()},
            {k:frozenset(v) for k,v in value['capability_roles'].items()},
            frozenset(value.get('disabled_principals',[])))
        return route_approval_candidates(policy=policy, organization_id=organization_id,
                                         capability=capability, requester_identity_id=requester_id)


@dataclass(frozen=True, slots=True)
class ConfiguredPlanApprovalAuthority:
    policy: UniversalApprovalPolicyFile
    kernel_checker: Any

    def can_approve(self, *, approver_identity_id: str, organization_id: str,
            client_id: str | None, capability: str, requested_mode: str) -> bool:
        try:
            candidates = self.policy.candidates(organization_id=organization_id,
                                               capability=capability, requester_id='__role_lookup_only__')
            if approver_identity_id not in candidates:
                return False
        except (ValueError, PermissionError):
            return False
        return self.kernel_checker.can_approve(approver_identity_id=approver_identity_id,
            organization_id=organization_id, client_id=client_id,
            capability=capability, requested_mode=requested_mode)


def build_universal_teams_approval_runtime(*, mode: str, database_path, policy_path,
        bindings, identities, grants, formal_approvals, authority,
        authenticator, allowed_machine_identities, orchestrator, governed_execution_ledger,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
    """Compose real durable ports; no monkey-patching, fake token source or grants."""
    if mode == 'off':
        return None
    if mode != 'enforced':
        raise ValueError('universal approval mode must be off or enforced')
    from pathlib import Path
    from connectors.src.jason_connectors.approval_requests import ApprovalRequestService, SQLiteApprovalRequestRepository
    from orchestrator.approval_audit import ApprovalAuditRecorder
    from orchestrator.approval_audit_sqlite import SQLiteApprovalAuditSink
    from orchestrator.approval_continuation import ApprovalExecutionContinuation
    from orchestrator.approval_continuation_guard import SQLiteApprovalContinuationGuard
    from orchestrator.approval_plan_grants import PlanGrantLedger
    from orchestrator.approvals import ApprovalResumeBridge, JKD001ApprovalAuthorityChecker
    from orchestrator.teams_approval_flow import TeamsApprovalFlow
    from orchestrator.teams_plan_proposal_repository import PlanProposalRepository
    from orchestrator.teams_plan_request_repository import PlanRequestRepository
    path = Path(database_path)
    policy = UniversalApprovalPolicyFile(Path(policy_path))
    policy.digest()  # Fail startup closed on missing or invalid activation configuration.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    requests = PlanRequestRepository(path, current_policy_digest=policy.digest)
    proposals = PlanProposalRepository(path)
    ledger = PlanGrantLedger(path)
    pending = SQLiteApprovalRequestRepository(path)
    checker = ConfiguredPlanApprovalAuthority(policy, JKD001ApprovalAuthorityChecker(identities, grants, clock))
    approval_service = ApprovalRequestService(pending, checker)
    verifier = SignedTeamsApprovalEvidenceVerifier(authenticator, frozenset(allowed_machine_identities), clock)
    audit_sink = SQLiteApprovalAuditSink(str(path))
    audit_sink.initialize()
    audit = ApprovalAuditRecorder(audit_sink)
    flow = TeamsApprovalFlow(verifier, RuntimeTeamsApprovalIngress(bindings,identities),
        approval_service, ApprovalResumeBridge(formal_approvals,authority),audit)
    continuation_guard = SQLiteApprovalContinuationGuard(str(path))
    continuation_guard.initialize()
    continuation = ApprovalExecutionContinuation(orchestrator,audit,continuation_guard,clock=clock)
    from .universal_plan_continuation import UniversalPlanContinuationMaintenance
    service=UniversalTeamsPlanApprovalService(flow,ledger)
    runner=UniversalPlanContinuationMaintenance(service,proposals,requests,continuation,policy,governed_execution_ledger,clock)
    handler = UniversalTeamsApprovalInteractionFlow(service,verifier,proposals,requests,continuation,clock,runner)
    return handler
