"""Bounded supervisor timeout/reminder/owner fallback via canonical approvals.

No provider writes, no new sender, no second approval repository, and no
implicit approval after timeout. The exact original purchase digest is carried
through every escalation request, with a new independent signed card instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from datetime import datetime, timedelta, timezone
from typing import Any

from connectors.src.jason_connectors.approval_requests import ApprovalRequestStatus
from .procurement_teams_flow import PROCUREMENT_APPROVAL_CAPABILITY


@dataclass
class ProcurementApprovalMaintenance:
    approval_service: Any
    submissions: Any
    processor: Any
    sender: Any
    now: Any = lambda:datetime.now(timezone.utc)
    interval: timedelta = timedelta(minutes=5)
    workflow_configuration: Any | None = None
    _next_due: datetime | None = field(default=None, init=False)

    def tick(self) -> bool:
        current=self.now()
        if self._next_due is not None and current < self._next_due:
            return False
        self._next_due=current+self.interval
        self.run_once(now=current)
        return True

    def run_once(self, *, now: datetime | None=None) -> dict[str,int]:
        current=now or self.now()
        if current.tzinfo is None:
            raise ValueError('maintenance requires aware clock')
        summary={'checked':0,'reminded':0,'escalated':0,'blocked':0}
        if self.workflow_configuration is not None:
            self._recover_communications(current)
        # Use only canonical persisted, still-pending, AOT procurement approvals.
        for request in self.approval_service.repository.list_all():
            if (not request.approval_id.startswith('procapproval-')
                    or request.capability!=PROCUREMENT_APPROVAL_CAPABILITY
                    or request.requested_mode!='purchase'
                    or request.organization_id!='aot' or request.client_id is not None
                    or request.status not in {ApprovalRequestStatus.PENDING, ApprovalRequestStatus.EXPIRED}):
                continue
            submission=self.submissions.get(str(request.metadata.get('submission_id') or ''))
            if (not submission or submission.get('approval_id')!=request.approval_id
                    or submission.get('digest')!=request.metadata.get('submission_digest')
                    or submission.get('status') not in {'approval_required','approval_delivery_blocked'}):
                continue
            if (request.status is ApprovalRequestStatus.EXPIRED
                    and not submission.get('workflow_configuration_digest')):
                continue
            summary['checked']+=1
            if submission.get('workflow_configuration_digest'):
                try:
                    outcome = self._configured_tick(request, submission, current)
                    if outcome:
                        summary[outcome] += 1
                except (PermissionError, RuntimeError, OSError, ValueError):
                    summary['blocked'] += 1
                continue
            policy_digest=request.metadata.get('supervisor_policy_digest')
            if policy_digest!='owner-udf-only':
                if self.processor.supervisor_policy is None:
                    summary['blocked']+=1;continue
                try:self.processor.supervisor_policy.revalidate(digest=policy_digest)
                except PermissionError:
                    summary['blocked']+=1;continue
            fallback=tuple(submission.get('owner_escalation_ids') or ())
            is_owner_fallback=bool(request.metadata.get('escalated_from'))
            unavailable=submission.get('status')=='approval_delivery_blocked'
            if current>=request.expires_at or unavailable:
                # Never escalate an owner fallback again. An unavailable owner
                # requires a human capacity/identity exception, not auto grant.
                if (is_owner_fallback or not fallback
                        or request.requested_by in fallback
                        or set(fallback)&set(request.authorized_approver_ids)):
                    summary['blocked']+=1;continue
                try:
                    new_request=self.processor._create_owner_approval(
                        submission,approver_override=fallback,
                        escalation_from=request.approval_id,approval_now=current)
                    self.submissions.update(submission['submission_id'],{
                        **submission,'status':'approval_required',
                        'approval_id':new_request.approval_id,
                    })
                    try:self.sender.send(new_request)
                    except (PermissionError, RuntimeError, OSError, ValueError) as error:
                        latest=self.submissions.get(submission['submission_id'])
                        self.submissions.update(submission['submission_id'],{
                            **latest,'status':'approval_delivery_blocked',
                            'delivery_error_type':type(error).__name__,
                        })
                        summary['blocked']+=1;continue
                    summary['escalated']+=1
                except (PermissionError, RuntimeError, OSError, ValueError):
                    summary['blocked']+=1
                continue
            # One reminder when the original supervisor approval is halfway
            # through its TTL. Reuse the same immutable request/challenge.
            halfway=request.requested_at+(request.expires_at-request.requested_at)/2
            if (current>=halfway and 'approval_reminder_sent_at' not in submission):
                try:
                    self.sender.send(request)
                    self.submissions.update(submission['submission_id'],{
                        **submission,'approval_reminder_sent_at':current.isoformat(),
                    })
                    summary['reminded']+=1
                except (PermissionError, RuntimeError, OSError, ValueError):
                    summary['blocked']+=1
        if self.workflow_configuration is not None:
            self._queue_terminal_card_updates(current)
        return summary

    def _queue_terminal_card_updates(self, current):
        for submission in self.submissions.list_all():
            if not submission.get('workflow_configuration_digest'):
                continue
            request = self.approval_service.repository.get(str(submission.get('approval_id') or ''))
            if request is None or request.status not in {ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.DENIED}:
                continue
            if self.approval_service.repository.accepted_decision(request.approval_id) is None:
                continue
            key='terminal_card'
            plan={'kind':'terminal_card', 'at':current.isoformat()}
            if self.submissions.claim_communication(submission['submission_id'],
                    approval_id=request.approval_id, event_key=key, plan=plan):
                try:self._resume_communication(request, submission, key, plan, current)
                except (AttributeError, PermissionError, RuntimeError, OSError, ValueError):pass

    def _configured_tick(self, request, submission, current):
        if any(claim.get('state') == 'claimed_reconciliation_required'
               for claim in submission.get('communication_claims', {}).values()):
            raise PermissionError('prior communication outcome requires reconciliation')
        configuration = self.workflow_configuration.load() if self.workflow_configuration else None
        if (configuration is None or not configuration.enabled
                or configuration.approval_scope_digest != submission['workflow_configuration_digest']):
            raise PermissionError('workflow timing policy changed; renewed review required')
        policy_digest = request.metadata.get('supervisor_policy_digest')
        if policy_digest != 'owner-udf-only':
            if self.processor.supervisor_policy is None:
                raise PermissionError('supervisor policy missing')
            self.processor.supervisor_policy.revalidate(digest=policy_digest)
        since = datetime.fromisoformat(submission.get('business_stage_started_at')
                                       or submission['workflow_requested_at'])
        previous = submission.get('last_business_reminder_at')
        last = datetime.fromisoformat(previous) if previous else since
        event = configuration.due(since=since, now=current, last_reminder=last)
        if event is None:
            return None
        chain = tuple(submission.get('supervisor_chain_ids') or ())
        active = tuple(request.authorized_approver_ids)
        if len(active) != 1 or active[0] not in chain:
            raise PermissionError('current approval is outside verified supervisor chain')
        index = chain.index(active[0])
        escalation = event == 'escalated' and index + 1 < len(chain)
        if not escalation and configuration.calendar.minutes_between(last, current) < configuration.raw['reminder_business_minutes']:
            return None
        event = 'escalated' if escalation else 'reminder'
        if event not in configuration.raw['events']:
            return None
        # One durable event claim across workers/restarts, before any send or
        # replacement request. Unknown partial outcomes require reconciliation.
        bucket = configuration.calendar.minutes_between(since, current) // configuration.raw['reminder_business_minutes']
        key = event + ':' + str(bucket)
        replacement = escalation or current >= request.expires_at
        plan = {'kind':'maintenance', 'at':current.isoformat(), 'event':event,
                'target': list((chain[index + 1],) if escalation else active),
                'escalated':escalation,
                'replacement_id': ('procapproval-' + sha256((request.approval_id + ':' + key).encode()).hexdigest()[:32])
                    if replacement else None}
        if not self.submissions.claim_communication(submission['submission_id'],
                approval_id=request.approval_id, event_key=key, plan=plan):
            return None
        self._resume_communication(request, submission, key, plan, current)
        return 'escalated' if escalation else 'reminded'

    def _recover_communications(self, current):
        # Existing maintenance owner, submission row and gateway receipts only.
        # Older claims without a persisted plan remain blocked for human review.
        for submission in self.submissions.list_all():
            if not submission.get('workflow_configuration_digest'):
                continue
            for claim in submission.get('communication_claims', {}).values():
                plan = claim.get('plan') or {}
                if claim.get('state') != 'claimed_reconciliation_required' or plan.get('kind') not in {'maintenance', 'initial_card', 'event', 'terminal_card'}:
                    continue
                try:
                    if current < datetime.fromisoformat(plan['at']) + timedelta(minutes=2):
                        continue
                    request = self.approval_service.repository.get(claim['approval_id'])
                    if request is None:
                        continue
                    self._resume_communication(request, submission, claim['event'], plan, current)
                except (PermissionError, RuntimeError, OSError, ValueError):
                    # Never clear an unknown provider outcome or invent consent.
                    continue

    def _resume_communication(self, request, submission, key, plan, current):
        configuration = self.workflow_configuration.load()
        if (not configuration.enabled or configuration.approval_scope_digest != submission['workflow_configuration_digest']
                or request.metadata.get('submission_digest') != submission.get('digest')):
            raise PermissionError('recovery scope or configuration changed')
        if (request.metadata.get('submission_id') != submission['submission_id']
                or request.capability != PROCUREMENT_APPROVAL_CAPABILITY or request.organization_id != 'aot'
                or request.client_id is not None or request.requested_mode != 'purchase'):
            raise PermissionError('recovery canonical approval scope mismatch')
        policy = request.metadata.get('supervisor_policy_digest')
        if policy != 'owner-udf-only':
            if self.processor.supervisor_policy is None:
                raise PermissionError('recovery spending authority missing')
            self.processor.supervisor_policy.revalidate(digest=policy)
        def supersede(reason):
            self.submissions.supersede_communication(submission['submission_id'],
                approval_id=request.approval_id, event_key=key, reason=reason)
        if plan['kind'] == 'terminal_card':
            accepted = self.approval_service.repository.accepted_decision(request.approval_id)
            if accepted is None or accepted.status not in {'approved','denied'}:
                raise PermissionError('terminal card requires a canonical decision')
            from connectors.microsoft_graph.teams_approval_channel import render_approval_card
            from .universal_interaction.teams import render_configured_event
            card = render_configured_event(configuration, render_approval_card(request), event=accepted.status)
            receipts = self.sender.update_decision(request, status=accepted.status, card=card)
            self.submissions.complete_communication(submission['submission_id'],
                approval_id=request.approval_id, event_key=key, receipts=receipts)
            return
        if plan['kind'] in {'initial_card', 'event'}:
            pending_only = plan['kind'] == 'initial_card' or plan.get('event') in {'approval_required','reminder','escalated'}
            if pending_only and (request.status is not ApprovalRequestStatus.PENDING or current >= request.expires_at):
                if request.status is ApprovalRequestStatus.PENDING:
                    self.approval_service.expire_if_due(request.approval_id, now=current)
                supersede('canonical_offer_no_longer_pending')
                return
            if plan['kind'] == 'initial_card':
                receipts = self.sender.send(request)
            else:
                receipts = self.sender.send_event(request, event=plan['event'], event_key=key,
                    requester_only=plan.get('requester_only', False))
            self.submissions.complete_communication(submission['submission_id'],
                approval_id=request.approval_id, event_key=key, receipts=receipts)
            if plan['kind'] == 'initial_card':
                self.processor.notify_approval_event(request, 'approval_required')
            return
        if request.status in {ApprovalRequestStatus.APPROVED, ApprovalRequestStatus.DENIED,
                              ApprovalRequestStatus.CHANGES_REQUESTED}:
            supersede('canonical_decision_recorded')
            return
        chain = tuple(submission.get('supervisor_chain_ids') or ())
        active = tuple(request.authorized_approver_ids)
        if len(active) != 1 or active[0] not in chain:
            raise PermissionError('recovery approval outside supervisor chain')
        index = chain.index(active[0])
        target = ((chain[index + 1],) if plan['escalated'] and index + 1 < len(chain) else active)
        if tuple(plan['target']) != target or plan['event'] not in {'reminder','escalated'}:
            raise PermissionError('recovery target changed')
        replacement_id = plan.get('replacement_id')
        if replacement_id:
            expected = 'procapproval-' + sha256((request.approval_id + ':' + key).encode()).hexdigest()[:32]
            if replacement_id != expected:
                raise PermissionError('recovery replacement reference changed')
            if request.status is ApprovalRequestStatus.PENDING:
                self.approval_service.repository.transition_pending(request, status=ApprovalRequestStatus.CANCELLED)
            elif request.status not in {ApprovalRequestStatus.EXPIRED, ApprovalRequestStatus.CANCELLED}:
                raise PermissionError('recovery offer is not replaceable')
            new_request = self.processor._create_owner_approval(submission,
                approver_override=target, escalation_from=request.approval_id,
                approval_now=current, approval_id_override=replacement_id)
            self.submissions.activate_communication_replacement(submission['submission_id'],
                old_id=request.approval_id, new_id=new_request.approval_id, digest=submission['digest'],
                at=plan['at'], escalated=plan['escalated'])
            if 'approval_replaced' in configuration.raw['events']:
                from connectors.microsoft_graph.teams_approval_channel import render_approval_card
                from .universal_interaction.teams import render_configured_event
                self.sender.update_decision(request, status='replaced', card=render_configured_event(
                    configuration, render_approval_card(request), event='approval_replaced'))
            if current >= new_request.expires_at:
                self.approval_service.expire_if_due(new_request.approval_id, now=current)
                supersede('replacement_expired_before_delivery_reconciled')
                return
            if new_request.status is not ApprovalRequestStatus.PENDING:
                supersede('replacement_decided')
                return
            receipts = self.sender.send(new_request)
            receipts += self.sender.send_event(new_request, event=plan['event'],
                                               requester_only=True, event_key=key)
        else:
            if request.status is not ApprovalRequestStatus.PENDING:
                supersede('offer_no_longer_pending')
                return
            receipts = self.sender.send_event(request, event=plan['event'], event_key=key)
            latest = self.submissions.get(submission['submission_id'])
            self.submissions.update(submission['submission_id'], {
                **latest, 'last_business_reminder_at': plan['at']})
        self.submissions.complete_communication(submission['submission_id'],
            approval_id=request.approval_id, event_key=key, receipts=receipts)
