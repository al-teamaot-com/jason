"""Exact one-transaction catalog root installer; source-only until root pinning.

Never accepts a chat assertion, arbitrary Owner identity, reusable approval,
command string, image promotion flag or provider write. The native root host
performs fresh Entra OAuth verification and all privileged operations.
"""
from __future__ import annotations

from hashlib import sha256
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping, Protocol

from tools.catalog_scoped_root_install_plan import (
    FILES, POLICY, POLICY_FIELDS, canonical, target_for_source,
)

ACTION = "catalog_root_install_only_v1"
CONFIRM = "APPROVE-EXACT-CATALOG-ROOT-INSTALL-ONLY"
APPROVAL_FIELDS = frozenset({
    "schema_version", "action", "approval_id", "release_id", "source_sha",
    "scope_sha256", "manifest_sha256", "rollback_source_sha", "freeze_sha256",
    "owner_tenant", "owner_oid", "owner_principal", "assurance",
    "verified_access_token_sha256", "approved_at", "affirmative_decision",
    "one_use", "standing_authority", "provider_write_approved",
})
SHA = re.compile(r"^[0-9a-f]{40}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
CID = re.compile(r"^catalog-root-owner-[0-9a-f]{32}$")
TID = "f7054323-d52b-4863-8c2f-1898f0b6077c"
OWNER_OIDS = frozenset({
    "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
    "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
})


class CatalogRootInstallDenied(PermissionError):
    pass


def fail(code: str) -> None:
    raise CatalogRootInstallDenied("CATALOG_ROOT_INSTALL_" + code)


def verify_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        fail("PLAN_NOT_A_MAPPING")
    required = {
        "schema_version", "status", "source_sha", "immutable_candidate_snapshot_sha",
        "rollback_source_sha", "catalog_scope_sha256", "original_admission_receipt_sha256",
        "fresh_admission_receipt_sha256", "signed_promotion_manifest_sha256",
        "runtime_image_id", "mcp_image_id", "rollback_runtime_image_id",
        "rollback_mcp_image_id", "freeze_sha256", "host_readback",
        "root_policy_after_separate_approval", "root_file_plan",
        "directories_after_separate_approval", "root_policy_target",
        "rollback_root_worker_sha256", "recovery_timer_name",
        "rollback_original_worker_required", "signed_exact_root_install_approval_required",
        "signed_separate_image_promotion_approval_required",
        "separate_autotask_provider_test_write_approval_required",
        "root_state_readback_after_install_required", "production_mutations",
        "provider_writes", "owner_approval_recorded",
        "installation_executable_in_source_only_mode", "installation_scope_sha256",
        "install_plan_sha256",
    }
    if set(plan) != required:
        fail("PLAN_SCHEMA_DRIFT")
    if (plan["schema_version"] != "1.0"
            or plan["status"] != "SOURCE_ONLY_ROOT_INSTALL_PREPARED_NOT_AUTHORIZED"
            or not isinstance(plan["source_sha"], str) or not SHA.fullmatch(plan["source_sha"])
            or not isinstance(plan["rollback_source_sha"], str)
            or not SHA.fullmatch(plan["rollback_source_sha"])
            or plan["source_sha"] == plan["rollback_source_sha"]
            or any(not isinstance(plan[name], str) or not HASH.fullmatch(plan[name])
                   for name in (
                       "install_plan_sha256", "installation_scope_sha256",
                       "freeze_sha256", "rollback_root_worker_sha256"))
            or plan["root_policy_target"] != str(POLICY)
            or plan["recovery_timer_name"] != "jason-catalog-scoped-recovery.timer"
            or plan["rollback_original_worker_required"] is not True
            or plan["signed_exact_root_install_approval_required"] is not True
            or plan["signed_separate_image_promotion_approval_required"] is not True
            or plan["separate_autotask_provider_test_write_approval_required"] is not True
            or plan["root_state_readback_after_install_required"] is not True
            or plan["production_mutations"] is not False
            or plan["provider_writes"] is not False
            or plan["owner_approval_recorded"] is not False
            or plan["installation_executable_in_source_only_mode"] is not False):
        fail("PLAN_PRODUCTION_PERMISSION_DRIFT")
    fileplan = plan["root_file_plan"]
    if (not isinstance(fileplan, list) or len(fileplan) != len(FILES)
            or {x.get("source") for x in fileplan if isinstance(x, Mapping)} != set(FILES)
            or any(not isinstance(x, Mapping)
                   or set(x) != {"source", "destination", "uid", "gid", "mode", "sha256"}
                   or x.get("destination") != target_for_source(x["source"])["destination"]
                   or x.get("mode") != target_for_source(x["source"])["mode"]
                   or x.get("uid") != "root" or x.get("gid") != "root"
                   or not isinstance(x.get("sha256"), str)
                   or not HASH.fullmatch(x["sha256"])
                   for x in fileplan)):
        fail("PLAN_FILE_ALLOWLIST_CHANGED")
    policy = plan["root_policy_after_separate_approval"]
    if (not isinstance(policy, Mapping) or set(policy) != POLICY_FIELDS
            or policy["source_sha"] != plan["source_sha"]
            or policy["automatic_recovery_installed"] is not True
            or policy["native_root_control_supported"] is not True
            or policy["no_global_owner_elevation"] is not True):
        fail("PLAN_ROOT_POLICY_CHANGED")
    raw = dict(plan)
    claimed = raw.pop("install_plan_sha256")
    if sha256(canonical(raw)).hexdigest() != claimed:
        fail("PLAN_DIGEST_CHANGED")
    return dict(plan)


def verify_owner_evidence(plan: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Only the root host can issue this evidence after signed Entra JWT check."""
    if not isinstance(evidence, Mapping) or set(evidence) != APPROVAL_FIELDS:
        fail("OWNER_RECEIPT_INVALID")
    source = plan["source_sha"]
    oid = evidence["owner_oid"]
    try:
        verified_at = datetime.fromisoformat(evidence["approved_at"])
    except (ValueError,TypeError,KeyError) as exc:
        raise CatalogRootInstallDenied("CATALOG_ROOT_INSTALL_OWNER_TIME_INVALID") from exc
    now = datetime.now(timezone.utc)
    if (verified_at.tzinfo is None or not timedelta(seconds=-30) <= now-verified_at
            <= timedelta(minutes=10)):
        fail("OWNER_EVIDENCE_STALE_OR_FUTURE")
    if (evidence["schema_version"] != "1.0" or evidence["action"] != ACTION
            or not isinstance(evidence["approval_id"], str)
            or not CID.fullmatch(evidence["approval_id"])
            or evidence["release_id"] != "release-" + source[:16]
            or evidence["source_sha"] != source
            or evidence["scope_sha256"] != plan["installation_scope_sha256"]
            or evidence["manifest_sha256"] != plan["install_plan_sha256"]
            or evidence["rollback_source_sha"] != plan["rollback_source_sha"]
            or evidence["freeze_sha256"] != plan["freeze_sha256"]
            or evidence["owner_tenant"] != TID
            or not isinstance(oid, str) or oid not in OWNER_OIDS
            or evidence["owner_principal"] != "person-entra-" + oid.replace("-", "")
            or evidence["assurance"] != "fresh_verified_entra_device_code_signed_jwt"
            or not isinstance(evidence["verified_access_token_sha256"], str)
            or not HASH.fullmatch(evidence["verified_access_token_sha256"])
            or evidence["affirmative_decision"] != CONFIRM
            or evidence["one_use"] is not True
            or evidence["standing_authority"] is not False
            or evidence["provider_write_approved"] is not False):
        fail("EXACT_OWNER_APPROVAL_SCOPE_OR_IDENTITY_INVALID")
    return dict(evidence)


class RootInstallerHost(Protocol):
    def verify_root_bootstrap_trust(self) -> None: ...
    def lock_existing_production_manager(self) -> Any: ...
    def independent_live_source_ci_and_freeze(self, plan: Mapping[str, Any]) -> None: ...
    def deny_prior_attempt_or_changed_root_files(self, plan: Mapping[str, Any]) -> None: ...
    def obtain_verified_entra_owner_for_exact_action(self, plan: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def consumed_owner_approvals(self) -> frozenset[str]: ...
    def journal_intent_before_mutation(self, plan: Mapping[str, Any], owner: Mapping[str, Any]) -> None: ...
    def consume_owner_approval_once(self, approval_id: str) -> None: ...
    def backup_original_worker_and_units(self, plan: Mapping[str, Any]) -> None: ...
    def install_exact_root_files(self, plan: Mapping[str, Any]) -> None: ...
    def install_root_policy(self, plan: Mapping[str, Any]) -> None: ...
    def activate_and_verify_recovery_watchdog(self, plan: Mapping[str, Any]) -> None: ...
    def independent_live_readback(self, plan: Mapping[str, Any]) -> None: ...
    def restore_original_worker_units_and_state(self, plan: Mapping[str, Any]) -> None: ...
    def independently_verify_rollback_and_freeze(self, plan: Mapping[str, Any]) -> None: ...
    def open_root_production_breaker(self, reason: str) -> None: ...
    def record_completion(self, plan: Mapping[str, Any], outcome: str) -> None: ...


def execute_root_install_transaction(plan: Mapping[str, Any], host: RootInstallerHost) -> dict[str, Any]:
    """One exact root installation; cannot approve image promotion."""
    approved_plan = verify_plan(plan)
    host.verify_root_bootstrap_trust()
    with host.lock_existing_production_manager():
        host.independent_live_source_ci_and_freeze(approved_plan)
        host.deny_prior_attempt_or_changed_root_files(approved_plan)
        receipt = verify_owner_evidence(
            approved_plan, host.obtain_verified_entra_owner_for_exact_action(approved_plan),
        )
        if receipt["approval_id"] in host.consumed_owner_approvals():
            fail("OWNER_REPLAY")
        host.journal_intent_before_mutation(approved_plan, receipt)
        host.consume_owner_approval_once(receipt["approval_id"])
        # A verified backup is a strict precondition for changing *any* live
        # root worker or systemd unit. Failure to stage it is NOT evidence of
        # a partial production mutation; fail closed and retain the audit.
        try:
            host.backup_original_worker_and_units(approved_plan)
        except BaseException:
            host.record_completion(approved_plan, "root_install_backup_failed_before_mutation")
            raise
        try:
            host.install_exact_root_files(approved_plan)
            host.install_root_policy(approved_plan)
            host.activate_and_verify_recovery_watchdog(approved_plan)
            host.independent_live_readback(approved_plan)
            host.record_completion(approved_plan, "exact_catalog_root_install_verified")
        except BaseException as original:
            try:
                host.restore_original_worker_units_and_state(approved_plan)
                host.independently_verify_rollback_and_freeze(approved_plan)
                host.record_completion(approved_plan, "catalog_root_rolled_back_verified")
            except BaseException as recovery:
                host.open_root_production_breaker("CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED")
                host.record_completion(approved_plan, "catalog_root_rollback_unverified")
                raise CatalogRootInstallDenied(
                    "CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED") from recovery
            raise CatalogRootInstallDenied("CATALOG_ROOT_INSTALL_ROLLED_BACK") from original
        return {
            "status": "exact_catalog_root_install_verified",
            "source_sha": approved_plan["source_sha"],
            "rollback_source_sha": approved_plan["rollback_source_sha"],
            "installation_scope_sha256": approved_plan["installation_scope_sha256"],
            "plan_sha256": approved_plan["install_plan_sha256"],
            "approval_id": receipt["approval_id"],
            "original_production_freeze_restored": True,
            "runtime_mcp_image_promotion_approved": False,
            "autotask_provider_write_approved": False,
        }
