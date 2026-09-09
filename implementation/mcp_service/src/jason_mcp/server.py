from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from functools import lru_cache
from typing import Any, Mapping
from urllib.request import Request, urlopen
from uuid import uuid4

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    AuthorityOutcome,
    AuthorityRequest,
    PermissionMode,
)
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from pydantic import AnyHttpUrl
from starlette.responses import JSONResponse

from jason_runtime.composition import RuntimeSettings, build_runtime_application


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


mcp = MCPServer(
    "Jason",
    instructions=(
        "Project Jason governed operational interface. "
        "This interface is read-only. "
        "Microsoft Entra authenticates the caller. "
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


@mcp.tool()
def jason_mcp_status() -> dict[str, object]:
    """Return Jason MCP pilot state."""
    return {
        "status": "ok",
        "service": "jason-mcp",
        "mode": "read-only",
        "phase": "governed-read-pilot",
        "governed_execution": "central-orchestrator",
        "direct_provider_access": False,
        "write_tools_enabled": False,
    }












def _capability_metadata(capability: Any) -> dict[str, Any]:
    metadata = dict(capability.metadata or {})

    return {
        "capability": capability.capability_name,
        "display_name": capability.display_name,
        "lifecycle": capability.lifecycle_status.value,
        "risk": capability.risk_level.value,
        "read_only": (
            str(metadata.get("read_only", "")).strip().lower()
            == "true"
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

        if not projected["read_only"]:
            continue

        if not projected["resource_types"]:
            continue

        result.append(projected)

    return sorted(
        result,
        key=lambda item: item["capability"],
    )


def _dynamic_capability_allowed(
    capability_name: str,
) -> bool:
    target = str(capability_name).strip()

    return any(
        item["capability"] == target
        for item in _discoverable_capabilities()
    )



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



@mcp.tool()
def discover_capabilities(
    resource_type: str = "",
    operation: str = "",
    facts: str = "",
) -> dict[str, Any]:
    """Discover Jason's currently active governed read capabilities.

    Use this before choosing an operation when the available resource,
    provider, facts, or environment may have changed. Results come from
    Jason's live capability registry rather than a fixed MCP task list.
    """

    resource_filter = str(resource_type).strip().casefold()
    operation_filter = str(operation).strip().casefold()

    fact_terms = {
        term.strip().casefold()
        for term in str(facts).replace(",", " ").split()
        if term.strip()
    }

    matches = []

    for item in _discoverable_capabilities():
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

    return {
        "status": "succeeded",
        "capability_count": len(matches),
        "capabilities": matches,
        "source": "jason_live_capability_registry",
    }


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

    if not _dynamic_capability_allowed(
        capability_name
    ):
        return {
            "status": "rejected",
            "capability": capability_name,
            "error_code": (
                "capability_not_active_read_only"
            ),
        }

    result = _governed_read(
        capability_name=capability_name,
        arguments=dict(arguments or {}),
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


async def healthz(_request):
    return JSONResponse(
        {
            "status": "ok",
            "service": "jason-mcp",
            "mode": "read-only",
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
