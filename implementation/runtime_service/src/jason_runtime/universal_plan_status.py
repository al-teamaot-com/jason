"""Bounded completion/blockage reports on the existing approved Teams transport.

Only original participants receive fixed status text, never provider content or
new action buttons. Delivery failure cannot turn a successful plan into a failed
execution, and an uncertain send is not blindly retried.
"""
from __future__ import annotations

from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
import logging
from typing import Any,Callable

logger=logging.getLogger(__name__)
_MESSAGES={
    'completed':'Completed: the reviewed plan finished successfully.',
    'denied':'Denied: the reviewed plan was not executed.',
    'blocked':'Blocked: the reviewed plan did not complete. Jason recorded the blocker; no further steps are being executed.',
    'indeterminate':'Needs review: Jason could not confirm an execution outcome. It will not repeat that action without verification.',
}


@dataclass
class UniversalPlanStatusMaintenance:
    handler: Any
    bindings: Any
    identities: Any
    sender_factory: Callable[...,Any]
    gateway_url: str
    token_file: Any
    clock: Callable[[],datetime]=lambda:datetime.now(timezone.utc)
    interval_seconds:int=5
    _next_due:datetime|None=field(default=None,init=False)
    _after:str=field(default='',init=False)

    def tick(self)->bool:
        now=self.clock()
        if self._next_due is not None and now<self._next_due:
            return False
        self._next_due=now+timedelta(seconds=self.interval_seconds)
        worked=False
        candidates=self.handler.requests.terminal_progress_ids(after=self._after)
        if not candidates:
            self._after=''
            return False
        for approval_id in candidates:
            self._after=approval_id
            progress=self.handler.requests.progress(approval_id)
            state=progress['state']
            proposal=self.handler.proposals.require(approval_id)
            # Original requester and actually authenticated decider only. Merely
            # belonging to an approver role does not authorize visibility into all plans.
            requester=self.identities.get(proposal.requester_id)
            if requester is None or requester.status!='active' or requester.organization_id!=proposal.organization_id:
                continue
            origin=self.bindings.find_active_by_jason_identity(jason_identity_id=proposal.requester_id)
            if origin is None or origin.status!='active':
                continue
            recipients={proposal.requester_id}
            decision=self.handler.service.teams_flow.approval_service.repository.accepted_decision(approval_id)
            if decision is not None:
                recipients.add(decision.decided_by)
            for actor in sorted(recipients):
                principal=self.identities.get(actor)
                binding=self.bindings.find_active_by_jason_identity(jason_identity_id=actor)
                if (principal is None or principal.status!='active' or principal.organization_id!=proposal.organization_id
                        or binding is None or binding.status!='active'
                        or binding.microsoft_tenant_id!=origin.microsoft_tenant_id):
                    continue
                if not self.handler.requests.claim_status_delivery(approval_id,state,actor,now=now):
                    continue
                worked=True
                count=progress.get('completed_steps',0)
                if type(count) is not int or not 0<=count<=32:
                    count=0
                text=_MESSAGES[state]+f' Completed steps: {count}. Approval ID: {approval_id}'
                try:
                    sender=self.sender_factory(gateway_url=self.gateway_url,token_file=self.token_file,
                        bindings=self.bindings,owner_identity_ids=(actor,))
                    receipts=sender.send_status(text=text)
                    if len(receipts)!=1 or not receipts[0]:
                        raise RuntimeError('status delivery not confirmed')
                    self.handler.requests.status_delivery_result(approval_id,state,actor,now=self.clock(),
                        status='sent',receipt=str(receipts[0]))
                    logger.info('UNIVERSAL_PLAN_NOTIFICATION state=%s approval_id=%s delivery=sent',state,approval_id)
                except Exception as exc:
                    self.handler.requests.status_delivery_result(approval_id,state,actor,now=self.clock(),
                        status='indeterminate')
                    logger.warning('UNIVERSAL_PLAN_NOTIFICATION state=%s approval_id=%s delivery=indeterminate error_type=%s',
                                   state,approval_id,type(exc).__name__)
            if worked:
                return True
        return worked
