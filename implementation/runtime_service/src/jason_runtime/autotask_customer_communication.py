from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


SERVICE_TICKET_CUSTOMER_COMMUNICATION_REQUEST = (
    "service.ticket.customer_communication.request"
)
JASON_CUSTOMER_COMMUNICATION_NOTE_TYPE = "Jason Customer Communication"
JASON_CUSTOMER_COMMUNICATION_TITLE = "Jason Customer Communication"


class AutotaskCustomerCommunicationContractError(ValueError):
    """Fail-closed contract error for customer communication requests."""


@dataclass(frozen=True, slots=True)
class CustomerCommunicationTrigger:
    ticket_id: int
    contact_id: int
    note_type: int
    publish: int
    title: str
    message: str

    def provider_payload(self) -> dict[str, Any]:
        return {
            "ticketID": self.ticket_id,
            "description": self.message,
            "noteType": self.note_type,
            "publish": self.publish,
            "title": self.title,
        }


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise AutotaskCustomerCommunicationContractError(
            f"{field} must be a positive integer"
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise AutotaskCustomerCommunicationContractError(
            f"{field} must be a positive integer"
        ) from error
    if normalized < 1:
        raise AutotaskCustomerCommunicationContractError(
            f"{field} must be a positive integer"
        )
    return normalized


def _field(fields: Sequence[Mapping[str, Any]], name: str) -> Mapping[str, Any]:
    matches = [item for item in fields if str(item.get("name")) == name]
    if len(matches) != 1:
        raise AutotaskCustomerCommunicationContractError(
            f"Autotask field metadata is not unique for {name}"
        )
    return matches[0]


def resolve_active_picklist_value(
    fields: Sequence[Mapping[str, Any]],
    *,
    field_name: str,
    label: str,
) -> int:
    metadata = _field(fields, field_name)
    if not metadata.get("isPickList"):
        raise AutotaskCustomerCommunicationContractError(
            f"Autotask field is not a picklist: {field_name}"
        )
    values = metadata.get("picklistValues")
    if not isinstance(values, list):
        raise AutotaskCustomerCommunicationContractError(
            f"Autotask picklist metadata is unavailable: {field_name}"
        )
    matches = [
        item
        for item in values
        if isinstance(item, Mapping)
        and bool(item.get("isActive"))
        and str(item.get("label", "")).strip().casefold()
        == label.strip().casefold()
    ]
    if len(matches) != 1:
        raise AutotaskCustomerCommunicationContractError(
            f"Required active Autotask picklist value is not unique: {field_name}={label}"
        )
    return _positive_int(matches[0].get("value"), field=f"{field_name} value")


def build_customer_communication_trigger(
    *,
    ticket: Mapping[str, Any],
    ticket_note_fields: Sequence[Mapping[str, Any]],
    message: str,
    title: str = JASON_CUSTOMER_COMMUNICATION_TITLE,
) -> CustomerCommunicationTrigger:
    ticket_id = _positive_int(ticket.get("id"), field="ticket id")
    contact_id = _positive_int(ticket.get("contactID"), field="ticket contact id")
    normalized_message = str(message or "").strip()
    if not normalized_message:
        raise AutotaskCustomerCommunicationContractError(
            "customer communication message is required"
        )
    if len(normalized_message) > 8000:
        raise AutotaskCustomerCommunicationContractError(
            "customer communication message exceeds the bounded 8000-character limit"
        )
    normalized_title = str(title or "").strip() or JASON_CUSTOMER_COMMUNICATION_TITLE
    if len(normalized_title) > 250:
        raise AutotaskCustomerCommunicationContractError(
            "customer communication title exceeds the Autotask 250-character limit"
        )

    note_type = resolve_active_picklist_value(
        ticket_note_fields,
        field_name="noteType",
        label=JASON_CUSTOMER_COMMUNICATION_NOTE_TYPE,
    )
    publish = resolve_active_picklist_value(
        ticket_note_fields,
        field_name="publish",
        label="All Autotask Users",
    )

    return CustomerCommunicationTrigger(
        ticket_id=ticket_id,
        contact_id=contact_id,
        note_type=note_type,
        publish=publish,
        title=normalized_title,
        message=normalized_message,
    )
