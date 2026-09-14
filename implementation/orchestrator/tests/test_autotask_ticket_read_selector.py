from __future__ import annotations

import pytest

from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
from orchestrator.provider_read_capability_catalog import SERVICE_TICKET_READ


def test_ticket_read_accepts_internal_ticket_id_selector() -> None:
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {"ticket_id": 140303},
    ) == {"ticket_id": 140303}


def test_ticket_read_accepts_human_ticket_number_in_any_documented_alias() -> None:
    expected = {"ticket_id": "T20260911.0010"}

    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {"ticket_number": "T20260911.0010"},
    ) == expected
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {"ticket_id": "T20260911.0010"},
    ) == expected
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {"resource_id": "T20260911.0010"},
    ) == expected


def test_ticket_read_allows_repeated_equivalent_aliases() -> None:
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {
            "ticket_id": "T20260911.0010",
            "resource_id": "T20260911.0010",
        },
    ) == {"ticket_id": "T20260911.0010"}


def test_ticket_read_rejects_conflicting_aliases() -> None:
    with pytest.raises(ValueError, match="conflicting ticket selectors"):
        adapt_autotask_arguments(
            SERVICE_TICKET_READ,
            {
                "ticket_id": 140303,
                "resource_id": "T20260911.0010",
            },
        )
