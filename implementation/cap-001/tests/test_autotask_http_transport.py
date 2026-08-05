from __future__ import annotations

import json

import pytest

from jason_cap_001.autotask_http_transport import (
    AutotaskCredentialReferences,
    AutotaskHttpTicketTransport,
    AutotaskTransportError,
)


class FakeSecrets:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def get_secret(self, reference: str) -> str:
        self.requested.append(reference)
        return {
            "autotask/username": "api@example.com",
            "autotask/secret": "secret-value",
            "autotask/integration": "integration-value",
        }[reference]


class FakeHttp:
    def __init__(self, status: int = 200, payload: object | None = None) -> None:
        self.status = status
        self.payload = payload if payload is not None else {"items": []}
        self.calls: list[dict[str, object]] = []

    def get_json(self, url, *, headers, params, timeout_seconds):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "params": dict(params),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.status, self.payload


def build_transport(http: FakeHttp, secrets: FakeSecrets | None = None):
    return AutotaskHttpTicketTransport(
        base_url="https://webservices1.autotask.net/atservicesrest",
        credentials=AutotaskCredentialReferences(
            username="autotask/username",
            secret="autotask/secret",
            integration_code="autotask/integration",
        ),
        secrets=secrets or FakeSecrets(),
        http=http,
        timeout_seconds=9.0,
    )


def test_queries_exact_ticket_and_company_with_brokered_headers() -> None:
    http = FakeHttp(
        payload={"items": [{"ticketNumber": "T2026.1", "companyID": 42}]}
    )
    secrets = FakeSecrets()

    result = build_transport(http, secrets).query_tickets(
        ticket_number="T2026.1",
        company_id="42",
    )

    assert result == [{"ticketNumber": "T2026.1", "companyID": 42}]
    assert secrets.requested == [
        "autotask/integration",
        "autotask/username",
        "autotask/secret",
    ]
    call = http.calls[0]
    assert call["url"].endswith("/v1.0/Tickets/query")
    assert call["timeout_seconds"] == 9.0
    assert call["headers"] == {
        "ApiIntegrationCode": "integration-value",
        "UserName": "api@example.com",
        "Secret": "secret-value",
        "Accept": "application/json",
    }
    query = json.loads(call["params"]["search"])
    assert query["filter"] == [
        {"op": "eq", "field": "ticketNumber", "value": "T2026.1"},
        {"op": "eq", "field": "companyID", "value": "42"},
    ]


def test_rejects_non_https_base_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        AutotaskHttpTicketTransport(
            base_url="http://example.test",
            credentials=AutotaskCredentialReferences("u", "s", "i"),
            secrets=FakeSecrets(),
            http=FakeHttp(),
        )


@pytest.mark.parametrize(
    ("status", "payload", "message"),
    [
        (401, {"items": []}, "HTTP status 401"),
        (200, [], "must be an object"),
        (200, {}, "missing the items"),
        (200, {"items": ["bad"]}, "objects only"),
    ],
)
def test_fails_closed_on_invalid_responses(status, payload, message) -> None:
    with pytest.raises(AutotaskTransportError, match=message):
        build_transport(FakeHttp(status=status, payload=payload)).query_tickets(
            ticket_number="T1",
            company_id="42",
        )


def test_redacts_transport_exception_details() -> None:
    class ExplodingHttp:
        def get_json(self, *args, **kwargs):
            raise RuntimeError("secret-value leaked")

    transport = AutotaskHttpTicketTransport(
        base_url="https://example.test",
        credentials=AutotaskCredentialReferences(
            "autotask/username",
            "autotask/secret",
            "autotask/integration",
        ),
        secrets=FakeSecrets(),
        http=ExplodingHttp(),
    )

    with pytest.raises(AutotaskTransportError) as exc:
        transport.query_tickets(ticket_number="T1", company_id="42")

    assert "secret-value" not in str(exc.value)
