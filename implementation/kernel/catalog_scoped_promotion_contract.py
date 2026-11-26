"""Pure catalog release offer validation shared by MCP and native PM.

No filesystem, network, signing key or provider connection. An offer is an
exact field/data binding, never proof of production authorization.
"""
from __future__ import annotations
from hashlib import sha256
import json
import re
from typing import Any, Mapping

PROFILE = "aot-catalog-scoped-runtime-mcp-promotion-v1"
RUNTIME_MODE = {"JASON_AUTOTASK_CATALOG_AUTH_MODE": "jason_managed"}
MCP_MODE = {"JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE": "aot-catalog-self-owner-v1"}
PROTECTED_CONTAINERS = ("jason-teams-gateway", "jason-pmv4-shadow-gateway", "openbao")
RECEIPT_SHA256 = "12c8fdeec4b3ffd361d06b40e51a94c8199dfb8f7b0bb30a6d7e6920defe9d31"
FIELDS = frozenset({
    "schema_version", "profile", "status", "release_id", "candidate_sha",
    "rollback_sha", "scope_sha256", "historical_admission_receipt_sha256",
    "fresh_admission_receipt_sha256", "protected_main_sha", "protected_feature_sha",
    "runtime_image_id", "mcp_image_id", "rollback_runtime_image_id",
    "rollback_mcp_image_id", "freeze_sha256", "runtime_settings",
    "mcp_settings", "protected_containers", "one_transaction_only",
    "separate_owner_approval_required", "no_global_owner_expansion",
    "original_host_revision", "manifest_sha256",
})
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")


class CatalogOfferDenied(PermissionError):
    pass


def canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(data), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def validate_offer(offer: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(offer, Mapping) or set(offer) != FIELDS:
        raise CatalogOfferDenied("CATALOG_OFFER_SCHEMA_INVALID")
    snapshot = offer["candidate_sha"]
    if (offer["schema_version"] != "1.0"
            or offer["profile"] != PROFILE
            or offer["status"] != "awaiting_exact_owner_approval"
            or not isinstance(snapshot, str) or not SHA.fullmatch(snapshot)
            or offer["release_id"] != "release-" + snapshot[:16]
            or not isinstance(offer["rollback_sha"], str)
            or not SHA.fullmatch(offer["rollback_sha"])
            or offer["rollback_sha"] == snapshot
            or offer["original_host_revision"] != offer["rollback_sha"]
            or not isinstance(offer["protected_main_sha"], str)
            or not SHA.fullmatch(offer["protected_main_sha"])
            or not isinstance(offer["protected_feature_sha"], str)
            or not SHA.fullmatch(offer["protected_feature_sha"])
            or not all(isinstance(offer[key], str) and DIGEST.fullmatch(offer[key])
                       for key in ("scope_sha256", "freeze_sha256", "manifest_sha256",
                                   "historical_admission_receipt_sha256",
                                   "fresh_admission_receipt_sha256"))
            or offer["historical_admission_receipt_sha256"] != RECEIPT_SHA256
            or not all(isinstance(offer[key], str) and IMAGE.fullmatch(offer[key])
                       for key in ("runtime_image_id", "mcp_image_id",
                                   "rollback_runtime_image_id", "rollback_mcp_image_id"))
            or offer["runtime_settings"] != RUNTIME_MODE
            or offer["mcp_settings"] != MCP_MODE
            or offer["protected_containers"] != list(PROTECTED_CONTAINERS)
            or offer["one_transaction_only"] is not True
            or offer["separate_owner_approval_required"] is not True
            or offer["no_global_owner_expansion"] is not True):
        raise CatalogOfferDenied("CATALOG_OFFER_FIELDS_INVALID")
    payload = dict(offer)
    claimed = payload.pop("manifest_sha256")
    if sha256(canonical(payload)).hexdigest() != claimed:
        raise CatalogOfferDenied("CATALOG_OFFER_CONTENT_CHANGED")
    return dict(offer)
