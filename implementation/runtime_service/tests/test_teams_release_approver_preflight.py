"""The one Teams gateway checks V4 admin usability before approval issuance."""
import io
import json
from urllib.error import HTTPError
from unittest.mock import patch
from types import SimpleNamespace

import pytest

from jason_runtime.teams_communication_service import ExistingTeamsGatewayTransport
from jason_runtime.teams_message_send import (
    check_existing_teams_gateway_approver_readiness,
)


class _MockResponse:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self): return self.content


def _binding():
    return SimpleNamespace(
        status="active",
        microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        microsoft_object_id="c848022d-e13b-4457-84b0-e2f5c00dcaf6",
    )


def test_gateway_readiness_checks_exact_admin_and_never_sends(tmp_path):
    token = tmp_path / "token"
    token.write_text("synthetic-token")
    transport = ExistingTeamsGatewayTransport(
        gateway_url="https://gateway.invalid", token_file=token,
    )
    seen = []
    def mock_open(request, timeout):
        seen.append((request.full_url, json.loads(request.data)))
        return _MockResponse({"status": "ready", "check": "teams_assigned_plan"})
    with patch("jason_runtime.teams_message_send.urlopen", side_effect=mock_open):
        transport.preflight_release_approver(binding=_binding())
    assert len(seen) == 1
    assert seen[0][0] == "https://gateway.invalid/internal/proactive/approver-readiness"
    assert seen[0][1] == {
        "aadObjectId": "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
        "tenantId": "f7054323-d52b-4863-8c2f-1898f0b6077c",
    }


@pytest.mark.parametrize("code", [
    "approver_teams_license_unavailable",
    "approver_readiness_unverifiable",
    "identity_not_authorized",
])
def test_gateway_teams_unreachable_fails_closed_without_sending(code):
    payload = json.dumps({"status": "blocked", "error_code": code}).encode()
    error = HTTPError(
        url="https://gateway.invalid/internal/proactive/approver-readiness",
        code=409, msg="Blocked", hdrs=None, fp=io.BytesIO(payload),
    )
    with patch("jason_runtime.teams_message_send.urlopen", side_effect=error):
        with pytest.raises(PermissionError, match=code):
            check_existing_teams_gateway_approver_readiness(
                gateway_url="https://gateway.invalid",
                token="synthetic-token",
                tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
                aad_object_id="c848022d-e13b-4457-84b0-e2f5c00dcaf6",
            )


def test_malformed_success_body_is_not_a_usable_approver():
    for body in (
        {"status": "succeeded", "message_id": "fake"},
        {"status": "ready", "check": "unknown"},
        {"status": "ready"},
    ):
        with patch("jason_runtime.teams_message_send.urlopen", return_value=_MockResponse(body)):
            with pytest.raises(PermissionError, match="unverifiable"):
                check_existing_teams_gateway_approver_readiness(
                    gateway_url="https://gateway.invalid",
                    token="synthetic-token",
                    tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
                    aad_object_id="c848022d-e13b-4457-84b0-e2f5c00dcaf6",
                )
