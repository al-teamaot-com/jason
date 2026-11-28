"""Read-only ledger entity searches use fixed server-authored QuickBooks queries."""
from __future__ import annotations

import pytest
from connectors.core.contracts import ConnectorRequest, ConnectorAuthorizationError, ConnectorConfigurationError
from test_quickbooks_connector import _build, _context
from connectors.quickbooks import connector as qbo

ENTITIES = {
    "PAYMENT": "Payment",
    "DEPOSIT": "Deposit",
    "PURCHASE": "Purchase",
    "TRANSFER": "Transfer",
    "JOURNAL_ENTRY": "JournalEntry",
    "CREDIT_MEMO": "CreditMemo",
    "VENDOR_CREDIT": "VendorCredit",
    "REFUND_RECEIPT": "RefundReceipt",
}

@pytest.mark.parametrize("key,entity", ENTITIES.items())
def test_transaction_search_fixed_query_and_realm(tmp_path, key, entity):
    connector, _, transport, _ = _build(tmp_path)
    capability = getattr(qbo, f"QUICKBOOKS_{key}_SEARCH")
    connector.execute(ConnectorRequest(_context(capability), {"start_position": 2, "max_results": 50}))
    call = transport.calls[-1]
    assert call["method"] == "GET"
    assert call["url"] == "https://sandbox-quickbooks.api.intuit.com/v3/company/1234567890123456/query"
    assert call["params"] == {"query": f"select * from {entity} startposition 2 maxresults 50"}

@pytest.mark.parametrize("key", ENTITIES)
@pytest.mark.parametrize("bad_args", [{"query":"select * from Account"}, {"realmId":"other"}, {"max_results":1001}])
def test_transaction_search_rejects_unsafe_args_before_provider(tmp_path, key, bad_args):
    connector, _, transport, _ = _build(tmp_path)
    capability = getattr(qbo, f"QUICKBOOKS_{key}_SEARCH")
    with pytest.raises((ConnectorAuthorizationError, ConnectorConfigurationError)):
        connector.execute(ConnectorRequest(_context(capability), bad_args))
    assert not transport.calls

@pytest.mark.parametrize("key", ENTITIES)
def test_transaction_search_rejects_non_aot_scope(tmp_path, key):
    connector, _, transport, _ = _build(tmp_path)
    capability = getattr(qbo, f"QUICKBOOKS_{key}_SEARCH")
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(ConnectorRequest(_context(capability, organization_id="another-company"), {}))
    assert not transport.calls

@pytest.mark.parametrize("key,entity", ENTITIES.items())
def test_transaction_search_date_bounded(tmp_path, key, entity):
    connector, _, transport, _ = _build(tmp_path)
    capability = getattr(qbo, f"QUICKBOOKS_{key}_SEARCH")
    connector.execute(ConnectorRequest(_context(capability), {
        "start_date": "2026-04-01", "end_date": "2026-04-30",
        "start_position": 1, "max_results": 100,
    }))
    assert transport.calls[-1]["params"] == {
        "query": f"select * from {entity} where TxnDate >= '2026-04-01' and TxnDate <= '2026-04-30' startposition 1 maxresults 100"
    }

@pytest.mark.parametrize("bad_args", [
    {"start_date": "2026-01-01' or Id > '0"},
    {"start_date": "2026-02-30"},
    {"start_date": "2026-05-01", "end_date": "2026-04-01"},
])
def test_transaction_search_rejects_bad_dates_before_transport(tmp_path, bad_args):
    connector, _, transport, _ = _build(tmp_path)
    with pytest.raises(ConnectorConfigurationError):
        connector.execute(ConnectorRequest(_context(qbo.QUICKBOOKS_PAYMENT_SEARCH), bad_args))
    assert not transport.calls
