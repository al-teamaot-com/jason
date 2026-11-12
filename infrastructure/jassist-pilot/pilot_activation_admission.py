"""Fail-closed offline admission gate for one governed J-Assist pilot.

Every evidence reference must be independently verified through a trusted
release ledger. Local labels, booleans, CLI flags and text files cannot
activate the pilot. No AWS, network, vault or container actions exist here.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Callable, Mapping

_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{11,220}$")
_GATE_NAMES = (
    "protected_main_build",
    "scope_and_rollback_attestation",
    "owner_exact_route_action_approval",
    "production_health_and_release_controls",
    "relay_caddy_immutable_baseline_and_validation",
    "entra_spa_send_scope_and_consent",
    "entra_app_graph_user_group_membership",
    "datto_by_id_native_uuid_account_binding",
    "openbao_scoped_keys_approle_rotation",
    "attested_test_frame_content_review",
    "encrypted_store_ttl_purge_audit",
    "private_https_and_host_firewall",
    "isolated_mcp_principal_authorization",
)
_POST_CHECKS = (
    "real_aot_technician_chrome_one_click",
    "read_only_one_device_screenshot_sha256_receipt",
    "same_technician_mcp_image_read",
    "deny_cross_user_device_replay_and_revocation",
    "verify_no_production_ticket_mcp_teams_degradation",
    "restore_original_freeze_and_release_hold",
)
_ALLOWED = {
    "schema_version", "status", "environment", "deployment_mode",
    "resource_host", "relay_instance_id", "relay_route",
    "pilot_upstream", "aot_tenant_id", "entra_group_id",
    "datto_site_uid", "datto_browser_device_id",
    "datto_provider_device_uid", "retention_seconds",
    "new_aws_resources", "requires_exact_action_owner_authorization",
    "production_deployment_authorized", "candidate_protected_main_sha",
    "scope_sha256", "verified_production_rollback_sha",
    "evidence", "post_activation_acceptance",
}


@dataclass(frozen=True)
class PilotAdmission:
    ready: bool
    failures: tuple[str, ...]
    checked_gates: tuple[str, ...]


def validate_manifest(candidate: Mapping) -> None:
    if (not isinstance(candidate,dict) or set(candidate) != _ALLOWED
            or type(candidate["schema_version"]) is not int
            or candidate["schema_version"] != 1
            or candidate["status"] != "prepared_no_go"
            or candidate["environment"] != "AOT-controlled-isolated-pilot-only"
            or candidate["deployment_mode"] != "reuse-existing-jason-host-and-relay"
            or candidate["resource_host"] != "mcp-jason.teamaot.com"
            or candidate["relay_instance_id"] != "i-0b0bb56884acb565c"
            or candidate["relay_route"] != "/v1/jassist/*"
            or candidate["pilot_upstream"] != "10.87.246.157:3981"
            or candidate["aot_tenant_id"] != "f7054323-d52b-4863-8c2f-1898f0b6077c"
            or candidate["entra_group_id"] != "5273dd8a-1456-4985-b0a3-c00061267e26"
            or candidate["datto_site_uid"] != "9bb56523-cade-4ffb-bc34-696e788f0f4c"
            or candidate["datto_browser_device_id"] != "1717088"
            or candidate["datto_provider_device_uid"] != "710e63d6-caca-d830-697a-81250b0a8321"
            or type(candidate["retention_seconds"]) is not int
            or candidate["retention_seconds"] != 120
            or type(candidate["new_aws_resources"]) is not int
            or candidate["new_aws_resources"] != 0
            or candidate["requires_exact_action_owner_authorization"] is not True
            or candidate["production_deployment_authorized"] is not False
            or not isinstance(candidate["evidence"],dict)
            or tuple(candidate["evidence"]) != _GATE_NAMES
            or candidate["post_activation_acceptance"] != list(_POST_CHECKS)):
        raise ValueError("pilot manifest scope or governance schema changed")


def _is_string_match(s, pattern):
    return isinstance(s,str) and bool(pattern.fullmatch(s))


def check_admission(
    candidate: dict,
    *,
    independently_verify: Callable[[str,str,dict],bool] | None = None,
) -> PilotAdmission:
    """Read-only check; the verifier must be a governed evidence ledger."""
    validate_manifest(candidate)
    failures=[]
    source=candidate["candidate_protected_main_sha"]
    rollback=candidate["verified_production_rollback_sha"]
    scope=candidate["scope_sha256"]
    if not _is_string_match(source,_SHA):
        failures.append("candidate_protected_main_sha_not_verified")
    if not _is_string_match(rollback,_SHA) or (source and source==rollback):
        failures.append("production_rollback_sha_not_independently_verified")
    if not _is_string_match(scope,_DIGEST):
        failures.append("reviewed_scope_sha256_unavailable")
    if independently_verify is None or not callable(independently_verify):
        failures.append("governance_evidence_verifier_unavailable")
    checked=[]
    for gate in _GATE_NAMES:
        evidence=candidate["evidence"][gate]
        if not _is_string_match(evidence,_REF):
            failures.append(gate+":evidence_reference_missing")
            continue
        if not callable(independently_verify):
            continue
        try:
            approved=independently_verify(gate,evidence,candidate)
            if approved is not True:
                failures.append(gate+":independent_verification_denied")
            else:
                checked.append(gate)
        except Exception:
            failures.append(gate+":independent_verification_unavailable")
    return PilotAdmission(
        ready=not failures, failures=tuple(failures),
        checked_gates=tuple(checked)
    )


def _no_duplicates(pairs):
    out={}
    for name,value in pairs:
        if name in out:
            raise ValueError("ambiguous pilot manifest field")
        out[name]=value
    return out


def load_candidate(path: Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size>12_000:
        raise ValueError("missing or oversized pilot manifest")
    return json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=_no_duplicates)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        # Offline CLI deliberately cannot inject a governance verifier.
        result=check_admission(load_candidate(args.manifest))
        print(json.dumps({
            "pilot_admission":"NO_GO",
            "missing":result.failures,
            "checked_gates":result.checked_gates,
            "writes_performed":False
        },sort_keys=True))
    except (OSError,ValueError) as exc:
        print(json.dumps({
            "pilot_admission":"DENIED",
            "reason":str(exc)[:180],
            "writes_performed":False
        },sort_keys=True))
    return 2


if __name__=="__main__":
    raise SystemExit(main())
