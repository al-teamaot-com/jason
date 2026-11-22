"""Fail-closed exact preproduction target and approval boundary.

This does not mint identity, grant approval, execute a provider operation,
or authorize JSON activation/legacy retirement. It validates only externally
attested inputs that must be checked again by the existing governed service.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from tools.legacy_json_acceptance_ledger import build


class PreprodBoundaryDenied(ValueError):
    """Missing independently verified preproduction scope or authorization."""


@dataclass(frozen=True)
class PreprodBoundaryDecision:
    allowed: bool
    mode: str
    reasons: tuple[str, ...]
    production_activation_allowed: bool = False
    legacy_retirement_allowed: bool = False


_ALLOWED_KINDS = frozenset({"readonly", "modifying"})


def evaluate_preprod_boundary(
    manifest: Mapping[str, Any], *, playbook_id: str, action_kind: str,
    known_main_sha: str, live_owner_status: Mapping[str, Any],
    live_registry: Mapping[str, Any],
) -> PreprodBoundaryDecision:
    """Evaluate request, never execute it. All evidence must be externally verified.

    The signed Owner receipt remains an input to Central Orchestrator and is
    never copied to source files or considered minted by this validation.
    """
    reasons: list[str] = []
    if action_kind not in _ALLOWED_KINDS:
        return PreprodBoundaryDecision(False, "denied", ("ACTION_KIND_INVALID",))
    if manifest.get("boundary_version") != "json-preprod-v1":
        reasons.append("BOUNDARY_VERSION_UNVERIFIED")
    if manifest.get("mode") != "isolated_preproduction":
        reasons.append("ISOLATED_PREPRODUCTION_MODE_UNVERIFIED")
    if manifest.get("production_activation_allowed") is not False:
        reasons.append("PRODUCTION_ACTIVATION_MUST_BE_DENIED")
    if manifest.get("legacy_retirement_allowed") is not False:
        reasons.append("LEGACY_RETIREMENT_MUST_BE_DENIED")
    if (len(known_main_sha) != 40 or
            manifest.get("reviewed_main_sha") != known_main_sha):
        reasons.append("EXACT_REVIEWED_MAIN_SHA_MISMATCH")
    try:
        entries = {row["id"]: row for row in build()["entries"]}
    except Exception:
        entries = {}
        reasons.append("CANONICAL_SOURCE_LEDGER_UNAVAILABLE")
    if playbook_id not in entries:
        reasons.append("PLAYBOOK_NOT_CANONICAL_SOURCE")
    else:
        case = next((row for row in manifest.get("cases", ())
                     if isinstance(row, Mapping) and row.get("playbook_id") == playbook_id), None)
        if not isinstance(case, Mapping):
            reasons.append("EXACT_PLAYBOOK_CASE_NOT_PRESENT")
        else:
            if case.get("json_fingerprint") != entries[playbook_id]["json_fingerprint"]:
                reasons.append("JSON_FINGERPRINT_CHANGED")
            if case.get("version") != entries[playbook_id]["json_version"]:
                reasons.append("JSON_VERSION_CHANGED")
            if case.get("client_test_scope") != "explicit_isolated_test_tenant":
                reasons.append("TEST_TENANT_NOT_EXPLICITLY_ISOLATED")
            for name in ("client_id", "provider_test_tenant_id", "target_id"):
                if not isinstance(case.get(name), str) or not case[name].strip():
                    reasons.append("EXACT_TEST_TARGET_MISSING:" + name)
            if case.get("provider_same_client_binding_verified") is not True:
                reasons.append("PROVIDER_TEST_TENANT_BINDING_UNVERIFIED")
            if case.get("target_nonproduction_verified") is not True:
                reasons.append("NONPRODUCTION_TARGET_UNVERIFIED")
            if case.get("source_legacy_dispatch_disabled_for_target") is not True:
                reasons.append("DUPLICATE_LEGACY_DISPATCH_NOT_EXCLUDED")
            if case.get("action_kind") != action_kind:
                reasons.append("EXACT_ACTION_KIND_CHANGED")
            if action_kind == "modifying":
                if not case.get("exact_action_arguments_sha256"):
                    reasons.append("ACTION_ARGUMENT_HASH_MISSING")
                if not case.get("owner_approval_receipt_id"):
                    reasons.append("OWNER_APPROVAL_RECEIPT_MISSING")
                if case.get("approval_exact_action_verified") is not True:
                    reasons.append("EXACT_ACTION_APPROVAL_UNVERIFIED")
    if (not isinstance(live_registry, Mapping) or
            live_registry.get("status") != "succeeded" or
            live_registry.get("generation") != 0 or
            live_registry.get("playbooks") != []):
        reasons.append("PRODUCTION_REGISTRY_BASELINE_CHANGED")
    # An authenticated chat assertion cannot replace an independent Jason
    # Owner-authenticated admin session. No token is accepted here.
    if (not isinstance(live_owner_status, Mapping) or
            live_owner_status.get("status") != "succeeded" or
            live_owner_status.get("owner_identity_verified") is not True):
        reasons.append("ADMIN_OWNER_SESSION_NOT_VERIFIED")
    if action_kind == "modifying":
        if (not isinstance(live_owner_status, Mapping) or
                live_owner_status.get("exact_action_approval_verified") is not True):
            reasons.append("EXACT_ACTION_APPROVAL_NOT_CONFIRMED_BY_JASON")
    return PreprodBoundaryDecision(
        allowed=not reasons,
        mode="isolated_preproduction" if not reasons else "denied",
        reasons=tuple(sorted(set(reasons))),
    )


def redacted_boundary_summary(manifest: Mapping[str, Any], *, main_sha: str,
                              owner_status: Mapping[str, Any],
                              registry_status: Mapping[str, Any]) -> dict[str, Any]:
    """Return public audit summary, never sensitive target/approval fields."""
    entries = build()["entries"]
    decisions = {
        row["id"]: evaluate_preprod_boundary(
            manifest, playbook_id=row["id"], action_kind="readonly",
            known_main_sha=main_sha, live_owner_status=owner_status,
            live_registry=registry_status,
        ) for row in entries
    }
    return {
        "boundary_version": "json-preprod-v1",
        "live_provider_authorized_playbooks": sum(x.allowed for x in decisions.values()),
        "live_provider_blocked_playbooks": sum(not x.allowed for x in decisions.values()),
        "all_19_candidates_unactivated": registry_status.get("generation") == 0
            and registry_status.get("playbooks") == [],
        "production_activation_allowed": False,
        "legacy_retirement_allowed": False,
        "blocked_reason_codes": sorted(set(code for decision in decisions.values()
                                           for code in decision.reasons)),
        "decisions": {name: {"allowed": d.allowed, "reason_codes": list(d.reasons)}
                      for name, d in sorted(decisions.items())},
    }
