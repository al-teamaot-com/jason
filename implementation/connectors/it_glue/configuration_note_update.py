"""Source-only, exact-plan IT Glue configuration notes update adapter.

Not registered or enabled by the runtime. It intentionally requires a separate
write credential, an independently verified client -> IT Glue organization
mapping, and a positive requester-authorization verifier. It cannot use the
existing IT Glue read-only credential or bypass the Central Orchestrator.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from connectors.core.contracts import (
    AuditSink, ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
    ConnectorResult, HttpTransport, SecretResolver,
)
from orchestrator.connector_invoker import ProviderPreparedExecution
from orchestrator.execution_plan import normalize_provider_relative_path


CAPABILITY = "it_glue.configuration.update"
WRITE_SECRET = "it_glue.readwrite"
PROFILE_ENV = "JASON_IT_GLUE_ROUTINE_RW_PROFILE"
PROFILE_VALUE = "configuration-notes-v1"
BASE_URL = "https://api.itglue.com"
_MAX_NOTES = 8000


class TrustedItGlueWriteAuthority(Protocol):
    """Must validate the authenticated Jason principal and exact client scope."""
    def require_authorized(self, context: ConnectorContext) -> None: ...
    def organization_id_for_client(self, *, client_id: str) -> int: ...


def _positive_id(value: Any, label: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError(f"IT_GLUE_{label}_INVALID")
    return int(value)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _profile_enabled() -> bool:
    return os.getenv(PROFILE_ENV, "").strip().casefold() == PROFILE_VALUE


@dataclass(frozen=True, slots=True)
class _PreparedNote:
    context: ConnectorContext
    configuration_id: int
    organization_id: int
    initial_notes_hash: str
    initial_updated_at: str
    desired_notes: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class ItGlueConfigurationNoteUpdateConnector:
    transport: HttpTransport
    credentials: SecretResolver
    authorization: TrustedItGlueWriteAuthority
    audit: AuditSink

    provider_name = "it_glue"
    capabilities = frozenset({CAPABILITY})

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        # No caller can bypass the J-102 prepare/fingerprint/execute contract.
        raise ConnectorAuthorizationError("IT_GLUE_GOVERNED_PLAN_REQUIRED")

    def _assert_request(self, request: ConnectorRequest) -> tuple[int, int, str]:
        if not _profile_enabled():
            raise PermissionError("IT_GLUE_ROUTINE_RW_DISABLED")
        ctx = request.context
        if (ctx.capability != CAPABILITY or ctx.mode != "execute"
                or ctx.organization_id != "aot" or not ctx.client_id):
            raise ConnectorAuthorizationError("IT_GLUE_EXACT_CLIENT_EXECUTE_SCOPE_REQUIRED")
        self.authorization.require_authorized(ctx)
        raw = request.arguments
        if set(raw) != {"configuration_id", "notes"}:
            raise ValueError("IT_GLUE_NOTES_ONLY_UPDATE_REQUIRED")
        config_id = _positive_id(raw.get("configuration_id"), "CONFIGURATION_ID")
        notes = raw.get("notes")
        if (not isinstance(notes, str) or not notes.strip()
                or len(notes) > _MAX_NOTES):
            raise ValueError("IT_GLUE_NOTES_INVALID")
        org_id = _positive_id(
            self.authorization.organization_id_for_client(client_id=ctx.client_id),
            "ORGANIZATION_ID",
        )
        return config_id, org_id, notes

    def _headers(self, ctx: ConnectorContext) -> Mapping[str, str]:
        creds = self.credentials.resolve(WRITE_SECRET, ctx)
        key = creds.get("api_key")
        if not isinstance(key, str) or not key.strip():
            raise PermissionError("IT_GLUE_RW_CREDENTIAL_UNAVAILABLE")
        return {
            "x-api-key": key,
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }

    def _read(self, config_id: int, org_id: int, headers: Mapping[str, str]) -> tuple[str, str]:
        response = self.transport.request(
            method="GET",
            url=f"{BASE_URL}/configurations/{config_id}",
            headers=headers,
            params=None, json=None, timeout_seconds=20.0,
        )
        resource = response.get("data") if isinstance(response, Mapping) else None
        if not isinstance(resource, Mapping):
            raise ConnectorAuthorizationError("IT_GLUE_CONFIGURATION_READ_INVALID")
        attributes = resource.get("attributes")
        if (resource.get("type") != "configurations"
                or str(resource.get("id")) != str(config_id)
                or not isinstance(attributes, Mapping)):
            raise ConnectorAuthorizationError("IT_GLUE_CONFIGURATION_IDENTITY_MISMATCH")
        try:
            observed_org = _positive_id(attributes.get("organization-id"), "ORGANIZATION_ID")
        except ValueError as error:
            raise ConnectorAuthorizationError("IT_GLUE_CONFIGURATION_ORGANIZATION_UNKNOWN") from error
        if observed_org != org_id:
            raise ConnectorAuthorizationError("IT_GLUE_CROSS_CLIENT_CONFIGURATION_DENIED")
        # Restricted records need separate positive per-object access evidence.
        if attributes.get("restricted") is not False:
            raise ConnectorAuthorizationError("IT_GLUE_RESTRICTED_CONFIGURATION_UNPROVEN")
        if "notes" not in attributes:
            raise ConnectorAuthorizationError("IT_GLUE_CONFIGURATION_NOTES_NOT_RETURNED")
        current = attributes["notes"]
        if current is not None and not isinstance(current, str):
            raise ConnectorAuthorizationError("IT_GLUE_CONFIGURATION_NOTES_INVALID")
        updated_at = attributes.get("updated-at")
        if not isinstance(updated_at, str) or not updated_at.strip():
            raise ConnectorAuthorizationError("IT_GLUE_CONFIGURATION_REVISION_UNAVAILABLE")
        return (current or ""), updated_at

    def prepare_governed_execution(self, request: ConnectorRequest) -> ProviderPreparedExecution:
        config_id, org_id, notes = self._assert_request(request)
        headers = self._headers(request.context)
        original, updated_at = self._read(config_id, org_id, headers)
        # Only a digest enters centrally stored plan material, never raw notes.
        # The exact text and credential remain in opaque provider-private state.
        return ProviderPreparedExecution(
            provider_capability=CAPABILITY, action_method="PATCH",
            resource_type="documentation_configuration",
            resource_identifier=str(config_id),
            normalized_path=f"/configurations/{config_id}",
            payload={
                "type": "configurations",
                "attributes": {
                    "notes_sha256": _digest(notes),
                    "notes_length": len(notes),
                },
                "source_notes_sha256": _digest(original),
                "source_updated_at": updated_at,
            },
            parameters={"organization_id": org_id},
            opaque=_PreparedNote(
                context=request.context,
                configuration_id=config_id,
                organization_id=org_id,
                initial_notes_hash=_digest(original),
                initial_updated_at=updated_at,
                desired_notes=notes,
                headers=headers,
            ),
        )

    def execute_governed_execution(self, prepared: ProviderPreparedExecution) -> ConnectorResult:
        opaque = prepared.opaque
        if not isinstance(opaque, _PreparedNote) or not _profile_enabled():
            raise PermissionError("IT_GLUE_PREPARED_NOTE_INVALID_OR_DISABLED")
        ctx = opaque.context
        if (ctx.capability != CAPABILITY or ctx.mode != "execute"
                or ctx.organization_id != "aot" or not ctx.client_id):
            raise ConnectorAuthorizationError("IT_GLUE_PREPARED_SCOPE_INVALID")
        self.authorization.require_authorized(ctx)
        expected_org = _positive_id(
            self.authorization.organization_id_for_client(client_id=ctx.client_id),
            "ORGANIZATION_ID",
        )
        if expected_org != opaque.organization_id:
            raise ConnectorAuthorizationError("IT_GLUE_CLIENT_BOUNDARY_CHANGED")
        expected_plan = {
            "type": "configurations",
            "attributes": {
                "notes_sha256": _digest(opaque.desired_notes),
                "notes_length": len(opaque.desired_notes),
            },
            "source_notes_sha256": opaque.initial_notes_hash,
            "source_updated_at": opaque.initial_updated_at,
        }
        expected_path = f"/configurations/{opaque.configuration_id}"
        if (prepared.provider_capability != CAPABILITY
                or prepared.action_method != "PATCH"
                or prepared.resource_type != "documentation_configuration"
                or prepared.resource_identifier != str(opaque.configuration_id)
                or normalize_provider_relative_path(prepared.normalized_path)
                    != normalize_provider_relative_path(expected_path)
                or dict(prepared.payload) != expected_plan
                or dict(prepared.parameters) != {"organization_id": expected_org}):
            raise ConnectorAuthorizationError("IT_GLUE_APPROVED_PLAN_MISMATCH")
        latest, updated_at = self._read(
            opaque.configuration_id, expected_org, opaque.headers,
        )
        performed = False
        if latest != opaque.desired_notes:
            if (_digest(latest) != opaque.initial_notes_hash
                    or updated_at != opaque.initial_updated_at):
                raise ConnectorAuthorizationError("IT_GLUE_STALE_CONFIGURATION_PREIMAGE")
            # Exactly one PATCH. No retry after ambiguous write outcome.
            self.audit.record("connector.mutation.requested", ctx, {
                "provider": self.provider_name, "configuration_id": opaque.configuration_id,
                "organization_id": expected_org,
            })
            self.transport.request(
                method="PATCH", url=f"{BASE_URL}{expected_path}",
                headers=opaque.headers, params=None,
                json={"data": {"type": "configurations",
                               "attributes": {"notes": opaque.desired_notes}}},
                timeout_seconds=20.0,
            )
            performed = True
        verified_notes, _ = self._read(
            opaque.configuration_id, expected_org, opaque.headers,
        )
        if verified_notes != opaque.desired_notes:
            self.audit.record("connector.mutation.verification_failed", ctx, {
                "provider": self.provider_name,
                "configuration_id": opaque.configuration_id,
            })
            raise RuntimeError("IT_GLUE_CONFIGURATION_NOTES_READBACK_FAILED")
        self.audit.record("connector.mutation.verified", ctx, {
            "provider": self.provider_name,
            "configuration_id": opaque.configuration_id,
            "mutation_performed": performed,
        })
        return ConnectorResult(
            capability=CAPABILITY, provider=self.provider_name,
            data={"configuration_id": opaque.configuration_id,
                  "organization_id": expected_org,
                  "mutation_performed": performed,
                  "jasonVerification": {"readbackVerified": True,
                                        "verifiedFields": ["notes"]}},
            evidence_ids=(f"it_glue:configuration:{opaque.configuration_id}",),
        )
