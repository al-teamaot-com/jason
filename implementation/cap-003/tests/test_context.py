from __future__ import annotations

import json

import pytest

from connectors.core.contracts import ConnectorResult
from connectors.core.openbao_secrets import OpenBaoSecretResolutionError
from jason_cap_003 import (
    AutotaskBusinessContextError,
    AutotaskBusinessContextReader,
)


class FakeConnector:
    provider_name = "autotask"
    capabilities = frozenset(
        {
            "autotask.company.search",
            "autotask.contact.search",
            "autotask.configuration.search",
            "autotask.ticket.search",
            "autotask.contract.search",
            "autotask.project.search",
        }
    )

    def __init__(self) -> None:
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        capability = request.context.capability
        search = json.loads(request.arguments["search"])
        field = search["filter"][0]["field"]
        value = search["filter"][0]["value"]

        if capability == "autotask.company.search":
            assert field == "CompanyName"
            assert value == "Acme Corp"
            items = [{"id": 208, "companyName": "Acme Corp", "isActive": True}]
        elif capability == "autotask.contact.search":
            items = [{"id": 11, "companyID": 208, "firstName": "Alex"}]
        elif capability == "autotask.configuration.search":
            items = [{"id": 22, "companyID": 208, "referenceTitle": "PC-22"}]
        elif capability == "autotask.ticket.search":
            if field == "ticketNumber":
                items = [{"id": 34, "companyID": 208, "ticketNumber": str(value)}]
            else:
                items = [{"id": 33, "companyID": 208, "ticketNumber": "T1"}]
        elif capability == "autotask.contract.search":
            items = [{"id": 44, "companyID": 208, "contractName": "Managed IT"}]
        elif capability == "autotask.project.search":
            items = [{"id": 55, "companyID": 208, "projectName": "Migration"}]
        else:
            raise AssertionError(f"Unexpected capability: {capability}")

        return ConnectorResult(
            capability=capability,
            provider="autotask",
            data={"items": items},
        )


def test_company_context_composes_narrow_canonical_reads() -> None:
    connector = FakeConnector()
    result = AutotaskBusinessContextReader(connector).read_company_context(
        company_name="Acme Corp",
        correlation_id="corr-1",
        principal_id="operator-1",
        organization_id="aot",
    )

    assert result.company_id == "208"
    assert result.company["companyName"] == "Acme Corp"
    assert len(result.contacts) == 1
    assert len(result.configurations) == 1
    assert len(result.tickets) == 1
    assert len(result.contracts) == 1
    assert len(result.projects) == 1

    assert [request.context.capability for request in connector.requests] == [
        "autotask.company.search",
        "autotask.ticket.search",
        "autotask.contact.search",
        "autotask.configuration.search",
        "autotask.contract.search",
        "autotask.project.search",
    ]
    assert connector.requests[0].context.client_id is None
    assert all(
        request.context.client_id == "208"
        for request in connector.requests[1:]
    )
    assert all(request.context.mode == "observe" for request in connector.requests)


def test_focused_ticket_is_resolved_explicitly_and_bound_to_company() -> None:
    connector = FakeConnector()
    result = AutotaskBusinessContextReader(connector).read_company_context(
        company_name="Acme Corp",
        correlation_id="corr-focus",
        principal_id="operator-1",
        organization_id="aot",
        focus_ticket_number="T99",
    )

    assert result.tickets[0]["ticketNumber"] == "T99"
    ticket_searches = [
        request
        for request in connector.requests
        if request.context.capability == "autotask.ticket.search"
    ]
    assert len(ticket_searches) == 2
    focused_search = json.loads(ticket_searches[1].arguments["search"])
    assert focused_search["filter"] == [
        {"op": "eq", "field": "ticketNumber", "value": "T99"}
    ]
    assert focused_search["MaxRecords"] == 2
    assert ticket_searches[1].context.client_id == "208"


def test_focused_ticket_company_mismatch_fails_closed() -> None:
    connector = FakeConnector()
    original_execute = connector.execute

    def mismatched_execute(request):
        if request.context.capability == "autotask.ticket.search":
            search = json.loads(request.arguments["search"])
            if search["filter"][0]["field"] == "ticketNumber":
                return ConnectorResult(
                    capability=request.context.capability,
                    provider="autotask",
                    data={"items": [{"id": 99, "companyID": 999, "ticketNumber": "T99"}]},
                )
        return original_execute(request)

    connector.execute = mismatched_execute  # type: ignore[method-assign]

    with pytest.raises(AutotaskBusinessContextError) as captured:
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-mismatch",
            principal_id="operator-1",
            organization_id="aot",
            focus_ticket_number="T99",
        )

    assert captured.value.error_code == "TICKET_FOCUS_COMPANY_MISMATCH"


def test_company_lookup_ambiguity_has_safe_code() -> None:
    connector = FakeConnector()

    def ambiguous_execute(request):
        if request.context.capability == "autotask.company.search":
            return ConnectorResult(
                capability=request.context.capability,
                provider="autotask",
                data={
                    "items": [
                        {"id": 1, "companyName": "Acme Corp"},
                        {"id": 2, "companyName": "ACME CORP"},
                    ]
                },
            )
        raise AssertionError("Related reads must not occur after ambiguous lookup.")

    connector.execute = ambiguous_execute  # type: ignore[method-assign]

    with pytest.raises(AutotaskBusinessContextError) as captured:
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-2",
            principal_id="operator-1",
            organization_id="aot",
        )

    assert captured.value.error_code == "COMPANY_MATCH_AMBIGUOUS"


def test_company_lookup_not_found_has_safe_code() -> None:
    connector = FakeConnector()

    def empty_execute(request):
        return ConnectorResult(
            capability=request.context.capability,
            provider="autotask",
            data={"items": []},
        )

    connector.execute = empty_execute  # type: ignore[method-assign]

    with pytest.raises(AutotaskBusinessContextError) as captured:
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-empty",
            principal_id="operator-1",
            organization_id="aot",
        )

    assert captured.value.error_code == "COMPANY_MATCH_NOT_FOUND"


def test_company_lookup_secret_failure_has_safe_code() -> None:
    connector = FakeConnector()

    def failed_execute(request):
        raise OpenBaoSecretResolutionError("protected secret detail")

    connector.execute = failed_execute  # type: ignore[method-assign]

    with pytest.raises(AutotaskBusinessContextError) as captured:
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-secret",
            principal_id="operator-1",
            organization_id="aot",
        )

    assert captured.value.error_code == "COMPANY_LOOKUP_SECRET_RESOLUTION_FAILED"
    assert "protected secret detail" not in str(captured.value)


def test_company_lookup_provider_failure_has_safe_code() -> None:
    connector = FakeConnector()

    def failed_execute(request):
        raise RuntimeError("protected provider detail")

    connector.execute = failed_execute  # type: ignore[method-assign]

    with pytest.raises(AutotaskBusinessContextError) as captured:
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-provider",
            principal_id="operator-1",
            organization_id="aot",
        )

    assert captured.value.error_code == "COMPANY_LOOKUP_PROVIDER_REQUEST_FAILED"
    assert "protected provider detail" not in str(captured.value)


def test_invalid_provider_items_fail_closed() -> None:
    connector = FakeConnector()

    def invalid_execute(request):
        return ConnectorResult(
            capability=request.context.capability,
            provider="autotask",
            data={"items": "not-a-list"},
        )

    connector.execute = invalid_execute  # type: ignore[method-assign]

    with pytest.raises(AutotaskBusinessContextError) as captured:
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-3",
            principal_id="operator-1",
            organization_id="aot",
        )

    assert captured.value.error_code == "COMPANY_LOOKUP_INVALID_RESPONSE"


def test_record_limit_is_bounded() -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        AutotaskBusinessContextReader(FakeConnector(), max_related_records=101)
