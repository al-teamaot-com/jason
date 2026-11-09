import base64
import time
from pathlib import Path

import pytest

from connectors.constant_contact.connector import (
    ConstantContactConnector, CONTACTS_SEARCH, LISTS_SEARCH,
)
from connectors.constant_contact.oauth_store import EncryptedOAuthStore
from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorConfigurationError,
    ConnectorContext, ConnectorRequest,
)


KEY = b"x" * 32


class Secrets:
    def resolve(self, logical, context):
        assert logical == "constant_contact.oauth_client"
        return {"client_id": "id", "client_secret": "secret",
                "token_key_b64": base64.b64encode(KEY).decode()}


class Audit:
    def __init__(self):
        self.events = []
    def record(self, event, context, details):
        self.events.append((event, details))


class Transport:
    def __init__(self):
        self.calls = []
    def request(self, **kwargs):
        self.calls.append(kwargs)
        return {"contacts": [], "_links": {}}


def ctx(capability=CONTACTS_SEARCH, organization="aot", mode="observe"):
    return ConnectorContext(correlation_id="cc-test", principal_id="aot-tech",
                            organization_id=organization, client_id=None,
                            capability=capability, mode=mode)


def connector(tmp_path):
    db = tmp_path / "oauth.sqlite3"
    EncryptedOAuthStore(db, KEY).save_tokens({
        "access_token": "fake", "refresh_token": "fake-refresh",
        "expires_at": int(time.time()) + 5000,
    })
    audit, transport = Audit(), Transport()
    return ConstantContactConnector(secrets=Secrets(), transport=transport,
                                    audit=audit, oauth_db=db), transport, audit


def test_read_routes_through_injected_transport(tmp_path):
    adapter, transport, audit = connector(tmp_path)
    result = adapter.execute(ConnectorRequest(ctx(), {"limit": 25}))
    assert result.provider == "constant_contact"
    assert transport.calls[0]["url"] == "https://api.cc.email/v3/contacts"
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["params"] == {"limit": 25}
    assert [name for name, details in audit.events] == ["connector.requested", "connector.completed"]


@pytest.mark.parametrize("context,arguments", [
    (ctx(organization="other"), {}),
    (ctx(mode="execute"), {}),
    (ctx(capability="marketing.contact.import"), {}),
    (ctx(), {"url": "https://evil.example"}),
    (ctx(), {"limit": 9999}),
])
def test_unauthorized_or_unbounded_requests_fail_without_provider_access(tmp_path, context, arguments):
    adapter, transport, audit = connector(tmp_path)
    with pytest.raises((ConnectorAuthorizationError, ConnectorConfigurationError)):
        adapter.execute(ConnectorRequest(context, arguments))
    assert transport.calls == []


def test_exact_email_lookup_includes_deleted_and_list_readback(tmp_path):
    adapter, transport, audit = connector(tmp_path)
    adapter.execute(ConnectorRequest(ctx(), {
        "email": "ONE@EXAMPLE.COM", "status": "all", "include": "list_memberships",
        "limit": 5,
    }))
    assert transport.calls[0]["params"] == {
        "limit": 5, "email": "one@example.com", "status": "all",
        "include": "list_memberships",
    }


@pytest.mark.parametrize("arguments", [
    {"email": "invalid"},
    {"email": "x" * 51 + "@example.com"},
    {"status": "something-else"},
    {"include": "notes"},
])
def test_invalid_contact_filters_denied_without_provider_access(tmp_path, arguments):
    adapter, transport, audit = connector(tmp_path)
    with pytest.raises(ConnectorConfigurationError):
        adapter.execute(ConnectorRequest(ctx(), arguments))
    assert transport.calls == []
