"""Persisted plan continuation using existing JKD and Central Orchestrator gates.

No free-running agent or parallel release manager is introduced. This maintenance
port runs in Jason's existing isolated maintenance process. Scheduling state is
not authority: the atomic human decision, immutable manifest, live grants, and
plan ledger are independently checked before each exact step.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import json
import sqlite3
from typing import Any, Callable

from orchestrator.approval_audit import ApprovalAuditEventType, ApprovalAuditRecorder
from orchestrator.approval_plan_scope import ProposedPlanStep
from orchestrator.teams_approval_flow import TeamsApprovalFlowResult
from orchestrator.teams_plan_grant_bridge import record_verified_teams_plan_grant

logger = logging.getLogger(__name__)
_RISK = {'low':0,'medium':1,'high':2,'critical':3}


@dataclass
class UniversalPlanContinuationMaintenance:
    service: Any
    proposals: Any
    requests: Any
    continuation: Any
    policy: Any
    execution_ledger: Any
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    interval_seconds: int = 5
    _next_due: datetime | None = field(default=None,init=False)

    def tick(self) -> bool:
        now=self.clock()
        if self._next_due is not None and now < self._next_due:
            return False
        self._next_due=now+timedelta(seconds=self.interval_seconds)
        for approval_id in self.requests.candidate_ids(limit=32):
            self.process(approval_id)
            return True  # One bounded plan per maintenance iteration.
        return False

    def _progress(self, approval_id, state, *, completed=0, execution_id=None, reason=None):
        self.requests.record_progress(approval_id,state=state,now=self.clock(),
            completed_steps=completed,current_execution_id=execution_id,reason_code=reason)
        logger.info('UNIVERSAL_PLAN state=%s approval_id=%s completed_steps=%s execution_id=%s reason=%s',
                    state,approval_id,completed,execution_id,reason)

    def _require_policy(self, proposal, accepted, steps):
        policy=self.policy.for_organization(proposal.organization_id)
        if (not policy['request_retention_allowed'] or proposal.scope.max_risk > policy['max_risk']
                or (proposal.scope.production_allowed and not policy['production_allowed'])):
            raise PermissionError('reviewed plan exceeds configured approval policy')
        pending=self.service.teams_flow.approval_service.repository.get(proposal.approval_id)
        if (pending is None or proposal.scope.expires_at > pending.requested_at+timedelta(seconds=policy['max_ttl_seconds'])
                or self.clock() >= accepted.expires_at or self.clock() >= proposal.scope.expires_at):
            raise PermissionError('plan approval expired or exceeds configured lifetime')
        if accepted.decided_by == proposal.requester_id:
            raise PermissionError('requester cannot approve their own plan')
        checker=self.service.teams_flow.approval_service.authority
        for step in steps:
            if not checker.can_approve(approver_identity_id=accepted.decided_by,
                    organization_id=step.organization_id,client_id=step.client_id,
                    capability=step.capability_name,requested_mode=step.permission_mode):
                raise PermissionError('plan approver authority was revoked or does not cover every step')

    def _require_or_recover_grant(self, proposal, accepted, first):
        ledger=self.service.ledger
        receipt=ledger.decision_receipt(proposal.approval_id)
        if receipt is None:
            # Crash recovery consumes a persisted, validated atomic decision, not a
            # new synthetic approval. Every live authority check still runs.
            resumed=self.service.teams_flow.resume_bridge.resume(
                original_request=first,accepted=accepted,
                authentication_assurance='botframework-authenticated')
            self.service.teams_flow._record(
                event_type=ApprovalAuditEventType.JKD_REAUTHORIZED,
                approval_id=accepted.approval_id,original_request=first,occurred_at=self.clock(),
                actor_identity_id=accepted.decided_by,channel=accepted.channel,
                channel_reference_id=accepted.channel_response_id,
                authority_context_id=resumed.authority_context_id,
                metadata={'recovery_source':'atomic_decision_receipt'})
            try:
                record_verified_teams_plan_grant(result=TeamsApprovalFlowResult(accepted,resumed),
                    proposal=proposal,ledger=ledger,decided_at=accepted.decided_at)
            except sqlite3.IntegrityError:
                pass  # A concurrent identical recovery must still pass the comparison below.
            receipt=ledger.decision_receipt(proposal.approval_id)
        if (receipt is None or receipt['revoked_at'] is not None
                or receipt['plan_id'] != proposal.scope.plan_id
                or receipt['approver_identity_id'] != accepted.decided_by
                or receipt['plan_fingerprint'] != proposal.plan_fingerprint
                or datetime.fromisoformat(receipt['decided_at']) != accepted.decided_at):
            raise PermissionError('plan decision ledger does not match the persisted human decision')

    def process(self, approval_id: str) -> None:
        stage='decision_validation'
        completed=0
        current_execution_id=None
        try:
            accepted=self.service.teams_flow.approval_service.repository.accepted_decision(approval_id)
            if accepted is None:
                raise PermissionError('no atomic approval decision receipt')
            if accepted.status != 'approved':
                self._progress(approval_id,'denied',reason=accepted.status)
                return
            proposal=self.proposals.require(approval_id)
            # Recovery must retain the original authenticated evidence chain; a
            # terminal status or a forged scheduling row is never authorization.
            events=self.service.teams_flow.audit.sink.list_for_approval(
                approval_id=approval_id,organization_id=proposal.organization_id)
            if (accepted.channel != 'microsoft_teams' or not accepted.authentication_evidence_hash
                    or not ApprovalAuditRecorder.verify_chain(events)
                    or not any(e.event_type is ApprovalAuditEventType.RESPONSE_AUTHENTICATED
                        and e.request_id==accepted.request_id
                        and e.metadata.get('authentication_evidence_hash')==accepted.authentication_evidence_hash
                        and e.metadata.get('authentication_assurance')=='botframework-authenticated'
                        for e in events)
                    or not any(e.event_type is ApprovalAuditEventType.RESPONSE_ACTOR_BOUND
                        and e.request_id==accepted.request_id and e.actor_identity_id==accepted.decided_by
                        and e.channel_reference_id==accepted.channel_response_id
                        and e.metadata.get('authentication_evidence_hash')==accepted.authentication_evidence_hash
                        for e in events)):
                raise PermissionError('atomic decision lacks matching verified Teams audit evidence')
            signed=self.requests.transport_evidence(accepted.authentication_evidence_hash)
            # A signed bot activity alone is not independently verified human
            # authorization. Require its separate recorded user-token proof.
            self.requests.require_verified_human_evidence(
                approval_id,accepted.authentication_evidence_hash)
            # Evaluate original transport freshness at the persisted decision time,
            # while current plan expiry/revocation/identity are separately rechecked.
            verifier=replace(self.service.teams_flow.token_verifier,clock=lambda:accepted.decided_at)
            token=json.dumps(signed,sort_keys=True,separators=(',',':'))
            _,parsed=verifier.parse(token)
            principal=verifier.verify(token)
            interaction=parsed.approval_submit
            if (principal.authentication_evidence_hash!=accepted.authentication_evidence_hash
                    or interaction.approval_id!=approval_id or interaction.decision!='approve'
                    or interaction.channel_response_id!=accepted.channel_response_id):
                raise PermissionError('persisted signature does not prove this human approval')
            actor=self.service.teams_flow.ingress.accept_verified_interaction(
                principal=principal,payload={'approval_id':approval_id,'decision':'approve',
                    'organization_id':proposal.organization_id,'channel_response_id':accepted.channel_response_id},
                decided_at=accepted.decided_at)
            if actor.approver_identity_id!=accepted.decided_by:
                raise PermissionError('persisted Teams approver binding changed')
            self.requests.verify_proposal(proposal)
            steps=self.requests.steps(approval_id)
            self._require_policy(proposal,accepted,steps)
            self._require_or_recover_grant(proposal,accepted,steps[0])
            for original in steps:
                current_execution_id=original.execution_id
                prior=self.requests.step_result(approval_id,current_execution_id)
                if prior is not None:
                    if prior['status'] != 'succeeded':
                        self._progress(approval_id,'blocked',completed=completed,
                            execution_id=current_execution_id,reason='prior_step_not_successful')
                        return
                    completed+=1
                    continue
                stage='step_reauthorization'
                # Current policy and actor authority are rechecked between steps.
                self.requests.verify_proposal(proposal)
                self._require_policy(proposal,accepted,(original,))
                scope=proposal.scope
                self.service.ledger.require_grant(
                    ProposedPlanStep(scope.plan_id,original.organization_id,scope.policy_digest,
                        original.capability_name,original.client_id,_RISK[original.risk],scope.production_allowed),
                    plan_fingerprint=proposal.plan_fingerprint,now=self.clock())
                child_id='planstep-'+hashlib.sha256(
                    (approval_id+'|'+original.execution_id+'|'+proposal.plan_fingerprint).encode()).hexdigest()
                reservation=self.execution_ledger.reserve_approved_plan_step(
                    approval_id=child_id,parent_approval_id=approval_id,
                    plan_fingerprint=proposal.plan_fingerprint,request=original,
                    expires_at=min(accepted.expires_at,proposal.scope.expires_at))
                original=replace(original,idempotency_key=reservation.idempotency_key)
                child=replace(accepted,approval_id=child_id,request_id=original.execution_id,
                    capability=original.capability_name,client_id=original.client_id,
                    organization_id=original.organization_id,requested_by=original.principal_id)
                resumed=self.service.teams_flow.resume_bridge.resume(original_request=original,
                    accepted=child,authentication_assurance='botframework-authenticated')
                self.service.teams_flow._record(event_type=ApprovalAuditEventType.JKD_REAUTHORIZED,
                    approval_id=child_id,original_request=original,occurred_at=self.clock(),
                    actor_identity_id=accepted.decided_by,channel=accepted.channel,
                    channel_reference_id=accepted.channel_response_id,authority_context_id=resumed.authority_context_id,
                    metadata={'parent_approval_id':approval_id,'plan_fingerprint':proposal.plan_fingerprint})
                # A post-provider crash may have lost the plan's small receipt,
                # while the canonical execution ledger still proves completion.
                # Recover that exact result without invoking the provider again.
                replay=self.execution_ledger.check_intent(resumed).replay_result
                if replay is not None:
                    self.requests.record_step_result(approval_id,replay,now=self.clock())
                    if replay.status.value != 'succeeded':
                        raise PermissionError('canonical prior execution was not successful')
                    completed+=1
                    continue
                self._progress(approval_id,'running',completed=completed,execution_id=current_execution_id)
                stage='step_execution'
                result=self.continuation.execute(approval_id=child_id,approved_by=child.decided_by,
                    request=resumed,channel=child.channel,channel_reference_id=child.channel_response_id)
                self.requests.record_step_result(approval_id,result,now=self.clock())
                if result.status.value != 'succeeded':
                    self._progress(approval_id,'blocked',completed=completed,
                        execution_id=current_execution_id,reason='governed_execution_'+result.status.value)
                    return
                completed+=1
            self._progress(approval_id,'completed',completed=completed)
        except Exception as exc:
            # Never restart a claimed provider step blindly after a crash or an
            # uncertain outcome. Keep its existing claim and report indeterminate.
            state='indeterminate' if stage=='step_execution' else 'blocked'
            self._progress(approval_id,state,completed=completed,execution_id=current_execution_id,
                           reason=stage+'_'+type(exc).__name__)
