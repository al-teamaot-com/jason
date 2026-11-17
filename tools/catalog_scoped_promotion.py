#!/usr/bin/env python3
"""Exactly one Autotask catalog runtime/MCP promotion under native release controls.

Source-only until a separately approved, root-attested installed host adapter
and OAuth Owner approval issuer exist. Do not execute a mutable Git worktree
as privileged code. The core cannot approve, unfreeze or deploy on its own:
every action is mediated by the native-host port and an exact signed proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Any, Mapping, Protocol, ContextManager

from implementation.kernel.signed_owner_release import (
    OwnerReleaseProofDenied, verify_exact_owner_release,
)
from tools.catalog_scoped_release_admission import (
    PROFILE, RUNTIME_MODE, MCP_MODE, fail as deny_admission,
)

SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID = re.compile(r"^release-[a-f0-9]{16}$")
PROFILE_ID = "aot-catalog-scoped-runtime-mcp-promotion-v1"
ADMISSION_RECEIPT_SHA256 = "12c8fdeec4b3ffd361d06b40e51a94c8199dfb8f7b0bb30a6d7e6920defe9d31"
ADMISSION_EVIDENCE_PATH = "docs/engineering/evidence/catalog-scope-admission-20261117.json"
PREDECESSOR_MANIFEST_PATH = "docs/engineering/evidence/catalog-scope-original-manifest-20261117.json"
PREDECESSOR_MANIFEST_SHA256 = "dd2480eb01508c9f53180775644dfa0343a631d1d6452d265c7c937fbf32a239"
SCOPED_MANIFEST_PATH = "config/catalog-scoped-release-admission.json"
PROTECTED_CONTAINERS = (
    "jason-teams-gateway", "jason-pmv4-shadow-gateway", "openbao",
)
OFFER_FIELDS = frozenset({
    "schema_version", "profile", "status", "release_id", "candidate_sha",
    "rollback_sha", "scope_sha256", "historical_admission_receipt_sha256",
    "fresh_admission_receipt_sha256", "protected_main_sha", "protected_feature_sha",
    "runtime_image_id", "mcp_image_id", "rollback_runtime_image_id",
    "rollback_mcp_image_id", "freeze_sha256", "runtime_settings",
    "mcp_settings", "protected_containers", "one_transaction_only",
    "separate_owner_approval_required", "no_global_owner_expansion",
    "original_host_revision", "manifest_sha256",
})


class ScopedPromotionDenied(PermissionError):
    """Exactly bounded release refused without changing production."""


def fail(code: str) -> None:
    raise ScopedPromotionDenied("CATALOG_SCOPED_PROMOTION_" + code)


def canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(data), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def historical_receipt_verified(
    historical: Mapping[str, Any], manifest: Mapping[str, Any], *,
    expected_sha256: str = ADMISSION_RECEIPT_SHA256,
) -> dict[str, Any]:
    """Consume exact immutable admission, not a new approval or output text."""
    if not isinstance(historical, Mapping):
        fail("HISTORICAL_ADMISSION_MISSING")
    # The Owner's previously verified receipt refers to the older *nine-file*
    # source and images. Revalidate it against its exact frozen predecessor
    # manifest rather than pretending those images contain the newer MCP
    # release signer. The new images have their own fresh independent receipt.
    previous_path=Path(__file__).resolve().parents[1]/PREDECESSOR_MANIFEST_PATH
    if previous_path.is_symlink() or not previous_path.is_file():
        fail("PREDECESSOR_MANIFEST_MISSING")
    original=previous_path.read_bytes()
    if sha256(original).hexdigest()!=PREDECESSOR_MANIFEST_SHA256:
        fail("PREDECESSOR_MANIFEST_CHANGED")
    try:
        predecessor=json.loads(original)
    except (ValueError,TypeError) as exc:
        raise ScopedPromotionDenied("CATALOG_SCOPED_PROMOTION_PREDECESSOR_MANIFEST_INVALID") from exc
    if (manifest.get("rollback_sha")!=predecessor.get("rollback_sha")
            or manifest.get("snapshot_sha")==predecessor.get("snapshot_sha")):
        fail("PREDECESSOR_AND_NEW_CANDIDATE_NOT_DISTINCT")
    source = historical.get("protected_source") or {}
    dual = historical.get("dual_image_rollback") or {}
    checks = historical.get("protected_ci") or {}
    preflights = historical.get("native_readonly_preflight") or {}
    if (historical.get("schema_version") != "1.0"
            or historical.get("profile") != PROFILE
            or historical.get("status") != "SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE"
            or historical.get("receipt_sha256") != expected_sha256
            or not isinstance(expected_sha256, str) or not DIGEST.fullmatch(expected_sha256)):
        fail("HISTORICAL_ADMISSION_PROFILE_OR_HASH")
    reconstructed = dict(historical)
    reconstructed.pop("receipt_sha256", None)
    if sha256(canonical(reconstructed)).hexdigest() != expected_sha256:
        fail("HISTORICAL_ADMISSION_CONTENT_CHANGED")
    expected_source = {
        "snapshot_source_sha": predecessor["snapshot_sha"],
        "rollback_source_sha": predecessor["rollback_sha"],
        "verified_protected_feature_sha": predecessor["protected_feature_sha"],
        "source_diff_sha256": predecessor["scope_sha256"],
    }
    if not isinstance(source, Mapping) or any(source.get(k) != v for k, v in expected_source.items()):
        fail("HISTORICAL_ADMISSION_SOURCE_MISMATCH")
    for key, expected in (
        ("candidate_runtime_image_id", predecessor["runtime_image_id"]),
        ("candidate_mcp_image_id", predecessor["mcp_image_id"]),
        ("rollback_runtime_image_id", predecessor["rollback_runtime_image_id"]),
        ("rollback_mcp_image_id", predecessor["rollback_mcp_image_id"]),
        ("rollback_sha", predecessor["rollback_sha"]),
        ("freeze_sha256", predecessor["freeze_sha256"]),
    ):
        if dual.get(key) != expected:
            fail("HISTORICAL_ADMISSION_IMAGE_OR_FREEZE_CHANGED")
    if (historical.get("production_mutations") is not False
            or historical.get("owner_approval_recorded") is not False
            or historical.get("provider_writes") is not False
            or historical.get("native_production_eligible_record_created") is not False
            or historical.get("separate_exact_release_approval_required") is not True
            or historical.get("separate_catalog_test_write_approval_required") is not True
            or historical.get("existing_native_release_promotion_unchanged") is not True):
        fail("HISTORICAL_ADMISSION_WAS_NOT_READ_ONLY")
    if (not isinstance(checks, Mapping) or checks.get("passed") is not True
            or "governed-security-regressions" not in checks.get("required_checks", [])):
        fail("HISTORICAL_ADMISSION_SECURITY_CI_MISSING")
    for kind, image in (("runtime", predecessor["runtime_image_id"]),
                        ("mcp", predecessor["mcp_image_id"])):
        result = preflights.get(kind) if isinstance(preflights, Mapping) else None
        if (not isinstance(result, Mapping) or result.get("preflight") != "PASS"
                or result.get("image_id") != image
                or result.get("additional_binds") != 0):
            fail("HISTORICAL_ADMISSION_PREFLIGHT_NOT_PROVEN")
    return {"receipt_sha256": expected_sha256,
            "source_sha": predecessor["snapshot_sha"],
            "rollback_sha": predecessor["rollback_sha"], "scope_sha256": predecessor["scope_sha256"]}


def make_offer(
    manifest: Mapping[str, Any], historical: Mapping[str, Any],
    fresh_admission: Mapping[str, Any],
) -> dict[str, Any]:
    """Exact source-only proposal, never a production-eligible native release."""
    historical_receipt_verified(historical, manifest)
    if (not isinstance(fresh_admission, Mapping)
            or fresh_admission.get("status") != "SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE"
            or fresh_admission.get("production_mutations") is not False
            or fresh_admission.get("owner_approval_recorded") is not False
            or fresh_admission.get("native_production_eligible_record_created") is not False
            or fresh_admission.get("provider_writes") is not False):
        fail("FRESH_ADMISSION_NOT_READ_ONLY")
    fresh_source = fresh_admission.get("protected_source") or {}
    fresh_dual = fresh_admission.get("dual_image_rollback") or {}
    fresh_checks = fresh_admission.get("protected_ci") or {}
    for key, expected in (
        ("snapshot_source_sha", manifest["snapshot_sha"]),
        ("rollback_source_sha", manifest["rollback_sha"]),
        ("source_diff_sha256", manifest["scope_sha256"]),
        ("verified_protected_feature_sha", manifest["protected_feature_sha"]),
    ):
        if fresh_source.get(key) != expected:
            fail("FRESH_SOURCE_CHANGED")
    for key, expected in (
        ("candidate_runtime_image_id", manifest["runtime_image_id"]),
        ("candidate_mcp_image_id", manifest["mcp_image_id"]),
        ("rollback_runtime_image_id", manifest["rollback_runtime_image_id"]),
        ("rollback_mcp_image_id", manifest["rollback_mcp_image_id"]),
        ("freeze_sha256", manifest["freeze_sha256"]),
        ("rollback_sha", manifest["rollback_sha"]),
    ):
        if fresh_dual.get(key) != expected:
            fail("FRESH_ARTIFACT_DRIFT")
    if (fresh_checks.get("passed") is not True or
            "governed-security-regressions" not in fresh_checks.get("required_checks", [])):
        fail("FRESH_PROTECTED_CI_NOT_GREEN")
    fresh_digest = fresh_admission.get("receipt_sha256")
    if (not isinstance(fresh_digest, str) or not DIGEST.fullmatch(fresh_digest)):
        fail("FRESH_RECEIPT_INVALID")
    check = dict(fresh_admission)
    check.pop("receipt_sha256", None)
    if sha256(canonical(check)).hexdigest() != fresh_digest:
        fail("FRESH_RECEIPT_FORGED")
    main_sha = fresh_source.get("verified_main_sha")
    if not isinstance(main_sha, str) or not SHA.fullmatch(main_sha):
        fail("FRESH_MAIN_SHA_INVALID")
    source_sha = manifest["snapshot_sha"]
    release_id = "release-" + source_sha[:16]
    payload = {
        "schema_version":"1.0", "profile":PROFILE_ID,
        "status":"awaiting_exact_owner_approval", "release_id":release_id,
        "candidate_sha":source_sha, "rollback_sha":manifest["rollback_sha"],
        "scope_sha256":manifest["scope_sha256"],
        "historical_admission_receipt_sha256":ADMISSION_RECEIPT_SHA256,
        "fresh_admission_receipt_sha256":fresh_digest,
        "protected_main_sha":main_sha,
        "protected_feature_sha":manifest["protected_feature_sha"],
        "runtime_image_id":manifest["runtime_image_id"],
        "mcp_image_id":manifest["mcp_image_id"],
        "rollback_runtime_image_id":manifest["rollback_runtime_image_id"],
        "rollback_mcp_image_id":manifest["rollback_mcp_image_id"],
        "freeze_sha256":manifest["freeze_sha256"],
        "runtime_settings":dict(RUNTIME_MODE), "mcp_settings":dict(MCP_MODE),
        "protected_containers":list(PROTECTED_CONTAINERS),
        "one_transaction_only":True,
        "separate_owner_approval_required":True,
        "no_global_owner_expansion":True,
        "original_host_revision":manifest["rollback_sha"],
    }
    payload["manifest_sha256"] = sha256(canonical(payload)).hexdigest()
    validate_offer(payload)
    return payload


def validate_offer(offer: Mapping[str, Any]) -> dict[str, Any]:
    """Use the same pure approved offer contract as the installed MCP."""
    from implementation.kernel.catalog_scoped_promotion_contract import (
        CatalogOfferDenied, validate_offer as validate_pure,
    )
    try:
        return validate_pure(offer)
    except CatalogOfferDenied as exc:
        raise ScopedPromotionDenied(str(exc)) from exc


def verify_owner_proof(
    offer: Mapping[str, Any], signed: Mapping[str, Any], *,
    root_pinned_public_key: Any, at: datetime | None = None,
    consumed_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    offer = validate_offer(offer)
    try:
        decision=verify_exact_owner_release(
            signed, public_key=root_pinned_public_key,
            expected_candidate_sha=offer["candidate_sha"],
            expected_rollback_sha=offer["rollback_sha"],
            expected_release_id=offer["release_id"],
            expected_scope_sha256=offer["scope_sha256"],
            expected_manifest_sha256=offer["manifest_sha256"],
            expected_freeze_sha256=offer["freeze_sha256"],
            at=at or datetime.now(timezone.utc),consumed_ids=consumed_ids,
        )
    except OwnerReleaseProofDenied as exc:
        raise ScopedPromotionDenied("CATALOG_SCOPED_PROMOTION_OWNER_PROOF_REJECTED:"+str(exc)) from exc
    return decision


class TrustedCatalogHost(Protocol):
    """Production adapter implements native controls, never caller-supplied code."""
    def enforce_installed_production_trust(self) -> None: ...
    def transaction_lock(self, offer: Mapping[str, Any]) -> ContextManager[Any]: ...
    def fresh_source_and_live_admission(self, offer: Mapping[str, Any]) -> None: ...
    def circuit_breaker_closed_and_workers_quiescent(self) -> None: ...
    def deny_unresolved_previous_attempt(self, offer: Mapping[str, Any]) -> None: ...
    def open_circuit_breaker(self, code: str) -> None: ...
    def pinned_owner_public_key(self) -> Any: ...
    def consumed_approval_ids(self) -> frozenset[str]: ...
    def protected_container_snapshot(self) -> Mapping[str, Any]: ...
    def durable_intent(self, offer: Mapping[str, Any], decision: Mapping[str, Any]) -> None: ...
    def consume_once(self, approval_id: str) -> None: ...
    def frozen_one_transaction(self, offer: Mapping[str, Any], decision: Mapping[str, Any]) -> ContextManager[Any]: ...
    def promote_exact(self, target: str, image: str, revision: str, setting: Mapping[str,str]) -> None: ...
    def verify_live_dual_image(self, offer: Mapping[str, Any]) -> None: ...
    def verify_unchanged_protected_containers(self, original: Mapping[str, Any]) -> None: ...
    def publish_scoped_control_readback(self, offer: Mapping[str, Any], decision: Mapping[str, Any]) -> None: ...
    def verify_scoped_control_readback(self, offer: Mapping[str, Any]) -> None: ...
    def rollback_both(self, offer: Mapping[str, Any]) -> None: ...
    def verify_rollback_and_host(self, offer: Mapping[str, Any]) -> None: ...
    def clear_scoped_control_readback(self, offer: Mapping[str, Any]) -> None: ...
    def record_outcome(self, offer: Mapping[str, Any], outcome: str, *, error: str = "") -> None: ...
    def freeze_restored_exactly(self, offer: Mapping[str, Any]) -> None: ...


def promote_scoped_catalog_pair(
    offer: Mapping[str, Any], signed: Mapping[str, Any], *, host: TrustedCatalogHost,
) -> dict[str, Any]:
    """Bounded mutation of exactly runtime and MCP, with paired rollback.

    Fail CLOSED on any mutation error; the host must make both restores durable
    and demonstrate baseline readback. A rollback verification failure leaves
    the root breaker open and needs human recovery. An incomplete transaction
    is never silently retried or reapproved.
    """
    offer=validate_offer(offer)
    host.enforce_installed_production_trust()
    # No caller may self-attest installation, security or the Owner proof.
    with host.transaction_lock(offer):
        host.fresh_source_and_live_admission(offer)
        host.circuit_breaker_closed_and_workers_quiescent()
        host.deny_unresolved_previous_attempt(offer)
        decision=verify_owner_proof(
            offer,signed,root_pinned_public_key=host.pinned_owner_public_key(),
            consumed_ids=host.consumed_approval_ids(),
        )
        before=host.protected_container_snapshot()
        host.durable_intent(offer,decision)
        # Consume BEFORE the first production mutation, so an interrupted
        # attempt cannot reuse an Owner signature for a second promotion.
        host.consume_once(decision["approval_id"])
        outcome="failed_before_mutation"
        try:
            with host.frozen_one_transaction(offer,decision):
                try:
                    outcome="promotion_attempted"
                    host.promote_exact("jason-runtime",offer["runtime_image_id"],
                                       offer["candidate_sha"],RUNTIME_MODE)
                    host.verify_unchanged_protected_containers(before)
                    host.promote_exact("jason-mcp-pilot",offer["mcp_image_id"],
                                       offer["candidate_sha"],MCP_MODE)
                    host.verify_live_dual_image(offer)
                    host.verify_unchanged_protected_containers(before)
                    host.publish_scoped_control_readback(offer,decision)
                    host.verify_scoped_control_readback(offer)
                    host.record_outcome(offer,"production_pair_verified")
                    outcome="production_pair_verified"
                except BaseException as exc:
                    # Even when the first mutation fails, the native helper
                    # may have stopped/renamed the previous container.
                    try:
                        host.rollback_both(offer)
                        host.verify_rollback_and_host(offer)
                        host.verify_unchanged_protected_containers(before)
                        host.clear_scoped_control_readback(offer)
                        outcome="rolled_back_and_verified"
                    except BaseException as rollback_exc:
                        outcome="rollback_unverified_breaker_required"
                        host.open_circuit_breaker("CATALOG_SCOPED_ROLLBACK_UNVERIFIED")
                        host.record_outcome(offer,outcome,error=type(rollback_exc).__name__)
                        raise ScopedPromotionDenied(
                            "CATALOG_SCOPED_PROMOTION_ROLLBACK_UNVERIFIED"
                        ) from rollback_exc
                    host.record_outcome(offer,outcome,error=type(exc).__name__)
                    raise
        except BaseException:
            if outcome == "failed_before_mutation":
                host.record_outcome(offer,"failed_before_mutation")
            raise
        finally:
            try:
                host.freeze_restored_exactly(offer)
            except BaseException:
                host.open_circuit_breaker("CATALOG_SCOPED_FREEZE_RESTORATION_UNVERIFIED")
                raise
        if outcome!="production_pair_verified":
            fail("PAIR_NOT_VERIFIED")
        return {
            "schema_version":"1.0", "status":"production_pair_verified",
            "release_id":offer["release_id"],
            "snapshot_sha":offer["candidate_sha"],
            "rollback_sha":offer["rollback_sha"],
            "scope_sha256":offer["scope_sha256"],
            "runtime_image_id":offer["runtime_image_id"],
            "mcp_image_id":offer["mcp_image_id"],
            "approved_by":decision["owner_principal"],
            "approval_id":decision["approval_id"],
            "freeze_restored":True,
            "provider_test_write_approved":False,
            "global_owner_allowlist_unchanged":True,
        }
