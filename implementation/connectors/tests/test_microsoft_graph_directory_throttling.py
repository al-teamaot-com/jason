from __future__ import annotations

import pytest

from connectors.core.contracts import ConnectorTransportError
from connectors.microsoft_graph.user_directory import MicrosoftGraphUserDirectoryReader


class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str:
        assert microsoft_tenant_id == "tenant-1"
        return "token"


class Transport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def success():
    return {
        "id": "object-1",
        "mail": "user@example.com",
        "userPrincipalName": "user@example.com",
        "accountEnabled": True,
    }


def test_graph_429_retries_with_bounded_retry_after_then_succeeds():
    transport = Transport(
        [
            ConnectorTransportError(
                "HTTP transport failed with status 429",
                status_code=429,
                retry_after_seconds=12.0,
            ),
            success(),
        ]
    )
    delays = []
    reader = MicrosoftGraphUserDirectoryReader(
        tokens=Tokens(),
        transport=transport,
        max_attempts=3,
        max_retry_delay_seconds=5.0,
        sleeper=delays.append,
    )

    email = reader.resolve_email(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    )

    assert email == "user@example.com"
    assert len(transport.calls) == 2
    assert delays == [5.0]


def test_graph_429_without_retry_after_uses_bounded_exponential_delay():
    transport = Transport(
        [
            ConnectorTransportError(
                "HTTP transport failed with status 429",
                status_code=429,
            ),
            ConnectorTransportError(
                "HTTP transport failed with status 429",
                status_code=429,
            ),
            success(),
        ]
    )
    delays = []
    reader = MicrosoftGraphUserDirectoryReader(
        tokens=Tokens(),
        transport=transport,
        sleeper=delays.append,
    )

    assert reader.resolve_email(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
    ) == "user@example.com"
    assert delays == [1.0, 2.0]


def test_non_throttling_transport_failure_is_not_retried():
    failure = ConnectorTransportError(
        "HTTP transport failed with status 503",
        status_code=503,
    )
    transport = Transport([failure])
    delays = []
    reader = MicrosoftGraphUserDirectoryReader(
        tokens=Tokens(),
        transport=transport,
        sleeper=delays.append,
    )

    with pytest.raises(ConnectorTransportError) as raised:
        reader.resolve_email(
            microsoft_tenant_id="tenant-1",
            microsoft_object_id="object-1",
        )

    assert raised.value is failure
    assert len(transport.calls) == 1
    assert delays == []


def test_persistent_graph_throttling_remains_fail_closed_after_bound():
    failures = [
        ConnectorTransportError(
            "HTTP transport failed with status 429",
            status_code=429,
            retry_after_seconds=0,
        )
        for _ in range(3)
    ]
    transport = Transport(failures)
    reader = MicrosoftGraphUserDirectoryReader(
        tokens=Tokens(),
        transport=transport,
        max_attempts=3,
        sleeper=lambda _: None,
    )

    with pytest.raises(ConnectorTransportError) as raised:
        reader.resolve_email(
            microsoft_tenant_id="tenant-1",
            microsoft_object_id="object-1",
        )

    assert raised.value.status_code == 429
    assert len(transport.calls) == 3
