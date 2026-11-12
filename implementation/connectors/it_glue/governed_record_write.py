"""Dormant governed IT Glue record creation and metadata/trait updates.

Source-only until a reviewed runtime composition registers it. No direct use of
this connector performs a write: J-102 prepare/bind/execute is mandatory.
Credential, requester ACL and client-to-organization identity are injected
through existing trusted interfaces; no read-only credential fallback exists.
"""
from __future__ import annotations

import hashlib
import json
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

WRITE_SECRET = "it_glue.readwrite"
PROFILE_ENV = "JASON_IT_GLUE_RECORDS_RW_PROFILE"
PROFILE_VALUE = "governed-records-v1"
CAPABILITIES = frozenset({
    "it_glue.flexible_asset.create",
    "it_glue.flexible_asset.update",
    "it_glue.document.create",
    "it_glue.document.update",
    "it_glue.configuration.create",
})
_TYPES = {
    "it_glue.flexible_asset": ("flexible-assets", "flexible_assets"),
    "it_glue.document": ("documents", "documents"),
    "it_glue.configuration": ("configurations", "configurations"),
}
_BASE_URLS = frozenset({
    "https://api.itglue.com",
    "https://api.eu.itglue.com",
    "https://api.au.itglue.com",
})
_BAD_TRAIT_KEY = re.compile(
    r"password|secret|token|credential|api[-_]?key|private[-_]?key|"
    r"passphrase|recovery[-_]?key|mfa[-_]?seed", re.I,
)
_TRAIT_KEY = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
_REQUEST_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_MAX_DOCUMENT_NAME = 200
_MAX_TRAIT_BYTES = 32000


class TrustedItGlueRecordWriteAuthority(Protocol):
    """Positive existing requester authorization and exact client mapping."""
    def require_authorized(self, context: ConnectorContext) -> None: ...
    def organization_id_for_client(self, *, client_id: str) -> int: ...


class DurableCreationClaim(Protocol):
    """Atomic durable no-retry claim; crashes/ambiguous results remain claimed."""
    def claim_once(self, *, key: str, payload_sha256: str) -> bool: ...


def _id(value: Any, label: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("IT_GLUE_" + label + "_INVALID")
    return int(value)


def _sha(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_DOCUMENT_NAME:
        raise ValueError("IT_GLUE_RECORD_NAME_INVALID")
    return value.strip()


def _traits(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not 1 <= len(value) <= 50:
        raise ValueError("IT_GLUE_TRAITS_INVALID")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _TRAIT_KEY.fullmatch(key) or _BAD_TRAIT_KEY.search(key):
            raise ValueError("IT_GLUE_TRAIT_FIELD_DENIED")
        allowed_scalar = type(item) in (str, int, float, bool)
        allowed_list = (isinstance(item, list) and len(item) <= 100
                        and all(type(x) in (str, int, float, bool) for x in item))
        if not (allowed_scalar or allowed_list):
            raise ValueError("IT_GLUE_TRAIT_VALUE_INVALID")
        result[key] = item
    try:
        if len(json.dumps(result, allow_nan=False).encode("utf-8")) > _MAX_TRAIT_BYTES:
            raise ValueError("IT_GLUE_TRAITS_TOO_LARGE")
    except (TypeError, OverflowError) as exc:
        raise ValueError("IT_GLUE_TRAITS_INVALID") from exc
    return result


@dataclass(frozen=True, slots=True)
class _PreparedRecord:
    context: ConnectorContext
    capability: str
    method: str
    relative_path: str
    resource_type: str
    organization_id: int
    resource_id: int | None
    before_sha256: str | None
    before_revision: str | None
    desired_attributes: Mapping[str, Any] = field(repr=False)
    check_attributes: Mapping[str, Any] = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    request_key: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ItGlueGovernedRecordWriter:
    transport: HttpTransport
    credentials: SecretResolver
    authorization: TrustedItGlueRecordWriteAuthority
    audit: AuditSink
    creation_claims: DurableCreationClaim | None = None
    base_url: str = "https://api.itglue.com"

    provider_name = "it_glue"
    capabilities = CAPABILITIES

    def __post_init__(self) -> None:
        if self.base_url not in _BASE_URLS:
            raise ValueError("IT_GLUE_PROVIDER_URL_NOT_ALLOWLISTED")

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        raise ConnectorAuthorizationError("IT_GLUE_J102_PLAN_REQUIRED")

    @staticmethod
    def _profile() -> None:
        if os.getenv(PROFILE_ENV, "").strip() != PROFILE_VALUE:
            raise PermissionError("IT_GLUE_RECORD_WRITES_DISABLED")

    def _scope(self, context: ConnectorContext, capability: str) -> int:
        self._profile()
        if (context.capability != capability or context.mode != "execute"
                or context.organization_id != "aot"
                or not context.client_id or not context.principal_id.strip()):
            raise ConnectorAuthorizationError("IT_GLUE_EXACT_CLIENT_SCOPE_REQUIRED")
        self.authorization.require_authorized(context)
        return _id(
            self.authorization.organization_id_for_client(client_id=context.client_id),
            "ORGANIZATION",
        )

    def _headers(self, context: ConnectorContext) -> Mapping[str, str]:
        key = self.credentials.resolve(WRITE_SECRET, context).get("api_key")
        if not isinstance(key, str) or not key.strip():
            raise PermissionError("IT_GLUE_SEPARATE_WRITE_KEY_UNAVAILABLE")
        return {
            "x-api-key": key,
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }

    def _get(self, path: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
        response = self.transport.request(
            method="GET", url=self.base_url + path, headers=headers,
            params=None, json=None, timeout_seconds=20.0,
        )
        data = response.get("data") if isinstance(response, Mapping) else None
        if not isinstance(data, Mapping):
            raise ConnectorAuthorizationError("IT_GLUE_PROVIDER_READ_INVALID")
        return data

    def _existing(self, path: str, kind: str, resource_id: int,
                  org_id: int, headers: Mapping[str, str]
                  ) -> tuple[Mapping[str, Any], str, str]:
        record = self._get(path, headers)
        attrs = record.get("attributes")
        if (record.get("type") != kind or str(record.get("id")) != str(resource_id)
                or not isinstance(attrs, Mapping)):
            raise ConnectorAuthorizationError("IT_GLUE_RECORD_IDENTITY_MISMATCH")
        try:
            observed_org = _id(attrs.get("organization-id", attrs.get("organization_id")),
                               "ORGANIZATION")
        except ValueError as exc:
            raise ConnectorAuthorizationError("IT_GLUE_ORGANIZATION_UNVERIFIED") from exc
        if observed_org != org_id:
            raise ConnectorAuthorizationError("IT_GLUE_CROSS_CLIENT_WRITE_DENIED")
        if attrs.get("restricted") is not False:
            raise ConnectorAuthorizationError("IT_GLUE_RESTRICTED_OR_UNKNOWN_RECORD")
        revision = attrs.get("updated-at")
        if not isinstance(revision, str) or not revision.strip():
            raise ConnectorAuthorizationError("IT_GLUE_REVISION_UNVERIFIED")
        return attrs, revision, _sha(attrs)

    def _validated_input(self, request: ConnectorRequest, org: int
                         ) -> tuple[str, str, str, int | None, dict[str, Any], str | None]:
        cap, a = request.context.capability, request.arguments
        if cap not in CAPABILITIES:
            raise ValueError("IT_GLUE_CAPABILITY_NOT_SUPPORTED")
        family, verb = cap.rsplit(".", 1)
        kind, route = _TYPES[family]
        if verb == "create":
            if cap == "it_glue.flexible_asset.create":
                required = {"flexible_asset_type_id", "traits", "request_id"}
                attrs = {"organization-id": org,
                         "flexible-asset-type-id": _id(a.get("flexible_asset_type_id"), "TYPE"),
                         "traits": _traits(a.get("traits"))}
            elif cap == "it_glue.document.create":
                required = {"name", "folder_id", "request_id"}
                attrs = {"organization_id": org, "name": _name(a.get("name")),
                         "document_folder_id": _id(a.get("folder_id"), "FOLDER"),
                         "public": False, "is_uploaded": "false"}
            else:
                required = {"name", "configuration_type_id", "request_id"}
                attrs = {"name": _name(a.get("name")),
                         "configuration-type-id": _id(a.get("configuration_type_id"), "TYPE")}
            request_id = a.get("request_id")
            if not isinstance(request_id, str) or not _REQUEST_KEY.fullmatch(request_id):
                raise ValueError("IT_GLUE_CREATE_REQUEST_ID_INVALID")
            path = "/organizations/" + str(org) + "/relationships/" + route
            record_id = None
        else:
            required = {"resource_id", "traits"} if kind == "flexible-assets" else {"resource_id", "name"}
            record_id = _id(a.get("resource_id"), "RECORD")
            attrs = ({"traits": _traits(a.get("traits"))} if kind == "flexible-assets"
                     else {"name": _name(a.get("name"))})
            request_id = None
            path = "/" + route + "/" + str(record_id)
        if set(a) != required:
            raise ValueError("IT_GLUE_RECORD_FIELDS_NOT_APPROVED")
        return verb.upper(), kind, path, record_id, attrs, request_id

    def prepare_governed_execution(self, request: ConnectorRequest) -> ProviderPreparedExecution:
        cap = request.context.capability
        org = self._scope(request.context, cap)
        method, kind, path, resource_id, attrs, request_id = self._validated_input(request, org)
        headers = self._headers(request.context)
        previous_hash: str | None = None
        revision: str | None = None
        if method == "UPDATE":
            before, revision, previous_hash = self._existing(path, kind, resource_id, org, headers)
            if kind == "flexible-assets":
                prior_traits = before.get("traits")
                if not isinstance(prior_traits, Mapping):
                    raise ConnectorAuthorizationError("IT_GLUE_EXISTING_TRAITS_MISSING")
                # IT Glue PATCH replaces the entire traits object. Never send
                # unreviewed existing sensitive traits back in a merged write.
                if any(not isinstance(k, str) or _BAD_TRAIT_KEY.search(k)
                       for k in prior_traits):
                    raise ConnectorAuthorizationError("IT_GLUE_EXISTING_SENSITIVE_TRAITS_DENIED")
                attrs["traits"] = {**prior_traits, **attrs["traits"]}
            http_method = "PATCH"
        else:
            # Confirm the path's organization exists; caller cannot choose an org ID.
            root = self._get("/organizations/" + str(org), headers)
            if root.get("type") != "organizations" or str(root.get("id")) != str(org):
                raise ConnectorAuthorizationError("IT_GLUE_CLIENT_ORGANIZATION_UNVERIFIED")
            if cap == "it_glue.document.create":
                # Folder must be in the same verified client organization.
                folder_id = attrs["document_folder_id"]
                folder = self._get("/document_folders/" + str(folder_id), headers)
                folder_attrs = folder.get("attributes")
                if (str(folder.get("id")) != str(folder_id)
                        or folder.get("type") not in {"document-folders", "document_folders"}
                        or not isinstance(folder_attrs, Mapping)):
                    raise ConnectorAuthorizationError("IT_GLUE_DOCUMENT_FOLDER_UNVERIFIED")
                try:
                    folder_org = _id(folder_attrs.get("organization-id", folder_attrs.get("organization_id")), "FOLDER_ORGANIZATION")
                except ValueError as exc:
                    raise ConnectorAuthorizationError("IT_GLUE_FOLDER_ORGANIZATION_UNVERIFIED") from exc
                if folder_org != org:
                    raise ConnectorAuthorizationError("IT_GLUE_CROSS_CLIENT_DOCUMENT_FOLDER_DENIED")
            http_method = "POST"
        public_plan = {
            "type": kind,
            "attributes_sha256": _sha(attrs),
            "attribute_names": sorted(attrs),
            "preimage_sha256": previous_hash,
            "preimage_updated_at": revision,
        }
        params = {"organization_id": org}
        if request_id is not None:
            params["request_id_sha256"] = _sha(request_id)
        prepared = _PreparedRecord(
            context=request.context, capability=cap, method=http_method,
            relative_path=path, resource_type=kind, organization_id=org,
            resource_id=resource_id, before_sha256=previous_hash,
            before_revision=revision, desired_attributes=attrs,
            check_attributes=dict(attrs), headers=headers, request_key=request_id,
        )
        return ProviderPreparedExecution(
            provider_capability=cap, action_method=http_method,
            resource_type=("documentation_" + kind.replace("-", "_").rstrip("s")),
            resource_identifier=str(resource_id) if resource_id is not None else None,
            normalized_path=path, payload=public_plan,
            parameters=params, opaque=prepared,
        )

    def execute_governed_execution(self, plan: ProviderPreparedExecution) -> ConnectorResult:
        state = plan.opaque
        if not isinstance(state, _PreparedRecord):
            raise ConnectorAuthorizationError("IT_GLUE_INVALID_PREPARED_STATE")
        org = self._scope(state.context, state.capability)
        if org != state.organization_id:
            raise ConnectorAuthorizationError("IT_GLUE_CLIENT_ORGANIZATION_CHANGED")
        attrs = dict(state.desired_attributes)
        expected = {
            "type": state.resource_type,
            "attributes_sha256": _sha(attrs),
            "attribute_names": sorted(attrs),
            "preimage_sha256": state.before_sha256,
            "preimage_updated_at": state.before_revision,
        }
        params = {"organization_id": org}
        if state.request_key is not None:
            params["request_id_sha256"] = _sha(state.request_key)
        if (plan.provider_capability != state.capability
                or plan.action_method != state.method
                or plan.resource_type != "documentation_" + state.resource_type.replace("-", "_").rstrip("s")
                or plan.resource_identifier != (
                    str(state.resource_id) if state.resource_id is not None else None)
                or normalize_provider_relative_path(plan.normalized_path)
                    != normalize_provider_relative_path(state.relative_path)
                or dict(plan.payload) != expected
                or dict(plan.parameters) != params):
            raise ConnectorAuthorizationError("IT_GLUE_PREPARED_PLAN_TAMPERED")
        performed = False
        rid = state.resource_id
        if state.method == "PATCH":
            current, rev, digest = self._existing(
                state.relative_path, state.resource_type, rid, org, state.headers)
            if all(current.get(k) == v for k, v in attrs.items()):
                pass
            elif digest != state.before_sha256 or rev != state.before_revision:
                raise ConnectorAuthorizationError("IT_GLUE_STALE_RESOURCE_PREIMAGE")
            else:
                self.audit.record("connector.mutation.requested", state.context, {
                    "provider": self.provider_name, "resource_type": state.resource_type,
                    "resource_id": rid, "organization_id": org,
                })
                self.transport.request(
                    method="PATCH", url=self.base_url + state.relative_path,
                    headers=state.headers, params=None,
                    json={"data": {"type": state.resource_type, "attributes": attrs}},
                    timeout_seconds=20.0,
                )
                performed = True
        else:
            if self.creation_claims is None:
                raise ConnectorAuthorizationError("IT_GLUE_DURABLE_CREATE_CLAIM_MISSING")
            # Claim before POST; ambiguous provider outcomes must never be retried.
            claim_key = _sha([state.context.client_id, state.capability,
                              org, state.request_key])
            if self.creation_claims.claim_once(
                    key=claim_key, payload_sha256=_sha(attrs)) is not True:
                raise ConnectorAuthorizationError("IT_GLUE_CREATE_ALREADY_CLAIMED")
            self.audit.record("connector.mutation.requested", state.context, {
                "provider": self.provider_name, "resource_type": state.resource_type,
                "organization_id": org, "request_id_sha256": _sha(state.request_key),
            })
            response = self.transport.request(
                method="POST", url=self.base_url + state.relative_path,
                headers=state.headers, params=None,
                json={"data": {"type": state.resource_type, "attributes": attrs}},
                timeout_seconds=20.0,
            )
            item = response.get("data") if isinstance(response, Mapping) else None
            if not isinstance(item, Mapping) or item.get("type") != state.resource_type:
                raise RuntimeError("IT_GLUE_CREATE_RESPONSE_INVALID")
            rid = _id(item.get("id"), "CREATED_ID")
            performed = True
        # Independent provider readback, never accept an unverified success.
        check_path = "/" + _TYPES[state.capability.rsplit(".", 1)[0]][1] + "/" + str(rid)
        observed, _, _ = self._existing(
            check_path, state.resource_type, rid, org, state.headers)
        checks = dict(state.check_attributes)
        if state.method == "POST":
            checks.pop("organization_id", None)
            checks.pop("organization-id", None)
            checks.pop("is_uploaded", None)
            # Server uses dash-case response keys.
            checks = {k.replace("_", "-"): v for k, v in checks.items()}
        if any(observed.get(k) != v for k, v in checks.items()):
            self.audit.record("connector.mutation.verification_failed", state.context, {
                "provider": self.provider_name, "resource_type": state.resource_type,
                "resource_id": rid,
            })
            raise RuntimeError("IT_GLUE_RECORD_READBACK_MISMATCH")
        self.audit.record("connector.mutation.verified", state.context, {
            "provider": self.provider_name, "resource_type": state.resource_type,
            "resource_id": rid, "mutation_performed": performed,
        })
        return ConnectorResult(
            capability=state.capability, provider=self.provider_name,
            data={
                "resource_id": rid, "organization_id": org,
                "mutation_performed": performed,
                "jasonVerification": {"readbackVerified": True,
                                      "verifiedFields": sorted(checks)},
            },
            evidence_ids=(f"it_glue:{state.resource_type}:{rid}",),
        )
