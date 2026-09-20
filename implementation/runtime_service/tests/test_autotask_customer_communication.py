from __future__ import annotations

import pytest

from jason_runtime.autotask_customer_communication import (
    AutotaskCustomerCommunicationContractError,
    build_customer_communication_trigger,
)


def _fields(*, include_trigger: bool = True):
    note_values = [
        {"value": "3", "label": "Task Notes", "isActive": True},
    ]
    if include_trigger:
        note_values.append(
            {"value": "501", "label": "Jason Customer Communication", "isActive": True}
        )
    return [
        {"name": "noteType", "isPickList": True, "picklistValues": note_values},
        {
            "name": "publish",
            "isPickList": True,
            "picklistValues": [
                {"value": "1", "label": "All Autotask Users", "isActive": True},
                {"value": "2", "label": "Internal Project Team", "isActive": True},
            ],
        },
    ]


def test_build_trigger_resolves_live_picklists_and_requires_ticket_contact() -> None:
    trigger = build_customer_communication_trigger(
        ticket={"id": 123, "contactID": 456},
        ticket_note_fields=_fields(),
        message="Please confirm whether printing is working now.",
    )
    assert trigger.contact_id == 456
    assert trigger.provider_payload() == {
        "ticketID": 123,
        "description": "Please confirm whether printing is working now.",
        "noteType": 501,
        "publish": 1,
        "title": "Jason Customer Communication",
    }


def test_trigger_fails_closed_when_dedicated_note_type_is_missing() -> None:
    with pytest.raises(
        AutotaskCustomerCommunicationContractError,
        match="Required active Autotask picklist value is not unique",
    ):
        build_customer_communication_trigger(
            ticket={"id": 123, "contactID": 456},
            ticket_note_fields=_fields(include_trigger=False),
            message="Test",
        )


def test_trigger_fails_closed_when_ticket_has_no_contact() -> None:
    with pytest.raises(
        AutotaskCustomerCommunicationContractError,
        match="ticket contact id must be a positive integer",
    ):
        build_customer_communication_trigger(
            ticket={"id": 123, "contactID": None},
            ticket_note_fields=_fields(),
            message="Test",
        )
