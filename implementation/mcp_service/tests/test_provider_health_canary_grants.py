from types import SimpleNamespace

from jason_mcp import server
from kernel.identity_authority import (
    IdentityRecord, InMemoryAuthorityGrantRepository, InMemoryIdentityRepository
)


class Audit:
    def __init__(self): self.events=[]
    def append_authority_audit(self, **kwargs): self.events.append(kwargs)


class CapabilityRegistry:
    def list_all(self):
        return tuple(
            SimpleNamespace(capability_name=name, lifecycle_status=SimpleNamespace(value="active"))
            for name in sorted(server.PROVIDER_HEALTH_CANARY_CAPABILITIES)
        )


def runtime():
    identities=InMemoryIdentityRepository()
    authority=SimpleNamespace(
        identities=identities,
        grants=InMemoryAuthorityGrantRepository(),
        audit=Audit(),
    )
    return SimpleNamespace(identity_authority=authority, capabilities=CapabilityRegistry())


def test_graph_canary_expected_grant_is_client_scoped():
    ids=server._provider_health_canary_grant_ids(app=SimpleNamespace(), organization="aot")
    expected=server._authority_grant_id(
        subject=server.PROVIDER_HEALTH_CANARY_PRINCIPAL,
        capability="identity.user.search",
        organization="aot",
        client_id="client-aot-internal",
        permission=server.PermissionMode.OBSERVE,
        approval_required=False,
    )
    assert ids["identity.user.search"] == expected


def test_owner_approval_creates_graph_canary_with_exact_client_scope(monkeypatch):
    app=runtime()
    monkeypatch.setattr(server,"_runtime",lambda:app)
    monkeypatch.setattr(server,"_authenticated_write_identity",lambda:("person-al","aot","entra",None))
    monkeypatch.setattr(server,"approval_owner_identities",lambda:frozenset({"person-al"}))
    result=server.approve_provider_health_canaries()
    assert result["status"] == "succeeded"
    graph=[
        g for g in app.identity_authority.grants.list_for_subject(server.PROVIDER_HEALTH_CANARY_PRINCIPAL)
        if g.capability == "identity.user.search"
    ]
    assert len(graph) == 1
    assert graph[0].client_id == "client-aot-internal"
    assert graph[0].permission.value == "observe"
    assert graph[0].approval_required is False
