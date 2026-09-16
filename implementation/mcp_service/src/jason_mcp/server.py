from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Any, Mapping
from urllib.request import Request, urlopen
from uuid import uuid4

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
from pydantic import AnyHttpUrl
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from jason_runtime.autotask_internal_note import (
    SERVICE_TICKET_NOTE_CREATE,
    autotask_internal_note_mcp_surface_enabled,
)
from jason_runtime.composition import RuntimeSettings, build_runtime_application
from jason_runtime.datto_component_scope import (
    configured_datto_components,
    resolve_datto_component,
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

    return {
        "provider": _safe(output.get("provider")),
        "provider_capability": _safe(
            output.get("provider_capability")
        ),
        "resource_matches": matches,
        "match_count": len(matches),
        "search": {
            "discovery_mode": _safe(
                provider_data.get("discovery_mode")
            ),
            "hostname_reference": _safe(
                provider_data.get("hostname_reference")
            ),
            "provider_pages_examined": len(pages),
            "provider_total_count": total_count,
            "match_output_bounded": len(raw_matches) > 100,
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


def _governed_read(
    *,
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    app = _runtime()
    (
        principal,
        organization,
        assurance,
        client_id,
    ) = _authenticated_identity()

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
                            else _safe(dict(result.output))
                        )
                    )
                )
            )
        ),
    }


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

        if job_uid:
            result["job_uid"] = _safe(job_uid)

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


def _resolve_live_datto_component_name(
    component_name: object,
) -> tuple[str, str]:
    """Resolve one exact component name through governed live catalog discovery."""

    requested_name = str(
        component_name or ""
    ).strip()

    if not requested_name:
        raise ValueError(
            "DATTO_COMPONENT_NAME_REQUIRED"
        )

    lookup = _governed_read(
        capability_name="automation.component.search",
        arguments=_canonical_datto_component_search_arguments(
            {
                "name": requested_name,
            }
        ),
    )

    if lookup.get("status") != "succeeded":
        raise ValueError(
            "DATTO_COMPONENT_CATALOG_LOOKUP_FAILED"
        )

    evidence = lookup.get("evidence")

    if not isinstance(evidence, Mapping):
        raise ValueError(
            "DATTO_COMPONENT_CATALOG_LOOKUP_FAILED"
        )

    data = evidence.get("data")

    if not isinstance(data, Mapping):
        raise ValueError(
            "DATTO_COMPONENT_CATALOG_LOOKUP_FAILED"
        )

    if data.get("discovery_complete") is not True:
        raise ValueError(
            "DATTO_COMPONENT_CATALOG_DISCOVERY_INCOMPLETE"
        )

    matches = data.get("resource_matches")

    if not isinstance(matches, (list, tuple)):
        raise ValueError(
            "DATTO_COMPONENT_CATALOG_LOOKUP_FAILED"
        )

    exact: list[tuple[str, str]] = []

    for item in matches:
        if not isinstance(item, Mapping):
            continue

        live_name = str(
            item.get("name") or ""
        ).strip()

        if (
            live_name.casefold()
            != requested_name.casefold()
        ):
            continue

        live_uid = str(
            item.get("resource_id") or ""
        ).strip()

        if not live_uid:
            raise ValueError(
                "DATTO_COMPONENT_IDENTITY_MISMATCH"
            )

        exact.append(
            (
                live_uid,
                live_name,
            )
        )

    if not exact:
        raise ValueError(
            "DATTO_COMPONENT_NAME_MISMATCH"
        )

    unique = {
        (
            uid,
            name.casefold(),
        )
        for uid, name in exact
    }

    if len(unique) != 1:
        raise ValueError(
            "DATTO_COMPONENT_CATALOG_AMBIGUOUS"
        )

    return exact[0]



def _canonicalize_governed_action_arguments(
    capability_name: str,
    arguments: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Canonicalize server-controlled action arguments before approval/execution.

    ChatGPT may express the same governed action with slightly different
    argument shapes. Provider containment must not depend on the model
    remembering internal allowlist/profile fields.

    For bounded Datto component execution, Jason supplies its own
    server-controlled allowlist, endpoint and device class. The caller must
    still identify the exact target and component. Component identity is
    resolved against an exact server-controlled UID/name pair set before the
    request can enter approval or provider execution.
    """

    raw = dict(arguments or {})

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

    if requested_device != expected["device_uid"]:
        raise ValueError(
            "DATTO_COMPONENT_TARGET_NOT_APPROVED"
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

    supplied_class = str(
        raw.get("device_class") or ""
    ).strip()

    if (
        supplied_class
        and supplied_class.casefold()
        != expected["device_class"].casefold()
    ):
        raise ValueError(
            "DATTO_COMPONENT_TARGET_CLASS_NOT_APPROVED"
        )

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

        if (
            supplied_component_uid
            and supplied_component_uid
            != live_component_uid
        ):
            raise ValueError(
                "DATTO_COMPONENT_IDENTITY_MISMATCH"
            )

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
        "device_uid": expected["device_uid"],
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

    if capability_name == "automation.component.execute":
        try:
            selected_component = resolve_datto_component(
                configured_datto_components(),
                component_uid=canonical_arguments.get("component_uid"),
                component_name=canonical_arguments.get("component_name"),
            )
        except ValueError as exc:
            return {
                "status": "rejected",
                "capability": capability_name,
                "error_code": "invalid_action_arguments",
                "reason_codes": [str(exc)],
            }

        datto_approval_mode = selected_component.approval_mode

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
                approval_decided_by = "policy:datto-standing-safe"
            elif datto_approval_mode == "per_run":
                imperative_approval = explicit_approval is True

                if not imperative_approval:
                    return {
                        "status": "approval_required",
                        "capability": capability_name,
                        "reason_codes": [
                            "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED",
                            *list(decision.reason_codes),
                        ],
                        "correlation_id": correlation_id,
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

    if capability_name == "automation.component.search":
        read_arguments = (
            _canonical_datto_component_search_arguments(
                read_arguments
            )
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
    explicit_approval: bool = False,
) -> dict[str, Any]:
    """Execute one active governed Jason capability.

    Reads continue through Jason's governed read path. Mutating actions must be
    ACTIVE in the live capability registry and explicitly MCP-action-enabled.
    Microsoft Entra authenticates the caller; Jason authority, approval policy,
    Central Orchestrator routing, provider isolation, attempt limits and audit
    remain authoritative. For server-classified Datto per_run components,
    explicit_approval must be true only after the authenticated technician has
    explicitly approved that exact execution. standing_safe classification is
    server-controlled and never accepted from action arguments.
    """

    capability_name = str(capability).strip()

    if not capability_name:
        return {
            "status": "rejected",
            "error_code": "capability_required",
        }

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
            arguments=dict(arguments or {}),
        )

    if not projected["action_enabled"]:
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": "capability_not_mcp_action_enabled",
        }

    return _governed_execute(
        capability_name=capability_name,
        arguments=dict(arguments or {}),
        explicit_approval=(explicit_approval is True),
    )


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
