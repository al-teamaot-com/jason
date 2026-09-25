from types import SimpleNamespace

from jason_mcp import server


class Authority:
    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []
    def evaluate(self, request):
        self.requests.append(request)
        return SimpleNamespace(outcome=self.outcome)


def test_bound_client_context_is_never_reselected(monkeypatch):
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kwargs: (_ for _ in ()).throw(AssertionError("company read not expected")))
    assert server._contract_client_context_for_identity(
        principal="person-tech", organization="aot", assurance="entra",
        bound_client_id="333", capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id": 333},
    ) == "333"


def test_org_scoped_owner_requires_exact_company_read_and_administer_authority(monkeypatch):
    calls=[]
    def company_read(**kwargs):
        calls.append(kwargs)
        return {"status":"succeeded"}
    authority=Authority(server.AuthorityOutcome.ALLOWED)
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-owner"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", company_read)
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace(identity_authority=authority))

    result=server._contract_client_context_for_identity(
        principal="person-owner", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id":333},
    )
    assert result == "333"
    assert calls[0]["capability_name"] == server.SERVICE_COMPANY_READ
    assert calls[0]["client_id"] is None
    assert calls[0]["arguments"] == {"resource_id":333}
    assert authority.requests[0].client_id == "333"
    assert authority.requests[0].requested_mode is server.PermissionMode.OBSERVE


def test_org_scoped_context_fails_closed_when_company_read_fails(monkeypatch):
    authority=Authority(server.AuthorityOutcome.ALLOWED)
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-owner"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kwargs: {"status":"failed"})
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace(identity_authority=authority))
    assert server._contract_client_context_for_identity(
        principal="person-owner", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_READ,
        arguments={"company_id":333,"resource_id":44},
    ) is None
    assert authority.requests == []


def test_org_scoped_context_fails_closed_without_administer_authority(monkeypatch):
    authority=Authority(server.AuthorityOutcome.DENIED)
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-observer"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kwargs: {"status":"succeeded"})
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace(identity_authority=authority))
    assert server._contract_client_context_for_identity(
        principal="person-observer", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id":333},
    ) is None


def test_governed_read_forwards_only_derived_contract_client(monkeypatch):
    monkeypatch.setattr(server, "_authenticated_identity", lambda: ("owner","aot","entra",None))
    monkeypatch.setattr(server, "_contract_client_context_for_identity", lambda **kwargs: "333")
    captured={}
    def final_read(**kwargs):
        captured.update(kwargs); return {"status":"succeeded"}
    monkeypatch.setattr(server, "_governed_read_for_identity", final_read)
    result=server._governed_read(capability_name=server.SERVICE_CONTRACT_SEARCH, arguments={"company_id":333})
    assert result["status"] == "succeeded"
    assert captured["client_id"] == "333"


def test_org_scoped_nonowner_cannot_select_contract_client(monkeypatch):
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-owner"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kwargs: (_ for _ in ()).throw(AssertionError("company read must not run for nonowner")))
    assert server._contract_client_context_for_identity(
        principal="person-observer", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id":333},
    ) is None
