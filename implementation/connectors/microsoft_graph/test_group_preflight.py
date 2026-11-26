"""Read-only pilot validation using simulated tenant identities and Graph GETs."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorTransportError
from connectors.microsoft_graph.group_executor import MicrosoftGroupBoundaryValidator
from connectors.microsoft_graph.group_preflight import MicrosoftGroupTenantPreflight
from connectors.microsoft_graph.token import GRAPH_DEFAULT_SCOPE, MicrosoftApplicationToken
from kernel.client_boundaries import InMemoryClientBoundaryRepository, BoundaryStatus, ClientBoundary

TENANT = "11111111-1111-4111-8111-111111111111"
READ_APP = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
WRITE_APP = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
NOW = datetime.now(timezone.utc)


class Tokens:
    def __init__(self, app):
        self.app = app
        self.tenant = TENANT
        self.calls = 0

    def acquire_for_client(self, *, client_id, correlation_id):
        assert client_id == "client-17" and correlation_id == "correlation-17"
        self.calls += 1
        return MicrosoftApplicationToken(
            access_token="private-token", token_type="Bearer", expires_at_epoch=9999999999,
            tenant_id=self.tenant, application_id=self.app, scope=GRAPH_DEFAULT_SCOPE,
            certificate_thumbprint="A" * 40,
        )


class ReadTransport:
    def __init__(self): self.calls = []; self.bad_shape = False
    def request(self, *, method, url, headers, params, timeout_seconds):
        self.calls.append((method, url))
        assert method == "GET" and url in {
            "https://graph.microsoft.com/v1.0/groups",
            "https://graph.microsoft.com/v1.0/users",
        }
        assert params == {"$select": "id", "$top": 1}
        return {} if self.bad_shape else {"value": []}


def boundary(bid, provider, profile, app):
    return ClientBoundary(
        id=bid, client_id="client-17", provider=provider, external_tenant_id=TENANT,
        primary_domain="example.test", profile=profile, application_id=app,
        status=BoundaryStatus.VALIDATED, consent_transaction_id="consent-17",
        created_at=NOW, consented_at=NOW, validated_at=NOW,
    )


def harness():
    registry = InMemoryClientBoundaryRepository()
    registry.add(boundary("read", "microsoft_graph_group_read", "group-read", READ_APP))
    registry.add(boundary("write", "microsoft_graph_group_write", "group-write", WRITE_APP))
    rt, wt, transport = Tokens(READ_APP), Tokens(WRITE_APP), ReadTransport()
    probe = MicrosoftGroupTenantPreflight(
        boundaries=MicrosoftGroupBoundaryValidator(registry),
        read_tokens=rt, write_tokens=wt, read_transport=transport,
    )
    return registry, rt, wt, transport, probe


def test_verified_identities_and_read_access_only():
    _, rt, wt, transport, probe = harness()
    result = probe.inspect(client_id="client-17", correlation_id="correlation-17")
    assert result.read_identity_verified and result.write_identity_verified
    assert result.group_read_verified and result.user_read_verified
    assert result.write_permission_grant_verified is False
    assert result.live_mutation_permitted is False
    assert rt.calls == wt.calls == 1
    assert len(transport.calls) == 2
    assert all(method == "GET" for method, _ in transport.calls)
    assert "private-token" not in repr(result)


def test_tenant_app_mismatch_blocks_before_http():
    _, rt, wt, transport, probe = harness()
    wt.app = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    with pytest.raises(ConnectorAuthorizationError, match="TOKEN_SCOPE_MISMATCH"):
        probe.inspect(client_id="client-17", correlation_id="correlation-17")
    assert not transport.calls


def test_read_consent_revoked_blocks_all_token_calls():
    registry, rt, wt, transport, probe = harness()
    registry.replace(replace(registry.get("read"), status=BoundaryStatus.REVOKED))
    with pytest.raises(ConnectorAuthorizationError, match="CONSENT_UNVERIFIED"):
        probe.inspect(client_id="client-17", correlation_id="correlation-17")
    assert rt.calls == wt.calls == 0
    assert not transport.calls


def test_read_endpoint_errors_fail_closed():
    _, _, _, transport, probe = harness()
    transport.bad_shape = True
    with pytest.raises(ConnectorTransportError):
        probe.inspect(client_id="client-17", correlation_id="correlation-17")
    assert len(transport.calls) == 1
