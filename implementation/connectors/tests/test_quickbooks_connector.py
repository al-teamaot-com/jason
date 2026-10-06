from __future__ import annotations

import pytest

from connectors.quickbooks import connector as quickbooks_connector
from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.quickbooks.connector import (
    QUICKBOOKS_ACCOUNT_SEARCH,
    QUICKBOOKS_BALANCE_SHEET_READ,
    QUICKBOOKS_COMPANY_READ,
    QUICKBOOKS_CUSTOMER_CREATE,
    QuickBooksConnector,
)
from connectors.quickbooks.oauth import QuickBooksOAuthStore, QuickBooksReconnectRequiredError


class FakeSecrets:
    def __init__(self):
        self.calls = []

    def resolve(self, logical_name, context):
        self.calls.append(logical_name)
        return {
            "client_id": "public-client-id",
            "client_secret": "private-secret",
        }


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


def _context(capability, *, organization_id="aot", mode="observe"):
    return ConnectorContext(
        correlation_id="corr-qbo-001",
        principal_id="person-al",
        organization_id=organization_id,
        client_id=None,
        capability=capability,
        mode=mode,
    )


def _build(tmp_path):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    store.set_token(
        {
            "access_token": "sandbox-access",
            "refresh_token": "sandbox-refresh",
            "expires_in": 3600,
        },
        realm_id="1234567890123456",
        environment="sandbox",
    )
    secrets = FakeSecrets()
    transport = FakeTransport()
    audit = FakeAudit()
    connector = QuickBooksConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        oauth_store=store,
        expected_environment="sandbox",
    )
    return connector, secrets, transport, audit


def test_company_read_uses_oauth_bound_realm_and_sandbox_base(tmp_path):
    connector, secrets, transport, audit = _build(tmp_path)

    result = connector.execute(
        ConnectorRequest(_context(QUICKBOOKS_COMPANY_READ), {})
    )

    assert result.provider == "quickbooks"
    call = transport.calls[-1]
    assert call["method"] == "GET"
    assert call["url"] == (
        "https://sandbox-quickbooks.api.intuit.com/v3/company/"
        "1234567890123456/companyinfo/1234567890123456"
    )
    assert call["headers"]["Authorization"] == "Bearer sandbox-access"
    assert secrets.calls == ["quickbooks.oauth_client"]
    assert audit.events[0][1]["realm_bound_by_oauth"] is True


def test_company_read_uses_production_secret_and_production_base(tmp_path):
    store = QuickBooksOAuthStore(tmp_path / "production-oauth.sqlite3")
    store.set_token(
        {"access_token": "production-access", "refresh_token": "production-refresh", "expires_in": 3600},
        realm_id="2222222222222222",
        environment="production",
    )
    secrets = FakeSecrets()
    transport = FakeTransport()
    audit = FakeAudit()
    connector = QuickBooksConnector(
        secrets=secrets, transport=transport, audit=audit, oauth_store=store,
        expected_environment="production",
    )
    result = connector.execute(ConnectorRequest(_context(QUICKBOOKS_COMPANY_READ), {}))
    assert result.provider == "quickbooks"
    call = transport.calls[-1]
    assert call["url"] == (
        "https://quickbooks.api.intuit.com/v3/company/"
        "2222222222222222/companyinfo/2222222222222222"
    )
    assert secrets.calls == ["quickbooks.production.oauth_client"]
    assert audit.events[0][1]["environment"] == "production"


def test_raw_query_realm_and_environment_are_rejected_before_provider_call(tmp_path):
    connector, secrets, transport, _ = _build(tmp_path)

    for arguments in (
        {"query": "select * from Vendor"},
        {"realm_id": "999"},
        {"realmId": "999"},
        {"environment": "production"},
    ):
        with pytest.raises(ConnectorAuthorizationError, match="server-derived"):
            connector.execute(
                ConnectorRequest(
                    _context(QUICKBOOKS_ACCOUNT_SEARCH),
                    arguments,
                )
            )

    assert secrets.calls == []
    assert transport.calls == []


def test_account_search_builds_only_fixed_entity_query(tmp_path):
    connector, _, transport, _ = _build(tmp_path)

    connector.execute(
        ConnectorRequest(
            _context(QUICKBOOKS_ACCOUNT_SEARCH),
            {"start_position": 5, "max_results": 25},
        )
    )

    call = transport.calls[-1]
    assert call["url"].endswith("/v3/company/1234567890123456/query")
    assert call["params"] == {
        "query": "select * from Account startposition 5 maxresults 25"
    }


def test_query_paging_is_bounded(tmp_path):
    connector, secrets, transport, _ = _build(tmp_path)

    with pytest.raises(ConnectorConfigurationError, match="max_results"):
        connector.execute(
            ConnectorRequest(
                _context(QUICKBOOKS_ACCOUNT_SEARCH),
                {"max_results": 1001},
            )
        )

    assert secrets.calls == []
    assert transport.calls == []


def test_report_dates_are_validated_and_forwarded(tmp_path):
    connector, _, transport, _ = _build(tmp_path)

    connector.execute(
        ConnectorRequest(
            _context(QUICKBOOKS_BALANCE_SHEET_READ),
            {"start_date": "2026-01-01", "end_date": "2026-09-30"},
        )
    )
    assert transport.calls[-1]["params"] == {
        "start_date": "2026-01-01",
        "end_date": "2026-09-30",
    }

    with pytest.raises(ConnectorConfigurationError, match="after"):
        connector.execute(
            ConnectorRequest(
                _context(QUICKBOOKS_BALANCE_SHEET_READ),
                {"start_date": "2026-10-01", "end_date": "2026-09-30"},
            )
        )


def test_non_aot_organization_fails_before_secret_resolution(tmp_path):
    connector, secrets, transport, _ = _build(tmp_path)

    with pytest.raises(ConnectorAuthorizationError, match="AOT organization"):
        connector.execute(
            ConnectorRequest(
                _context(QUICKBOOKS_COMPANY_READ, organization_id="other"),
                {},
            )
        )

    assert secrets.calls == []
    assert transport.calls == []


def test_reconnect_required_is_explicit_and_audited(tmp_path, monkeypatch):
    connector, _, _, audit = _build(tmp_path)
    monkeypatch.setattr(
        quickbooks_connector,
        "quickbooks_access_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            QuickBooksReconnectRequiredError("reconnect is required")
        ),
    )

    with pytest.raises(ConnectorAuthorizationError, match="requires reconnect"):
        connector.execute(ConnectorRequest(_context(QUICKBOOKS_COMPANY_READ), {}))

    assert audit.events[-1][0] == "connector.authorization_reconnect_required"
    assert audit.events[-1][1] == {"provider": "quickbooks"}


def test_completed_read_audits_intuit_tid_without_raw_headers(tmp_path):
    connector, _, transport, audit = _build(tmp_path)
    original_request = transport.request

    def request_with_trace(**kwargs):
        kwargs["response_metadata"]["provider_trace_id"] = "intuit-trace-qbo-789"
        return original_request(**kwargs)

    transport.request = request_with_trace

    connector.execute(ConnectorRequest(_context(QUICKBOOKS_COMPANY_READ), {}))

    event_type, details = audit.events[-1]
    assert event_type == "connector.completed"
    assert details["intuit_tid"] == "intuit-trace-qbo-789"
    assert set(details) == {
        "provider",
        "environment",
        "realm_bound_by_oauth",
        "intuit_tid",
    }


def test_customer_create_is_sandbox_only_and_uses_bounded_payload(tmp_path):
    connector, _, transport, audit = _build(tmp_path)

    result = connector.execute(
        ConnectorRequest(
            _context(QUICKBOOKS_CUSTOMER_CREATE, mode="execute"),
            {
                "display_name": "Jason Sandbox Write Probe",
                "company_name": "Atlantic Office Technologies",
                "given_name": "Jason",
                "family_name": "Probe",
                "email": "sandbox-probe@example.invalid",
                "phone": "555-0100",
            },
        )
    )

    assert result.provider == "quickbooks"
    call = transport.calls[-1]
    assert call["method"] == "POST"
    assert call["url"] == (
        "https://sandbox-quickbooks.api.intuit.com/v3/company/"
        "1234567890123456/customer"
    )
    assert call["params"] is None
    assert call["json"] == {
        "DisplayName": "Jason Sandbox Write Probe",
        "CompanyName": "Atlantic Office Technologies",
        "GivenName": "Jason",
        "FamilyName": "Probe",
        "PrimaryEmailAddr": {"Address": "sandbox-probe@example.invalid"},
        "PrimaryPhone": {"FreeFormNumber": "555-0100"},
    }
    assert audit.events[0][1]["environment"] == "sandbox"


def test_customer_create_requires_execute_mode(tmp_path):
    connector, secrets, transport, _ = _build(tmp_path)

    with pytest.raises(ConnectorAuthorizationError, match="requires execute mode"):
        connector.execute(
            ConnectorRequest(
                _context(QUICKBOOKS_CUSTOMER_CREATE),
                {"display_name": "Blocked Probe"},
            )
        )

    assert secrets.calls == []
    assert transport.calls == []


def test_customer_create_rejects_raw_payload_and_missing_name(tmp_path):
    connector, secrets, transport, _ = _build(tmp_path)

    with pytest.raises(ConnectorConfigurationError, match="unsupported argument"):
        connector.execute(
            ConnectorRequest(
                _context(QUICKBOOKS_CUSTOMER_CREATE, mode="execute"),
                {"payload": {"DisplayName": "raw-provider-payload"}},
            )
        )

    with pytest.raises(ConnectorConfigurationError, match="requires display_name"):
        connector.execute(
            ConnectorRequest(
                _context(QUICKBOOKS_CUSTOMER_CREATE, mode="execute"),
                {},
            )
        )

    assert secrets.calls == []
    assert transport.calls == []


def test_customer_create_is_hard_blocked_in_production(tmp_path):
    store = QuickBooksOAuthStore(tmp_path / "production-oauth.sqlite3")
    store.set_token(
        {"access_token": "production-access", "refresh_token": "production-refresh", "expires_in": 3600},
        realm_id="2222222222222222",
        environment="production",
    )
    secrets = FakeSecrets()
    transport = FakeTransport()
    connector = QuickBooksConnector(
        secrets=secrets, transport=transport, audit=FakeAudit(), oauth_store=store,
        expected_environment="production",
    )

    with pytest.raises(ConnectorAuthorizationError, match="sandbox-only"):
        connector.execute(
            ConnectorRequest(
                _context(QUICKBOOKS_CUSTOMER_CREATE, mode="execute"),
                {"display_name": "Never Create In Production"},
            )
        )

    assert secrets.calls == []
    assert transport.calls == []
