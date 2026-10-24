"""Reusable, unactivated Jason-governed SharePoint read adapter.

Owner-wide Graph consent is *not* requester-wide document access.
Every request must be bound to an authenticated Jason identity, a validated
Microsoft tenant/client and an independent exact resource authorization policy.
Do not register this class as a live MCP capability without approval.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    require_capability,
)

from .sharepoint_reader import MicrosoftGraphSharePointReader


class TrustedIdentityBindings(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str) -> object: ...


class SharePointDocumentAuthorizer(Protocol):
    def authorized(
        self,
        *,
        principal_id: str,
        organization_id: str,
        client_id: str,
        tenant_id: str,
        operation: str,
        site_id: str,
        drive_id: str | None,
        item_id: str | None,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class GovernedSharePointConnector:
    reader: MicrosoftGraphSharePointReader
    bindings: TrustedIdentityBindings
    authorizer: SharePointDocumentAuthorizer
    audit: AuditSink

    provider_name = "microsoft_graph"
    capabilities = frozenset({
        "knowledge.library.search",
        "knowledge.document.search",
        "knowledge.document.metadata.read",
        "knowledge.document.content.read",
    })

    _required = {
        "knowledge.library.search": frozenset({"site_id"}),
        "knowledge.document.search": frozenset({"site_id", "drive_id"}),
        "knowledge.document.metadata.read": frozenset({"site_id", "drive_id", "item_id"}),
        "knowledge.document.content.read": frozenset({"site_id", "drive_id", "item_id"}),
    }

    def _tenant(self, context: ConnectorContext) -> str:
        if not context.principal_id or not context.client_id or not context.organization_id:
            raise ConnectorAuthorizationError("An authenticated Jason tenant/client boundary is required")
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=context.principal_id
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise ConnectorAuthorizationError("An active validated Microsoft identity binding is required")
        tenant_id = str(getattr(binding, "microsoft_tenant_id", "") or "").strip()
        client_id = str(getattr(binding, "client_id", "") or "").strip()
        if not tenant_id or client_id != context.client_id:
            raise ConnectorAuthorizationError("Microsoft identity/client binding mismatch")
        return tenant_id

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        operation = request.context.capability
        args = request.arguments
        allowed = self._required[operation]
        optional = frozenset({"folder_id"}) if operation == "knowledge.document.search" else frozenset()
        if not isinstance(args, Mapping) or set(args) - (allowed | optional) or not allowed.issubset(args):
            raise ValueError("Exact document selectors required; arbitrary Graph arguments are prohibited")
        for key in allowed | optional:
            if key in args and (not isinstance(args[key], str) or not args[key]):
                raise ValueError("Document selector must be a nonempty string")

        tenant_id = self._tenant(request.context)
        site_id = args["site_id"]
        drive_id = args.get("drive_id")
        item_id = args.get("item_id")
        allowed_result = self.authorizer.authorized(
            principal_id=request.context.principal_id,
            organization_id=request.context.organization_id,
            client_id=request.context.client_id,
            tenant_id=tenant_id,
            operation=operation,
            site_id=site_id,
            drive_id=drive_id,
            item_id=item_id,
        )
        if allowed_result is not True:
            raise ConnectorAuthorizationError("Document access is not authorized by Jason release policy")

        self.audit.record("connector.requested", request.context, {
            "provider": self.provider_name, "operation": operation,
            "site_id": site_id, "client_id": request.context.client_id,
        })
        if operation == "knowledge.library.search":
            data: Mapping[str, Any] = self.reader.list_libraries(
                tenant_id=tenant_id, site_id=site_id)
        elif operation == "knowledge.document.search":
            data = self.reader.list_children(
                tenant_id=tenant_id, site_id=site_id, drive_id=drive_id,
                folder_id=args.get("folder_id"))
        elif operation == "knowledge.document.metadata.read":
            data = {"item": self.reader.read_metadata(
                tenant_id=tenant_id, site_id=site_id, drive_id=drive_id, item_id=item_id)}
        else:
            # This can only be activated with an explicit document-content release
            # classification and bounded evidence handling in the orchestrator.
            contents = self.reader.read_bytes(
                tenant_id=tenant_id, site_id=site_id, drive_id=drive_id, item_id=item_id)
            data = {
                "content_b64": base64.b64encode(contents).decode("ascii"),
                "sha256": hashlib.sha256(contents).hexdigest(),
                "byte_length": len(contents),
                "encoding": "base64",
            }

        self.audit.record("connector.completed", request.context, {
            "provider": self.provider_name, "operation": operation,
            "site_id": site_id, "client_id": request.context.client_id,
        })
        return ConnectorResult(capability=operation, provider=self.provider_name, data=data)
