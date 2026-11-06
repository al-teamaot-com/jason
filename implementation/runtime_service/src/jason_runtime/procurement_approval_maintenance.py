"""Bounded supervisor timeout/reminder/owner fallback via canonical approvals.

No provider writes, no new sender, no second approval repository, and no
implicit approval after timeout. The exact original purchase digest is carried
through every escalation request, with a new independent signed card instance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
        # Use only canonical persisted, still-pending, AOT procurement approvals.
        for request in self.approval_service.repository.list_all():
            if (not request.approval_id.startswith('procapproval-')
                    or request.capability!=PROCUREMENT_APPROVAL_CAPABILITY
                    or request.requested_mode!='purchase'
                    or request.organization_id!='aot' or request.client_id is not None
                    or request.status is not ApprovalRequestStatus.PENDING):
                continue
            submission=self.submissions.get(str(request.metadata.get('submission_id') or ''))
            if (not submission or submission.get('approval_id')!=request.approval_id
                    or submission.get('digest')!=request.metadata.get('submission_digest')
                    or submission.get('status') not in {'approval_required','approval_delivery_blocked'}):
                continue
            summary['checked']+=1
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
        return summary
