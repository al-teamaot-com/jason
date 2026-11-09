"""Governed, read-only Constant Contact V3 connector.

Only the central orchestrator may invoke this connector. It enforces AOT-only
tenant context, exact read capability, fixed provider host, bounded pagination
and encrypted OAuth refresh. Import mutations deliberately remain unavailable.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink, ConnectorAuthorizationError, ConnectorConfigurationError,
    ConnectorContext, ConnectorRequest, ConnectorResult, HttpTransport,
    SecretResolver, require_capability,
)
from .oauth_store import EncryptedOAuthStore
from .session import current_access_token

PROVIDER = "constant_contact"
LOGICAL_SECRET = "constant_contact.oauth_client"
CONTACTS_SEARCH = "marketing.contact.search"
LISTS_SEARCH = "marketing.contact.list.search"
CUSTOM_FIELDS_SEARCH = "marketing.contact.field.search"
READ_CAPABILITIES = frozenset({CONTACTS_SEARCH, LISTS_SEARCH, CUSTOM_FIELDS_SEARCH})
PATHS = {
    CONTACTS_SEARCH: "/contacts",
    LISTS_SEARCH: "/contact_lists",
    CUSTOM_FIELDS_SEARCH: "/contact_custom_fields",
}
BASE_URL = "https://api.cc.email/v3"


class ConstantContactConnector:
    provider_name = PROVIDER
    capabilities = READ_CAPABILITIES

    def __init__(
        self, *, secrets: SecretResolver, transport: HttpTransport,
        audit: AuditSink, oauth_db: Path,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._oauth_db = Path(oauth_db)

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id.strip().casefold() != "aot":
            raise ConnectorAuthorizationError("Constant Contact access is restricted to AOT")
        args = dict(request.arguments)
        if set(args) - {"limit", "cursor"}:
            raise ConnectorConfigurationError("Unsupported Constant Contact selectors")
        limit = args.get("limit", 50)
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ConnectorConfigurationError("Constant Contact page size is invalid")
        cursor = args.get("cursor")
        if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
            raise ConnectorConfigurationError("Constant Contact cursor is invalid")

        credentials = self._secrets.resolve(LOGICAL_SECRET, request.context)
        try:
            key = base64.b64decode(credentials["token_key_b64"], validate=True)
            if len(key) != 32:
                raise ValueError("Bad key length")
            access = current_access_token(
                EncryptedOAuthStore(self._oauth_db, key), credentials,
            )
        except Exception:
            raise ConnectorAuthorizationError(
                "Constant Contact OAuth credentials or connection unavailable"
            ) from None
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        self._audit.record("connector.requested", request.context, {
            "provider": PROVIDER,
            "capability": request.context.capability,
            "read_only": True,
        })
        response = self._transport.request(
            method="GET", url=BASE_URL + PATHS[request.context.capability],
            headers={"Accept": "application/json", "Authorization": "Bearer " + access},
            params=params, timeout_seconds=30.0,
        )
        if not isinstance(response, Mapping):
            raise ConnectorConfigurationError("Constant Contact response shape invalid")
        self._audit.record("connector.completed", request.context, {
            "provider": PROVIDER, "capability": request.context.capability,
        })
        return ConnectorResult(capability=request.context.capability,
                               provider=PROVIDER, data=dict(response))
