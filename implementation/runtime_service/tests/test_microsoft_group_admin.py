"""Reusable runtime builder acceptance with only simulated Graph network calls."""
from urllib.parse import urlparse
from dataclasses import replace

from connectors.microsoft_graph.test_group_executor import (
    FakeReader, FakeTransport, FakeTokens, FakeAudit, FakeEntitlements,
    TENANT, GROUP_ID, OWNER_ID, MEMBER_ID, READ_APP, WRITE_APP, _boundary,
)
from kernel.client_boundaries import InMemoryClientBoundaryRepository
from orchestrator.invokers import CapabilityInvokerRegistry
from jason_runtime.microsoft_group_admin import (
    build_microsoft_group_admin_invoker, register_microsoft_group_admin_invoker,
)


class BoundedGraphTransport:
    def __init__(self):
        self.reader = FakeReader()
        self.posts = FakeTransport(self.reader)
        self.read_calls = []

    def request(self, *, method, url, headers, params=None, json=None,
                timeout_seconds=None, **kwargs):
        if method == "POST":
            return self.posts.request(method=method, url=url, headers=headers,
                                      params=params, json=json, timeout_seconds=timeout_seconds)
        assert method == "GET", "Unexpected method"
        assert headers["Authorization"] == "Bearer private-bearer-token"
        assert url.startswith("https://graph.microsoft.com/v1.0/")
        self.read_calls.append((url, params))
        path = urlparse(url).path
        if path == "/v1.0/groups":
            alias = params["$filter"].split("'")[1]
            return {"value": list(self.reader.find_groups_by_alias(tenant_id=TENANT, alias=alias))}
        if path.startswith("/v1.0/users/"):
            user_id = path.split("/")[-1]
            return self.reader.read_user(tenant_id=TENANT, user_id=user_id)
        if path.startswith("/v1.0/groups/"):
            sections = path.split("/")
            gid = sections[3]
            if len(sections) == 4:
                return self.reader.read_group(tenant_id=TENANT, group_id=gid)
            if len(sections) == 5 and sections[4] in {"owners", "members"}:
                members = self.reader.owners if sections[4] == "owners" else self.reader.members
                return {"value": [{"id": uid} for uid in sorted(members.get(gid, set()))]}
        raise AssertionError("Unrecognized safe GET path " + path)


def build():
    registry = InMemoryClientBoundaryRepository()
    registry.add(_boundary("r", "microsoft_graph_group_read", "group-read", READ_APP))
    registry.add(_boundary("w", "microsoft_graph_group_write", "group-write", WRITE_APP))
    transport = BoundedGraphTransport()
    class ReadTokens(FakeTokens):
        def acquire_for_client(self, *, client_id, correlation_id):
            assert client_id == "client-17"
            assert correlation_id == "microsoft-directory:" + TENANT
            self.calls += 1
            from connectors.microsoft_graph.token import MicrosoftApplicationToken, GRAPH_DEFAULT_SCOPE
            return MicrosoftApplicationToken(
                access_token="private-bearer-token", token_type="Bearer",
                expires_at_epoch=9999999999, tenant_id=TENANT,
                application_id=READ_APP, scope=GRAPH_DEFAULT_SCOPE,
                certificate_thumbprint="A" * 40,
            )
    read_tokens = ReadTokens()
    write_tokens = FakeTokens()
    audit, entitlement = FakeAudit(), FakeEntitlements()
    invoker = build_microsoft_group_admin_invoker(
        boundaries=registry, read_tokens=read_tokens, write_tokens=write_tokens,
        transport=transport, entitlement=entitlement, audit=audit)
    return registry, transport, read_tokens, write_tokens, invoker


def test_builder_does_not_create_live_state_and_maps_two_catalog_operations():
    _, transport, read_tokens, write_tokens, invoker = build()
    assert set(invoker.provider_capability_map) == {
        ("microsoft_graph_group_write", "identity.group.create"),
        ("microsoft_graph_group_write", "identity.group.member.add"),
    }
    assert transport.read_calls == []
    assert transport.posts.calls == []
    assert read_tokens.calls == write_tokens.calls == 0


def test_explicit_registration_only_and_bounded_no_network_calls():
    _, transport, _, _, invoker = build()
    registry = CapabilityInvokerRegistry()
    assert registry.registered_capabilities() == ()
    register_microsoft_group_admin_invoker(invokers=registry, invoker=invoker)
    assert set(registry.registered_capabilities()) == {
        "identity.group.create", "identity.group.member.add"}
    assert transport.read_calls == []
    assert transport.posts.calls == []


def test_builder_enforces_separate_read_write_token_app_ids_and_real_graph_response():
    from types import SimpleNamespace
    from connectors.microsoft_graph.test_group_executor import direct_request
    from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
    from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
    from decimal import Decimal
    registry, transport, read_tokens, write_tokens, invoker = build()
    direct = direct_request()
    request = OrchestrationRequest(
        execution_id="exec-17", correlation_id="correlation-17",
        principal_id="tech-17", organization_id="aot", client_id="client-17",
        capability_name="identity.group.create", capability_version="1.0",
        requested_mode="deterministic", orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True, approval_present=True, risk="high",
        data_handling=DataHandlingPolicy(classification="internal", hosted_processing_allowed=False),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
        permission_mode="execute", arguments=direct.arguments,
    )
    resolution = SimpleNamespace(
        selected_provider_id="microsoft_graph_group_write",
        capability_name="identity.group.create",
        metadata={},
    )
    prepared = invoker.prepare_execution_plan(request=request, resolution=resolution)
    assert len(transport.posts.calls) == 0
    result = invoker.invoke_execution_plan(
        request=request, resolution=resolution, prepared=prepared)
    assert result.output["data"]["group_id"] == GROUP_ID
    assert result.output["data"]["readback_verified"] is True
    assert len(transport.posts.calls) == 1
    assert len(transport.read_calls) > 1
    assert read_tokens.calls > 0
    assert write_tokens.calls == 1



def test_openbao_builder_keeps_read_and_write_bootstrap_separate_and_dormant(tmp_path):
    from jason_runtime.microsoft_group_admin import build_microsoft_group_admin_openbao_invoker
    from connectors.microsoft_graph.group_executor import WRITE_PROVIDER
    registry = InMemoryClientBoundaryRepository()
    transport = BoundedGraphTransport()
    invoker = build_microsoft_group_admin_openbao_invoker(
        boundaries=registry, openbao_url="http://openbao.test:8200",
        read_role_id_path=tmp_path / "read" / "role_id",
        read_secret_id_path=tmp_path / "read" / "secret_id",
        write_role_id_path=tmp_path / "write" / "role_id",
        write_secret_id_path=tmp_path / "write" / "secret_id",
        transport=transport, entitlement=FakeEntitlements(), audit=FakeAudit(),
    )
    assert WRITE_PROVIDER in invoker.connectors
    assert not transport.read_calls and not transport.posts.calls
    assert set(invoker.provider_capability_map) == {
        (WRITE_PROVIDER, "identity.group.create"),
        (WRITE_PROVIDER, "identity.group.member.add"),
    }


def test_openbao_builder_rejects_same_credential_identity_for_read_and_write(tmp_path):
    import pytest
    from jason_runtime.microsoft_group_admin import build_microsoft_group_admin_openbao_invoker
    with pytest.raises(ValueError, match="MUST_BE_DISTINCT"):
        build_microsoft_group_admin_openbao_invoker(
            boundaries=InMemoryClientBoundaryRepository(),
            openbao_url="http://openbao.test:8200",
            read_role_id_path=tmp_path / "shared" / "role_id",
            read_secret_id_path=tmp_path / "shared" / "secret_id",
            write_role_id_path=tmp_path / "shared" / "role_id",
            write_secret_id_path=tmp_path / "shared" / "secret_id",
            transport=BoundedGraphTransport(), entitlement=FakeEntitlements(), audit=FakeAudit(),
        )


def test_exact_aot_pilot_entitlement_limits_name_owner_and_membership():
    from jason_runtime.microsoft_group_admin import AotPilotGroupEntitlement
    from orchestrator.microsoft_group_admin_catalog import (
        AOT_PILOT_CLIENT_ID, AOT_PILOT_TENANT_ID, AOT_PILOT_OWNER_ID,
        AOT_PILOT_OWNER_PRINCIPAL_ID, AOT_PILOT_GROUP_NAME, AOT_PILOT_GROUP_ALIAS,
    )
    from connectors.microsoft_graph.group_executor import GroupWriteScope
    from connectors.core.contracts import ConnectorContext, ConnectorAuthorizationError
    import pytest
    r = FakeReader()
    # FakeReader hardcodes a test tenant; use strict fixture to keep AOT IDs explicit.
    class AotReader:
        def __init__(self): self.group = None
        def find_groups_by_alias(self, *, tenant_id, alias):
            assert tenant_id == AOT_PILOT_TENANT_ID
            return tuple([self.group] if self.group is not None and alias == AOT_PILOT_GROUP_ALIAS else [])
        def read_group(self, *, tenant_id, group_id):
            assert tenant_id == AOT_PILOT_TENANT_ID
            assert self.group is not None and self.group["id"] == group_id
            return self.group
        def is_owner(self, *, tenant_id, group_id, user_id):
            assert user_id == AOT_PILOT_OWNER_ID
            return True
    reader=AotReader()
    entitlement=AotPilotGroupEntitlement(reader)
    scope=GroupWriteScope(AOT_PILOT_CLIENT_ID,AOT_PILOT_TENANT_ID,
                          "read-boundary",READ_APP,"write-boundary",WRITE_APP)
    ctx=ConnectorContext("corr",AOT_PILOT_OWNER_PRINCIPAL_ID,"aot",
                         AOT_PILOT_CLIENT_ID,"identity.group.create","execute")
    args={"display_name":AOT_PILOT_GROUP_NAME,"mail_nickname":AOT_PILOT_GROUP_ALIAS,
          "group_type":"security","verified_owner_id":AOT_PILOT_OWNER_ID}
    entitlement.require_entitled(context=ctx,scope=scope,arguments=args,
                                 operation_name="identity.group.create")
    with pytest.raises(ConnectorAuthorizationError,match="ARGUMENTS_NOT_APPROVED"):
        entitlement.require_entitled(context=ctx,scope=scope,
            arguments={**args,"display_name":"Other Group"},
            operation_name="identity.group.create")
    with pytest.raises(ConnectorAuthorizationError,match="NOT_AUTHORIZED"):
        entitlement.require_entitled(
            context=replace(ctx,principal_id="person-unknown"),scope=scope,
            arguments=args,operation_name="identity.group.create")
    group_id="77777777-7777-4777-8777-777777777777"
    reader.group={"id":group_id,"displayName":AOT_PILOT_GROUP_NAME,
                  "mailNickname":AOT_PILOT_GROUP_ALIAS,"groupTypes":[],
                  "mailEnabled":False,"securityEnabled":True,"isAssignableToRole":False,
                  "onPremisesSyncEnabled":False}
    entitlement.require_entitled(
        context=replace(ctx,capability="identity.group.member.add"),scope=scope,
        arguments={"verified_group_id":group_id,"verified_member_id":AOT_PILOT_OWNER_ID},
        operation_name="identity.group.member.add")
    with pytest.raises(ConnectorAuthorizationError):
        entitlement.require_entitled(
            context=replace(ctx,capability="identity.group.member.add"),scope=scope,
            arguments={"verified_group_id":group_id,"verified_member_id":MEMBER_ID},
            operation_name="identity.group.member.add")
