"""Provider-shaped group read tests, including pagination origin pinning."""
import pytest

from connectors.core.contracts import ConnectorTransportError
from connectors.microsoft_graph.group_reader import MicrosoftGraphGroupReader
from connectors.microsoft_graph.user_directory import MicrosoftGraphUserDirectoryReader

TENANT = "11111111-1111-4111-8111-111111111111"
GROUP = "77777777-7777-4777-8777-777777777777"
OWNER = "55555555-5555-4555-8555-555555555555"
MEMBER = "66666666-6666-4666-8666-666666666666"
BASE = "https://graph.microsoft.com/v1.0"


class Tokens:
    def __init__(self): self.calls = []
    def access_token_for_tenant(self, *, microsoft_tenant_id):
        self.calls.append(microsoft_tenant_id)
        assert microsoft_tenant_id == TENANT
        return "read-only-token"


class Transport:
    def __init__(self): self.response = {}; self.calls = []
    def request(self, *, method, url, headers, params=None, timeout_seconds=None, **unused):
        assert method == "GET"
        assert headers["Authorization"] == "Bearer read-only-token"
        self.calls.append((url, params))
        if callable(self.response):
            return self.response(url, params)
        return self.response


def harness(response):
    tokens, transport = Tokens(), Transport()
    transport.response = response
    users = MicrosoftGraphUserDirectoryReader(tokens=tokens, transport=transport)
    return MicrosoftGraphGroupReader(tokens, transport, users), tokens, transport


def test_exact_alias_and_group_readback():
    response = {"value": [{
        "id": GROUP, "mailNickname": "acct", "displayName": "Accounting"}]}
    reader, token, transport = harness(response)
    assert reader.find_groups_by_alias(tenant_id=TENANT, alias="acct")[0]["id"] == GROUP
    assert transport.calls[0][0] == BASE + "/groups"
    assert transport.calls[0][1]["$top"] == 2
    assert token.calls == [TENANT]


def test_search_fails_closed_when_incomplete_or_mismatched():
    for response in (
        {"value": [{"id": GROUP, "mailNickname": "different"}]},
        {"value": [], "@odata.nextLink": "https://graph.microsoft.com/v1.0/groups?$skiptoken=next"},
        {"value": [{}]},
        {"value": None},
        {"value": "broken"},
    ):
        reader, _, _ = harness(response)
        with pytest.raises((ConnectorTransportError, ValueError)):
            reader.find_groups_by_alias(tenant_id=TENANT, alias="acct")


def test_read_group_requires_exact_canonical_id():
    reader, _, _ = harness({"id": GROUP, "groupTypes": [], "isAssignableToRole": False})
    assert reader.read_group(tenant_id=TENANT, group_id=GROUP)["id"] == GROUP
    with pytest.raises((ValueError, ConnectorTransportError)):
        reader.read_group(tenant_id=TENANT, group_id=OWNER)


def test_user_read_only_uses_existing_directory_reader():
    reader, _, transport = harness({"id": OWNER, "accountEnabled": True})
    assert reader.read_user(tenant_id=TENANT, user_id=OWNER)["id"] == OWNER
    assert transport.calls[-1][0] == BASE + "/users/" + OWNER
    reader, _, _ = harness({"id": OWNER, "accountEnabled": False})
    with pytest.raises(PermissionError, match="active"):
        reader.read_user(tenant_id=TENANT, user_id=OWNER)


def test_relationship_paginated_readback_and_no_cross_host_redirect():
    def responses(url, params):
        if url == BASE + "/groups/" + GROUP + "/members":
            return {
                "value": [{"id": OWNER}],
                "@odata.nextLink": BASE + "/groups/" + GROUP + "/members?$skiptoken=two",
            }
        if url.endswith("?$skiptoken=two"):
            return {"value": [{"id": MEMBER}]}
        raise AssertionError("Unknown graph route " + url)
    reader, token, transport = harness(responses)
    assert reader.is_member(tenant_id=TENANT, group_id=GROUP, user_id=MEMBER)
    assert len(transport.calls) == 2
    assert token.calls == [TENANT, TENANT]

    reader, _, transport = harness(lambda url, params: {
        "value": [],
        "@odata.nextLink": "https://malicious.example/v1.0/groups/" + GROUP + "/members?$skiptoken=x",
    })
    with pytest.raises(ConnectorTransportError, match="origin"):
        reader.is_member(tenant_id=TENANT, group_id=GROUP, user_id=MEMBER)
    assert len(transport.calls) == 1


def test_relationship_no_pagination_means_not_member():
    reader, _, _ = harness({"value": [{"id": OWNER}]})
    assert reader.is_member(tenant_id=TENANT, group_id=GROUP, user_id=MEMBER) is False


def test_relationship_same_host_wrong_group_path_denied():
    reader, _, transport = harness({
        "value": [],
        "@odata.nextLink": BASE + "/groups/" + OWNER + "/members?$skiptoken=one",
    })
    with pytest.raises(ConnectorTransportError, match="origin"):
        reader.is_member(tenant_id=TENANT, group_id=GROUP, user_id=MEMBER)
    assert len(transport.calls) == 1
