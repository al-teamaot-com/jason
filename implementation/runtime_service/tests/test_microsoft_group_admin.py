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
