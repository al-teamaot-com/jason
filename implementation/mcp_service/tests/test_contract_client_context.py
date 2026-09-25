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
    ) == ("333", None)


def test_org_scoped_owner_derives_one_minute_exact_observe_context(monkeypatch):
    from datetime import datetime, timedelta, timezone
    calls=[]
    def company_read(**kwargs):
        calls.append(kwargs)
        return {"status":"succeeded"}
    now=datetime.now(timezone.utc)
    base_context=server.ExecutionContext(
        context_id="base", correlation_id="base-corr", principal_id="person-owner",
        organization_id="aot", client_id=None, capability=server.SERVICE_CONTRACT_SEARCH,
        requested_mode=server.PermissionMode.OBSERVE, maximum_mode=server.PermissionMode.OBSERVE,
        outcome=server.AuthorityOutcome.ALLOWED, approval_required=False,
        matched_grants=("org-provider-read",), authentication_assurance="entra",
        issued_at=now, expires_at=now+timedelta(minutes=5),
    )
    authority=Authority(server.AuthorityOutcome.ALLOWED)
    authority.evaluate=lambda request: SimpleNamespace(outcome=server.AuthorityOutcome.ALLOWED, execution_context=base_context)
    class Contexts:
        def __init__(self): self.saved=[]
        def put_context(self, context): self.saved.append(context)
    contexts=Contexts(); authority.contexts=contexts; authority.audit=None
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-owner"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", company_read)
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace(identity_authority=authority))

    client, derived=server._contract_client_context_for_identity(
        principal="person-owner", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id":333},
    )
    assert client == "333" and derived is contexts.saved[0]
    assert calls[0]["capability_name"] == server.SERVICE_COMPANY_READ
    assert calls[0]["client_id"] is None
    assert derived.client_id == "333"
    assert derived.capability == server.SERVICE_CONTRACT_SEARCH
    assert derived.maximum_mode is server.PermissionMode.OBSERVE
    assert derived.matched_grants == ("org-provider-read",)
    assert derived.expires_at <= derived.issued_at + timedelta(minutes=1)


def test_org_scoped_context_fails_closed_when_company_read_fails(monkeypatch):
    authority=Authority(server.AuthorityOutcome.ALLOWED)
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-owner"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kwargs: {"status":"failed"})
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace(identity_authority=authority))
    assert server._contract_client_context_for_identity(
        principal="person-owner", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_READ,
        arguments={"company_id":333,"resource_id":44},
    ) == (None, None)
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
    ) == (None, None)


def test_governed_read_forwards_only_derived_contract_client(monkeypatch):
    monkeypatch.setattr(server, "_authenticated_identity", lambda: ("owner","aot","entra",None))
    monkeypatch.setattr(server, "_contract_client_context_for_identity", lambda **kwargs: ("333", None))
    captured={}
    def final_read(**kwargs):
        captured.update(kwargs); return {"status":"succeeded"}
    monkeypatch.setattr(server, "_governed_read_for_identity", final_read)
    result=server._governed_read(capability_name=server.SERVICE_CONTRACT_SEARCH, arguments={"company_id":333})
    assert result["status"] == "succeeded"
    assert captured["client_id"] == "333"
    assert captured["preauthorized_context"] is None


def test_org_scoped_nonowner_cannot_select_contract_client(monkeypatch):
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-owner"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kwargs: (_ for _ in ()).throw(AssertionError("company read must not run for nonowner")))
    assert server._contract_client_context_for_identity(
        principal="person-observer", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id":333},
    ) == (None, None)
