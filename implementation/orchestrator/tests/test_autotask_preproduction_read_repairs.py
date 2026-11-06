from __future__ import annotations

import json

import pytest

from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
from orchestrator.provider_read_capability_catalog import (
    SERVICE_COMPANY_SEARCH,
    SERVICE_TICKET_TIME_ENTRY_SEARCH,
)


def _search_args(capability, args):
    result = adapt_autotask_arguments(capability, args)
    return json.loads(result["search"])


def test_company_partial_name_uses_contains_and_bounded_page():
    result = _search_args(SERVICE_COMPANY_SEARCH, {"name": "Riggins", "page_size": 5})
    assert result["MaxRecords"] == 5
    assert {"op": "contains", "field": "companyName", "value": "Riggins"} in result["filter"]


def test_company_id_remains_exact_and_pagination_bounded():
    result = _search_args(SERVICE_COMPANY_SEARCH, {"resource_id": 827, "page_size": 5})
    assert {"op": "eq", "field": "id", "value": 827} in result["filter"]
    assert not any(x["op"] == "contains" for x in result["filter"])


def test_company_name_with_cursor_does_not_change_id_comparison():
    result = _search_args(
        SERVICE_COMPANY_SEARCH,
        {"name": "Riggins", "after_resource_id": 800, "page_size": 5},
    )
    assert {"op": "gt", "field": "id", "value": 800} in result["filter"]
    assert {"op": "contains", "field": "companyName", "value": "Riggins"} in result["filter"]


def test_time_entry_read_is_exact_ticket_and_company_scoped():
    result = adapt_autotask_arguments(
        SERVICE_TICKET_TIME_ENTRY_SEARCH,
        {"ticket_id": 143272, "company_id": 827, "page_size": 10},
    )
    assert result["entity"] == "TimeEntries"
    assert result["ticket_id"] == 143272
    assert result["company_id"] == 827
    parsed = json.loads(result["search"])
    assert {"op": "eq", "field": "ticketID", "value": 143272} in parsed["filter"]


@pytest.mark.parametrize("arguments", [
    {"ticket_id": 143272},
    {"ticket_id": 143272, "company_id": 0},
    {"ticket_id": 143272, "company_id": 827, "filters": {"ticketID": 8}},
])
def test_time_entry_read_rejects_missing_scope_or_raw_filters(arguments):
    with pytest.raises(ValueError):
        adapt_autotask_arguments(SERVICE_TICKET_TIME_ENTRY_SEARCH, arguments)
