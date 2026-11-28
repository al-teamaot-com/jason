"""Provider-neutral human-input contracts for blocked reconciliation work.

This module defines what Jason needs from a human. It does not send Teams
messages and therefore does not create a new general conversation path.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import SourceLocation


@dataclass(frozen=True, slots=True)
class HumanInputRequest:
    request_id: str
    workflow_id: str
    account_id: str
    recipient: str
    question: str
    reason: str
    source: SourceLocation
    evidence_context: str
    suggested_answers: tuple[str, ...] = ()
    freeform_reply_allowed: bool = True
    blocking: bool = True
    context_note: str | None = None
    parent_request_id: str | None = None
    redirected_by: str | None = None

    def __post_init__(self) -> None:
        required = {
            "request_id": self.request_id,
            "workflow_id": self.workflow_id,
            "account_id": self.account_id,
            "recipient": self.recipient,
            "question": self.question,
            "reason": self.reason,
            "evidence_context": self.evidence_context,
        }
        missing = sorted(name for name, value in required.items() if not str(value).strip())
        if missing:
            raise ValueError("human input request fields are empty: " + ", ".join(missing))


def build_visual_ambiguity_request(
    *,
    request_id: str,
    workflow_id: str,
    account_id: str,
    recipient: str,
    question: str,
    reason: str,
    source: SourceLocation,
    evidence_context: str,
    suggested_answers: tuple[str, ...] = (),
) -> HumanInputRequest:
    return HumanInputRequest(
        request_id=request_id,
        workflow_id=workflow_id,
        account_id=account_id,
        recipient=recipient,
        question=question,
        reason=reason,
        source=source,
        evidence_context=evidence_context,
        suggested_answers=suggested_answers,
        freeform_reply_allowed=True,
        blocking=True,
    )


def reroute_human_input_request(
    request: HumanInputRequest,
    *,
    new_request_id: str,
    new_recipient: str,
    redirector_display_name: str,
) -> HumanInputRequest:
    if not new_recipient.strip():
        raise ValueError("new_recipient is required")
    if not redirector_display_name.strip():
        raise ValueError("redirector_display_name is required")

    return HumanInputRequest(
        request_id=new_request_id,
        workflow_id=request.workflow_id,
        account_id=request.account_id,
        recipient=new_recipient,
        question=request.question,
        reason=request.reason,
        source=request.source,
        evidence_context=request.evidence_context,
        suggested_answers=request.suggested_answers,
        freeform_reply_allowed=request.freeform_reply_allowed,
        blocking=request.blocking,
        context_note=f"{redirector_display_name} thinks you may know the answer to this.",
        parent_request_id=request.request_id,
        redirected_by=redirector_display_name,
    )
