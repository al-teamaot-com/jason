import json
from urllib.parse import parse_qs

import pytest

from connectors.constant_contact.oauth import TOKEN_URL, REDIRECT_URI
from connectors.constant_contact.token_exchange import OAuthTokenError, exchange_code, rotate_refresh_token


class Response:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        return json.dumps(self.data).encode()[:n]


def valid_response():
    return {"token_type": "Bearer", "access_token": "access-secret",
            "refresh_token": "refresh-secret", "scope": "contact_data offline_access",
            "expires_in": 28800}


def test_exchange_is_exact_host_basic_auth_and_form_data():
    seen = {}
    def transport(request, timeout):
        seen["url"], seen["method"], seen["auth"] = request.full_url, request.get_method(), request.get_header("Authorization")
        seen["form"] = parse_qs(request.data.decode())
        return Response(valid_response())
    token = exchange_code("auth-code", client_id="client", client_secret="private", transport=transport)
    assert seen["url"] == TOKEN_URL
    assert seen["method"] == "POST"
    assert seen["auth"].startswith("Basic ")
    assert seen["form"] == {"code": ["auth-code"], "grant_type": ["authorization_code"], "redirect_uri": [REDIRECT_URI]}
    assert token["access_token"] == "access-secret"
    assert token["refresh_token"] == "refresh-secret"


def test_refresh_replaces_token_pair():
    def transport(request, timeout):
        assert parse_qs(request.data.decode()) == {"refresh_token": ["old-token"], "grant_type": ["refresh_token"]}
        return Response(valid_response())
    assert rotate_refresh_token("old-token", client_id="c", client_secret="s", transport=transport)["refresh_token"] == "refresh-secret"


def test_scope_failure_is_redacted():
    bad = dict(valid_response(), scope="offline_access")
    with pytest.raises(OAuthTokenError) as exc:
        exchange_code("private-code", client_id="c", client_secret="s",
                      transport=lambda req, timeout: Response(bad))
    assert "private-code" not in str(exc.value)


def test_token_response_missing_rotated_refresh_fails_closed():
    bad = dict(valid_response())
    bad.pop("refresh_token")
    with pytest.raises(OAuthTokenError):
        rotate_refresh_token("old", client_id="c", client_secret="s",
                             transport=lambda req, timeout: Response(bad))
