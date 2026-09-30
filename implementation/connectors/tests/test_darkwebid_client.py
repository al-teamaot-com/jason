from __future__ import annotations

import pytest

from connectors.core.contracts import ConnectorConfigurationError, ConnectorTransportError
from connectors.darkwebid.client import DARKWEBID_API_URL, DarkWebIdClient


class Response:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data if data is not None else {"list": []}
    def json(self):
        return self._data


class Session:
    def __init__(self, response=None, exc=None):
        self.auth = None
        self.headers = {}
        self.response = response or Response()
        self.exc = exc
        self.calls = []
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if self.exc:
            raise self.exc
        return self.response


def test_client_uses_basic_auth_and_documented_host():
    session = Session(Response(data={"list": [{"uuid": "u1"}]}))
    client = DarkWebIdClient(
        {"username": "jason@teamaot.com", "password": "opaque"},
        session=session,
    )
    data = client.get("services/organization.json", {"page": 1})
    assert data["list"][0]["uuid"] == "u1"
    assert session.auth == ("jason@teamaot.com", "opaque")
    assert session.calls[0][0] == DARKWEBID_API_URL + "services/organization.json"
    assert session.calls[0][1] == {"page": 1}


def test_unapproved_path_fails_before_request():
    session = Session()
    client = DarkWebIdClient(
        {"username": "jason@teamaot.com", "password": "opaque"},
        session=session,
    )
    with pytest.raises(ConnectorConfigurationError, match="allowlisted"):
        client.get("services/v2/organization")
    assert session.calls == []


def test_authentication_failure_does_not_expose_secret():
    session = Session(Response(status_code=401, data={}))
    client = DarkWebIdClient(
        {"username": "jason@teamaot.com", "password": "super-secret"},
        session=session,
    )
    with pytest.raises(ConnectorTransportError) as exc:
        client.get("services/organization.json")
    assert "super-secret" not in str(exc.value)


def test_missing_password_fails_closed():
    with pytest.raises(ConnectorConfigurationError, match="password"):
        DarkWebIdClient({"username": "jason@teamaot.com", "password": ""})
