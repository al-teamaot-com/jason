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
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace(microsoft_identity_bindings=None))
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kwargs: (_ for _ in ()).throw(AssertionError("company read must not run for nonowner")))
    assert server._contract_client_context_for_identity(
        principal="person-observer", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id":333},
    ) == (None, None)


def test_org_scoped_owner_derives_resolution_memory_client_context(monkeypatch):
    from datetime import datetime, timedelta, timezone

    calls = []

    def company_read(**kwargs):
        calls.append(kwargs)
        return {"status": "succeeded"}

    now = datetime.now(timezone.utc)
    base_context = server.ExecutionContext(
        context_id="base-resolution",
        correlation_id="base-resolution-corr",
        principal_id="person-owner",
        organization_id="aot",
        client_id=None,
        capability=server.RESOLUTION_MEMORY_SEARCH,
        requested_mode=server.PermissionMode.OBSERVE,
        maximum_mode=server.PermissionMode.OBSERVE,
        outcome=server.AuthorityOutcome.ALLOWED,
        approval_required=False,
        matched_grants=("org-resolution-read",),
        authentication_assurance="entra",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )

    authority = Authority(server.AuthorityOutcome.ALLOWED)
    authority.evaluate = lambda request: SimpleNamespace(
        outcome=server.AuthorityOutcome.ALLOWED,
        execution_context=base_context,
    )

    class Contexts:
        def __init__(self):
            self.saved = []

        def put_context(self, context):
            self.saved.append(context)

    contexts = Contexts()
    authority.contexts = contexts
    authority.audit = None

    monkeypatch.setattr(
        server,
        "approval_owner_identities",
        lambda: frozenset({"person-owner"}),
    )
    monkeypatch.setattr(server, "_governed_read_for_identity", company_read)
    monkeypatch.setattr(
        server,
        "_runtime",
        lambda: SimpleNamespace(identity_authority=authority),
    )

    client, derived = server._contract_client_context_for_identity(
        principal="person-owner",
        organization="aot",
        assurance="entra",
        bound_client_id=None,
        capability_name=server.RESOLUTION_MEMORY_SEARCH,
        arguments={
            "company_id": 196,
            "category": "disk space",
            "product": "windows",
            "device_role": "workstation",
            "platform": "windows",
        },
    )

    assert client == "196"
    assert derived is contexts.saved[0]
    assert calls[0]["capability_name"] == server.SERVICE_COMPANY_READ
    assert calls[0]["arguments"] == {"resource_id": 196}
    assert derived.client_id == "196"
    assert derived.capability == server.RESOLUTION_MEMORY_SEARCH
    assert derived.maximum_mode is server.PermissionMode.OBSERVE


def test_nonowner_cannot_select_resolution_memory_client(monkeypatch):
    monkeypatch.setattr(
        server,
        "approval_owner_identities",
        lambda: frozenset({"person-owner"}),
    )
    monkeypatch.setattr(
        server,
        "_governed_read_for_identity",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("company read must not run for nonowner")
        ),
    )
    assert server._contract_client_context_for_identity(
        principal="person-observer",
        organization="aot",
        assurance="entra",
        bound_client_id=None,
        capability_name=server.RESOLUTION_MEMORY_SEARCH,
        arguments={
            "company_id": 196,
            "category": "disk space",
            "product": "windows",
            "device_role": "workstation",
            "platform": "windows",
        },
    ) == (None, None)


def test_aot_trusted_staff_contract_context_with_exact_observe_authority(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    base_context = server.ExecutionContext(
        context_id="base-staff", correlation_id="staff-corr",
        principal_id="person-tech", organization_id="aot", client_id=None,
        capability=server.SERVICE_CONTRACT_SEARCH,
        requested_mode=server.PermissionMode.OBSERVE,
        maximum_mode=server.PermissionMode.OBSERVE,
        outcome=server.AuthorityOutcome.ALLOWED,
        approval_required=False, matched_grants=("exact-staff-observe",),
        authentication_assurance="entra", issued_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    authority = Authority(server.AuthorityOutcome.ALLOWED)
    authority.evaluate = lambda request: SimpleNamespace(
        outcome=server.AuthorityOutcome.ALLOWED,
        execution_context=base_context,
    )
    class Contexts:
        def __init__(self):
            self.saved = []
        def put_context(self, context):
            self.saved.append(context)
    authority.contexts = Contexts()
    authority.audit = None
    trusted = SimpleNamespace(status="active", client_id=None)
    bindings = SimpleNamespace(
        find_active_by_jason_identity=lambda *, jason_identity_id:
            trusted if jason_identity_id == "person-tech" else None
    )
    app = SimpleNamespace(identity_authority=authority, microsoft_identity_bindings=bindings)
    monkeypatch.setattr(server, "_runtime", lambda: app)
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-owner"}))
    monkeypatch.setattr(server, "_governed_read_for_identity", lambda **kw: {"status":"succeeded"})
    client, context = server._contract_client_context_for_identity(
        principal="person-tech", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id": 827},
    )
    assert client == "827"
    assert context.client_id == "827"
    assert context.maximum_mode == server.PermissionMode.OBSERVE
    assert context.matched_grants == ("exact-staff-observe",)


def test_untrusted_aot_staff_cannot_derive_contract_client_scope(monkeypatch):
    app = SimpleNamespace(microsoft_identity_bindings=SimpleNamespace(
        find_active_by_jason_identity=lambda **kwargs: None
    ))
    monkeypatch.setattr(server, "_runtime", lambda: app)
    monkeypatch.setattr(server, "_governed_read_for_identity",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("no provider read")))
    assert server._contract_client_context_for_identity(
        principal="person-unbound", organization="aot", assurance="entra",
        bound_client_id=None, capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id": 827},
    ) == (None, None)


def test_bound_client_contract_read_rejects_cross_client_selector(monkeypatch):
    monkeypatch.setattr(server, "_authenticated_identity", lambda: (
        "person-bound", "aot", "entra", "827"
    ))
    monkeypatch.setattr(
        server, "_governed_read_for_identity",
        lambda **kw: (_ for _ in ()).throw(AssertionError("provider read forbidden"))
    )
    result = server._governed_read(
        capability_name=server.SERVICE_CONTRACT_SEARCH,
        arguments={"company_id": 828, "page_size": 5},
    )
    assert result["status"] == "denied"
    assert result["reason_codes"] == ["CLIENT_SCOPE_MISMATCH"]
