from __future__ import annotations

import json
from typing import Any

import pytest

from connectors.core.contracts import ConnectorResult
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
            assert field == "companyName"
            assert value == "Acme Corp"
            items = [{"id": 208, "companyName": "Acme Corp", "isActive": True}]
        elif capability == "autotask.contact.search":
            items = [{"id": 11, "companyID": 208, "firstName": "Alex"}]
        elif capability == "autotask.configuration.search":
            items = [{"id": 22, "companyID": 208, "referenceTitle": "PC-22"}]
        elif capability == "autotask.ticket.search":
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
        "autotask.contact.search",
        "autotask.configuration.search",
        "autotask.ticket.search",
        "autotask.contract.search",
        "autotask.project.search",
    ]
    assert connector.requests[0].context.client_id is None
    assert all(
        request.context.client_id == "208"
        for request in connector.requests[1:]
    )
    assert all(request.context.mode == "observe" for request in connector.requests)


def test_company_lookup_requires_exactly_one_exact_match() -> None:
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

    with pytest.raises(
        AutotaskBusinessContextError,
        match="exactly one exact Autotask company",
    ):
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-2",
            principal_id="operator-1",
            organization_id="aot",
        )


def test_invalid_provider_items_fail_closed() -> None:
    connector = FakeConnector()

    def invalid_execute(request):
        return ConnectorResult(
            capability=request.context.capability,
            provider="autotask",
            data={"items": "not-a-list"},
        )

    connector.execute = invalid_execute  # type: ignore[method-assign]

    with pytest.raises(
        AutotaskBusinessContextError,
        match="invalid items collection",
    ):
        AutotaskBusinessContextReader(connector).read_company_context(
            company_name="Acme Corp",
            correlation_id="corr-3",
            principal_id="operator-1",
            organization_id="aot",
        )


def test_record_limit_is_bounded() -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        AutotaskBusinessContextReader(FakeConnector(), max_related_records=101)
