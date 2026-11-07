"""Deterministic completion gate for governed conversational investigations.

A model declaring an answer ready is not completion evidence. The evidence
collector must account for every human information need before answer drafting.
This gate is provider-independent and does not grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .conversation_answer import ConversationLimitation, ConversationSupport
from .conversation_kernel import InformationNeed


class InvestigationIncompleteError(ValueError):
    """A conversational investigation was finalized without outcome evidence."""


_TERMINAL_REASONS = frozenset(
    {"no_further_authorized_read", "read_budget_exhausted"}
)


@dataclass(frozen=True, slots=True)
class NeedCompletionRecord:
    """Evidence collection outcome for exactly one requested information need."""

    information_need: str
    target_reference: str
    disposition: str
    attempted_reads: tuple[str, ...]
    terminal_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.information_need.strip() or not self.target_reference.strip():
            raise ValueError("completion record requires an identified information need")
        if self.disposition not in {"supported", "limited"}:
            raise ValueError("completion record disposition is invalid")
        if not self.attempted_reads or any(not item.strip() for item in self.attempted_reads):
            raise ValueError("completion record requires attempted governed evidence reads")
        if len(self.attempted_reads) != len(set(self.attempted_reads)):
            raise ValueError("completion record contains duplicate read attempts")
        if self.disposition == "supported" and self.terminal_reason is not None:
            raise ValueError("supported need cannot claim a terminal evidence limitation")
        if self.disposition == "limited" and self.terminal_reason not in _TERMINAL_REASONS:
            raise ValueError("limited need requires an explicit terminal evidence reason")


def require_investigation_completion(
    *,
    needs: Sequence[InformationNeed],
    records: Sequence[NeedCompletionRecord],
    supports: Sequence[ConversationSupport],
    limitations: Sequence[ConversationLimitation],
) -> None:
    """Refuse answer drafting unless every requested need is accounted for.

    A limitation is a legitimate outcome only after a governed read was attempted
    and the collector explicitly established the terminal reason. This cannot
    prove that an unregistered provider capability exists; it prevents silently
    dropping needs or treating a partial answer as complete.
    """
    if len(records) != len(needs):
        raise InvestigationIncompleteError(
            "investigation did not account for every requested information need"
        )

    support_keys = {
        (item.information_need, item.target_reference)
        for item in supports
    }
    limited_needs = {item.information_need for item in limitations}

    for need, record in zip(needs, records):
        expected = (need.need, need.target.reference)
        actual = (record.information_need, record.target_reference)
        if actual != expected:
            raise InvestigationIncompleteError(
                "investigation completion record did not match the human request"
            )
        if record.disposition == "supported":
            if expected not in support_keys:
                raise InvestigationIncompleteError(
                    "information need marked supported without governed evidence"
                )
        elif need.need not in limited_needs:
            raise InvestigationIncompleteError(
                "unanswered information need has no explicit bounded limitation"
            )

    accounted = {
        (record.information_need, record.target_reference)
        for record in records
    }
    if support_keys - accounted:
        raise InvestigationIncompleteError(
            "governed support was not tied to a requested information need"
        )
    if limited_needs - {record.information_need for record in records}:
        raise InvestigationIncompleteError(
            "limitation was not tied to a requested information need"
        )
