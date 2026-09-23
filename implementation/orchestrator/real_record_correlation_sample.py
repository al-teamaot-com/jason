from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence


class CorrelationSampleSelectionError(ValueError):
    """Raised when a bounded acceptance sample cannot be selected safely."""


@dataclass(frozen=True, slots=True)
class AutotaskTicketSampleSelection:
    """In-memory acceptance sample identity plus sanitized selection metadata.

    The ticket number and provider ID are retained only so the caller can perform
    an exact follow-up read. They must not be printed or persisted in acceptance
    evidence; use ``sanitized_metadata`` for durable output.
    """

    ticket_number: str
    ticket_id: str
    candidate_count: int
    configuration_linked_candidate_count: int
    selection_basis: str

    def sanitized_metadata(self) -> Mapping[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "configuration_linked_candidate_count": (
                self.configuration_linked_candidate_count
            ),
            "selection_basis": self.selection_basis,
            "selected_ticket_selector_sha256": _sha256(self.ticket_number),
            "selected_ticket_resource_sha256": _sha256(self.ticket_id),
        }


def select_autotask_ticket_sample(
    items: Sequence[Mapping[str, Any]],
    *,
    maximum_records: int,
) -> AutotaskTicketSampleSelection:
    """Select one deterministic acceptance sample from a bounded ticket collection.

    This is intentionally *not* general resource resolution. It is an operator
    acceptance sampler whose only purpose is choosing one real record to exercise
    the already-governed exact correlation path. It never treats provider order as
    semantic identity: among the bounded candidates it prefers records that carry a
    configuration-item relationship, then chooses the greatest durable provider ID.
    """

    if isinstance(maximum_records, bool) or maximum_records < 1:
        raise CorrelationSampleSelectionError(
            "maximum_records must be a positive integer"
        )
    if len(items) > maximum_records:
        raise CorrelationSampleSelectionError(
            "Autotask acceptance sample exceeded its bounded record limit"
        )
    if not items:
        raise CorrelationSampleSelectionError(
            "Autotask acceptance sample returned no tickets"
        )

    candidates: list[tuple[str, str, bool]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise CorrelationSampleSelectionError(
                "Autotask acceptance sample contained a malformed ticket"
            )
        ticket_id = _scalar(item, ("id",))
        ticket_number = _scalar(item, ("ticketNumber", "ticket_number"))
        if ticket_id is None or ticket_number is None:
            continue
        linked = _scalar(
            item,
            (
                "configurationItemID",
                "configurationItemId",
                "installedProductID",
                "installedProductId",
            ),
        ) is not None
        candidates.append((ticket_id, ticket_number, linked))

    if not candidates:
        raise CorrelationSampleSelectionError(
            "Autotask acceptance sample contained no ticket with durable identity"
        )

    linked_candidates = [item for item in candidates if item[2]]
    pool = linked_candidates or candidates
    selected = max(pool, key=lambda item: _provider_id_order(item[0]))

    return AutotaskTicketSampleSelection(
        ticket_number=selected[1],
        ticket_id=selected[0],
        candidate_count=len(candidates),
        configuration_linked_candidate_count=len(linked_candidates),
        selection_basis=(
            "greatest_provider_id_with_configuration_link"
            if linked_candidates
            else "greatest_provider_id_in_bounded_sample"
        ),
    )


def _scalar(record: Mapping[str, Any], names: Sequence[str]) -> str | None:
    for name in names:
        value = record.get(name)
        if value is None or isinstance(value, (Mapping, list, tuple, set, bool)):
            continue
        text = str(value).strip()
        if text and text not in {"0", "None", "null"}:
            return text
    return None


def _provider_id_order(value: str) -> tuple[int, int, str]:
    try:
        numeric = int(value)
    except ValueError:
        return (0, -1, value.casefold())
    return (1, numeric, value.casefold())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
