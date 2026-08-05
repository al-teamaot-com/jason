from __future__ import annotations

import io
import json
from urllib.error import URLError

import pytest

from jason_cap_001.autotask_http_transport import (
    AutotaskCredentialReferences,
    AutotaskTransportError,
)
from jason_cap_001.autotask_production_transport import (
    AutotaskZoneDiscovery,
    ProductionJsonHttpClient,
    build_autotask_ticket_transport,
)


class Response:
    def __init__(self, status: int, payload: object) -> None:
        self._status = status
        self._body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body.read()


class Secrets:
    def __init__(self) -> None:
        self.values = {
            "autotask/username": "integration@example.com",
            "autotask/secret": "secret-value",
            "autotask/code": "integration-code",
        }

    def get_secret(self, reference: str) -> str:
        return self.values[reference]


def credentials() -> AutotaskCredentialReferences:
    return AutotaskCredentialReferences(
        username="autotask/username",
        secret="autotask/secret",
        integration_code="autotask/code",
    )


def test_http_client_performs_https_get_and_decodes_json() -> None:
    captured = {}

    def opener(request, *, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return Response(200, {"items": []})

    client = ProductionJsonHttpClient(opener=opener, retry_attempts=0)
    status, payload = client.get_json(
        "https://example.test/v1.0/Tickets/query",
        headers={"Accept": "application/json"},
        params={"search": '{"filter":[]}'},
        timeout_seconds=7.5,
    )

    assert status == 200
    assert payload == {"items": []}
    assert captured["url"].startswith("https://example.test/")
    assert "search=" in captured["url"]
    assert captured["timeout"] == 7.5


def test_http_client_retries_transient_network_failures() -> None:
    attempts = []
    sleeps = []

    def opener(_request, *, timeout):
        attempts.append(timeout)
        if len(attempts) < 3:
            raise URLError("temporary failure with secret-value")
        return Response(200, {"items": []})

    client = ProductionJsonHttpClient(
        opener=opener,
        retry_attempts=2,
        retry_delay_seconds=0.1,
        sleeper=sleeps.append,
    )

    assert client.get_json(
        "https://example.test/query",
        headers={},
        params={},
        timeout_seconds=3.0,
    ) == (200, {"items": []})
    assert len(attempts) == 3
    assert sleeps == [0.1, 0.1]


def test_http_client_redacts_terminal_network_failure() -> None:
    def opener(_request, *, timeout):
        raise URLError(f"failed at {timeout} with secret-value")

    client = ProductionJsonHttpClient(opener=opener, retry_attempts=0)

    with pytest.raises(AutotaskTransportError) as error:
        client.get_json(
            "https://example.test/query",
            headers={"Secret": "secret-value"},
            params={},
            timeout_seconds=3.0,
        )

    assert "secret-value" not in str(error.value)


def test_zone_discovery_requires_https_url() -> None:
    class Http:
        def get_json(self, *_args, **_kwargs):
            return 200, {"url": "http://unsafe.example.test/atservicesrest"}

    with pytest.raises(AutotaskTransportError, match="non-HTTPS"):
        AutotaskZoneDiscovery().resolve_base_url(
            username_reference="autotask/username",
            secrets=Secrets(),
            http=Http(),
        )


def test_builder_discovers_zone_and_creates_read_only_transport() -> None:
    requests = []

    def opener(request, *, timeout):
        requests.append((request.full_url, dict(request.header_items()), timeout))
        if "zoneInformation" in request.full_url:
            return Response(
                200,
                {"url": "https://zone.example.test/atservicesrest"},
            )
        return Response(
            200,
            {
                "items": [
                    {
                        "ticketNumber": "T20260805.0001",
                        "companyID": 42,
                    }
                ]
            },
        )

    http = ProductionJsonHttpClient(opener=opener, retry_attempts=0)
    transport = build_autotask_ticket_transport(
        credentials=credentials(),
        secrets=Secrets(),
        http=http,
    )

    items = transport.query_tickets(
        ticket_number="T20260805.0001",
        company_id="42",
    )

    assert items[0]["ticketNumber"] == "T20260805.0001"
    assert requests[0][0].startswith(
        "https://webservices.autotask.net/atservicesrest/"
    )
    assert requests[1][0].startswith(
        "https://zone.example.test/atservicesrest/v1.0/Tickets/query"
    )
    request_headers = requests[1][1]
    assert request_headers["Secret"] == "secret-value"
    assert request_headers["Username"] == "integration@example.com"
    assert request_headers["Apiintegrationcode"] == "integration-code"
