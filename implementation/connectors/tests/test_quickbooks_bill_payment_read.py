"""Governed, read-only QuickBooks BillPayment discovery regression."""
from __future__ import annotations

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorConfigurationError,
    ConnectorRequest,
)
from connectors.quickbooks.connector import QUICKBOOKS_BILL_PAYMENT_SEARCH
from test_quickbooks_connector import _build, _context


def test_billpayment_uses_only_server_constructed_query_and_oauth_realm(tmp_path):
    connector, secrets, transport, audit = _build(tmp_path)
    result = connector.execute(ConnectorRequest(
        _context(QUICKBOOKS_BILL_PAYMENT_SEARCH),
        {"start_position": 1, "max_results": 50},
    ))
    assert result.provider == "quickbooks"
    call = transport.calls[-1]
    assert call["method"] == "GET"
    assert call["url"] == (
        "https://sandbox-quickbooks.api.intuit.com/v3/company/"
        "1234567890123456/query"
    )
    assert call["params"] == {
        "query": "select * from BillPayment startposition 1 maxresults 50"
    }
    assert secrets.calls == ["quickbooks.oauth_client"]
    assert audit.events[0][1]["realm_bound_by_oauth"] is True


@pytest.mark.parametrize("arguments", [
    {"query": "select * from BillPayment"},
    {"realm_id": "foreign-company"},
    {"environment": "production"},
])
def test_billpayment_caller_cannot_override_scope_or_query(tmp_path, arguments):
    connector, secrets, transport, _ = _build(tmp_path)
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(ConnectorRequest(
            _context(QUICKBOOKS_BILL_PAYMENT_SEARCH), arguments,
        ))
    assert secrets.calls == []
    assert transport.calls == []


@pytest.mark.parametrize("arguments", [
    {"max_results": 1001}, {"start_position": 0}, {"vendor_id": "1"},
])
def test_billpayment_bounded_paging_without_free_form_filters(tmp_path, arguments):
    connector, secrets, transport, _ = _build(tmp_path)
    with pytest.raises(ConnectorConfigurationError):
        connector.execute(ConnectorRequest(
            _context(QUICKBOOKS_BILL_PAYMENT_SEARCH), arguments,
        ))
    assert secrets.calls == []
    assert transport.calls == []


def test_billpayment_denies_other_organization_before_provider_access(tmp_path):
    connector, secrets, transport, _ = _build(tmp_path)
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(ConnectorRequest(
            _context(QUICKBOOKS_BILL_PAYMENT_SEARCH, organization_id="other-msp"),
            {},
        ))
    assert secrets.calls == []
    assert transport.calls == []
