from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from functools import lru_cache
from typing import Any, Mapping
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    ApprovalRecord,
    AuthorityOutcome,
    AuthorityRequest,
    PermissionMode,
)
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from mcp.server import MCPServer
from mcp.server.transport_security import (
    TransportSecurityMiddleware,
    TransportSecuritySettings,
)
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from connectors.datto_edr.threat_correlation import (
    AmbiguousThreatCorrelationError,
    ThreatCorrelationError,
    correlate_drmm_threat_to_edr_detection,
)
from pydantic import AnyHttpUrl
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from jason_runtime.autotask_internal_note import (
    SERVICE_TICKET_NOTE_CREATE,
    autotask_internal_note_mcp_surface_enabled,
)
from jason_runtime.composition import RuntimeSettings, build_runtime_application
from jason_runtime.datto_component_scope import (
    DATTO_AD_HOC_POWERSHELL_NAME,
    DATTO_AD_HOC_POWERSHELL_UID,
    DATTO_APPROVAL_MODE_PER_RUN,
    configured_datto_components,
    effective_datto_component_approval_mode,
    resolve_datto_component,
)
from jason_runtime.datto_component_approval_registry import (
    approval_owner_identities,
    approve_component as persist_component_approval,
    component_metadata_fingerprint,
    list_records as list_component_approval_records,
    revoke_component as persist_component_revocation,
)


JASON_ENTRA_TENANT_ID = os.environ.get(
    "JASON_MCP_ENTRA_TENANT_ID",
    "f7054323-d52b-4863-8c2f-1898f0b6077c",
).strip()

JASON_ENTRA_CLIENT_ID = os.environ.get(
    "JASON_MCP_ENTRA_CLIENT_ID",
    "9b9996e9-5c34-48b7-948c-f44f89352f89",
).strip()

JASON_REQUIRED_SCOPE = os.environ.get(
    "JASON_MCP_REQUIRED_SCOPE",
    "Jason.Read",
).strip()

JASON_RESOURCE_URL = os.environ.get(
    "JASON_MCP_RESOURCE_URL",
    "http://127.0.0.1:8000/mcp",
).strip()

JASON_OAUTH_REQUEST_SCOPE = os.environ.get(
    "JASON_MCP_OAUTH_REQUEST_SCOPE",
    JASON_RESOURCE_URL.rstrip("/") + "/" + JASON_REQUIRED_SCOPE,
).strip()

# OAuth discovery facade used by MCP clients.  The actual authorization
# and token endpoints remain Microsoft Entra.
JASON_OAUTH_ISSUER_URL = os.environ.get(
    "JASON_MCP_OAUTH_ISSUER_URL",
    "https://mcp-jason.teamaot.com/",
).strip()

JASON_ENTRA_OIDC_CONFIGURATION_URL = (
    "https://login.microsoftonline.com/"
    f"{JASON_ENTRA_TENANT_ID}/v2.0/.well-known/openid-configuration"
)

JASON_ENTRA_ISSUER = (
    "https://login.microsoftonline.com/"
    f"{JASON_ENTRA_TENANT_ID}/v2.0"
)

JASON_ENTRA_JWKS_URL = (
    "https://login.microsoftonline.com/"
    f"{JASON_ENTRA_TENANT_ID}/discovery/v2.0/keys"
)


class EntraTokenVerifier(TokenVerifier):
    """Validate AOT Entra access tokens for the Jason MCP resource."""

    def __init__(self) -> None:
        self._jwks = PyJWKClient(
            JASON_ENTRA_JWKS_URL,
            cache_keys=True,
        )

    async def verify_token(
        self,
        token: str,
    ) -> AccessToken | None:
        if not token:
            return None

        try:
            signing_key = (
                self._jwks.get_signing_key_from_jwt(
                    token
                )
            )

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=JASON_ENTRA_CLIENT_ID,
                issuer=JASON_ENTRA_ISSUER,
                leeway=60,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "nbf",
                        "aud",
                        "iss",
                        "tid",
                        "oid",
                    ],
                },
            )

        except (
            PyJWTError,
            ValueError,
            TypeError,
            KeyError,
        ):
            return None
        except Exception:
            # Authentication fails closed. Do not expose JWKS/provider
            # transport or token-validation internals to the caller.
            return None

        tenant_id = str(
            claims.get("tid") or ""
        ).strip()

        object_id = str(
            claims.get("oid") or ""
        ).strip()

        if (
            tenant_id != JASON_ENTRA_TENANT_ID
            or not object_id
        ):
            return None

        raw_scopes = str(
            claims.get("scp") or ""
        ).strip()

        scopes = [
            item
            for item in raw_scopes.split()
            if item
        ]

        if JASON_REQUIRED_SCOPE not in scopes:
            return None

        mcp_scopes = list(scopes)

        if JASON_OAUTH_REQUEST_SCOPE not in mcp_scopes:
            mcp_scopes.append(JASON_OAUTH_REQUEST_SCOPE)

        authorized_client = str(
            claims.get("azp")
            or claims.get("appid")
            or "unknown-oauth-client"
        ).strip()

        try:
            expires_at = int(
                claims.get("exp")
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        # Minimize identity claims placed into MCP request context.
        safe_claims = {
            "tid": tenant_id,
            "oid": object_id,
        }

        return AccessToken(
            token=token,
            client_id=authorized_client,
            scopes=mcp_scopes,
            expires_at=expires_at,
            subject=object_id,
            claims=safe_claims,
        )


_MCP_INTERNAL_NOTE_SURFACE_ENABLED = (
    autotask_internal_note_mcp_surface_enabled()
)

mcp = MCPServer(
    "Jason",
    instructions=(
        "Project Jason governed operational interface. "
        + (
            "This interface provides governed reads plus one narrowly "
            "scoped Autotask internal-note write capability. "
            if _MCP_INTERNAL_NOTE_SURFACE_ENABLED
            else "This interface is read-only. "
        )
        + "Microsoft Entra authenticates the caller. "
        "Jason identity, authority, policy and Central Orchestrator "
        "remain authoritative."
    ),
    token_verifier=EntraTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(
            JASON_OAUTH_ISSUER_URL
        ),
        resource_server_url=AnyHttpUrl(
            JASON_RESOURCE_URL
        ),
        required_scopes=[
            JASON_OAUTH_REQUEST_SCOPE
        ],
        validate_token_resource=False,
    ),
)


@lru_cache(maxsize=1)
def _runtime():
    settings = RuntimeSettings.from_env()
    app = build_runtime_application(settings)

    if app.governed_orchestrator is None:
        raise RuntimeError("governed orchestrator unavailable")
    if app.identity_authority is None:
        raise RuntimeError("identity authority unavailable")

    return app


def _authenticated_identity() -> tuple[
    str,
    str,
    str,
    str | None,
]:
    """Resolve the authenticated Microsoft subject to Jason authority."""

    access_token = get_access_token()

    if access_token is None:
        raise PermissionError(
            "MCP_AUTHENTICATION_REQUIRED"
        )

    claims = access_token.claims or {}

    tenant_id = str(
        claims.get("tid") or ""
    ).strip()

    object_id = str(
        claims.get("oid") or ""
    ).strip()

    if (
        tenant_id != JASON_ENTRA_TENANT_ID
        or not object_id
    ):
        raise PermissionError(
            "MCP_AUTHENTICATED_IDENTITY_INVALID"
        )

    app = _runtime()

    bindings = (
        app.microsoft_identity_bindings
    )

    if bindings is None:
        raise PermissionError(
            "MCP_IDENTITY_BINDING_UNAVAILABLE"
        )

    binding = bindings.find(
        microsoft_tenant_id=tenant_id,
        microsoft_object_id=object_id,
    )

    if (
        binding is None
        or binding.status != "active"
    ):
        raise PermissionError(
            "MCP_IDENTITY_NOT_BOUND"
        )

    identity = (
        app.identity_authority.identities.get(
            binding.jason_identity_id
        )
    )

    if (
        identity is None
        or identity.status != "active"
    ):
        raise PermissionError(
            "MCP_JASON_IDENTITY_INACTIVE"
        )

    return (
        identity.identity_id,
        identity.organization_id,
        "entra-oauth-bearer",
        binding.client_id,
    )


def _authenticated_write_identity() -> tuple[
    str,
    str,
    str,
    str | None,
]:
    """Reuse authenticated Entra identity; Jason authority grants writes."""

    return _authenticated_identity()


def _safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[depth-bounded]"

    if isinstance(value, Mapping):
        output = {}

        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= 80:
                output["_bounded"] = True
                break

            key = str(raw_key)
            lowered = key.lower()

            if any(
                token in lowered
                for token in (
                    "password",
                    "secret",
                    "credential",
                    "access_token",
                    "refresh_token",
                    "api_key",
                    "private_key",
                    "authorization",
                )
            ):
                output[key] = "[redacted]"
            else:
                output[key] = _safe(
                    raw_value,
                    depth=depth + 1,
                )

        return output

    if isinstance(value, (list, tuple)):
        items = [
            _safe(item, depth=depth + 1)
            for item in value[:100]
        ]

        if len(value) > 100:
            items.append("[collection-bounded]")

        return items

    if value is None or isinstance(value, (bool, int, float)):
        return value

    text = str(value)

    if len(text) > 2000:
        return text[:2000] + "...[bounded]"

    return text



def _project_endpoint_search(output: Mapping[str, Any]) -> dict[str, Any]:
    """Return only model-useful endpoint search evidence.

    Full provider evidence remains inside Jason. MCP receives the resolved
    matches and deterministic discovery/completeness metadata only.
    """
    data = output.get("data")
    if not isinstance(data, Mapping):
        data = {}

    raw_matches = data.get("resource_matches")
    if not isinstance(raw_matches, (list, tuple)):
        raw_matches = []

    matches: list[dict[str, Any]] = []

    for item in raw_matches[:100]:
        if not isinstance(item, Mapping):
            continue

        match: dict[str, Any] = {}

        for key in ("resource_id", "hostname", "site", "site_id"):
            value = item.get(key)
            if value is not None and str(value).strip():
                match[key] = _safe(value)

        if match:
            matches.append(match)

    provider_data = data.get("provider_data")
    if not isinstance(provider_data, Mapping):
        provider_data = {}

    pages = provider_data.get("pages")
    if not isinstance(pages, (list, tuple)):
        pages = []

    total_count = None

    for page in pages:
        if not isinstance(page, Mapping):
            continue

        details = page.get("pageDetails")
        if not isinstance(details, Mapping):
            continue

        try:
            value = int(details.get("totalCount"))
        except (TypeError, ValueError):
            continue

        if total_count is None or value > total_count:
            total_count = value

    discovery_complete = data.get("discovery_complete")
    incomplete_reason = data.get("incomplete_reason")

    return {
        "provider": _safe(output.get("provider")),
        "provider_capability": _safe(
            output.get("provider_capability")
        ),
        "resource_matches": matches,
        "match_count": len(matches),
        "discovery_complete": (
            True
            if discovery_complete is True
            else (
                False
                if discovery_complete is False
                else None
            )
        ),
        "search": {
            "discovery_mode": _safe(
                provider_data.get("discovery_mode")
            ),
            "hostname_reference": _safe(
                provider_data.get("hostname_reference")
            ),
            "site_reference": _safe(
                provider_data.get("site_reference")
            ),
            "provider_pages_examined": len(pages),
            "provider_total_count": total_count,
            "match_output_bounded": len(raw_matches) > 100,
            "incomplete_reason": (
                _safe(incomplete_reason)
                if discovery_complete is False
                else None
            ),
        },
    }


def _project_endpoint_read(output: Mapping[str, Any]) -> dict[str, Any]:
    """Project an exact endpoint read into a bounded technician-facing record."""

    data = output.get("data")
    if not isinstance(data, Mapping):
        data = {}

    provider_data = data.get("provider_data")

    if not isinstance(provider_data, Mapping):
        provider_data = data

    record: dict[str, Any] = {}

    aliases = (
        ("resource_id", ("resource_id", "uid", "deviceUid", "device_uid")),
        ("hostname", ("hostname", "name")),
        ("site", ("site", "siteName")),
        ("site_id", ("site_id", "siteUid", "siteId")),
        ("device_type", ("deviceType",)),
        ("lan_ip", ("intIpAddress", "lan_ip")),
        ("wan_ip", ("extIpAddress", "wan_ip")),
        ("operating_system", ("operatingSystem", "operating_system")),
        ("last_logged_in_user", ("lastLoggedInUser", "last_logged_in_user")),
        ("domain", ("domain",)),
        ("online", ("online",)),
        ("suspended", ("suspended",)),
        ("deleted", ("deleted",)),
        ("reboot_required", ("rebootRequired", "reboot_required")),
        ("last_seen", ("lastSeen", "last_seen")),
        ("last_reboot", ("lastReboot", "last_reboot")),
        ("last_audit", ("lastAuditDate", "last_audit")),
        ("antivirus", ("antivirus",)),
        ("patch_management", ("patchManagement", "patch_management")),
        ("software_status", ("softwareStatus", "software_status")),
    )

    for target, candidates in aliases:
        for candidate in candidates:
            if candidate not in provider_data:
                continue

            value = provider_data.get(candidate)

            if value is None:
                continue

            if isinstance(value, str) and not value.strip():
                continue

            record[target] = _safe(value)
            break

    return {
        "provider": _safe(output.get("provider")),
        "provider_capability": _safe(
            output.get("provider_capability")
        ),
        "record": record,
        "field_count": len(record),
        "raw_provider_evidence_exposed": False,
    }


def _project_endpoint_audit(
    output: Mapping[str, Any],
) -> dict[str, Any]:
    """Project detailed endpoint audit evidence into a bounded MCP result.

    Audit data may contain nested hardware/inventory structures. Jason retains
    full provider evidence internally while MCP receives a recursively bounded
    governed representation suitable for reasoning.
    """

    data = output.get("data")

    if not isinstance(data, Mapping):
        data = {}

    provider_data = data.get("provider_data")

    if not isinstance(provider_data, Mapping):
        provider_data = data

    return {
        "provider": _safe(output.get("provider")),
        "provider_capability": _safe(
            output.get("provider_capability")
        ),
        "audit": _safe(provider_data),
        "raw_provider_evidence_exposed": False,
    }


def _project_endpoint_collection(
    output: Mapping[str, Any],
    *,
    collection_kind: str,
) -> dict[str, Any]:
    """Project governed endpoint collection evidence into a bounded MCP result."""

    data = output.get("data")
    if not isinstance(data, Mapping):
        data = {}

    provider_data = data.get("provider_data")
    if provider_data is None:
        provider_data = data

    result: dict[str, Any] = {
        "provider": _safe(output.get("provider")),
        "provider_capability": _safe(
            output.get("provider_capability")
        ),
        "collection_kind": collection_kind,
        "raw_provider_evidence_exposed": False,
    }

    if isinstance(provider_data, (list, tuple)):
        result["items"] = _safe(provider_data)
        result["item_count_returned"] = min(
            len(provider_data),
            100,
        )
        result["bounded"] = len(provider_data) > 100
        return result

    if not isinstance(provider_data, Mapping):
        result["items"] = _safe(provider_data)
        return result

    candidate_keys = (
        "alerts",
        "software",
        "applications",
        "items",
        "results",
        "devices",
        "data",
    )

    selected_key = None
    selected_value = None

    for key in candidate_keys:
        value = provider_data.get(key)

        if isinstance(value, (list, tuple)):
            selected_key = key
            selected_value = value
            break

    if selected_key is not None:
        result["collection_key"] = selected_key
        result["items"] = _safe(selected_value)
        result["item_count_returned"] = min(
            len(selected_value),
            100,
        )
        result["bounded"] = len(selected_value) > 100

        for metadata_key in (
            "pageDetails",
            "totalCount",
            "count",
            "page",
            "max",
        ):
            if metadata_key in provider_data:
                result[metadata_key] = _safe(
                    provider_data.get(metadata_key)
                )

        return result

    result["items"] = _safe(provider_data)
    return result

def _governed_read(
    *,
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    (
        principal,
        organization,
        assurance,
        client_id,
    ) = _authenticated_identity()
    return _governed_read_for_identity(
        principal=principal,
        organization=organization,
        assurance=assurance,
        client_id=client_id,
        capability_name=capability_name,
        arguments=arguments,
    )


def _internal_note_arguments(
    *,
    ticket_id: int,
    note: str,
    title: str = "",
) -> dict[str, Any]:
    if isinstance(ticket_id, bool):
        raise ValueError("ticket_id must be a positive integer")

    try:
        durable_ticket_id = int(ticket_id)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "ticket_id must be a positive integer"
        ) from error

    if durable_ticket_id < 1:
        raise ValueError(
            "ticket_id must be a positive integer"
        )

    description = str(note or "").strip()
    if not description:
        raise ValueError(
            "internal note text is required"
        )
    if len(description) > 8000:
        raise ValueError(
            "internal note text exceeds the bounded MCP limit"
        )

    normalized_title = str(title or "").strip()
    if len(normalized_title) > 255:
        raise ValueError(
            "internal note title exceeds the bounded MCP limit"
        )

    payload: dict[str, Any] = {
        "ticketID": durable_ticket_id,
        "description": description,
        "noteType": 3,
        "publish": 1,
    }

    if normalized_title:
        payload["title"] = normalized_title

    return {
        "payload": payload,
    }


def _governed_internal_note_create(
    *,
    ticket_id: int,
    note: str,
    title: str = "",
) -> dict[str, Any]:
    """Create one internal Autotask note through the governed write path."""

    if not autotask_internal_note_mcp_surface_enabled():
        return {
            "status": "rejected",
            "capability": SERVICE_TICKET_NOTE_CREATE,
            "error_code": "internal_note_write_surface_disabled",
        }

    app = _runtime()

    (
        principal,
        organization,
        assurance,
        client_id,
    ) = _authenticated_write_identity()

    # AOT Owner is intentionally organization-scoped in the first
    # internal-note pilot. Exact principal authority plus Autotask
    # requester impersonation remains mandatory. A later Tech scope
    # model can add client restrictions without redefining Owner.
    try:
        capability = app.capabilities.get_current(
            capability_name=SERVICE_TICKET_NOTE_CREATE
        )
    except LookupError:
        return {
            "status": "rejected",
            "capability": SERVICE_TICKET_NOTE_CREATE,
            "error_code": "internal_note_capability_not_active",
        }

    if (
        str(
            capability.metadata.get(
                "mcp_action_enabled",
                "",
            )
        ).casefold()
        != "true"
    ):
        return {
            "status": "rejected",
            "capability": SERVICE_TICKET_NOTE_CREATE,
            "error_code": "internal_note_mcp_not_approved",
        }

    arguments = _internal_note_arguments(
        ticket_id=ticket_id,
        note=note,
        title=title,
    )

    execution_id = f"exec_mcp_write_{uuid4().hex}"
    correlation_id = f"corr_mcp_write_{uuid4().hex}"

    authority_request = AuthorityRequest(
        request_id=execution_id,
        correlation_id=correlation_id,
        principal_id=principal,
        organization_id=organization,
        client_id=client_id,
        capability=SERVICE_TICKET_NOTE_CREATE,
        requested_mode=PermissionMode.EXECUTE,
        authentication_assurance=assurance,
    )

    decision = app.identity_authority.evaluate(
        authority_request
    )

    approval_present = False

    if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:
        imperative_approval = (
            str(
                capability.metadata.get(
                    "conversation_authenticated_imperative_is_approval",
                    "",
                )
            ).casefold()
            == "true"
        )

        if not imperative_approval:
            return {
                "status": "approval_required",
                "capability": SERVICE_TICKET_NOTE_CREATE,
                "reason_codes": list(decision.reason_codes),
                "correlation_id": correlation_id,
            }

        approval_repository = getattr(
            app.identity_authority,
            "approvals",
            None,
        )
        approval_writer = getattr(
            approval_repository,
            "put",
            None,
        )

        if not callable(approval_writer):
            return {
                "status": "denied",
                "capability": SERVICE_TICKET_NOTE_CREATE,
                "reason_codes": [
                    "APPROVAL_PERSISTENCE_UNAVAILABLE",
                ],
                "correlation_id": correlation_id,
            }

        now = datetime.now(timezone.utc)
        approval_id = f"approval_mcp_{uuid4().hex}"

        approval_writer(
            ApprovalRecord(
                approval_id=approval_id,
                request_id=execution_id,
                capability=SERVICE_TICKET_NOTE_CREATE,
                organization_id=organization,
                client_id=client_id,
                requested_by=principal,
                status="approved",
                decided_by=principal,
                decided_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )

        decision = app.identity_authority.evaluate(
            AuthorityRequest(
                request_id=execution_id,
                correlation_id=correlation_id,
                principal_id=principal,
                organization_id=organization,
                client_id=client_id,
                capability=SERVICE_TICKET_NOTE_CREATE,
                requested_mode=PermissionMode.EXECUTE,
                authentication_assurance=assurance,
                approval_id=approval_id,
            )
        )

        approval_present = True

    if decision.outcome is not AuthorityOutcome.ALLOWED:
        return {
            "status": "denied",
            "capability": SERVICE_TICKET_NOTE_CREATE,
            "reason_codes": list(decision.reason_codes),
            "correlation_id": correlation_id,
        }

    context = decision.execution_context

    if context is None:
        return {
            "status": "denied",
            "capability": SERVICE_TICKET_NOTE_CREATE,
            "reason_codes": [
                "AUTHORITY_CONTEXT_MISSING",
            ],
            "correlation_id": correlation_id,
        }

    # A write grant that does not require explicit approval is a
    # configuration error for this MCP surface. Fail closed rather
    # than treating execute authority alone as sufficient.
    if not context.approval_required:
        return {
            "status": "denied",
            "capability": SERVICE_TICKET_NOTE_CREATE,
            "reason_codes": [
                "WRITE_GRANT_MUST_REQUIRE_APPROVAL",
            ],
            "correlation_id": correlation_id,
        }

    request = OrchestrationRequest(
        execution_id=execution_id,
        correlation_id=correlation_id,
        principal_id=principal,
        organization_id=organization,
        client_id=client_id,
        capability_name=SERVICE_TICKET_NOTE_CREATE,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=(
            approval_present
            or context.approval_required
        ),
        risk="high",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("1.00"),
            maximum_attempts=1,
        ),
        arguments=arguments,
        requester_kind="human",
        permission_mode="execute",
        policy_ids=(
            "mcp-autotask-internal-note-v1",
        ),
        authority_context_id=context.context_id,
        idempotency_key=f"idem_mcp_write_{uuid4().hex}",
    )

    result = app.governed_orchestrator.execute(
        request
    )

    output = result.output
    data = (
        output.get("data")
        if isinstance(output, Mapping)
        else None
    )

    note_id = None
    if isinstance(data, Mapping):
        for key in (
            "itemId",
            "itemID",
            "id",
        ):
            value = data.get(key)
            if value is not None:
                note_id = _safe(value)
                break

    return {
        "status": result.status.value,
        "stage": result.stage.value,
        "capability": result.capability_name,
        "provider": result.provider_id,
        "reason_codes": list(result.reason_codes),
        "error_code": result.error_code,
        "correlation_id": result.correlation_id,
        "note_id": note_id,
        "provider_write_attempts": result.attempts,
    }


def _governed_read_for_identity(
    *,
    principal: str,
    organization: str,
    assurance: str,
    client_id: str | None,
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    app = _runtime()

    execution_id = f"exec_mcp_{uuid4().hex}"
    correlation_id = f"corr_mcp_{uuid4().hex}"

    decision = app.identity_authority.evaluate(
        AuthorityRequest(
            request_id=execution_id,
            correlation_id=correlation_id,
            principal_id=principal,
            organization_id=organization,
            client_id=client_id,
            capability=capability_name,
            requested_mode=PermissionMode.OBSERVE,
            authentication_assurance=assurance,
        )
    )

    if decision.outcome is not AuthorityOutcome.ALLOWED:
        return {
            "status": "denied",
            "capability": capability_name,
            "reason_codes": list(decision.reason_codes),
            "correlation_id": correlation_id,
        }

    context = decision.execution_context

    if context is None:
        return {
            "status": "denied",
            "capability": capability_name,
            "reason_codes": ["AUTHORITY_CONTEXT_MISSING"],
            "correlation_id": correlation_id,
        }

    request = OrchestrationRequest(
        execution_id=execution_id,
        correlation_id=correlation_id,
        principal_id=principal,
        organization_id=organization,
        client_id=client_id,
        capability_name=capability_name,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=context.approval_required,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("1.00"),
            maximum_attempts=1,
        ),
        arguments=dict(arguments),
        requester_kind="human",
        permission_mode="observe",
        policy_ids=("mcp-read-pilot-v1",),
        authority_context_id=context.context_id,
    )

    result = app.governed_orchestrator.execute(request)

    return {
        "status": result.status.value,
        "stage": result.stage.value,
        "capability": result.capability_name,
        "provider": result.provider_id,
        "reason_codes": list(result.reason_codes),
        "error_code": result.error_code,
        "correlation_id": result.correlation_id,
        "evidence": (
            _project_endpoint_search(result.output)
            if capability_name == "endpoint.device.search"
            else (
                _project_endpoint_read(result.output)
                if capability_name == "endpoint.device.read"
                else (
                    _project_endpoint_audit(result.output)
                    if capability_name == "endpoint.audit.read"
                    else (
                        _project_endpoint_collection(
                            result.output,
                            collection_kind="alerts",
                        )
                        if capability_name == "endpoint.alert.search"
                        else (
                            _project_endpoint_collection(
                                result.output,
                                collection_kind="software",
                            )
                            if capability_name == "endpoint.software.search"
                            else (
                                _project_dynamic_evidence(
                                    capability_name,
                                    result.output,
                                )
                                if capability_name == "automation.component.search"
                                else _safe(dict(result.output))
                            )
                        )
                    )
                )
            )
        ),
    }


def _is_canonical_uuid(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        return str(UUID(text)) == text.casefold()
    except ValueError:
        return False


def _correlation_collection(
    result: Mapping[str, Any],
    *keys: str,
) -> list[Mapping[str, Any]]:
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        return []

    direct_items = evidence.get("items")
    if isinstance(direct_items, list):
        return [item for item in direct_items if isinstance(item, Mapping)]

    data = evidence.get("data")
    if not isinstance(data, Mapping):
        return []

    for key in keys:
        values = data.get(key)
        if isinstance(values, list):
            return [item for item in values if isinstance(item, Mapping)]

    provider_data = data.get("provider_data")
    if isinstance(provider_data, Mapping):
        for key in keys:
            values = provider_data.get(key)
            if isinstance(values, list):
                return [item for item in values if isinstance(item, Mapping)]

    return []


def _correlation_failure(
    *,
    error_code: str,
    reason: str,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "stage": "failed",
        "capability": "endpoint.security.detection.read",
        "provider": None,
        "reason_codes": [reason],
        "error_code": error_code,
        "correlation_id": correlation_id or f"corr_mcp_{uuid4().hex}",
        "evidence": {},
    }


def _governed_datto_threat_correlation_read(
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    resource_id = str(
        arguments.get("resource_id")
        or arguments.get("device_uid")
        or ""
    ).strip()
    threat_reference = str(
        arguments.get("threat_reference")
        or (
            arguments.get("alert_id")
            if not _is_canonical_uuid(arguments.get("alert_id"))
            else ""
        )
        or ""
    ).strip()
    requested_drmm_alert_uid = str(
        arguments.get("drmm_alert_uid") or ""
    ).strip()

    if not resource_id:
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_DEVICE_REQUIRED",
            reason="DATTO_THREAT_CORRELATION_DEVICE_REQUIRED",
        )
    if not threat_reference:
        return _correlation_failure(
            error_code="DATTO_THREAT_REFERENCE_REQUIRED",
            reason="DATTO_THREAT_REFERENCE_REQUIRED",
        )

    status_result = _governed_read(
        capability_name="endpoint.security.status.read",
        arguments={"resource_id": resource_id},
    )
    if status_result.get("status") != "succeeded":
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_STATUS_READ_FAILED",
            reason="DATTO_THREAT_CORRELATION_STATUS_READ_FAILED",
            correlation_id=str(status_result.get("correlation_id") or ""),
        )

    status_matches = _correlation_collection(
        status_result,
        "resource_matches",
    )
    exact_status = [
        item
        for item in status_matches
        if str(item.get("resource_id") or "").strip() == resource_id
        and str(item.get("agent_id") or "").strip()
    ]
    if len(exact_status) != 1:
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_EDR_IDENTITY_AMBIGUOUS",
            reason="DATTO_THREAT_CORRELATION_EDR_IDENTITY_AMBIGUOUS",
        )
    agent_id = str(exact_status[0]["agent_id"]).strip()

    open_result = _governed_read(
        capability_name="endpoint.alert.search",
        arguments={"resource_id": resource_id},
    )
    open_alerts = (
        _correlation_collection(open_result, "alerts")
        if open_result.get("status") == "succeeded"
        else []
    )

    def matching_drmm(items: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        matches: list[Mapping[str, Any]] = []
        for item in items:
            context = item.get("alertContext")
            source = item.get("alertSourceInfo")
            if not isinstance(context, Mapping) or not isinstance(source, Mapping):
                continue
            if str(context.get("esAlertId") or "").strip() != threat_reference:
                continue
            if str(source.get("deviceUid") or "").strip() != resource_id:
                continue
            if requested_drmm_alert_uid and (
                str(item.get("alertUid") or "").strip()
                != requested_drmm_alert_uid
            ):
                continue
            matches.append(item)
        return matches

    drmm_matches = matching_drmm(open_alerts)
    history_result: Mapping[str, Any] | None = None
    if not drmm_matches:
        history_result = _governed_read(
            capability_name="endpoint.alert.history.search",
            arguments={"resource_id": resource_id},
        )
        if history_result.get("status") != "succeeded":
            return _correlation_failure(
                error_code="DATTO_THREAT_CORRELATION_ALERT_HISTORY_FAILED",
                reason="DATTO_THREAT_CORRELATION_ALERT_HISTORY_FAILED",
                correlation_id=str(history_result.get("correlation_id") or ""),
            )
        drmm_matches = matching_drmm(
            _correlation_collection(history_result, "alerts")
        )

    if len(drmm_matches) == 0:
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_DRMM_ALERT_NOT_FOUND",
            reason="DATTO_THREAT_CORRELATION_DRMM_ALERT_NOT_FOUND",
        )
    if len(drmm_matches) != 1:
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_DRMM_ALERT_AMBIGUOUS",
            reason="DATTO_THREAT_CORRELATION_DRMM_ALERT_AMBIGUOUS",
        )
    drmm_alert = drmm_matches[0]

    detections_result = _governed_read(
        capability_name="endpoint.security.detection.search",
        arguments={"agent_id": agent_id, "limit": 200},
    )
    if detections_result.get("status") != "succeeded":
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_DETECTION_SEARCH_FAILED",
            reason="DATTO_THREAT_CORRELATION_DETECTION_SEARCH_FAILED",
            correlation_id=str(detections_result.get("correlation_id") or ""),
        )
    detections = _correlation_collection(
        detections_result,
        "alerts",
    )

    try:
        correlated = correlate_drmm_threat_to_edr_detection(
            threat_reference=threat_reference,
            drmm_alert=drmm_alert,
            edr_detections=detections,
            device_uid=resource_id,
            agent_id=agent_id,
        )
    except AmbiguousThreatCorrelationError:
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_EDR_ALERT_AMBIGUOUS",
            reason="DATTO_THREAT_CORRELATION_EDR_ALERT_AMBIGUOUS",
        )
    except ThreatCorrelationError:
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_EDR_ALERT_NOT_FOUND",
            reason="DATTO_THREAT_CORRELATION_EDR_ALERT_NOT_FOUND",
        )

    detail = _governed_read(
        capability_name="endpoint.security.detection.read",
        arguments={"alert_id": correlated.edr_alert_id},
    )
    if detail.get("status") != "succeeded":
        return _correlation_failure(
            error_code="DATTO_THREAT_CORRELATION_DETAIL_READ_FAILED",
            reason="DATTO_THREAT_CORRELATION_DETAIL_READ_FAILED",
            correlation_id=str(detail.get("correlation_id") or ""),
        )

    result = dict(detail)
    result["correlation"] = {
        "threat_reference": correlated.threat_reference,
        "drmm_alert_uid": correlated.drmm_alert_uid,
        "edr_alert_id": correlated.edr_alert_id,
        "device_uid": correlated.device_uid,
        "agent_id": correlated.agent_id,
        "event_delta_seconds": correlated.event_delta_seconds,
        "basis": correlated.basis,
        "fail_closed": True,
    }
    return result


def _project_action_result(
    capability_name: str,
    output: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose only capability-specific verified action evidence."""

    data = output.get("data")

    if not isinstance(data, Mapping):
        data = {}

    result: dict[str, Any] = {
        "raw_provider_evidence_exposed": False,
    }

    if capability_name == "service.ticket.note.create":
        verification = data.get("jasonVerification")

        if not isinstance(verification, Mapping):
            result["verification_available"] = False
            return result

        result["verification_available"] = True
        result["readback_verified"] = bool(
            verification.get("readbackVerified")
        )

        note_id = verification.get("ticketNoteId")

        if note_id is not None:
            result["ticket_note_id"] = _safe(note_id)

        result["impersonator_recorded"] = bool(
            verification.get("impersonatorRecorded")
        )

        return result

    if capability_name == "service.ticket.update":
        verification = data.get("jasonVerification")

        if not isinstance(verification, Mapping):
            result["verification_available"] = False
            return result

        result["verification_available"] = True
        result["readback_verified"] = bool(
            verification.get("readbackVerified")
        )

        ticket_id = verification.get("ticketId")

        if ticket_id is not None:
            result["ticket_id"] = _safe(ticket_id)

        fields = verification.get("verifiedFields")

        if isinstance(fields, (list, tuple)):
            result["verified_fields"] = [
                str(value)
                for value in fields[:20]
            ]
            result["verified_fields_bounded"] = (
                len(fields) > 20
            )

        return result

    if capability_name == "endpoint.alert.resolve":
        for source in (
            "status",
            "alert_uid",
            "device_uid",
            "resolved",
            "already_resolved",
            "mutation_performed",
            "readback_verified",
        ):
            if source in data:
                result[source] = _safe(data.get(source))
        return result

    if capability_name == "endpoint.security.scan.start":
        for source in (
            "status",
            "resource_id",
            "agent_id",
            "scan_type",
            "task_name",
            "task_id",
            "provider_accepted",
            "readback_required",
        ):
            if source in data:
                result[source] = _safe(data.get(source))
        return result

    if capability_name == "automation.component.execute":
        for source, target in (
            ("status", "status"),
            ("job_status", "job_status"),
            ("readback_verified", "readback_verified"),
            ("completion_verified", "completion_verified"),
            ("allowlist_name", "allowlist_name"),
        ):
            if source in data:
                result[target] = _safe(data.get(source))

        job_uid = str(
            data.get("job_uid") or ""
        ).strip()
        device_uid = str(
            data.get("device_uid") or ""
        ).strip()
        component_uid = str(
            data.get("component_uid") or ""
        ).strip()
        component_name = str(
            data.get("component_name") or ""
        ).strip()

        if job_uid:
            result["job_uid"] = _safe(job_uid)
            result["job_read_arguments"] = {
                "resource_id": job_uid,
            }

        if device_uid:
            result["device_uid"] = _safe(device_uid)

        if component_uid:
            result["component_uid"] = _safe(
                component_uid
            )

        if component_name:
            result["component_name"] = _safe(
                component_name
            )

        if job_uid and device_uid and component_uid:
            result["output_read_arguments"] = {
                "resource_id": job_uid,
                "device_uid": device_uid,
                "component_uid": component_uid,
                "stream": "stdout",
            }
            result["follow_up_contract"] = {
                "poll_same_job": True,
                "read_output_after_terminal": True,
                "do_not_redispatch": True,
            }

        result["job_reference_present"] = bool(job_uid)

        return result

    result["result_exposed"] = False
    return result



def _canonical_datto_component_search_arguments(
    arguments: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Use one stable provider page size while Jason completes the catalog."""

    normalized = dict(arguments or {})

    # Provider page navigation is internal to Jason. Every conversational
    # component lookup begins at Datto page zero and Jason follows all pages
    # before applying the requested name filter.
    normalized["page"] = 0
    normalized["max"] = 100

    return normalized


def _resolve_live_datto_component_record(
    component_name: object,
) -> Mapping[str, Any]:
    """Resolve one exact component through complete governed catalog discovery."""

    requested_name = str(component_name or "").strip()
    if not requested_name:
        raise ValueError("DATTO_COMPONENT_NAME_REQUIRED")

    lookup = _governed_read(
        capability_name="automation.component.search",
        arguments=_canonical_datto_component_search_arguments(
            {"name": requested_name}
        ),
    )
    if lookup.get("status") != "succeeded":
        raise ValueError("DATTO_COMPONENT_CATALOG_LOOKUP_FAILED")
    evidence = lookup.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("DATTO_COMPONENT_CATALOG_LOOKUP_FAILED")
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("DATTO_COMPONENT_CATALOG_LOOKUP_FAILED")
    if data.get("discovery_complete") is not True:
        raise ValueError("DATTO_COMPONENT_CATALOG_DISCOVERY_INCOMPLETE")
    matches = data.get("resource_matches")
    if not isinstance(matches, (list, tuple)):
        raise ValueError("DATTO_COMPONENT_CATALOG_LOOKUP_FAILED")

    exact: list[Mapping[str, Any]] = []
    for item in matches:
        if not isinstance(item, Mapping):
            continue
        live_name = str(item.get("name") or "").strip()
        if live_name.casefold() != requested_name.casefold():
            continue
        live_uid = str(item.get("resource_id") or "").strip()
        if not live_uid:
            raise ValueError("DATTO_COMPONENT_IDENTITY_MISMATCH")
        exact.append(dict(item))

    if not exact:
        raise ValueError("DATTO_COMPONENT_NAME_MISMATCH")
    unique = {
        (
            str(item.get("resource_id") or "").strip(),
            str(item.get("name") or "").strip().casefold(),
        )
        for item in exact
    }
    if len(unique) != 1:
        raise ValueError("DATTO_COMPONENT_CATALOG_AMBIGUOUS")
    return exact[0]


def _resolve_live_datto_component_name(
    component_name: object,
) -> tuple[str, str]:
    record = _resolve_live_datto_component_record(component_name)
    return (
        str(record.get("resource_id") or "").strip(),
        str(record.get("name") or "").strip(),
    )



def _verify_managed_datto_component_target(
    device_uid: object,
) -> str:
    """Verify one exact Datto target through Jason's governed read path."""

    requested = str(device_uid or "").strip()
    if not requested:
        raise ValueError("DATTO_COMPONENT_TARGET_REQUIRED")

    lookup = _governed_read(
        capability_name="endpoint.device.read",
        arguments={"resource_id": requested},
    )

    if lookup.get("status") != "succeeded":
        raise ValueError("DATTO_COMPONENT_TARGET_LOOKUP_FAILED")

    evidence = lookup.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("DATTO_COMPONENT_TARGET_LOOKUP_FAILED")

    record = evidence.get("record")
    if not isinstance(record, Mapping):
        raise ValueError("DATTO_COMPONENT_TARGET_LOOKUP_FAILED")

    observed = str(record.get("resource_id") or "").strip()
    if observed != requested:
        raise ValueError("DATTO_COMPONENT_TARGET_IDENTITY_MISMATCH")

    if record.get("deleted") is True or record.get("suspended") is True:
        raise ValueError("DATTO_COMPONENT_TARGET_NOT_ACTIVE")

    return observed


def _exact_ticket_record_for_work_start(ticket_id: int) -> Mapping[str, Any]:
    result = _governed_read(
        capability_name="service.ticket.read",
        arguments={"ticket_id": ticket_id},
    )
    if result.get("status") != "succeeded":
        raise ValueError("AUTOTASK_TICKET_WORK_START_READ_FAILED")
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("AUTOTASK_TICKET_WORK_START_READ_FAILED")
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("AUTOTASK_TICKET_WORK_START_READ_FAILED")
    items = data.get("items")
    if not isinstance(items, list) or len(items) != 1:
        raise ValueError("AUTOTASK_TICKET_WORK_START_IDENTITY_NOT_UNIQUE")
    record = items[0]
    if not isinstance(record, Mapping):
        raise ValueError("AUTOTASK_TICKET_WORK_START_READ_FAILED")
    try:
        observed = int(record.get("id"))
    except (TypeError, ValueError) as error:
        raise ValueError("AUTOTASK_TICKET_WORK_START_READ_FAILED") from error
    if observed != ticket_id:
        raise ValueError("AUTOTASK_TICKET_WORK_START_IDENTITY_MISMATCH")
    return record


def _ticket_context_device_name(record: Mapping[str, Any]) -> str | None:
    title = str(record.get("title") or "").strip()
    if not title:
        return None

    patterns = (
        r"\bfor\s+([A-Za-z0-9][A-Za-z0-9._-]{1,63})\s*$",
        r"\bon\s+([A-Za-z0-9][A-Za-z0-9._-]{1,63})\s*$",
        r"\bmachine\s+([A-Za-z0-9][A-Za-z0-9._-]{1,63})(?:\s|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, title, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip()
        # Avoid treating ordinary trailing words as hostnames. AOT endpoint
        # names consistently contain a digit and/or a hyphen.
        if any(char.isdigit() for char in candidate) or "-" in candidate:
            return candidate
    return None


def _exact_configuration_for_ticket_device(
    *,
    ticket: Mapping[str, Any],
    device_name: str,
) -> int | None:
    endpoint = _governed_read(
        capability_name="endpoint.device.search",
        arguments={"name": device_name},
    )
    if endpoint.get("status") != "succeeded":
        return None
    evidence = endpoint.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    matches = evidence.get("resource_matches")
    if not isinstance(matches, list):
        return None
    exact_endpoints = [
        item
        for item in matches
        if isinstance(item, Mapping)
        and str(item.get("hostname") or "").strip().casefold()
        == device_name.casefold()
        and str(item.get("resource_id") or "").strip()
    ]
    if len(exact_endpoints) != 1:
        return None
    device_uid = str(exact_endpoints[0]["resource_id"]).strip()

    try:
        company_id = int(ticket.get("companyID"))
    except (TypeError, ValueError):
        return None
    if company_id < 0:
        return None

    configuration = _governed_read(
        capability_name="service.configuration.search",
        arguments={
            "name": device_name,
            "company_id": company_id,
            "page_size": 50,
        },
    )
    if configuration.get("status") != "succeeded":
        return None
    config_evidence = configuration.get("evidence")
    if not isinstance(config_evidence, Mapping):
        return None
    data = config_evidence.get("data")
    if not isinstance(data, Mapping):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None

    exact_configs: list[int] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if item.get("isActive") is not True:
            continue
        if str(item.get("referenceTitle") or "").strip().casefold() != device_name.casefold():
            continue
        if str(item.get("referenceNumber") or "").strip() != device_uid:
            continue
        try:
            observed_company = int(item.get("companyID"))
            config_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if observed_company != company_id or config_id < 1:
            continue
        exact_configs.append(config_id)

    unique = sorted(set(exact_configs))
    if len(unique) != 1:
        return None
    return unique[0]


def _ticket_work_start_arguments(raw: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "ticket_id",
        "ticketID",
        "resource_id",
        "begin_work",
        "device_name",
        "issue_type",
        "sub_issue_type",
        "ticket_type",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(
            "AUTOTASK_TICKET_WORK_START_UNSUPPORTED_ARGUMENTS:"
            + ",".join(sorted(unknown))
        )

    value = raw.get("ticket_id", raw.get("ticketID", raw.get("resource_id")))
    if isinstance(value, bool):
        raise ValueError("AUTOTASK_TICKET_WORK_START_TICKET_ID_REQUIRED")
    try:
        ticket_id = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("AUTOTASK_TICKET_WORK_START_TICKET_ID_REQUIRED") from error
    if ticket_id < 1:
        raise ValueError("AUTOTASK_TICKET_WORK_START_TICKET_ID_REQUIRED")

    ticket = _exact_ticket_record_for_work_start(ticket_id)
    payload: dict[str, Any] = {
        "id": ticket_id,
        "queueID": "Jason",
        "status": "In Progress",
        "billingCodeID": "Remote Support",
    }

    current_configuration = ticket.get("configurationItemID")
    try:
        current_configuration_id = int(current_configuration)
    except (TypeError, ValueError):
        current_configuration_id = 0

    if current_configuration_id < 1:
        requested_device = str(raw.get("device_name") or "").strip()
        candidate = requested_device or _ticket_context_device_name(ticket)
        if candidate:
            configuration_id = _exact_configuration_for_ticket_device(
                ticket=ticket,
                device_name=candidate,
            )
            if configuration_id is not None:
                payload["configurationItemID"] = configuration_id

    issue_type = str(raw.get("issue_type") or "").strip()
    sub_issue_type = str(raw.get("sub_issue_type") or "").strip()
    ticket_type = str(raw.get("ticket_type") or "").strip()

    if issue_type:
        payload["issueType"] = issue_type
    if sub_issue_type:
        if "issueType" not in payload:
            current_issue = ticket.get("issueType")
            try:
                current_issue_id = int(current_issue)
            except (TypeError, ValueError):
                current_issue_id = 0
            if current_issue_id < 1:
                raise ValueError(
                    "AUTOTASK_TICKET_WORK_START_SUBISSUE_REQUIRES_ISSUE"
                )
            payload["issueType"] = current_issue_id
        payload["subIssueType"] = sub_issue_type
    if ticket_type:
        payload["ticketType"] = ticket_type

    return {
        "payload": payload,
        "jason_policy_class": "ticket_work_start",
    }


def _canonicalize_governed_action_arguments(
    capability_name: str,
    arguments: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Canonicalize server-controlled action arguments before approval/execution.

    ChatGPT may express the same governed action with slightly different
    argument shapes. Provider containment must not depend on the model
    remembering internal allowlist/profile fields.

    For bounded Datto component execution, Jason supplies its own
    server-controlled allowlist and policy class. The caller must identify the
    exact managed target and component. Jason verifies the target through the
    governed endpoint read path and resolves component identity through the live
    Datto catalog before approval or provider execution.
    """

    raw = dict(arguments or {})

    if capability_name == "service.ticket.update":
        if raw.get("begin_work") is True:
            return _ticket_work_start_arguments(raw)
        return raw

    if capability_name == SERVICE_TICKET_NOTE_CREATE:
        if "payload" in raw:
            return raw

        allowed = {"ticket_id", "ticketID", "note", "description", "title"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(
                "AUTOTASK_INTERNAL_NOTE_UNSUPPORTED_ARGUMENTS:"
                + ",".join(sorted(unknown))
            )

        ticket_id = raw.get("ticket_id", raw.get("ticketID"))
        note = raw.get("note", raw.get("description"))
        title = raw.get("title", "")
        return _internal_note_arguments(
            ticket_id=ticket_id,
            note=note,
            title=title,
        )

    if capability_name == "endpoint.alert.resolve":
        allowed = {"alert_uid", "device_uid", "resource_id"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(
                "DATTO_ALERT_RESOLVE_UNSUPPORTED_ARGUMENTS:"
                + ",".join(sorted(unknown))
            )
        alert_uid = str(raw.get("alert_uid") or "").strip()
        device_uid = str(
            raw.get("device_uid")
            or raw.get("resource_id")
            or ""
        ).strip()
        if not alert_uid:
            raise ValueError("DATTO_ALERT_UID_REQUIRED")
        if not device_uid:
            raise ValueError("DATTO_ALERT_DEVICE_UID_REQUIRED")
        return {
            "alert_uid": alert_uid,
            "device_uid": device_uid,
        }

    if capability_name == "endpoint.security.scan.start":
        allowed = {"resource_id", "device_uid", "agent_id", "scan_type"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(
                "DATTO_EDR_SCAN_UNSUPPORTED_ARGUMENTS:"
                + ",".join(sorted(unknown))
            )
        resource_id = str(
            raw.get("resource_id") or raw.get("device_uid") or ""
        ).strip()
        agent_id = str(raw.get("agent_id") or "").strip()
        scan_type = str(raw.get("scan_type") or "").strip().casefold()
        if not resource_id:
            raise ValueError("DATTO_EDR_SCAN_RESOURCE_REQUIRED")
        if not agent_id:
            raise ValueError("DATTO_EDR_SCAN_AGENT_REQUIRED")
        if scan_type not in {"quick", "full"}:
            raise ValueError("DATTO_EDR_SCAN_TYPE_INVALID")
        return {
            "resource_id": resource_id,
            "agent_id": agent_id,
            "scan_type": scan_type,
        }

    if capability_name != "automation.component.execute":
        return raw

    expected = {
        "allowlist_name": os.environ.get(
            "JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME",
            "",
        ).strip(),
        "device_uid": os.environ.get(
            "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID",
            "",
        ).strip(),
        "device_class": os.environ.get(
            "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_CLASS",
            "",
        ).strip(),
    }

    components = configured_datto_components()

    if not all(expected.values()) or not components:
        raise ValueError(
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INCOMPLETE"
        )

    requested_device = str(
        raw.get("device_uid")
        or raw.get("resource_id")
        or raw.get("target_device_uid")
        or ""
    ).strip()

    if not requested_device:
        raise ValueError(
            "DATTO_COMPONENT_TARGET_REQUIRED"
        )

    requested_device = _verify_managed_datto_component_target(
        requested_device
    )

    supplied_allowlist = str(
        raw.get("allowlist_name") or ""
    ).strip()

    if (
        supplied_allowlist
        and supplied_allowlist != expected["allowlist_name"]
    ):
        raise ValueError(
            "DATTO_COMPONENT_ALLOWLIST_MISMATCH"
        )

    # device_class is server-controlled policy metadata. Caller/model-provided
    # class labels are deliberately ignored. Exact endpoint identity and active
    # managed state are independently verified above.
    supplied_class = expected["device_class"]

    supplied_component_uid = str(
        raw.get("component_uid")
        or raw.get("component_id")
        or ""
    ).strip()

    supplied_component_name = str(
        raw.get("component_name") or ""
    ).strip()

    # Human callers identify components by their Datto display name.
    # Jason resolves that name against the complete governed live catalog
    # before selecting approval policy or creating a provider mutation.
    if supplied_component_name:
        (
            live_component_uid,
            live_component_name,
        ) = _resolve_live_datto_component_name(
            supplied_component_name
        )

        # Exact live name resolution is authoritative. Some callers retain a
        # stale provider UID in conversation/tool state; that advisory hint must
        # not block an otherwise exact, uniquely resolved component name. Jason
        # always replaces any supplied UID with the current live Datto UID.
        supplied_component_uid = (
            live_component_uid
        )
        supplied_component_name = (
            live_component_name
        )

    selected_component = resolve_datto_component(
        components,
        component_uid=supplied_component_uid,
        component_name=supplied_component_name,
        catalog_verified=bool(supplied_component_name),
    )

    variables = raw.get("variables", {})
    if variables is None:
        variables = {}

    if not isinstance(variables, Mapping):
        raise ValueError(
            "DATTO_COMPONENT_VARIABLES_INVALID"
        )

    # Only exact server-resolved component identity and provider-neutral values
    # required by the runtime are forwarded. The model cannot widen the set.
    return {
        "allowlist_name": expected["allowlist_name"],
        "device_uid": requested_device,
        "device_class": expected["device_class"],
        "component_uid": selected_component.uid,
        "component_name": selected_component.name,
        "variables": dict(variables),
    }


def _governed_execute(
    *,
    capability_name: str,
    arguments: Mapping[str, Any],
    explicit_approval: bool = False,
) -> dict[str, Any]:
    """Execute one explicitly MCP-enabled mutation through Jason governance."""

    app = _runtime()

    (
        principal,
        organization,
        assurance,
        client_id,
    ) = _authenticated_write_identity()

    try:
        capability = app.capabilities.get_current(
            capability_name=capability_name
        )
    except LookupError:
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": "capability_not_active",
        }

    metadata = dict(capability.metadata or {})

    if (
        str(metadata.get("mcp_action_enabled", "")).casefold()
        != "true"
    ):
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": "capability_not_mcp_action_enabled",
        }

    try:
        canonical_arguments = (
            _canonicalize_governed_action_arguments(
                capability_name,
                arguments,
            )
        )
    except ValueError as exc:
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": "invalid_action_arguments",
            "reason_codes": [str(exc)],
        }

    datto_approval_mode: str | None = None
    datto_approval_reason_code: str | None = None

    if capability_name == "automation.component.execute":
        try:
            selected_component = resolve_datto_component(
                configured_datto_components(),
                component_uid=canonical_arguments.get("component_uid"),
                component_name=canonical_arguments.get("component_name"),
                catalog_verified=True,
            )
        except ValueError as exc:
            return {
                "status": "rejected",
                "capability": capability_name,
                "error_code": "invalid_action_arguments",
                "reason_codes": [str(exc)],
            }

        (
            datto_approval_mode,
            datto_approval_reason_code,
        ) = effective_datto_component_approval_mode(
            selected_component,
            canonical_arguments.get(
                "variables",
                {},
            ),
        )

        if (
            datto_approval_mode != DATTO_APPROVAL_MODE_PER_RUN
            and selected_component.approval_source == "durable_registry"
            and selected_component.metadata_fingerprint
        ):
            try:
                live_record = _resolve_live_datto_component_record(
                    selected_component.name
                )
                current_fingerprint = component_metadata_fingerprint(
                    live_record
                )
            except ValueError as exc:
                return {
                    "status": "rejected",
                    "capability": capability_name,
                    "error_code": "invalid_action_arguments",
                    "reason_codes": [str(exc)],
                }

            if current_fingerprint != selected_component.metadata_fingerprint:
                datto_approval_mode = DATTO_APPROVAL_MODE_PER_RUN
                datto_approval_reason_code = (
                    "DATTO_COMPONENT_STANDING_APPROVAL_STALE"
                )

    execution_id = f"exec_mcp_action_{uuid4().hex}"
    correlation_id = f"corr_mcp_action_{uuid4().hex}"

    decision = app.identity_authority.evaluate(
        AuthorityRequest(
            request_id=execution_id,
            correlation_id=correlation_id,
            principal_id=principal,
            organization_id=organization,
            client_id=client_id,
            capability=capability_name,
            requested_mode=PermissionMode.EXECUTE,
            authentication_assurance=assurance,
        )
    )

    approval_present = False

    if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:
        approval_decided_by = principal

        if capability_name == "automation.component.execute":
            if datto_approval_mode == "standing_safe":
                imperative_approval = True

                if (
                    datto_approval_reason_code
                    == "DATTO_POWERSHELL_READ_ONLY_COMMAND"
                ):
                    approval_decided_by = (
                        "policy:datto-powershell-readonly"
                    )
                else:
                    approval_decided_by = (
                        "policy:datto-standing-safe"
                    )
            elif datto_approval_mode == "per_run":
                imperative_approval = explicit_approval is True

                if not imperative_approval:
                    return {
                        "status": "approval_required",
                        "capability": capability_name,
                        "reason_codes": [
                            *(
                                [datto_approval_reason_code]
                                if datto_approval_reason_code
                                else []
                            ),
                            "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED",
                            *list(decision.reason_codes),
                        ],
                        "correlation_id": correlation_id,
                        "approval_signal": {
                            "argument": "explicit_approval",
                            "required_value": True,
                            "scope": "exact_execution",
                        },
                    }
            else:
                return {
                    "status": "denied",
                    "capability": capability_name,
                    "reason_codes": [
                        "DATTO_COMPONENT_APPROVAL_MODE_INVALID",
                    ],
                    "correlation_id": correlation_id,
                }
        elif (
            capability_name == "service.ticket.update"
            and canonical_arguments.get("jason_policy_class")
            == "ticket_work_start"
        ):
            # Owner-approved standing administrative lifecycle transition:
            # claiming a ticket that Jason has begun working is not a second
            # approval gate. The server, not the caller, fixes queue/status/
            # work-type defaults and all provider labels are resolved live.
            imperative_approval = True
            approval_decided_by = "policy:ticket-work-start"
        else:
            imperative_approval = (
                str(
                    metadata.get(
                        "conversation_authenticated_imperative_is_approval",
                        "",
                    )
                ).casefold()
                == "true"
            )

        if not imperative_approval:
            return {
                "status": "approval_required",
                "capability": capability_name,
                "reason_codes": list(decision.reason_codes),
                "correlation_id": correlation_id,
            }

        approval_repository = getattr(
            app.identity_authority,
            "approvals",
            None,
        )
        approval_writer = getattr(
            approval_repository,
            "put",
            None,
        )

        if not callable(approval_writer):
            return {
                "status": "denied",
                "capability": capability_name,
                "reason_codes": [
                    "APPROVAL_PERSISTENCE_UNAVAILABLE",
                ],
                "correlation_id": correlation_id,
            }

        now = datetime.now(timezone.utc)
        approval_id = f"approval_mcp_{uuid4().hex}"

        approval_writer(
            ApprovalRecord(
                approval_id=approval_id,
                request_id=execution_id,
                capability=capability_name,
                organization_id=organization,
                client_id=client_id,
                requested_by=principal,
                status="approved",
                decided_by=approval_decided_by,
                decided_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )

        decision = app.identity_authority.evaluate(
            AuthorityRequest(
                request_id=execution_id,
                correlation_id=correlation_id,
                principal_id=principal,
                organization_id=organization,
                client_id=client_id,
                capability=capability_name,
                requested_mode=PermissionMode.EXECUTE,
                authentication_assurance=assurance,
                approval_id=approval_id,
            )
        )

        approval_present = True

    if decision.outcome is not AuthorityOutcome.ALLOWED:
        return {
            "status": "denied",
            "capability": capability_name,
            "reason_codes": list(decision.reason_codes),
            "correlation_id": correlation_id,
        }

    context = decision.execution_context

    if context is None:
        return {
            "status": "denied",
            "capability": capability_name,
            "reason_codes": [
                "AUTHORITY_CONTEXT_MISSING",
            ],
            "correlation_id": correlation_id,
        }

    if capability.approval.required and not context.approval_required:
        return {
            "status": "denied",
            "capability": capability_name,
            "reason_codes": [
                "ACTION_GRANT_APPROVAL_POLICY_MISMATCH",
            ],
            "correlation_id": correlation_id,
        }

    request = OrchestrationRequest(
        execution_id=execution_id,
        correlation_id=correlation_id,
        principal_id=principal,
        organization_id=organization,
        client_id=client_id,
        capability_name=capability_name,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=(
            approval_present
            or not capability.approval.required
            or context.approval_required
        ),
        risk=capability.risk_level.value,
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("1.00"),
            maximum_attempts=1,
        ),
        arguments=canonical_arguments,
        requester_kind="human",
        permission_mode="execute",
        policy_ids=("mcp-governed-execution-v1",),
        authority_context_id=context.context_id,
        idempotency_key=f"idem_mcp_action_{uuid4().hex}",
    )

    result = app.governed_orchestrator.execute(request)

    response = {
        "status": result.status.value,
        "stage": result.stage.value,
        "capability": result.capability_name,
        "provider": result.provider_id,
        "reason_codes": list(result.reason_codes),
        "error_code": result.error_code,
        "correlation_id": result.correlation_id,
        "provider_attempts": result.attempts,
    }

    if isinstance(result.output, Mapping):
        response["result"] = _project_action_result(
            capability_name,
            result.output,
        )

    return response


def create_autotask_internal_note(
    ticket_id: int,
    note: str,
    title: str = "",
) -> dict[str, Any]:
    """Create one internal Autotask ticket note.

    This tool is registered only when the explicit internal-note MCP
    activation profile, mutation execution gate, and requester-native
    impersonation gate are all enabled. Microsoft Entra authenticates
    the caller; Jason's exact execute grant and per-execution approval
    determine mutation authority. noteType and publish are fixed
    server-side.
    """

    return _governed_internal_note_create(
        ticket_id=ticket_id,
        note=note,
        title=title,
    )


if _MCP_INTERNAL_NOTE_SURFACE_ENABLED:
    mcp.tool()(create_autotask_internal_note)


_UNSUPERVISED_COMPONENT_BLOCK_PATTERNS = (
    "reboot",
    "restart",
    "shutdown",
    "shut down",
    "logoff",
    "log off",
    "poweroff",
    "power off",
    "uninstall",
    "remove ",
    "delete ",
    "disable ",
    "stop service",
    "factory reset",
    "wipe",
    "format disk",
)


def _component_approval_owner() -> tuple[str, str]:
    principal, organization, _, _ = _authenticated_write_identity()
    owners = approval_owner_identities()
    if not owners or principal not in owners:
        raise PermissionError("DATTO_COMPONENT_APPROVAL_OWNER_REQUIRED")
    return principal, organization


def _component_unsupervised_block_reason(
    record: Mapping[str, Any],
) -> str | None:
    uid = str(record.get("resource_id") or "").strip()
    name = str(record.get("name") or "").strip()
    if (
        uid == DATTO_AD_HOC_POWERSHELL_UID
        or name.casefold() == DATTO_AD_HOC_POWERSHELL_NAME.casefold()
    ):
        return "DATTO_COMPONENT_AD_HOC_SHELL_CANNOT_BE_UNSUPERVISED"

    review_text = " ".join(
        (
            name,
            str(record.get("description") or ""),
        )
    ).casefold()
    for pattern in _UNSUPERVISED_COMPONENT_BLOCK_PATTERNS:
        if pattern in review_text:
            return "DATTO_COMPONENT_DISRUPTIVE_OR_DESTRUCTIVE_REVIEW_REQUIRED"
    return None


@mcp.tool()
def list_datto_component_approvals() -> dict[str, Any]:
    """List server-controlled Datto component execution classifications.

    Standing-safe components may be selected by Jason without a per-run
    technician approval. Per-run components still require the exact technician
    instruction for the specific execution. Durable registry approvals and
    revocations are included without exposing provider credentials.
    """

    try:
        _component_approval_owner()
        configured = configured_datto_components()
        records = list_component_approval_records()
    except (PermissionError, ValueError) as exc:
        return {
            "status": "rejected",
            "error_code": str(exc),
        }

    return {
        "status": "succeeded",
        "standing_safe": [
            {
                "uid": item.uid,
                "name": item.name,
                "approval_mode": item.approval_mode,
                "approval_source": item.approval_source,
                "metadata_fingerprint_present": bool(
                    item.metadata_fingerprint
                ),
            }
            for item in configured
            if item.approval_mode == "standing_safe"
        ],
        "per_run": [
            {
                "uid": item.uid,
                "name": item.name,
                "approval_mode": item.approval_mode,
                "approval_source": item.approval_source,
            }
            for item in configured
            if item.approval_mode == "per_run"
        ],
        "durable_history": [
            {
                "uid": item.uid,
                "name": item.name,
                "status": item.status,
                "approved_by": item.approved_by,
                "approved_at": item.approved_at,
                "reason": item.reason,
                "revoked_by": item.revoked_by,
                "revoked_at": item.revoked_at,
                "revoke_reason": item.revoke_reason,
            }
            for item in records[-100:]
        ],
    }


@mcp.tool()
def approve_datto_component_for_unsupervised_use(
    component_name: str,
    reason: str = "",
) -> dict[str, Any]:
    """Owner-only: approve one exact live Datto component for standing use.

    The component is resolved from the complete governed Datto catalog. The
    durable approval binds to its UID/name and reviewable metadata fingerprint.
    Obvious disruptive/destructive components and the generic PowerShell runner
    cannot be promoted to unsupervised authority by this tool.
    """

    try:
        principal, _ = _component_approval_owner()
        live = _resolve_live_datto_component_record(component_name)
        blocked = _component_unsupervised_block_reason(live)
        if blocked:
            return {
                "status": "rejected",
                "error_code": blocked,
                "component_name": str(live.get("name") or ""),
            }
        fingerprint = component_metadata_fingerprint(live)
        record = persist_component_approval(
            uid=str(live.get("resource_id") or "").strip(),
            name=str(live.get("name") or "").strip(),
            approved_by=principal,
            metadata_fingerprint=fingerprint,
            reason=reason,
        )
        selected = resolve_datto_component(
            configured_datto_components(),
            component_uid=record.uid,
            component_name=record.name,
            catalog_verified=True,
        )
    except (PermissionError, ValueError) as exc:
        return {
            "status": "rejected",
            "error_code": str(exc),
        }

    if selected.approval_mode != "standing_safe":
        return {
            "status": "rejected",
            "error_code": "DATTO_COMPONENT_CANNOT_BE_STANDING_SAFE",
            "component_uid": record.uid,
            "component_name": record.name,
        }

    return {
        "status": "succeeded",
        "component_uid": record.uid,
        "component_name": record.name,
        "approval_mode": "standing_safe",
        "approved_by": record.approved_by,
        "approved_at": record.approved_at,
        "metadata_fingerprint": record.metadata_fingerprint,
        "scope": "verified_managed_endpoints",
        "variables": "empty_or_server-governed_only",
    }


@mcp.tool()
def revoke_datto_component_unsupervised_approval(
    component_name: str,
    reason: str = "",
) -> dict[str, Any]:
    """Owner-only: revoke standing approval and return the component to per-run."""

    try:
        principal, _ = _component_approval_owner()
        requested = str(component_name or "").strip()
        if not requested:
            raise ValueError("DATTO_COMPONENT_NAME_REQUIRED")

        configured = configured_datto_components()
        matches = [
            item
            for item in configured
            if item.name.casefold() == requested.casefold()
        ]
        if len(matches) == 1:
            uid = matches[0].uid
            name = matches[0].name
        else:
            live = _resolve_live_datto_component_record(requested)
            uid = str(live.get("resource_id") or "").strip()
            name = str(live.get("name") or "").strip()

        record = persist_component_revocation(
            uid=uid,
            name=name,
            revoked_by=principal,
            reason=reason,
        )
        selected = resolve_datto_component(
            configured_datto_components(),
            component_uid=uid,
            component_name=name,
            catalog_verified=True,
        )
    except (PermissionError, ValueError) as exc:
        return {
            "status": "rejected",
            "error_code": str(exc),
        }

    return {
        "status": "succeeded",
        "component_uid": record.uid,
        "component_name": record.name,
        "approval_mode": selected.approval_mode,
        "revoked_by": record.revoked_by,
        "revoked_at": record.revoked_at,
    }


def _component_bulk_names(
    component_names: list[str] | tuple[str, ...],
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(component_names, (list, tuple)):
        raise ValueError("DATTO_COMPONENT_BULK_SELECTION_INVALID")
    names: list[str] = []
    seen: set[str] = set()
    for raw in component_names:
        name = str(raw or "").strip()
        if not name:
            continue
        folded = name.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        names.append(name)
    if not names and not allow_empty:
        raise ValueError("DATTO_COMPONENT_BULK_SELECTION_EMPTY")
    if len(names) > 1000:
        raise ValueError("DATTO_COMPONENT_BULK_SELECTION_TOO_LARGE")
    return names


@mcp.tool()
def bulk_approve_datto_components_for_unsupervised_use(
    component_names: list[str],
    reason: str = "",
) -> dict[str, Any]:
    """Owner-only bulk standing approval for selected live Datto components."""

    try:
        principal, _ = _component_approval_owner()
        names = _component_bulk_names(component_names)
    except (PermissionError, ValueError) as exc:
        return {"status": "rejected", "error_code": str(exc)}

    approved: list[dict[str, Any]] = []
    ineligible: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for name in names:
        try:
            live = _resolve_live_datto_component_record(name)
            blocked = _component_unsupervised_block_reason(live)
            if blocked:
                ineligible.append({"name": name, "reason": blocked})
                continue
            fingerprint = component_metadata_fingerprint(live)
            record = persist_component_approval(
                uid=str(live.get("resource_id") or "").strip(),
                name=str(live.get("name") or "").strip(),
                approved_by=principal,
                metadata_fingerprint=fingerprint,
                reason=reason,
            )
            selected = resolve_datto_component(
                configured_datto_components(),
                component_uid=record.uid,
                component_name=record.name,
                catalog_verified=True,
            )
            if selected.approval_mode != "standing_safe":
                ineligible.append({
                    "name": record.name,
                    "reason": "DATTO_COMPONENT_CANNOT_BE_STANDING_SAFE",
                })
                continue
            approved.append({
                "uid": record.uid,
                "name": record.name,
                "approved_at": record.approved_at,
            })
        except Exception as exc:
            failed.append({"name": name, "reason": str(exc)})

    return {
        "status": "succeeded" if not failed else "partial",
        "selected_count": len(names),
        "approved_count": len(approved),
        "ineligible_count": len(ineligible),
        "failed_count": len(failed),
        "approved": approved,
        "ineligible": ineligible,
        "failed": failed,
    }


@mcp.tool()
def bulk_revoke_datto_component_unsupervised_approvals(
    component_names: list[str],
    reason: str = "",
) -> dict[str, Any]:
    """Owner-only bulk revoke of standing Datto component approvals."""

    try:
        principal, _ = _component_approval_owner()
        names = _component_bulk_names(component_names)
    except (PermissionError, ValueError) as exc:
        return {"status": "rejected", "error_code": str(exc)}

    revoked: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for name in names:
        try:
            configured = configured_datto_components()
            matches = [
                item for item in configured
                if item.name.casefold() == name.casefold()
            ]
            if len(matches) == 1:
                uid, live_name = matches[0].uid, matches[0].name
            else:
                live = _resolve_live_datto_component_record(name)
                uid = str(live.get("resource_id") or "").strip()
                live_name = str(live.get("name") or "").strip()
            record = persist_component_revocation(
                uid=uid,
                name=live_name,
                revoked_by=principal,
                reason=reason,
            )
            revoked.append({
                "uid": record.uid,
                "name": record.name,
                "revoked_at": record.revoked_at,
            })
        except Exception as exc:
            failed.append({"name": name, "reason": str(exc)})

    return {
        "status": "succeeded" if not failed else "partial",
        "selected_count": len(names),
        "revoked_count": len(revoked),
        "failed_count": len(failed),
        "revoked": revoked,
        "failed": failed,
    }


@mcp.tool()
def jason_mcp_status() -> dict[str, object]:
    """Return Jason MCP governed capability state."""

    actions = _active_action_capabilities()
    write_enabled = bool(actions)

    return {
        "status": "ok",
        "service": "jason-mcp",
        "mode": (
            "governed-read-plus-actions"
            if write_enabled
            else "read-only"
        ),
        "phase": (
            "governed-action-pilot"
            if write_enabled
            else "governed-read-pilot"
        ),
        "governed_execution": "central-orchestrator",
        "generic_execution_tool": True,
        "direct_provider_access": False,
        "write_tools_enabled": write_enabled,
        "write_capabilities": actions,
        "write_authority": (
            "jason_exact_grant_plus_server_governed_approval_policy"
            if write_enabled
            else None
        ),
        "datto_component_approval_policy": (
            "server_classified_standing_safe_or_per_run"
            if "automation.component.execute" in actions
            else None
        ),
    }












def _capability_metadata(capability: Any) -> dict[str, Any]:
    metadata = dict(capability.metadata or {})

    read_only = (
        str(metadata.get("read_only", "")).strip().lower()
        == "true"
    )
    write_capability = (
        str(metadata.get("write_capability", "")).strip().lower()
        == "true"
    )
    action_enabled = (
        str(metadata.get("mcp_action_enabled", "")).strip().lower()
        == "true"
    )

    return {
        "capability": capability.capability_name,
        "display_name": capability.display_name,
        "lifecycle": capability.lifecycle_status.value,
        "risk": capability.risk_level.value,
        "read_only": read_only,
        "write_capability": write_capability,
        "action_enabled": action_enabled,
        "classification": (
            "read"
            if read_only
            else "action"
            if write_capability
            else "operation"
        ),
        "resource_types": [
            value.strip()
            for value in str(
                metadata.get("resource_types", "")
            ).split(",")
            if value.strip()
        ],
        "operation": str(
            metadata.get("operation", "")
        ).strip(),
        "selector_keys": [
            value.strip()
            for value in str(
                metadata.get("selector_keys", "")
            ).split(",")
            if value.strip()
        ],
        "fact_hints": [
            value.strip()
            for value in str(
                metadata.get("fact_hints", "")
            ).split(",")
            if value.strip()
        ],
        "canonical_facts": [
            value.strip()
            for value in str(
                metadata.get("canonical_facts", "")
            ).split(",")
            if value.strip()
        ],
        "input_schema": capability.input_schema_reference,
        "output_schema": capability.output_schema_reference,
        "approval_required": capability.approval.required,
        "tenant_isolation_required": (
            capability.tenant_isolation_required
        ),
        "client_isolation_required": (
            capability.client_isolation_required
        ),
    }


def _discoverable_capabilities() -> list[dict[str, Any]]:
    app = _runtime()

    result = []

    for capability in app.capabilities.list_all():
        projected = _capability_metadata(capability)

        if projected["lifecycle"] != "active":
            continue

        if not projected["resource_types"]:
            continue

        # Reads are discoverable when active. Mutating capabilities require an
        # explicit MCP action activation flag in addition to ACTIVE lifecycle.
        # This prevents a provider/runtime activation from silently exposing a
        # new conversational write surface.
        if (
            not projected["read_only"]
            and not projected["action_enabled"]
        ):
            continue

        result.append(projected)

    return sorted(
        result,
        key=lambda item: item["capability"],
    )


def _active_action_capabilities() -> list[str]:
    return sorted(
        item["capability"]
        for item in _discoverable_capabilities()
        if (
            item["read_only"] is False
            and item["action_enabled"] is True
        )
    )


def _annotate_requester_eligibility(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Add bounded requester-specific authority eligibility to discovery."""

    app = _runtime()

    (
        principal,
        organization,
        assurance,
        client_id,
    ) = _authenticated_identity()

    def annotate(
        item: Mapping[str, Any],
    ) -> dict[str, Any]:
        projected = dict(item)

        requested_mode = (
            PermissionMode.OBSERVE
            if projected.get("read_only") is True
            else PermissionMode.EXECUTE
        )

        decision = app.identity_authority.evaluate(
            AuthorityRequest(
                request_id=(
                    f"discover_{uuid4().hex}"
                ),
                correlation_id=(
                    f"corr_discover_{uuid4().hex}"
                ),
                principal_id=principal,
                organization_id=organization,
                client_id=client_id,
                capability=str(
                    projected.get("capability")
                    or ""
                ),
                requested_mode=requested_mode,
                authentication_assurance=assurance,
            )
        )

        projected["permission_mode"] = (
            requested_mode.value
        )

        projected["authority_outcome"] = (
            decision.outcome.value
        )

        projected["potentially_eligible"] = (
            decision.outcome
            in {
                AuthorityOutcome.ALLOWED,
                AuthorityOutcome.APPROVAL_REQUIRED,
            }
        )

        return projected

    output = dict(result)

    capabilities = output.get("capabilities")

    if isinstance(capabilities, list):
        output["capabilities"] = [
            annotate(item)
            for item in capabilities
            if isinstance(item, Mapping)
        ]

    alternatives = output.get("alternatives")

    if isinstance(alternatives, list):
        output["alternatives"] = [
            annotate(item)
            for item in alternatives
            if isinstance(item, Mapping)
        ]

    return output


def _dynamic_capability_allowed(
    capability_name: str,
) -> bool:
    target = str(capability_name).strip()

    return any(
        item["capability"] == target
        for item in _discoverable_capabilities()
    )


def _dynamic_read_capability_allowed(
    capability_name: str,
) -> bool:
    target = str(capability_name).strip()

    return any(
        item["capability"] == target
        and item["read_only"] is True
        for item in _discoverable_capabilities()
    )


def _discoverable_capability(
    capability_name: str,
) -> dict[str, Any] | None:
    target = str(capability_name).strip()

    for item in _discoverable_capabilities():
        if item["capability"] == target:
            return item

    return None



def _strip_dynamic_navigation(
    value: Any,
) -> Any:
    """Remove provider navigation/transport URLs from model evidence."""

    if isinstance(value, Mapping):
        clean = {}

        for key, item in value.items():
            normalized = str(key).casefold()

            if (
                normalized.endswith("url")
                or normalized in {
                    "href",
                    "link",
                    "links",
                }
            ):
                continue

            clean[str(key)] = (
                _strip_dynamic_navigation(item)
            )

        return clean

    if isinstance(value, (list, tuple)):
        return [
            _strip_dynamic_navigation(item)
            for item in value[:100]
        ]

    return value


def _project_dynamic_evidence(
    capability_name: str,
    output: Mapping[str, Any],
) -> Any:
    """Bound evidence without assuming a technician question.

    Existing normalized provider results are preferred. Provider-wide discovery
    pages are never projected through the generic MCP interface.
    """

    if capability_name == "endpoint.device.search":
        return _project_endpoint_search(output)

    if capability_name == "endpoint.device.read":
        return _project_endpoint_read(output)

    if capability_name == "endpoint.audit.read":
        return _project_endpoint_audit(output)

    if capability_name == "endpoint.alert.search":
        return _project_endpoint_collection(
            output,
            collection_kind="alerts",
        )

    if capability_name == "endpoint.software.search":
        return _project_endpoint_collection(
            output,
            collection_kind="software",
        )

    data = output.get("data")

    if not isinstance(data, Mapping):
        return _safe(output)

    provider_data = data.get("provider_data")

    if capability_name == "automation.component.search":
        raw_matches = data.get("resource_matches")
        if not isinstance(raw_matches, (list, tuple)):
            raw_matches = []
        projected_matches: list[dict[str, Any]] = []
        for item in raw_matches[:5000]:
            if not isinstance(item, Mapping):
                continue
            projected_matches.append(
                {
                    str(key): _safe(value)
                    for key, value in item.items()
                    if str(key) in {
                        "resource_id",
                        "name",
                        "description",
                        "category",
                        "credentials_required",
                        "variables",
                    }
                }
            )
        return {
            "provider": _safe(output.get("provider")),
            "provider_capability": _safe(output.get("provider_capability")),
            "resource_matches": projected_matches,
            "match_count": len(raw_matches),
            "discovery_complete": data.get("discovery_complete") is True,
            "raw_provider_evidence_exposed": False,
        }

    # Never expose provider-wide raw discovery pages through the dynamic
    # interface. Prefer normalized resource matches when they exist.
    matches = data.get("resource_matches")

    if isinstance(matches, (list, tuple)):
        return {
            "provider": _safe(output.get("provider")),
            "provider_capability": _safe(
                output.get("provider_capability")
            ),
            "resource_matches": _safe(matches),
            "match_count": len(matches),
            "raw_provider_evidence_exposed": False,
        }

    if isinstance(provider_data, Mapping):
        provider_data = dict(provider_data)

        provider_data.pop("pages", None)

        return {
            "provider": _safe(output.get("provider")),
            "provider_capability": _safe(
                output.get("provider_capability")
            ),
            "data": _safe(
                _strip_dynamic_navigation(
                    provider_data
                )
            ),
            "raw_provider_evidence_exposed": False,
        }

    return _safe(output)



def _filter_discoverable_capabilities(
    resource_type: str = "",
    operation: str = "",
    facts: str = "",
) -> dict[str, Any]:
    """Apply strict registry filters and retain safe same-resource alternatives."""

    resource_filter = str(resource_type).strip().casefold()
    operation_filter = str(operation).strip().casefold()

    fact_terms = {
        term.strip().casefold()
        for term in str(facts).replace(",", " ").split()
        if term.strip()
    }

    available = _discoverable_capabilities()
    matches = []

    for item in available:
        if resource_filter:
            resource_types = {
                value.casefold()
                for value in item["resource_types"]
            }

            if resource_filter not in resource_types:
                continue

        if operation_filter:
            if item["operation"].casefold() != operation_filter:
                continue

        if fact_terms:
            phrases = [
                value.casefold()
                for value in (
                    item["fact_hints"]
                    + item["canonical_facts"]
                    + [item["display_name"]]
                )
            ]

            tokens = {
                token
                for phrase in phrases
                for token in phrase.replace(
                    "/",
                    " ",
                ).replace(
                    "-",
                    " ",
                ).split()
            }

            if not any(
                term in tokens
                or any(
                    term == phrase
                    for phrase in phrases
                )
                for term in fact_terms
            ):
                continue

        matches.append(item)

    result: dict[str, Any] = {
        "status": "succeeded",
        "capability_count": len(matches),
        "capabilities": matches,
        "source": "jason_live_capability_registry",
        "exact_filter_match": bool(matches),
        "filter_semantics": {
            "resource_type": "exact_when_supplied",
            "operation": "exact_registry_operation_when_supplied",
            "facts": "capability_hint_filter_when_supplied",
        },
    }

    if matches:
        if resource_filter:
            result["resource_capability_available"] = True
        return result

    if not resource_filter:
        return result

    alternatives = []

    for item in available:
        resource_types = {
            value.casefold()
            for value in item["resource_types"]
        }

        if resource_filter in resource_types:
            alternatives.append(item)

    result["resource_capability_available"] = bool(alternatives)
    result["alternative_count"] = len(alternatives)
    result["alternatives"] = alternatives

    if alternatives:
        result["selection_guidance"] = (
            "No exact registry filter match was found, but active governed "
            "capabilities exist for this resource type. Evaluate the "
            "listed alternatives before concluding that the resource cannot "
            "be read. A search operation can be the supported lookup path "
            "for an exact identifier or number."
        )
    else:
        result["selection_guidance"] = (
            "No active governed capability is registered for this "
            "resource type."
        )

    return result


@mcp.tool()
def discover_capabilities(
    resource_type: str = "",
    operation: str = "",
    facts: str = "",
) -> dict[str, Any]:
    """Discover Jason's currently active governed capabilities.

    resource_type, operation, and facts are registry filters. In particular,
    operation is an exact registry operation and must not be inferred directly
    from conversational verbs such as read, get, or show. A request to read a
    known object may be satisfiable through an active search capability.

    When exact filters produce no match, same-resource active governed read
    alternatives are returned when available. Evaluate those alternatives
    before concluding that Jason lacks a capability for the resource.
    """

    return _annotate_requester_eligibility(
        _filter_discoverable_capabilities(
            resource_type=resource_type,
            operation=operation,
            facts=facts,
        )
    )


@mcp.tool()
def execute_read_capability(
    capability: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute one discovered Jason read capability through governance.

    The capability must currently be active, read-only, and present in Jason's
    live capability registry. Jason performs identity/authority evaluation and
    Central Orchestrator execution. Provider credentials are never exposed.

    For automation.job.output.read, use the exact output_read_arguments
    returned by automation.component.execute. Missing job/device/component
    selectors are a request-construction error, not evidence of a Datto or
    provider failure. Correct the selectors and retry the read-only operation;
    never redispatch a component because an output-read request was incomplete.
    """

    capability_name = str(capability).strip()

    if not capability_name:
        return {
            "status": "rejected",
            "error_code": "capability_required",
        }

    if not _dynamic_read_capability_allowed(
        capability_name
    ):
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": (
                "capability_not_active_read_only"
            ),
        }

    read_arguments = dict(arguments or {})

    if capability_name == "automation.job.output.read":
        selector_bundle = read_arguments.get(
            "output_read_arguments"
        )

        if isinstance(selector_bundle, Mapping):
            for key in (
                "resource_id",
                "device_uid",
                "component_uid",
                "stream",
            ):
                if (
                    not read_arguments.get(key)
                    and selector_bundle.get(key)
                ):
                    read_arguments[key] = (
                        selector_bundle.get(key)
                    )

        resource_id = str(
            read_arguments.get("resource_id")
            or read_arguments.get("job_uid")
            or ""
        ).strip()

        device_uid = str(
            read_arguments.get("device_uid")
            or read_arguments.get(
                "target_device_uid"
            )
            or ""
        ).strip()

        component_uid = str(
            read_arguments.get("component_uid")
            or read_arguments.get("component_id")
            or ""
        ).strip()

        stream = str(
            read_arguments.get("stream")
            or "stdout"
        ).strip().casefold()

        missing_arguments = []

        if not resource_id:
            missing_arguments.append(
                "resource_id"
            )

        if not device_uid:
            missing_arguments.append(
                "device_uid"
            )

        if not component_uid:
            missing_arguments.append(
                "component_uid"
            )

        if missing_arguments:
            return {
                "status": "rejected",
                "capability": capability_name,
                "error_code": (
                    "AUTOMATION_JOB_OUTPUT_SELECTORS_REQUIRED"
                ),
                "reason_codes": [
                    "AUTOMATION_JOB_OUTPUT_SELECTORS_REQUIRED",
                ],
                "failure_domain": (
                    "request_construction"
                ),
                "provider_called": False,
                "retryable": True,
                "missing_arguments": (
                    missing_arguments
                ),
                "required_arguments": [
                    "resource_id",
                    "device_uid",
                    "component_uid",
                ],
                "defaulted_arguments": {
                    "stream": "stdout",
                },
                "do_not_redispatch": True,
                "operator_message": (
                    "The output-read request is incomplete. "
                    "This is not evidence of a Datto/provider "
                    "failure. Supply the exact job, device, and "
                    "component selectors and retry this read-only "
                    "operation. Do not rerun the component."
                ),
            }

        if stream not in {
            "stdout",
            "stderr",
            "all",
        }:
            return {
                "status": "rejected",
                "capability": capability_name,
                "error_code": (
                    "AUTOMATION_JOB_OUTPUT_STREAM_INVALID"
                ),
                "reason_codes": [
                    "AUTOMATION_JOB_OUTPUT_STREAM_INVALID",
                ],
                "failure_domain": (
                    "request_construction"
                ),
                "provider_called": False,
                "retryable": True,
                "allowed_streams": [
                    "stdout",
                    "stderr",
                    "all",
                ],
                "do_not_redispatch": True,
            }

        # Only the exact provider-neutral selectors required by the governed
        # Datto read path are forwarded.
        read_arguments = {
            "resource_id": resource_id,
            "device_uid": device_uid,
            "component_uid": component_uid,
            "stream": stream,
        }

    if capability_name == "automation.component.search":
        read_arguments = (
            _canonical_datto_component_search_arguments(
                read_arguments
            )
        )

    if capability_name == "endpoint.security.detection.read":
        correlation_requested = bool(
            str(read_arguments.get("threat_reference") or "").strip()
        )
        supplied_alert_id = str(
            read_arguments.get("alert_id") or ""
        ).strip()
        if supplied_alert_id and not _is_canonical_uuid(supplied_alert_id):
            correlation_requested = True

        if correlation_requested:
            return _governed_datto_threat_correlation_read(
                read_arguments
            )

    result = _governed_read(
        capability_name=capability_name,
        arguments=read_arguments,
    )

    if result.get("status") != "succeeded":
        return result

    evidence = result.get("evidence")

    # Existing _governed_read projections are already safe for known
    # capabilities. For every dynamically discovered capability that does not
    # have a dedicated projection, apply a provider-neutral evidence boundary.
    known_projected = {
        "endpoint.device.search",
        "endpoint.device.read",
        "endpoint.audit.read",
        "endpoint.alert.search",
        "endpoint.software.search",
    }

    if capability_name not in known_projected:
        raw_output = result.pop(
            "_raw_output",
            None,
        )

        if isinstance(raw_output, Mapping):
            result["evidence"] = (
                _project_dynamic_evidence(
                    capability_name,
                    raw_output,
                )
            )
        else:
            # _governed_read currently returns its bounded evidence rather
            # than raw provider output. Re-bound that result here and strip
            # provider-wide page collections defensively.
            if isinstance(evidence, Mapping):
                clean = dict(evidence)

                clean.pop("pages", None)

                nested = clean.get("data")

                if isinstance(nested, Mapping):
                    nested = dict(nested)
                    nested.pop("pages", None)
                    clean["data"] = nested

                provider_data = clean.get(
                    "provider_data"
                )

                if isinstance(
                    provider_data,
                    Mapping,
                ):
                    provider_data = dict(
                        provider_data
                    )

                    provider_data.pop(
                        "pages",
                        None,
                    )

                    clean[
                        "provider_data"
                    ] = provider_data

                result["evidence"] = _safe(
                    _strip_dynamic_navigation(
                        clean
                    )
                )
            else:
                result["evidence"] = _safe(
                    evidence
                )

    return result


@mcp.tool()
def execute_governed_capability(
    capability: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute one active governed Jason capability.

    Reads continue through Jason's governed read path. Mutating actions must be
    ACTIVE in the live capability registry and explicitly MCP-action-enabled.
    Microsoft Entra authenticates the caller; Jason authority, approval policy,
    Central Orchestrator routing, provider isolation, attempt limits and audit
    remain authoritative. For Datto component execution, Jason derives
    approval server-side. The exact reviewed ad-hoc PowerShell component may
    execute a narrowly classified deterministic read-only command under standing
    policy. For a per-run component, the authenticated technician's direct
    imperative to run that exact component on that exact endpoint is itself the
    approval; callers must carry that same-turn instruction as
    arguments.explicit_approval=true. Autonomous selection of a per-run
    component must not set that flag and must stop for technician instruction.
    Classification is never accepted from action arguments.
    """

    capability_name = str(capability).strip()

    if not capability_name:
        return {
            "status": "rejected",
            "error_code": "capability_required",
        }

    execution_arguments = dict(arguments or {})

    # The live MCP contract intentionally exposes only capability + arguments.
    # Carry current conversational approval inside the governed argument
    # envelope so approval does not depend on an out-of-band tool parameter.
    #
    # This reserved value is consumed here and is never forwarded to Datto.
    datto_explicit_approval = False

    if capability_name == "automation.component.execute":
        datto_explicit_approval = (
            execution_arguments.pop(
                "explicit_approval",
                False,
            )
            is True
        )

    projected = _discoverable_capability(
        capability_name
    )

    if projected is None:
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": "capability_not_active_or_exposed",
        }

    if projected["read_only"]:
        return execute_read_capability(
            capability=capability_name,
            arguments=execution_arguments,
        )

    if not projected["action_enabled"]:
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": "capability_not_mcp_action_enabled",
        }

    return _governed_execute(
        capability_name=capability_name,
        arguments=execution_arguments,
        explicit_approval=datto_explicit_approval,
    )


def _grafana_component_control_identity(request: StarletteRequest) -> tuple[str, str]:
    expected = os.environ.get(
        "JASON_GRAFANA_COMPONENT_CONTROL_TOKEN",
        "",
    ).strip()
    if not expected:
        token_file = os.environ.get(
            "JASON_GRAFANA_COMPONENT_CONTROL_TOKEN_FILE",
            "",
        ).strip()
        if token_file:
            try:
                expected = Path(token_file).read_text(encoding="utf-8").strip()
            except OSError:
                expected = ""
    principal = os.environ.get(
        "JASON_GRAFANA_COMPONENT_CONTROL_PRINCIPAL_ID",
        "",
    ).strip()
    organization = os.environ.get(
        "JASON_GRAFANA_COMPONENT_CONTROL_ORGANIZATION_ID",
        "",
    ).strip()
    if not expected or not principal or not organization:
        raise PermissionError("GRAFANA_COMPONENT_CONTROL_NOT_CONFIGURED")

    auth = str(request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        raise PermissionError("GRAFANA_COMPONENT_CONTROL_AUTH_REQUIRED")
    supplied = auth.split(" ", 1)[1].strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise PermissionError("GRAFANA_COMPONENT_CONTROL_AUTH_INVALID")

    owners = approval_owner_identities()
    if principal not in owners:
        raise PermissionError("DATTO_COMPONENT_APPROVAL_OWNER_REQUIRED")
    return principal, organization


def _component_control_catalog(
    *,
    principal: str,
    organization: str,
) -> list[dict[str, Any]]:
    result = _governed_read_for_identity(
        principal=principal,
        organization=organization,
        assurance="grafana-component-control-token",
        client_id=None,
        capability_name="automation.component.search",
        arguments={},
    )
    if result.get("status") != "succeeded":
        raise RuntimeError("DATTO_COMPONENT_CATALOG_LOOKUP_FAILED")
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        raise RuntimeError("DATTO_COMPONENT_CATALOG_LOOKUP_FAILED")
    matches = evidence.get("resource_matches")
    if not isinstance(matches, list):
        raise RuntimeError("DATTO_COMPONENT_CATALOG_LOOKUP_FAILED")

    configured = configured_datto_components()
    configured_by_uid = {item.uid: item for item in configured}
    configured_by_name = {item.name.casefold(): item for item in configured}
    latest = {
        (item.uid, item.name.casefold()): item
        for item in list_component_approval_records()
    }

    rows: list[dict[str, Any]] = []
    for raw in matches:
        if not isinstance(raw, Mapping):
            continue
        uid = str(raw.get("resource_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not uid or not name:
            continue
        selected = configured_by_uid.get(uid) or configured_by_name.get(name.casefold())
        approval_mode = selected.approval_mode if selected else "per_run"
        approval_source = selected.approval_source if selected else "unclassified"
        blocked = _component_unsupervised_block_reason(raw)
        fingerprint = component_metadata_fingerprint(raw)
        stale = False
        history = latest.get((uid, name.casefold()))
        if (
            selected is not None
            and selected.approval_source == "durable_registry"
            and selected.metadata_fingerprint
            and selected.metadata_fingerprint != fingerprint
        ):
            stale = True
            approval_mode = "per_run"
            approval_source = "durable_registry_stale"
        rows.append({
            "uid": uid,
            "name": name,
            "description": str(raw.get("description") or ""),
            "category": str(raw.get("category") or ""),
            "metadata_fingerprint": fingerprint,
            "run_autonomously": approval_mode == "standing_safe" and not stale,
            "approval_mode": approval_mode,
            "approval_source": approval_source,
            "eligible": blocked is None,
            "blocked_reason": blocked,
            "approved_by": getattr(history, "approved_by", None),
            "approved_at": getattr(history, "approved_at", None),
            "revoked_by": getattr(history, "revoked_by", None),
            "revoked_at": getattr(history, "revoked_at", None),
            "metadata_stale": stale,
        })
    rows.sort(key=lambda item: item["name"].casefold())
    return rows


async def grafana_component_control_components(request: StarletteRequest):
    try:
        principal, organization = _grafana_component_control_identity(request)
        rows = await asyncio.to_thread(
            _component_control_catalog,
            principal=principal,
            organization=organization,
        )
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except Exception:
        return JSONResponse({"error": "component_catalog_unavailable"}, status_code=502)
    return JSONResponse({
        "status": "ok",
        "component_count": len(rows),
        "components": rows,
        "autonomous_names": [
            item["name"] for item in rows if item["run_autonomously"]
        ],
        "eligible_names": [
            item["name"] for item in rows if item["eligible"]
        ],
    })


async def grafana_component_control_bulk(request: StarletteRequest):
    try:
        principal, organization = _grafana_component_control_identity(request)
        body = await request.json()
        if not isinstance(body, Mapping):
            raise ValueError("COMPONENT_CONTROL_PAYLOAD_INVALID")
        approve_names = _component_bulk_names(
            body.get("approve_names") or [],
            allow_empty=True,
        )
        revoke_names = _component_bulk_names(
            body.get("revoke_names") or [],
            allow_empty=True,
        )
        if not approve_names and not revoke_names:
            raise ValueError("DATTO_COMPONENT_BULK_SELECTION_EMPTY")
        overlap = set(x.casefold() for x in approve_names) & set(x.casefold() for x in revoke_names)
        if overlap:
            raise ValueError("COMPONENT_CONTROL_SELECTION_CONFLICT")
        reason = str(body.get("reason") or "Grafana Component Control").strip()[:500]
        rows = await asyncio.to_thread(
            _component_control_catalog,
            principal=principal,
            organization=organization,
        )
        by_name = {item["name"].casefold(): item for item in rows}
        approved = []
        revoked = []
        ineligible = []
        failed = []
        for name in approve_names:
            row = by_name.get(name.casefold())
            if row is None:
                failed.append({"name": name, "reason": "COMPONENT_NOT_FOUND"})
                continue
            if not row["eligible"]:
                ineligible.append({"name": name, "reason": row["blocked_reason"]})
                continue
            try:
                live = next(
                    item for item in rows
                    if item["name"].casefold() == name.casefold()
                )
                record = persist_component_approval(
                    uid=live["uid"],
                    name=live["name"],
                    approved_by=principal,
                    metadata_fingerprint=str(
                        live["metadata_fingerprint"]
                    ),
                    reason=reason,
                )
                approved.append({"uid": record.uid, "name": record.name})
            except Exception as exc:
                failed.append({"name": name, "reason": str(exc)})
        for name in revoke_names:
            row = by_name.get(name.casefold())
            if row is None:
                failed.append({"name": name, "reason": "COMPONENT_NOT_FOUND"})
                continue
            try:
                record = persist_component_revocation(
                    uid=row["uid"],
                    name=row["name"],
                    revoked_by=principal,
                    reason=reason,
                )
                revoked.append({"uid": record.uid, "name": record.name})
            except Exception as exc:
                failed.append({"name": name, "reason": str(exc)})
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "component_control_failed"}, status_code=500)
    return JSONResponse({
        "status": "ok" if not failed else "partial",
        "approved_count": len(approved),
        "revoked_count": len(revoked),
        "ineligible_count": len(ineligible),
        "failed_count": len(failed),
        "approved": approved,
        "revoked": revoked,
        "ineligible": ineligible,
        "failed": failed,
    })


async def healthz(_request):
    actions = _active_action_capabilities()

    return JSONResponse(
        {
            "status": "ok",
            "service": "jason-mcp",
            "mode": (
                "governed-read-plus-actions"
                if actions
                else "read-only"
            ),
            "write_tools_enabled": bool(actions),
            "write_capabilities": actions,
            "mcp_path": "/mcp",
        }
    )


async def oauth_authorization_server_metadata(_request):
    return JSONResponse(
        {
            "issuer": JASON_OAUTH_ISSUER_URL,
            "authorization_endpoint": (
                "https://login.microsoftonline.com/"
                f"{JASON_ENTRA_TENANT_ID}/oauth2/v2.0/authorize"
            ),
            "token_endpoint": (
                "https://login.microsoftonline.com/"
                f"{JASON_ENTRA_TENANT_ID}/oauth2/v2.0/token"
            ),
            "jwks_uri": JASON_ENTRA_JWKS_URL,
            "response_types_supported": [
                "code"
            ],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
            ],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
                "private_key_jwt",
            ],
            "code_challenge_methods_supported": [
                "S256"
            ],
            "scopes_supported": [
                JASON_OAUTH_REQUEST_SCOPE,
                "openid",
                "profile",
                "email",
                "offline_access",
            ],
        },
        headers={
            "Cache-Control": "public, max-age=300"
        },
    )


def _fetch_entra_oidc_metadata() -> dict[str, object]:
    request = Request(
        JASON_ENTRA_OIDC_CONFIGURATION_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "Jason-MCP-OIDC-Compatibility/1.0",
        },
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(
            response.read().decode("utf-8")
        )

    if not isinstance(payload, dict):
        raise ValueError("OIDC metadata was not an object")

    if str(payload.get("issuer") or "").rstrip("/") != (
        JASON_ENTRA_ISSUER.rstrip("/")
    ):
        raise ValueError("OIDC issuer mismatch")

    payload["code_challenge_methods_supported"] = ["S256"]

    return payload


async def entra_oidc_configuration(_request):
    try:
        metadata = await asyncio.to_thread(
            _fetch_entra_oidc_metadata
        )
    except Exception:
        return JSONResponse(
            {"error": "oidc_metadata_unavailable"},
            status_code=502,
        )

    return JSONResponse(
        metadata,
        headers={
            "Cache-Control": "public, max-age=300"
        },
    )


transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "mcp-jason.teamaot.com",
        "mcp-jason.teamaot.com:*",
    ],
    allowed_origins=[
        "https://chatgpt.com",
        "https://chatgpt.com:*",
        "https://mcp-jason.teamaot.com",
        "https://mcp-jason.teamaot.com:*",
    ],
)


class JasonMcpOuterTransportGuard:
    """Enforce MCP Host/Origin policy before authentication.

    MCP 2.2.0 places RequireAuthMiddleware outside its transport
    validator. This outer ASGI middleware reuses the SDK validator
    for Host/Origin checks before authentication while leaving
    Content-Type validation to the normal MCP transport path.
    """

    def __init__(
        self,
        app,
        settings: TransportSecuritySettings,
    ) -> None:
        self.app = app
        self.validator = TransportSecurityMiddleware(
            settings
        )

    async def __call__(
        self,
        scope,
        receive,
        send,
    ) -> None:
        if (
            scope.get("type") == "http"
            and str(scope.get("path") or "")
            in {"/mcp", "/mcp/"}
        ):
            request = StarletteRequest(scope)

            rejection = (
                await self.validator.validate_request(
                    request,
                    is_post=False,
                )
            )

            if rejection is not None:
                await rejection(
                    scope,
                    receive,
                    send,
                )
                return

        await self.app(
            scope,
            receive,
            send,
        )


app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    transport_security=transport_security,
)

app.add_route(
    "/healthz",
    healthz,
    methods=["GET"],
)

app.add_route(
    "/component-control/components",
    grafana_component_control_components,
    methods=["GET"],
)

app.add_route(
    "/component-control/bulk",
    grafana_component_control_bulk,
    methods=["POST"],
)

app.add_route(
    "/oauth/entra-openid-configuration",
    entra_oidc_configuration,
    methods=["GET"],
)

app.add_route(
    "/.well-known/oauth-authorization-server",
    oauth_authorization_server_metadata,
    methods=["GET"],
)

app.add_middleware(
    JasonMcpOuterTransportGuard,
    settings=transport_security,
)


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
