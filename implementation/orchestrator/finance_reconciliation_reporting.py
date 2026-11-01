"""Provider-neutral, fail-closed finance reconciliation reporting contract.

Presentation is not evidence of reconciliation, authority to post, or proof of
notification delivery. The finance orchestrator supplies verified facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class RunStatus(str, Enum):
    COMPLETED_NO_EXCEPTIONS = "COMPLETED_NO_EXCEPTIONS"
    COMPLETED_WITH_EXCEPTIONS = "COMPLETED_WITH_EXCEPTIONS"
    PARTIAL_REVIEW_REQUIRED = "PARTIAL_REVIEW_REQUIRED"
    BLOCKED_NOT_COMPLETED = "BLOCKED_NOT_COMPLETED"


@dataclass(frozen=True)
class ExceptionItem:
    reference: str
    amount: Decimal
    reason: str
    action_owner: str
    next_action: str
    human_action_required: bool


@dataclass(frozen=True)
class ReconciliationRun:
    run_id: str
    account_masked: str
    period: str
    recipient_role: str
    started_at: datetime
    ended_at: datetime
    status: RunStatus
    examined: int
    matched: int
    exceptions: tuple[ExceptionItem, ...]
    steps: tuple[str, ...]
    accounting_records_changed: bool
    accounting_change_description: str = ""


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} required")
    return value.strip()


def validate_run(run: ReconciliationRun) -> None:
    _required(run.run_id, "run_id")
    _required(run.account_masked, "account_masked")
    _required(run.period, "period")
    _required(run.recipient_role, "recipient_role")
    if not run.account_masked.endswith(tuple(str(i) for i in range(10))):
        raise ValueError("masked account required")
    if len(run.account_masked) > 35 or not ("*" in run.account_masked or "ending" in run.account_masked.lower()):
        raise ValueError("masked account required")
    if not isinstance(run.status, RunStatus):
        raise ValueError("explicit run status required")
    if (run.started_at.tzinfo is None or run.ended_at.tzinfo is None
            or run.ended_at < run.started_at):
        raise ValueError("valid timezone-aware timestamps required")
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (run.examined, run.matched)):
        raise ValueError("nonnegative integer counts required")
    if run.matched > run.examined:
        raise ValueError("matched exceeds examined")
    references = [item.reference for item in run.exceptions]
    if len(references) != len(set(references)):
        raise ValueError("duplicate exception reference")
    for item in run.exceptions:
        for key in ("reference", "reason", "action_owner", "next_action"):
            _required(getattr(item, key), key)
        if not isinstance(item.amount, Decimal) or not item.amount.is_finite():
            raise ValueError("finite Decimal amount required")
    if run.status is RunStatus.COMPLETED_NO_EXCEPTIONS:
        if run.exceptions or run.matched != run.examined:
            raise ValueError("clean completion cannot have unresolved transactions")
    if run.status is RunStatus.COMPLETED_WITH_EXCEPTIONS and not run.exceptions:
        raise ValueError("exception completion requires exceptions")
    if run.accounting_records_changed and not run.accounting_change_description.strip():
        raise ValueError("accounting change must be described")
    if not run.steps:
        raise ValueError("actual completed steps required")


def render_run_summary(run: ReconciliationRun) -> str:
    """Return plain-text report to be routed by authorized notification service.

    Does not send, claim delivery, imply accounting closure or request approval.
    """
    validate_run(run)
    labels = {
        RunStatus.COMPLETED_NO_EXCEPTIONS: "Completed — no exceptions",
        RunStatus.COMPLETED_WITH_EXCEPTIONS: "Completed — exceptions remain",
        RunStatus.PARTIAL_REVIEW_REQUIRED: "Partially verified — review required",
        RunStatus.BLOCKED_NOT_COMPLETED: "Blocked — reconciliation not completed",
    }
    lines = [
        "Jason | Checking account reconciliation",
        f"Status: {labels[run.status]}",
        f"Account: {run.account_masked} | Period: {run.period}",
        f"Run: {run.run_id}",
        f"Started: {run.started_at.isoformat()} | Finished: {run.ended_at.isoformat()}",
        f"Transactions examined: {run.examined} | Verified matches: {run.matched} | Exceptions: {len(run.exceptions)}",
        "What Jason did:",
        *[f"- {step}" for step in run.steps],
        ("Accounting records changed: Yes — " + run.accounting_change_description
         if run.accounting_records_changed else "Accounting records changed: No"),
        "What the assignee needs to do:",
    ]
    human_items = [item for item in run.exceptions if item.human_action_required]
    if not human_items:
        lines.append("No action required.")
    else:
        for item in human_items:
            lines.append(
                f"- {item.action_owner}: {item.next_action} | "
                f"{item.reference}, ${item.amount:,.2f} | Reason: {item.reason}"
            )
    if run.exceptions:
        lines.append("Outstanding / tracked exceptions:")
        for item in run.exceptions:
            lines.append(
                f"- {item.reference}: ${item.amount:,.2f} — {item.reason}; "
                f"owner: {item.action_owner}; next: {item.next_action}"
            )
    lines.append("Delivery status: Not established by this report. Verify through the notification service.")
    return "\n".join(lines)
