"""Source-only Microsoft 365 group mutation integration tests; no live tenant used."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
    ConnectorTransportError,
)
from connectors.microsoft_graph.group_executor import (
    MicrosoftGraphGroupWriter, MicrosoftGraphGovernedGroupConnector,
    MicrosoftGroupBoundaryValidator, WRITE_PROVIDER, READ_PROVIDER,
)
from connectors.microsoft_graph.token import (
    GRAPH_DEFAULT_SCOPE, MicrosoftApplicationToken,
)
from kernel.client_boundaries import (
    BoundaryStatus, ClientBoundary, InMemoryClientBoundaryRepository,
)
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest


TENANT = "11111111-1111-4111-8111-111111111111"
OTHER_TENANT = "22222222-2222-4222-8222-222222222222"
READ_APP = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
WRITE_APP = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OWNER_ID = "55555555-5555-4555-8555-555555555555"
MEMBER_ID = "66666666-6666-4666-8666-666666666666"
GROUP_ID = "77777777-7777-4777-8777-777777777777"
STAMP = datetime(2026, 11, 12, tzinfo=timezone.utc)


class FakeReader:
    def __init__(self):
        self.groups = {}
        self.members = {}
        self.owners = {}
        self.user_ids = {OWNER_ID, MEMBER_ID}
        self.force_bad_readback = False
        self.force_member_not_found = False
        self.mismatch_tenant = False

    def tenant(self, tenant_id):
        if tenant_id != TENANT or self.mismatch_tenant:
            raise ConnectorAuthorizationError("READ_BOUNDARY_MISMATCH")

    def find_groups_by_alias(self, *, tenant_id, alias):
        self.tenant(tenant_id)
        return tuple(g for g in self.groups.values()
                     if g["mailNickname"].casefold() == alias.casefold())

    def read_group(self, *, tenant_id, group_id):
        self.tenant(tenant_id)
        g = dict(self.groups[group_id])
        if self.force_bad_readback:
            g["displayName"] = "CHANGED"
        return g

    def read_user(self, *, tenant_id, user_id):
        self.tenant(tenant_id)
        if user_id not in self.user_ids:
            raise ConnectorAuthorizationError("USER_NOT_IN_CLIENT_TENANT")
        return {"id": user_id, "accountEnabled": True}

    def is_member(self, *, tenant_id, group_id, user_id):
        self.tenant(tenant_id)
        if self.force_member_not_found:
            return False
        return user_id in self.members.get(group_id, set())

    def is_owner(self, *, tenant_id, group_id, user_id):
        self.tenant(tenant_id)
        return user_id in self.owners.get(group_id, set())


class FakeTokens:
    def __init__(self):
        self.tenant_id = TENANT
        self.app_id = WRITE_APP
        self.calls = 0

    def acquire_for_client(self, *, client_id, correlation_id):
        assert client_id == "client-17"
        assert correlation_id == "correlation-17"
        self.calls += 1
        return MicrosoftApplicationToken(
            access_token="fake-private-token", token_type="Bearer",
            expires_at_epoch=9999999999, tenant_id=self.tenant_id,
            application_id=self.app_id, scope=GRAPH_DEFAULT_SCOPE,
            certificate_thumbprint="A" * 40,
        )


class FakeTransport:
    def __init__(self, reader):
        self.reader = reader
        self.calls = []
        self.failure = None

    def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=20, **kwargs):
        self.calls.append((method, url, json))
        assert method == "POST"
        assert url.startswith("https://graph.microsoft.com/v1.0/groups")
        assert headers["Authorization"] == "Bearer fake-private-token"
        if self.failure == "before":
            raise ConnectorTransportError("Fake timeout")
        if url == "https://graph.microsoft.com/v1.0/groups":
            assert set(json).issubset({
                "displayName", "description", "mailNickname", "groupTypes", "securityEnabled",
                "mailEnabled", "owners@odata.bind",
            })
            self.reader.groups[GROUP_ID] = {
                "id": GROUP_ID, "displayName": json["displayName"],
                "mailNickname": json["mailNickname"], "groupTypes": json["groupTypes"],
                "mailEnabled": json["mailEnabled"], "securityEnabled": json["securityEnabled"],
                "isAssignableToRole": False, "onPremisesSyncEnabled": False,
            }
            self.reader.owners[GROUP_ID] = {json["owners@odata.bind"][0].split("/")[-1]}
            result = {"id": GROUP_ID}
        else:
            group_id = url.split("/")[-3]
            self.reader.members.setdefault(group_id, set()).add(json["@odata.id"].split("/")[-1])
            result = {}
        if self.failure == "after":
            raise ConnectorTransportError("Fake timeout after commit")
        return result


class FakeEntitlements:
    revoked = False
    permitted_groups = None
    def require_entitled(self, *, context, operation_name, scope, arguments):
        if (self.revoked or context.principal_id != "tech-17" or scope.client_id != "client-17"
                or operation_name not in {
                    "identity.group.create", "identity.group.member.add"}
                or (operation_name == "identity.group.member.add"
                    and self.permitted_groups is not None
                    and arguments["verified_group_id"] not in self.permitted_groups)):
            raise ConnectorAuthorizationError("TECHNICIAN_NOT_ENTITLED")


class FakeAudit:
    def __init__(self):
        self.entries = []
    def record(self, event_type, context, details):
        self.entries.append((event_type, dict(details)))


def _boundary(id, provider, profile, app, tenant=TENANT, status=BoundaryStatus.VALIDATED):
    return ClientBoundary(
        id=id, client_id="client-17", provider=provider, external_tenant_id=tenant,
        primary_domain="example.test", profile=profile, application_id=app,
        status=status, consent_transaction_id="consent-17",
        created_at=STAMP, consented_at=STAMP, validated_at=STAMP,
    )


def harness():
    registry = InMemoryClientBoundaryRepository()
    registry.add(_boundary("read-17", READ_PROVIDER, "group-read", READ_APP))
    registry.add(_boundary("write-17", WRITE_PROVIDER, "group-write", WRITE_APP))
    reader = FakeReader()
    transport = FakeTransport(reader)
    token = FakeTokens()
    entitlement = FakeEntitlements()
    audit = FakeAudit()
    connector = MicrosoftGraphGovernedGroupConnector(
        boundaries=MicrosoftGroupBoundaryValidator(registry),
        reader=reader, writer=MicrosoftGraphGroupWriter(token, transport),
        entitlement=entitlement, audit=audit)
    return registry, reader, transport, token, entitlement, audit, connector


def direct_request(capability="identity.group.create", client="client-17", org="aot",
                   principal="tech-17", mode="execute", args=None):
    if args is None:
        args = {"display_name": "Accounting", "mail_nickname": "acct",
                "group_type": "security", "verified_owner_id": OWNER_ID}
    return ConnectorRequest(
        ConnectorContext("correlation-17", principal, org, client, capability, mode), args)


def member_request(**kwargs):
    return direct_request(
        capability="identity.group.member.add",
        args={"verified_group_id": GROUP_ID, "verified_member_id": MEMBER_ID},
        **kwargs,
    )


def assert_member_prepared(connector, request):
    prepared = connector.prepare_governed_execution(request)
    assert prepared.provider_capability == request.context.capability
    assert prepared.action_method == "POST"
    assert prepared.parameters["tenant_id"] == TENANT
    assert prepared.parameters["write_application_id"] == WRITE_APP
    return prepared


def test_group_create_and_add_member_shared_executor():
    registry, reader, transport, tokens, access, audit, connector = harness()
    with pytest.raises(ConnectorAuthorizationError, match="CENTRAL"):
        connector.execute(direct_request())

    prepared = assert_member_prepared(connector, direct_request())
    assert prepared.payload == {
        "displayName": "Accounting", "mailNickname": "acct", "groupTypes": [],
        "mailEnabled": False, "securityEnabled": True,
        "owners@odata.bind": ["https://graph.microsoft.com/v1.0/users/" + OWNER_ID],
    }
    assert not transport.calls
    created = connector.execute_governed_execution(prepared)
    assert created.data["readback_verified"] is True
    assert created.data["group_id"] == GROUP_ID
    assert len(transport.calls) == 1

    membership = assert_member_prepared(connector, member_request())
    assert membership.normalized_path.endswith("/members/$ref")
    result = connector.execute_governed_execution(membership)
    assert result.data["readback_verified"] is True
    assert MEMBER_ID in reader.members[GROUP_ID]
    assert len(transport.calls) == 2 and tokens.calls == 2
    assert [e[0] for e in audit.entries] == [
        "connector.mutation.requested", "connector.mutation.verified",
        "connector.mutation.requested", "connector.mutation.verified",
    ]
    assert "fake-private-token" not in str(audit.entries)
    assert "fake-private-token" not in repr(prepared)


@pytest.mark.parametrize("kind,expected", [
    ("client", "TENANT_CONSENT_UNVERIFIED"),
    ("org", "EXACT_EXECUTION_CONTEXT_REQUIRED"),
    ("principal", "TECHNICIAN_NOT_ENTITLED"),
    ("mode", "EXACT_EXECUTION_CONTEXT_REQUIRED"),
])
def test_wrong_context_fails_before_graph(kind, expected):
    _, _, transport, _, _, _, connector = harness()
    overrides = {
        "client": {"client": "other-client"},
        "org": {"org": "unauthorized-org"},
        "principal": {"principal": "unauthorized-tech"},
        "mode": {"mode": "observe"},
    }
    with pytest.raises(ConnectorAuthorizationError, match=expected):
        connector.prepare_governed_execution(direct_request(**overrides[kind]))
    assert not transport.calls


@pytest.mark.parametrize("alteration", ["read_revoked", "write_revoked", "tenant_mismatch", "same_app", "wrong_profile"])
def test_real_client_boundaries_deny_unvalidated_or_cross_tenant(alteration):
    registry, _, transport, _, _, _, connector = harness()
    write = registry.get("write-17")
    read = registry.get("read-17")
    if alteration == "read_revoked":
        registry.replace(replace(read, status=BoundaryStatus.REVOKED))
    if alteration == "write_revoked":
        registry.replace(replace(write, status=BoundaryStatus.REVOKED))
    if alteration == "tenant_mismatch":
        registry.replace(replace(write, external_tenant_id=OTHER_TENANT))
    if alteration == "same_app":
        registry.replace(replace(write, application_id=READ_APP))
    if alteration == "wrong_profile":
        registry.replace(replace(write, profile="directory-read"))
    with pytest.raises(ConnectorAuthorizationError):
        connector.prepare_governed_execution(direct_request())
    assert not transport.calls


def test_revocation_after_prepare_and_plan_tampering_denied_without_write():
    registry, _, transport, _, entitlement, _, connector = harness()
    prepared = connector.prepare_governed_execution(direct_request())
    entitlement.revoked = True
    with pytest.raises(ConnectorAuthorizationError, match="NOT_ENTITLED"):
        connector.execute_governed_execution(prepared)
    assert not transport.calls

    entitlement.revoked = False
    with pytest.raises(ConnectorAuthorizationError, match="PLAN_CHANGED"):
        connector.execute_governed_execution(replace(prepared, payload={"displayName": "hijacked"}))
    assert not transport.calls

    registry.replace(replace(registry.get("write-17"), status=BoundaryStatus.REVOKED))
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute_governed_execution(prepared)
    assert not transport.calls


def test_token_mismatch_denied_before_http():
    _, _, transport, tokens, _, _, connector = harness()
    prepared = connector.prepare_governed_execution(direct_request())
    tokens.tenant_id = OTHER_TENANT
    with pytest.raises(ConnectorAuthorizationError, match="TOKEN_SCOPE_MISMATCH"):
        connector.execute_governed_execution(prepared)
    assert not transport.calls


def test_duplicate_group_and_duplicate_membership_do_not_mutate():
    _, reader, transport, _, _, _, connector = harness()
    connector.execute_governed_execution(connector.prepare_governed_execution(direct_request()))
    with pytest.raises(ConnectorAuthorizationError, match="ALIAS_ALREADY_EXISTS"):
        connector.prepare_governed_execution(direct_request())
    connector.execute_governed_execution(connector.prepare_governed_execution(member_request()))
    with pytest.raises(ConnectorAuthorizationError, match="ALREADY_MEMBER"):
        connector.prepare_governed_execution(member_request())
    assert len(transport.calls) == 2


@pytest.mark.parametrize("flag", ["role_assignable", "dynamic", "synced", "mail_security", "missing_role"])
def test_privileged_and_unsupported_group_membership_denied(flag):
    _, reader, transport, _, _, _, connector = harness()
    connector.execute_governed_execution(connector.prepare_governed_execution(direct_request()))
    group = reader.groups[GROUP_ID]
    if flag == "role_assignable": group["isAssignableToRole"] = True
    if flag == "dynamic": group["groupTypes"] = ["DynamicMembership"]
    if flag == "synced": group["onPremisesSyncEnabled"] = True
    if flag == "mail_security": group["mailEnabled"] = True
    if flag == "missing_role": group.pop("isAssignableToRole")
    with pytest.raises(ConnectorAuthorizationError, match="UNSAFE"):
        connector.prepare_governed_execution(member_request())
    assert len(transport.calls) == 1


@pytest.mark.parametrize("failure", ["before", "after"])
def test_provider_failure_never_automatically_reposts(failure):
    _, _, transport, _, _, audit, connector = harness()
    prepared = connector.prepare_governed_execution(direct_request())
    transport.failure = failure
    with pytest.raises(ConnectorTransportError):
        connector.execute_governed_execution(prepared)
    assert len(transport.calls) == 1
    assert audit.entries[-1][0] == "connector.mutation.outcome_unknown"


def test_bad_create_readback_fails_without_retrying_post():
    _, reader, transport, _, _, audit, connector = harness()
    prepared = connector.prepare_governed_execution(direct_request())
    reader.force_bad_readback = True
    with pytest.raises(RuntimeError, match="READBACK_MISMATCH"):
        connector.execute_governed_execution(prepared)
    assert len(transport.calls) == 1
    assert audit.entries[-1][0] == "connector.mutation.verification_failed"


def test_member_readback_failure_fails_without_duplicate_post():
    _, reader, transport, _, _, audit, connector = harness()
    connector.execute_governed_execution(connector.prepare_governed_execution(direct_request()))
    prepared = connector.prepare_governed_execution(member_request())
    reader.force_member_not_found = True
    with pytest.raises(RuntimeError, match="READBACK_MISMATCH"):
        connector.execute_governed_execution(prepared)
    assert len(transport.calls) == 2
    assert audit.entries[-1][0] == "connector.mutation.verification_failed"


def test_shared_invoker_prepares_identical_canonical_operation_plan():
    _, _, transport, _, _, _, connector = harness()
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={WRITE_PROVIDER: connector},
        provider_capability_map={
            (WRITE_PROVIDER, name): name for name in connector.capabilities},
    )
    request = OrchestrationRequest(
        execution_id="exec-17", correlation_id="correlation-17",
        principal_id="tech-17", organization_id="aot", client_id="client-17",
        capability_name="identity.group.create", capability_version="1.0",
        requested_mode="deterministic", permission_mode="execute",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True, approval_present=True, risk="medium",
        data_handling=DataHandlingPolicy(
            classification="internal", hosted_processing_allowed=False),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
        arguments=direct_request().arguments,
    )

    class Resolution:
        capability_name = "identity.group.create"
        selected_provider_id = WRITE_PROVIDER
        metadata = {}
    plan = invoker.prepare_execution_plan(request=request, resolution=Resolution())
    assert plan.plan.canonical_capability == "identity.group.create"
    assert plan.plan.selected_provider_id == WRITE_PROVIDER
    assert plan.plan.client_id == "client-17"
    assert plan.plan.material_parameters["tenant_id"] == TENANT
    assert plan.plan.fingerprint
    assert not transport.calls
    result = invoker.invoke_execution_plan(request=request, resolution=Resolution(), prepared=plan)
    assert result.output["data"]["readback_verified"] is True
    assert len(transport.calls) == 1


def test_nonapproved_mappings_are_not_executable():
    _, _, transport, _, _, _, connector = harness()
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={WRITE_PROVIDER: connector}, provider_capability_map={},
    )
    from types import SimpleNamespace
    context = direct_request()
    request = SimpleNamespace(
        correlation_id=context.context.correlation_id, principal_id=context.context.principal_id,
        organization_id=context.context.organization_id, client_id=context.context.client_id,
        permission_mode="execute", policy_ids=(), principal_attributes={},
        arguments=context.arguments,
    )
    resolution = SimpleNamespace(
        capability_name="identity.group.create", selected_provider_id=WRITE_PROVIDER,
    )
    with pytest.raises(PermissionError, match="not approved"):
        invoker.prepare_execution_plan(request=request, resolution=resolution)
    assert not transport.calls


class _GroupResolutionService:
    def resolve(self, request):
        from kernel.resolution import (
            CapabilityResolutionResult, CapabilityResolutionStatus, ResolutionOutcome,
        )
        return CapabilityResolutionResult(
            execution_id=request.execution_id, correlation_id=request.correlation_id,
            capability_name=request.capability_name, capability_version="1.0",
            outcome=ResolutionOutcome.RESOLVED,
            capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
            reason_codes=("resolved",),
            eligible_provider_ids=(WRITE_PROVIDER,),
            selected_provider_id=WRITE_PROVIDER,
        )


class _CentralAudit:
    def __init__(self): self.events = []
    def append(self, event_type, details): self.events.append((event_type, details))


def _approved_request(reservation, *, capability="identity.group.create", args=None, execution_id="exec-17"):
    if args is None:
        args = direct_request().arguments
    return OrchestrationRequest(
        execution_id=execution_id, correlation_id="correlation-17",
        principal_id="tech-17", organization_id="aot", client_id="client-17",
        capability_name=capability, capability_version="1.0", requested_mode="deterministic",
        permission_mode="execute", orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True, approval_present=True, risk="high",
        data_handling=DataHandlingPolicy(classification="internal", hosted_processing_allowed=False,
                                          retention_allowed=False),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0"), maximum_attempts=1),
        arguments=args, requester_kind="human", authority_context_id="microsoft-test",
        approval_id=reservation.approval_id, idempotency_key=reservation.idempotency_key,
    )


def test_central_orchestrator_exact_action_approval_and_replay(tmp_path):
    """Real central ledger and invoker; fake Graph transport; one authorized write."""
    from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger
    from orchestrator.service import CentralOrchestrator
    from orchestrator.contracts import OrchestrationStatus

    _, reader, transport, _, _, _, connector = harness()
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={WRITE_PROVIDER: connector},
        provider_capability_map={(WRITE_PROVIDER, op): op for op in connector.capabilities},
    )
    ledger = SQLiteGovernedExecutionLedger(str(tmp_path / "m365-approval.sqlite3"))
    ledger.initialize()
    args = direct_request().arguments
    reservation = ledger.reserve_approval(
        principal_id="tech-17", organization_id="aot", client_id="client-17",
        capability_name="identity.group.create", arguments=args,
        request_id="m365-owner-approval-17",
    )
    central_audit = _CentralAudit()
    runtime = CentralOrchestrator(
        resolution=_GroupResolutionService(), invoker=invoker,
        audit=central_audit, governed_execution_ledger=ledger,
    )
    request = _approved_request(reservation)
    result = runtime.execute(request)
    assert result.status is OrchestrationStatus.SUCCEEDED
    assert len(transport.calls) == 1
    assert GROUP_ID in reader.groups
    evidence = ledger.evidence(reservation.approval_id)
    assert evidence["state"] == "succeeded"
    assert evidence["execution_plan_fingerprint"]
    replay = runtime.execute(_approved_request(reservation, execution_id="exec-replay"))
    assert len(transport.calls) == 1  # replay must not execute provider again
    assert replay.status is OrchestrationStatus.SUCCEEDED
    assert replay.output["data"] == result.output["data"]
    assert replay.output["provider"] == result.output["provider"]

    # Original approval cannot authorize a different payload.
    altered = runtime.execute(_approved_request(
        reservation, args={**args, "display_name": "Unapproved Group"}, execution_id="exec-tampered",
    ))
    assert altered.status is not OrchestrationStatus.SUCCEEDED
    assert len(transport.calls) == 1


def test_central_orchestrator_cannot_swap_group_create_to_membership(tmp_path):
    from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger
    from orchestrator.service import CentralOrchestrator
    from orchestrator.contracts import OrchestrationStatus

    _, _, transport, _, _, _, connector = harness()
    ledger = SQLiteGovernedExecutionLedger(str(tmp_path / "m365-action.sqlite3"))
    ledger.initialize()
    reservation = ledger.reserve_approval(
        principal_id="tech-17", organization_id="aot", client_id="client-17",
        capability_name="identity.group.create", arguments=direct_request().arguments,
        request_id="m365-owner-approval-action",
    )
    runtime = CentralOrchestrator(
        resolution=_GroupResolutionService(),
        invoker=GovernedConnectorCapabilityInvoker(
            connectors={WRITE_PROVIDER: connector},
            provider_capability_map={(WRITE_PROVIDER, name): name for name in connector.capabilities},
        ),
        audit=_CentralAudit(), governed_execution_ledger=ledger,
    )
    request = _approved_request(
        reservation, capability="identity.group.member.add", args=member_request().arguments,
    )
    assert runtime.execute(request).status is not OrchestrationStatus.SUCCEEDED
    assert not transport.calls


def test_microsoft365_group_create_payload_and_membership():
    _, reader, transport, _, _, _, connector = harness()
    request = direct_request(args={
        "display_name": "Finance Collaboration", "mail_nickname": "finance-collab",
        "group_type": "microsoft365", "verified_owner_id": OWNER_ID,
        "description": "Finance project team",
    })
    create = assert_member_prepared(connector, request)
    assert create.payload["groupTypes"] == ["Unified"]
    assert create.payload["mailEnabled"] is True
    connector.execute_governed_execution(create)
    connector.execute_governed_execution(connector.prepare_governed_execution(member_request()))
    assert GROUP_ID in reader.groups
    assert MEMBER_ID in reader.members[GROUP_ID]
    assert len(transport.calls) == 2


def test_owner_must_be_an_active_user_in_the_bound_tenant():
    _, reader, transport, _, _, _, connector = harness()
    reader.user_ids.remove(OWNER_ID)
    with pytest.raises(ConnectorAuthorizationError, match="USER_NOT_IN_CLIENT_TENANT"):
        connector.prepare_governed_execution(direct_request())
    assert not transport.calls


@pytest.mark.parametrize("route,payload", [
    ("/v1.0/users", {}),
    ("/v1.0/groups", {"displayName": "Bad"}),
    ("/v1.0/groups", {
        "displayName": "Bad", "mailNickname": "bad", "groupTypes": ["DynamicMembership"],
        "mailEnabled": False, "securityEnabled": True,
        "owners@odata.bind": ["https://graph.microsoft.com/v1.0/users/" + OWNER_ID],
    }),
    ("/v1.0/groups/" + GROUP_ID + "/members/$ref", {
        "@odata.id": "https://malicious.example/v1.0/directoryObjects/" + MEMBER_ID,
    }),
])
def test_writer_has_own_fixed_route_and_payload_policy(route, payload):
    _, _, transport, _, _, _, connector = harness()
    scope = connector.boundaries.require_scope(client_id="client-17")
    with pytest.raises((ConnectorAuthorizationError, ValueError)):
        connector.writer.post(
            scope=scope, route=route, payload=payload, correlation_id="correlation-17")
    assert not transport.calls


def test_group_permission_profiles_are_separate_least_privilege_profiles():
    from connectors.microsoft_graph.service_catalog import (
        MicrosoftOperationMode, permission_profile,
    )
    read = permission_profile("group-read")
    write = permission_profile("group-write")
    assert read.maximum_mode is MicrosoftOperationMode.READ
    assert set(read.application_permissions) == {"User.Read.All", "Group.Read.All"}
    assert write.maximum_mode is MicrosoftOperationMode.WRITE_WITH_APPROVAL
    assert set(write.application_permissions) == {
        "User.Read.All", "Group.Create", "GroupMember.ReadWrite.All",
    }
    assert "Directory.ReadWrite.All" not in write.application_permissions
    assert "RoleManagement.ReadWrite.Directory" not in write.application_permissions



def test_technician_entitlement_may_restrict_exact_membership_target():
    _, reader, transport, _, access, _, connector = harness()
    connector.execute_governed_execution(connector.prepare_governed_execution(direct_request()))
    access.permitted_groups = frozenset({"99999999-9999-4999-8999-999999999999"})
    with pytest.raises(ConnectorAuthorizationError, match="NOT_ENTITLED"):
        connector.prepare_governed_execution(member_request())
    assert len(transport.calls) == 1
