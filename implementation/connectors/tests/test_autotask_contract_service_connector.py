"""No-network tests of dormant exact-contract scoped read adapter."""
from __future__ import annotations

import json
import pytest

from connectors.autotask.contract_service_connector import (
    DormantScopedContractServicesReadConnector,
)
from connectors.core.contracts import ConnectorContext, ConnectorRequest


class Secrets:
    def resolve(self, logical_name, context):
        assert logical_name == "autotask.write"
        return {
            "username": "synthetic@invalid.example",
            "secret": "never-real",
            "integration_code": "synthetic",
        }


class Audit:
    def record(self, *args, **kwargs):
        pass


class Authorization:
    def __init__(self):
        self.allow = True
        self.calls = []

    def authorize_contract_company(self, *, context, company_id, contract_id):
        self.calls.append((context.principal_id, company_id, contract_id))
        return self.allow


class Transport:
    def __init__(self):
        self.urls = []
        self.company = 32
        self.parent = 101
        self.access = "Restricted"
        self.child_records = [{"id": 4, "contractID": 101, "unitCost": 2.5}]
        self.more = False

    def request(self, *, method, url, headers, params=None, json=None,
                timeout_seconds=30):
        assert method == "GET"
        assert json is None
        self.urls.append(url)
        if url.endswith("/zoneInformation"):
            return {"url": "https://webservices3.autotask.net/atservicesrest"}
        if url.endswith("/Contracts/101"):
            return {"item": {"id": self.parent, "companyID": self.company}}
        if url.endswith("/ContractServices/entityInformation"):
            return {"info": {"name": "ContractService",
                             "canQuery": True,
                             "userAccessForQuery": self.access}}
        if url.endswith("/ContractServices/entityInformation/fields"):
            return {"fields": [
                {"name": "id", "isQueryable": True},
                {"name": "contractID", "isQueryable": True},
                {"name": "unitCost", "isQueryable": False},
            ]}
        if url.endswith("/ContractServices/query"):
            assert params is not None
            query = json_module.loads(params["search"])
            assert query["filter"] == [
                {"field": "contractID", "op": "eq", "value": 101}
            ]
            return {"items": self.child_records, "pageDetails": {
                "nextPageUrl": "https://webservices3.autotask.net/next"
                if self.more else None,
            }}
        raise AssertionError("unexpected provider URL " + url)


json_module = json


def context(**kwargs):
    args = dict(correlation_id="test-contract-service-20261104",
                principal_id="person-al", organization_id="aot", client_id=None,
                capability="autotask.contract_service.scoped_query",
                mode="observe")
    args.update(kwargs)
    return ConnectorContext(**args)


def setup():
    transport, auth = Transport(), Authorization()
    connector = DormantScopedContractServicesReadConnector(
        secrets=Secrets(), transport=transport, audit=Audit(),
        company_authorizer=auth)
    return transport, auth, connector


def query(connector, **kwargs):
    args = {"contract_id": 101, "page_size": 25}
    args.update(kwargs.pop("arguments", {}))
    return connector.execute(ConnectorRequest(
        context=context(**kwargs), arguments=args))


def test_positive_scope_uses_readonly_get_steps_and_explicit_authorizer():
    t, a, c = setup()
    r = query(c)
    assert r.data == {
        "items": [{"id": 4, "contractID": 101, "unitCost": 2.5}],
        "contractID": 101, "companyID": 32,
        "boundedPageValidated": True, "fullContractCoverageVerified": False,
    }
    assert a.calls == [("person-al", 32, 101)]
    assert len(t.urls) == 5
    assert t.urls[-1].endswith("/ContractServices/query")


def test_no_authorizer_is_rejected_at_construction():
    with pytest.raises(PermissionError, match="AUTHORIZER_REQUIRED"):
        DormantScopedContractServicesReadConnector(
            secrets=Secrets(), transport=Transport(), audit=Audit(),
            company_authorizer=None)


def test_explicit_authorization_denial_stops_before_sensitive_child_metadata():
    t, a, c = setup()
    a.allow = False
    with pytest.raises(PermissionError, match="REQUESTER_DENIED"):
        query(c)
    assert not any("ContractServices" in u for u in t.urls)


def test_mismatched_verified_parent_id_stops_child_read():
    t, a, c = setup()
    t.parent = 102
    with pytest.raises(PermissionError):
        query(c)
    assert not any("/ContractServices/query" in u for u in t.urls)


@pytest.mark.parametrize("access", ["None", "Mine", None, "garbled"])
def test_provider_restriction_must_be_all_or_restricted(access):
    t, a, c = setup()
    t.access = access
    with pytest.raises(PermissionError, match="PROVIDER_DENIED"):
        query(c)
    assert not any("/ContractServices/query" in u for u in t.urls)


@pytest.mark.parametrize("row", [
    {"id": 4, "contractID": 102},
    {"id": 4, "contractID": 101, "companyID": 33},
    {"id": 4, "contractID": True},
])
def test_cross_contract_or_company_response_not_released(row):
    t, a, c = setup()
    t.child_records = [{"id": 1, "contractID": 101}, row]
    with pytest.raises(PermissionError):
        query(c)


def test_provider_pagination_must_not_release_partial_results():
    t, a, c = setup()
    t.more = True
    with pytest.raises(PermissionError, match="CONTINUATION_UNSUPPORTED"):
        query(c)


@pytest.mark.parametrize("args", [
    {"company_id": 32},
    {"contract_id": True},
    {"page_size": 0},
    {"page_size": 101},
])
def test_unrecognized_or_bad_selectors_stop_before_network(args):
    t, a, c = setup()
    with pytest.raises(PermissionError):
        query(c, arguments=args)
    assert t.urls == []


@pytest.mark.parametrize("override", [
    {"organization_id": "another-tenant"},
    {"mode": "execute"},
    {"principal_id": ""},
    {"capability": "autotask.entity.query"},
])
def test_wrong_organization_mode_identity_or_capability_denied(override):
    t, a, c = setup()
    with pytest.raises(PermissionError):
        query(c, **override)
    assert t.urls == []

def test_client_scoped_request_fail_closed_until_canonical_scope_adapter_exists():
    t, a, c = setup()
    with pytest.raises(PermissionError, match="AUTHORITY_INVALID"):
        query(c, client_id="customer-32")
    assert t.urls == []
    assert a.calls == []
