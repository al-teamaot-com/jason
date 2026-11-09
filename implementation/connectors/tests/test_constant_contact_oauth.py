from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from connectors.constant_contact.oauth import (
    AUTHORIZE_URL,
    REDIRECT_URI,
    ConstantContactOAuthError,
    authorization_url,
    callback_code,
)

CLIENT_ID = "ad24a820-822f-4c66-8446-3407167bc78a"
STATE = "0123456789abcdef0123456789abcdef0123456789abcdef"


def test_authorization_url_uses_exact_scope_and_registered_host():
    url = authorization_url(client_id=CLIENT_ID, state=STATE)
    parsed = urlsplit(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTHORIZE_URL
    query = parse_qs(parsed.query)
    assert query == {
        "client_id": [CLIENT_ID],
        "redirect_uri": [REDIRECT_URI],
        "response_type": ["code"],
        "scope": ["contact_data offline_access"],
        "state": [STATE],
    }


@pytest.mark.parametrize("client_id,state,redirect_uri", [
    ("", STATE, REDIRECT_URI),
    (CLIENT_ID, "short", REDIRECT_URI),
    (CLIENT_ID, STATE, "https://attacker.example/callback"),
])
def test_authorization_url_rejects_invalid_inputs(client_id, state, redirect_uri):
    with pytest.raises(ConstantContactOAuthError):
        authorization_url(client_id=client_id, state=state, redirect_uri=redirect_uri)


def test_callback_accepts_matching_state():
    assert callback_code(query_string=f"code=one-time-code&state={STATE}", expected_state=STATE) == "one-time-code"


@pytest.mark.parametrize("query", [
    "code=secret&state=incorrect",
    f"code=a&code=b&state={STATE}",
    f"code=a&state={STATE}&state=another",
    f"error=access_denied&state={STATE}",
    f"code=a&state={STATE}&redirect_uri=https://attacker.example",
    f"code=&state={STATE}",
    "malformed",
])
def test_callback_rejects_invalid_and_ambiguous_responses(query):
    with pytest.raises(ConstantContactOAuthError):
        callback_code(query_string=query, expected_state=STATE)


def test_callback_does_not_include_secret_code_in_exception():
    with pytest.raises(ConstantContactOAuthError) as exc:
        callback_code(query_string="code=private-code&state=wrong", expected_state=STATE)
    assert "private-code" not in str(exc.value)
