from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit

import pytest

from connectors.constant_contact.read_transport import ConstantContactProviderError, read_page


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.content[:size]


def test_read_is_allowlisted_paginated_and_bearer_authenticated():
    seen = {}

    def fake_transport(request, timeout):
        seen["url"] = request.full_url
        seen["token"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return FakeResponse(b'{"lists": [], "_links": {}}')

    output = read_page(resource="/contact_lists", access_token="test-token", cursor="abc+123",
                       transport=fake_transport)
    assert output["lists"] == []
    assert urlsplit(seen["url"]).netloc == "api.cc.email"
    assert parse_qs(urlsplit(seen["url"]).query)["cursor"] == ["abc+123"]
    assert seen["token"] == "Bearer test-token"
    assert seen["timeout"] == 15


@pytest.mark.parametrize("resource", [
    "https://attacker.example/contacts",
    "/activities/contacts_json_import",
    "/contacts/123",
    "//attacker.example/contacts",
    "/contacts?limit=999999",
])
def test_external_or_write_resources_are_refused(resource):
    with pytest.raises(ConstantContactProviderError):
        read_page(resource=resource, access_token="token")


def test_response_limit_is_enforced_without_leaking_data():
    with pytest.raises(ConstantContactProviderError, match="exceeds limit"):
        read_page(resource="/contacts", access_token="token",
                  transport=lambda req, timeout: FakeResponse(b"x" * 1048577))
