"""Reusable, source-only governed Microsoft Entra group mutation adapter.

Uses Jason's existing central prepare / exact-action plan / execute contract.
No production route is registered by this module. Two separate application
identities are required: a validated read boundary and a write-scoped boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from connectors.core.contracts import (
    AuditSink, ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
    ConnectorResult, ConnectorTransportError, HttpTransport,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository
from orchestrator.connector_invoker import ProviderPreparedExecution
from .governed_operations import MICROSOFT_GOVERNED_OPERATIONS, operation
from .group_reader import canonical_uuid
from .token import GRAPH_DEFAULT_SCOPE, MicrosoftApplicationTokenProvider


WRITE_PROVIDER = "microsoft_graph_group_write"
READ_PROVIDER = "microsoft_graph_group_read"
WRITE_PROFILE = "group-write"
READ_PROFILE = "group-read"
_GRAPH_BASE = "https://graph.microsoft.com"


@dataclass(frozen=True, slots=True)
class GroupWriteScope:
    client_id: str
    tenant_id: str
    read_boundary_id: str
    read_application_id: str
    write_boundary_id: str
    write_application_id: str


@dataclass(frozen=True, slots=True)
class MicrosoftGroupBoundaryValidator:
    """Require both independently validated identities on exactly one client tenant."""
    boundaries: ClientBoundaryRepository

    def require_scope(self, *, client_id: str) -> GroupWriteScope:
        if not isinstance(client_id, str) or not client_id.strip():
            raise ConnectorAuthorizationError("M365_CLIENT_REQUIRED")
        read = self.boundaries.find_active_for_client(client_id=client_id, provider=READ_PROVIDER)
        write = self.boundaries.find_active_for_client(client_id=client_id, provider=WRITE_PROVIDER)
        if (read is None or write is None
                or read.status != BoundaryStatus.VALIDATED or write.status != BoundaryStatus.VALIDATED
                or read.profile != READ_PROFILE or write.profile != WRITE_PROFILE
                or read.client_id != client_id or write.client_id != client_id
                or not read.consented_at or not read.validated_at
                or not write.consented_at or not write.validated_at):
            raise ConnectorAuthorizationError("M365_GROUP_WRITE_TENANT_CONSENT_UNVERIFIED")
        try:
            tenant = canonical_uuid(read.external_tenant_id)
            if canonical_uuid(write.external_tenant_id) != tenant:
                raise ValueError("mismatched tenants")
            read_app = canonical_uuid(read.application_id)
            write_app = canonical_uuid(write.application_id)
        except ValueError as error:
            raise ConnectorAuthorizationError("M365_GROUP_WRITE_BOUNDARY_INVALID") from error
        if read_app == write_app:
            raise ConnectorAuthorizationError("M365_GROUP_WRITE_IDENTITY_NOT_SEPARATE")
        for name, boundary in ((READ_PROVIDER, read), (WRITE_PROVIDER, write)):
            mirror = self.boundaries.find_active_for_external_tenant(
                provider=name, external_tenant_id=tenant)
            if mirror is None or mirror.id != boundary.id:
                raise ConnectorAuthorizationError("M365_GROUP_WRITE_TENANT_ALIAS_CONFLICT")
        return GroupWriteScope(client_id, tenant, read.id, read_app, write.id, write_app)


class MicrosoftGroupReader(Protocol):
    def find_groups_by_alias(self, *, tenant_id: str, alias: str) -> tuple[Mapping[str, Any], ...]: ...
    def read_group(self, *, tenant_id: str, group_id: str) -> Mapping[str, Any]: ...
    def read_user(self, *, tenant_id: str, user_id: str) -> Mapping[str, Any]: ...
    def is_member(self, *, tenant_id: str, group_id: str, user_id: str) -> bool: ...
    def is_owner(self, *, tenant_id: str, group_id: str, user_id: str) -> bool: ...


class MicrosoftWriteEntitlement(Protocol):
    """Existing policy/authority adapter, not a new human approval flow."""
    def require_entitled(
        self, *, context: ConnectorContext, operation_name: str,
        scope: GroupWriteScope, arguments: Mapping[str, str],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphGroupWriter:
    tokens: MicrosoftApplicationTokenProvider
    transport: HttpTransport

    def post(self, *, scope: GroupWriteScope, route: str, payload: Mapping[str, Any],
             correlation_id: str) -> Mapping[str, Any]:
        if route == "/v1.0/groups":
            expected = {"displayName", "mailNickname", "groupTypes", "mailEnabled",
                        "securityEnabled", "owners@odata.bind"}
            if (not expected.issubset(payload)
                    or set(payload) - (expected | {"description"})
                    or payload.get("groupTypes") not in ([], ["Unified"])
                    or payload.get("securityEnabled") is not True
                    or payload.get("mailEnabled") is not (payload["groupTypes"] == ["Unified"])
                    or not isinstance(payload.get("owners@odata.bind"), list)
                    or len(payload["owners@odata.bind"]) != 1):
                raise ConnectorAuthorizationError("M365_GROUP_CREATE_PAYLOAD_INVALID")
            owner_link = payload["owners@odata.bind"][0]
            prefix = _GRAPH_BASE + "/v1.0/users/"
            if not isinstance(owner_link, str) or not owner_link.startswith(prefix):
                raise ConnectorAuthorizationError("M365_GROUP_OWNER_LINK_INVALID")
            canonical_uuid(owner_link[len(prefix):])
        else:
            prefix = "/v1.0/groups/"
            suffix = "/members/$ref"
            if not route.startswith(prefix) or not route.endswith(suffix):
                raise ConnectorAuthorizationError("M365_UNREGISTERED_GRAPH_ROUTE")
            group_id = route[len(prefix):-len(suffix)]
            if canonical_uuid(group_id) != group_id:
                raise ConnectorAuthorizationError("M365_GRAPH_ROUTE_INVALID")
            member_link = payload.get("@odata.id")
            member_prefix = _GRAPH_BASE + "/v1.0/directoryObjects/"
            if (set(payload) != {"@odata.id"}
                    or not isinstance(member_link, str)
                    or not member_link.startswith(member_prefix)):
                raise ConnectorAuthorizationError("M365_GROUP_MEMBER_LINK_INVALID")
            canonical_uuid(member_link[len(member_prefix):])
        token = self.tokens.acquire_for_client(
            client_id=scope.client_id, correlation_id=correlation_id)
        try:
            token_matches = (
                canonical_uuid(token.tenant_id) == scope.tenant_id
                and canonical_uuid(token.application_id) == scope.write_application_id
                and token.scope == GRAPH_DEFAULT_SCOPE
                and token.token_type.lower() == "bearer"
                and bool(token.access_token)
            )
        except (ValueError, AttributeError):
            token_matches = False
        if not token_matches:
            raise ConnectorAuthorizationError("M365_GROUP_WRITE_TOKEN_SCOPE_MISMATCH")
        result = self.transport.request(
            method="POST", url=_GRAPH_BASE + route,
            headers={"Authorization": "Bearer " + token.access_token,
                     "Content-Type": "application/json"},
            params=None, json=payload, timeout_seconds=20.0,
        )
        if not isinstance(result, Mapping):
            raise ConnectorTransportError("Microsoft Graph write returned invalid JSON")
        return result


@dataclass(frozen=True, slots=True)
class _PreparedGroupAction:
    context: ConnectorContext
    scope: GroupWriteScope
    operation_name: str
    arguments: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class MicrosoftGraphGovernedGroupConnector:
    """One adapter for multiple registered group operations, with no generic HTTP escape."""
    boundaries: MicrosoftGroupBoundaryValidator
    reader: MicrosoftGroupReader
    writer: MicrosoftGraphGroupWriter
    entitlement: MicrosoftWriteEntitlement
    audit: AuditSink

    provider_name = WRITE_PROVIDER
    capabilities = frozenset(MICROSOFT_GOVERNED_OPERATIONS)

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        raise ConnectorAuthorizationError("M365_CENTRAL_GOVERNED_EXECUTION_REQUIRED")

    def _require(
        self, *, context: ConnectorContext, operation_name: str,
        arguments: Mapping[str, str],
    ) -> GroupWriteScope:
        if (context.organization_id != "aot" or context.capability != operation_name
                or context.mode != "execute" or not context.principal_id
                or not context.correlation_id or not context.client_id):
            raise ConnectorAuthorizationError("M365_EXACT_EXECUTION_CONTEXT_REQUIRED")
        operation(operation_name)  # fail closed on unknown capability
        scope = self.boundaries.require_scope(client_id=context.client_id)
        self.entitlement.require_entitled(
            context=context, operation_name=operation_name,
            scope=scope, arguments=arguments)
        return scope

    def _material(self, *, scope: GroupWriteScope, operation_name: str,
                  args: Mapping[str, str]) -> tuple[str, str, dict[str, Any]]:
        """Build deterministic, caller-independent Graph payloads."""
        if operation_name == "identity.group.create":
            group_type = args["group_type"]
            owner = args["verified_owner_id"]
            payload: dict[str, Any] = {
                "displayName": args["display_name"],
                "mailNickname": args["mail_nickname"],
                "groupTypes": ["Unified"] if group_type == "microsoft365" else [],
                "mailEnabled": group_type == "microsoft365",
                "securityEnabled": True,
                "owners@odata.bind": [_GRAPH_BASE + "/v1.0/users/" + owner],
            }
            if "description" in args:
                payload["description"] = args["description"]
            return "/v1.0/groups", args["mail_nickname"], payload
        if operation_name == "identity.group.member.add":
            group_id = args["verified_group_id"]
            return (
                "/v1.0/groups/" + group_id + "/members/$ref",
                group_id,
                {"@odata.id": _GRAPH_BASE + "/v1.0/directoryObjects/" + args["verified_member_id"]},
            )
        raise ConnectorAuthorizationError("M365_UNREGISTERED_GROUP_OPERATION")

    def _precheck(self, *, scope: GroupWriteScope,
                  operation_name: str, args: Mapping[str, str]) -> None:
        tenant = scope.tenant_id
        if operation_name == "identity.group.create":
            matches = self.reader.find_groups_by_alias(
                tenant_id=tenant, alias=args["mail_nickname"])
            if matches:
                raise ConnectorAuthorizationError("M365_GROUP_ALIAS_ALREADY_EXISTS")
            self.reader.read_user(tenant_id=tenant, user_id=args["verified_owner_id"])
        else:
            group_id = args["verified_group_id"]
            group = self.reader.read_group(tenant_id=tenant, group_id=group_id)
            # Managed role / dynamic / synced groups and unsupported group classes are excluded.
            group_types = group.get("groupTypes")
            if (group.get("isAssignableToRole") is not False
                    or "onPremisesSyncEnabled" not in group
                    or group.get("onPremisesSyncEnabled") is True
                    or group_types not in ([], ["Unified"])
                    or not isinstance(group.get("securityEnabled"), bool)
                    or not isinstance(group.get("mailEnabled"), bool)
                    or (group_types == [] and (group["mailEnabled"] is not False
                                                or group["securityEnabled"] is not True))
                    or (group_types == ["Unified"] and group["mailEnabled"] is not True)):
                raise ConnectorAuthorizationError("M365_GROUP_TYPE_UNSAFE_FOR_MEMBERSHIP")
            self.reader.read_user(tenant_id=tenant, user_id=args["verified_member_id"])
            if self.reader.is_member(
                    tenant_id=tenant, group_id=group_id, user_id=args["verified_member_id"]):
                raise ConnectorAuthorizationError("M365_GROUP_USER_ALREADY_MEMBER")

    def prepare_governed_execution(self, request: ConnectorRequest) -> ProviderPreparedExecution:
        ctx = request.context
        args = operation(ctx.capability).validate_arguments(request.arguments)
        scope = self._require(
            context=ctx, operation_name=ctx.capability, arguments=args)
        self._precheck(scope=scope, operation_name=ctx.capability, args=args)
        route, target, payload = self._material(
            scope=scope, operation_name=ctx.capability, args=args)
        return ProviderPreparedExecution(
            provider_capability=ctx.capability,
            action_method="POST", resource_type="identity_group",
            resource_identifier=target,
            normalized_path=route,
            payload=payload,
            parameters={
                "operation_id": ctx.capability,
                "client_id": scope.client_id,
                "tenant_id": scope.tenant_id,
                "read_boundary_id": scope.read_boundary_id,
                "read_application_id": scope.read_application_id,
                "write_boundary_id": scope.write_boundary_id,
                "write_application_id": scope.write_application_id,
                "permission_profile": WRITE_PROFILE,
            },
            opaque=_PreparedGroupAction(
                context=ctx, scope=scope, operation_name=ctx.capability, arguments=dict(args)),
        )

    def execute_governed_execution(self, prepared: ProviderPreparedExecution) -> ConnectorResult:
        opaque = prepared.opaque
        if not isinstance(opaque, _PreparedGroupAction):
            raise ConnectorAuthorizationError("M365_GROUP_PREPARED_PLAN_REQUIRED")
        args = operation(opaque.operation_name).validate_arguments(opaque.arguments)
        scope = self._require(
            context=opaque.context, operation_name=opaque.operation_name,
            arguments=args)
        if scope != opaque.scope:
            raise ConnectorAuthorizationError("M365_GROUP_SCOPE_CHANGED")
        route, target, payload = self._material(
            scope=scope, operation_name=opaque.operation_name, args=args)
        expected_params = {
            "operation_id": opaque.operation_name,
            "client_id": scope.client_id,
            "tenant_id": scope.tenant_id,
            "read_boundary_id": scope.read_boundary_id,
            "read_application_id": scope.read_application_id,
            "write_boundary_id": scope.write_boundary_id,
            "write_application_id": scope.write_application_id,
            "permission_profile": WRITE_PROFILE,
        }
        if (prepared.provider_capability != opaque.operation_name
                or prepared.action_method != "POST"
                or prepared.resource_type != "identity_group"
                or prepared.resource_identifier != target
                or prepared.normalized_path != route
                or dict(prepared.payload) != payload
                or dict(prepared.parameters) != expected_params):
            raise ConnectorAuthorizationError("M365_GROUP_EXECUTION_PLAN_CHANGED")
        # Repeat safe reads after the centrally authorized re-prepare.
        self._precheck(scope=scope, operation_name=opaque.operation_name, args=args)
        self.audit.record("connector.mutation.requested", opaque.context, {
            "provider": self.provider_name, "operation": opaque.operation_name,
            "tenant_id": scope.tenant_id, "client_id": scope.client_id,
        })
        try:
            posted = self.writer.post(
                scope=scope, route=route, payload=payload,
                correlation_id=opaque.context.correlation_id)
        except Exception:
            # A timeout may have applied remotely; do not blindly POST again.
            self.audit.record("connector.mutation.outcome_unknown", opaque.context, {
                "provider": self.provider_name, "operation": opaque.operation_name})
            raise

        try:
            if opaque.operation_name == "identity.group.create":
                group_id = canonical_uuid(posted.get("id"))
                group = self.reader.read_group(tenant_id=scope.tenant_id, group_id=group_id)
                expected_types = payload["groupTypes"]
                if (canonical_uuid(group.get("id")) != group_id
                        or group.get("displayName") != payload["displayName"]
                        or group.get("mailNickname") != payload["mailNickname"]
                        or group.get("groupTypes") != expected_types
                        or group.get("mailEnabled") != payload["mailEnabled"]
                        or group.get("securityEnabled") is not True
                        or not self.reader.is_owner(
                            tenant_id=scope.tenant_id, group_id=group_id,
                            user_id=args["verified_owner_id"])):
                    raise RuntimeError("M365_GROUP_CREATE_READBACK_MISMATCH")
                data = {"operation": opaque.operation_name, "group_id": group_id,
                        "readback_verified": True}
                evidence = (f"microsoft_graph:group:{group_id}",)
            else:
                group_id = args["verified_group_id"]
                member_id = args["verified_member_id"]
                if not self.reader.is_member(
                        tenant_id=scope.tenant_id, group_id=group_id, user_id=member_id):
                    raise RuntimeError("M365_GROUP_MEMBERSHIP_READBACK_MISMATCH")
                data = {"operation": opaque.operation_name, "group_id": group_id,
                        "member_id": member_id, "readback_verified": True}
                evidence = (f"microsoft_graph:group:{group_id}:member:{member_id}",)
        except Exception:
            self.audit.record("connector.mutation.verification_failed", opaque.context, {
                "provider": self.provider_name, "operation": opaque.operation_name})
            raise
        self.audit.record("connector.mutation.verified", opaque.context, {
            "provider": self.provider_name, "operation": opaque.operation_name,
            "tenant_id": scope.tenant_id, "client_id": scope.client_id})
        return ConnectorResult(
            capability=opaque.operation_name, provider=self.provider_name,
            data=data, evidence_ids=evidence,
        )
