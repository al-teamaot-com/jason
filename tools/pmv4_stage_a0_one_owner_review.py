"""Exact one-human-decision PMv4 Stage A0 source-review contract (read-only).

Combines the THREE already-prepared governed operations with their distinct
root artifacts and rollback-to-absence, keeping live production LKG/freeze/
hold completely unchanged. It does NOT authorize any root execution, issue a
parent signature, consume a final Owner approval, publish MCP tools or deploy.
The independently root-owned native consumer is still a hard prerequisite.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import stat
import subprocess
from typing import Any

from orchestrator.pmv4_objective_scope import (
    BoundedObjective, ObjectiveAction,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/pmv4-stage-a0/one-owner-recovery-review-20261115.json"
CONTRACT_SHA256 = "f5f525e33e4cad46827018e23ea7ae8f72603459dcd740bfbf63f9a176cfa52a"
SOURCE = "7b42ce983896711525de4c7955bf9fc43ac003d0"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
RUNTIME_IMAGE = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
ZERO = "0" * 40
ARCHIVE = Path("/srv/jason/archive")
GIT = Path("/home/al/.local/lib/jason/engineering-source-repo")
RELEASE_ROOT = Path("/opt/jason/releases") / SOURCE
MISSING = RELEASE_ROOT / "tools/pmv4_host_install_contract.py"
BOOTSTRAP = ARCHIVE / "pmv4-a0-closure-bootstrap-plan-7b42.json"
ONEFILE = ARCHIVE / ("pmv4-stage-a0-root-source-closure-repair-proposal-"
                     + SOURCE + ".json")
NATIVE_SCOPE = "6786baad0fc9d07aca6ba80dedad5c25bcfa7fb3e50fdde7c4d36ad067285eac"
NATIVE_MANIFEST = "addba768d1ab92d9507d466fdd3980b93ea2041f42901f5d6e5a2cde81dcb025"
MISSING_SHA = "ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db"
REVIEWED_ACTIONS = (
    ("pmv4.stage-a0.root-source-helper.bootstrap",
     "root-source-closure-helper",
     "e5515b5e0d5243c5e18c3118fcc0c39580535c7e0da31525390c141e1aa298cb",
     "25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564"),
    ("pmv4.stage-a0.immutable-root-source-onefile",
     "exact-one-missing-root-blob",
     "089f8706b61b70c9f31406204bb27fab0bde47bc8df56f13a274defb8b537381",
     MISSING_SHA),
    ("pmv4.stage-a0.native-empty-baseline-install",
     "independent-stage-a0-native",
     NATIVE_SCOPE, NATIVE_MANIFEST),
)


class PMv4StageA0ReviewDenied(PermissionError):
    pass


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _require(value: bool, reason: str) -> None:
    if not value:
        raise PMv4StageA0ReviewDenied(reason)


def exact_contract() -> dict[str, Any]:
    """One immutable review contract, never a dynamic user-supplied manifest."""
    data = CONTRACT.read_bytes()
    _require(_hash(data) == CONTRACT_SHA256, "OWNER_PLAN_REVIEW_SOURCE_CHANGED")
    p = json.loads(data)
    required = {
        "schema_version", "service", "status", "production_apply_supported",
        "action", "source_sha", "lkg_sha", "freeze_sha256",
        "promotion_hold_sha256", "runtime_image_sha256", "mcp_image_sha256",
        "base_rollback_sha", "native_create_only_rollback_sha",
        "owner_decisions", "require_entrusted_owner_oauth",
        "require_independent_root_acceptance", "require_native_breaker_closed",
        "require_genuine_four_sqlite_and_restore_pass", "require_current_drift_pass",
        "must_not_change", "ordered_actions", "archived_bootstrap_plan_path",
        "archived_bootstrap_plan_sha256",
        "archived_onefile_proposal_path", "archived_onefile_proposal_sha256",
        "expected_existing_pinned_source_files",
        "expected_after_source_closure_files",
        "one_missing_root_file", "one_missing_root_file_sha256",
    }
    _require(isinstance(p, dict) and set(p) == required,
             "OWNER_PLAN_REVIEW_UNDECLARED_FIELD")
    _require(p["schema_version"] == "1.0"
             and p["service"] == "pmv4-stage-a0-one-owner-reviewed-objective"
             and p["status"] == "source_only_not_authorized"
             and p["production_apply_supported"] is False
             and p["action"] == "pmv4-stage-a0-one-owner-source-repair-and-install-v1"
             and p["source_sha"] == SOURCE and p["lkg_sha"] == LKG
             and p["base_rollback_sha"] == LKG
             and p["native_create_only_rollback_sha"] == ZERO
             and p["freeze_sha256"] == FREEZE and p["promotion_hold_sha256"] == HOLD
             and p["runtime_image_sha256"] == RUNTIME_IMAGE
             and p["mcp_image_sha256"] == MCP_IMAGE
             and type(p["owner_decisions"]) is int and p["owner_decisions"] == 1
             and all(p[k] is True for k in (
                 "require_entrusted_owner_oauth", "require_independent_root_acceptance",
                 "require_native_breaker_closed",
                 "require_genuine_four_sqlite_and_restore_pass",
                 "require_current_drift_pass",
             ))
             and p["expected_existing_pinned_source_files"] == 13
             and p["expected_after_source_closure_files"] == 14
             and p["one_missing_root_file"] == str(MISSING)
             and p["one_missing_root_file_sha256"] == MISSING_SHA
             and p["archived_bootstrap_plan_path"] == str(BOOTSTRAP)
             and p["archived_onefile_proposal_path"] == str(ONEFILE)
             and p["archived_bootstrap_plan_sha256"] == REVIEWED_ACTIONS[0][3]
             and p["archived_onefile_proposal_sha256"]
                == "7a5752e80c378de8e3a5e9c4ad46132a46431be196c0e0fc4e9ac27c21a617e9",
             "OWNER_PLAN_REVIEW_PROTECTED_IDENTITY_CHANGED")
    _require(p["must_not_change"] == [
        "ticket_runtime", "mcp_image", "production_lkg_pointer",
        "production_freeze", "auto_promotion_hold", "provider_data",
    ], "OWNER_PLAN_REVIEW_DISALLOWED_EFFECT_CHANGED")
    rows = p["ordered_actions"]
    _require(isinstance(rows, list) and len(rows) == len(REVIEWED_ACTIONS),
             "OWNER_PLAN_REVIEW_UNEXPECTED_STAGE_COUNT")
    for row, (capability, component, scope, artifact) in zip(rows, REVIEWED_ACTIONS):
        _require(isinstance(row, dict)
                 and row == {
                     "capability": capability, "component": component,
                     "scope_sha256": scope, "artifact_sha256": artifact,
                     "rollback_sha": ZERO, "risk": 3,
                 }, "OWNER_PLAN_REVIEW_STEP_CHANGED")
    return p


def read_source_evidence(*, git: Path = GIT,
                         blob_revision: str = SOURCE) -> str:
    """Independently read exact Git object; never import mutable source."""
    _require(blob_revision == SOURCE, "OWNER_PLAN_REVIEW_SOURCE_REV_CHANGED")
    try:
        blob = subprocess.check_output([
            "git", "-c", "safe.directory=" + str(git), "-C", str(git),
            "show", SOURCE + ":tools/pmv4_host_install_contract.py",
        ], timeout=15)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PMv4StageA0ReviewDenied("OWNER_PLAN_REVIEW_GIT_BLOB_UNAVAILABLE") from exc
    _require(_hash(blob) == MISSING_SHA and len(blob) == 9571,
             "OWNER_PLAN_REVIEW_MISSING_BLOB_CHANGED")
    return _hash(blob)


def build_reviewed_plan(*, expires_at: datetime) -> BoundedObjective:
    """One *future* exact Owner decision, never an already approved release."""
    p = exact_contract()
    _require(isinstance(expires_at, datetime) and expires_at.tzinfo is not None,
             "OWNER_PLAN_REVIEW_EXACT_EXPIRY_REQUIRED")
    return BoundedObjective(
        plan_id="pmv4-a0-one-owner-source-closure-and-native-install",
        organization_id="aot", policy_digest=CONTRACT_SHA256,
        candidate_sha=SOURCE, rollback_sha=LKG,
        freeze_sha256=FREEZE, hold_sha256=HOLD,
        actions=tuple(ObjectiveAction(
            capability=x["capability"], component=x["component"],
            scope_sha256=x["scope_sha256"],
            artifact_sha256=x["artifact_sha256"], risk=x["risk"],
            rollback_sha=x["rollback_sha"],
        ) for x in p["ordered_actions"]),
        expires_at=expires_at,
    )


def read_archive_proof() -> None:
    """Live read-only source evidence; archived proposals grant NO authority."""
    p = exact_contract()
    sources = ((BOOTSTRAP, p["archived_bootstrap_plan_sha256"]),
               (ONEFILE, p["archived_onefile_proposal_sha256"]))
    for path, expected in sources:
        _require(path.is_file() and not path.is_symlink()
                 and _hash(path.read_bytes()) == expected,
                 "OWNER_PLAN_REVIEW_ARCHIVE_PACKET_CHANGED")
    bootstrap = json.loads(BOOTSTRAP.read_bytes())
    proposal = json.loads(ONEFILE.read_bytes())
    _require(bootstrap.get("scope_sha256") == REVIEWED_ACTIONS[0][2]
             and _hash(_canonical({
                 k:v for k,v in bootstrap.items() if k!="scope_sha256"
             })) == REVIEWED_ACTIONS[0][2]
             and bootstrap.get("source_sha") == SOURCE
             and bootstrap.get("lkg_sha") == LKG
             and bootstrap.get("approved_before_execution") is False
             and bootstrap.get("production_install_authorized") is False
             and bootstrap.get("freeze_sha256") == FREEZE
             and bootstrap.get("hold_sha256") == HOLD
             and len(bootstrap.get("files",[])) == 2,
             "OWNER_PLAN_REVIEW_BOOTSTRAP_INCOMPATIBLE")
    _require(proposal.get("proposal_sha256") == REVIEWED_ACTIONS[1][2]
             and _hash(_canonical({
                 k:v for k,v in proposal.items() if k!="proposal_sha256"
             })) == REVIEWED_ACTIONS[1][2]
             and proposal.get("source_revision") == SOURCE
             and proposal.get("production_current_lkg_sha") == LKG
             and proposal.get("next_native_stage_a0_scope_sha256") == NATIVE_SCOPE
             and proposal.get("next_native_stage_a0_manifest_sha256") == NATIVE_MANIFEST
             and proposal.get("one_added_file",{}).get("path") == str(MISSING)
             and proposal["one_added_file"]["sha256"] == MISSING_SHA
             and proposal.get("root_approved") is False
             and proposal.get("production_apply_supported") is False,
             "OWNER_PLAN_REVIEW_ONEFILE_INCOMPATIBLE")


def _read_live_host() -> None:
    """Current root readback only, no request, authorizations, or side effects."""
    import datetime as dt
    _require(subprocess.check_output([
        "git", "-C", str(GIT), "rev-parse", "origin/main",
    ], text=True, timeout=8).strip() == SOURCE,
             "OWNER_PLAN_REVIEW_PROTECTED_MAIN_CHANGED")
    _require(Path("/opt/jason/current").resolve(strict=True).name == LKG,
             "OWNER_PLAN_REVIEW_LKG_CHANGED")
    control = Path("/var/lib/jason/openclaw/release-manager")
    _require(_hash((control/"production-deployment-freeze").read_bytes()) == FREEZE
             and _hash((control/"auto-promotion-incident-hold").read_bytes()) == HOLD,
             "OWNER_PLAN_REVIEW_FREEZE_OR_HOLD_CHANGED")
    readback = control/"protected-readback"
    native = json.loads((readback/"production-control-state.json").read_bytes())
    drift = json.loads((readback/"production-drift.json").read_bytes())
    _require(native.get("circuit_breaker",{}).get("state") == "closed"
             and native["circuit_breaker"].get("revalidated_revision") == LKG
             and drift.get("status") == "pass" and drift.get("problems") == [],
             "OWNER_PLAN_REVIEW_NATIVE_BREAKER_NOT_READY")
    stamp = dt.datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))
    age = (dt.datetime.now(dt.timezone.utc)-stamp).total_seconds()
    _require(stamp.tzinfo is not None and -10 <= age <= 180,
             "OWNER_PLAN_REVIEW_DRIFT_STALE")
    root = Path("/var/lib/jason/openclaw")
    full = json.loads((root/"operational-full-health.json").read_bytes())
    fast = json.loads((root/"operational-health.json").read_bytes())
    _require(full.get("status") == fast.get("status") == "pass"
             and full.get("failures") == fast.get("failures") == []
             and fast.get("full_proof_status") == "pass"
             and all(full.get("files",{}).get(name,{}).get("integrity") == "ok"
                     for name in ("authority","orchestration_audit","replay","security_audit"))
             and all(full.get("backup_restore_proof",{}).get(k) == "ok"
                     for k in ("backup_integrity","restore_integrity")),
             "OWNER_PLAN_REVIEW_REAL_INTEGRITY_NOT_PASS")
    _require(not MISSING.exists() and not MISSING.is_symlink(),
             "OWNER_PLAN_REVIEW_ROOT_SOURCE_ALREADY_PRESENT")
    files = [path for path in RELEASE_ROOT.rglob("*") if path.is_file()]
    _require(len(files) == 13 and all(
        not f.is_symlink() and f.lstat().st_uid == 0 and f.lstat().st_gid == 0
        and stat.S_IMODE(f.lstat().st_mode) == 0o444
        for f in files), "OWNER_PLAN_REVIEW_EXISTING_ROOT_SPARSE_CHANGED")
    for obj in (Path("/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py"),
                Path("/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json")):
        _require(not obj.exists() and not obj.is_symlink(),
                 "OWNER_PLAN_REVIEW_HELPER_ALREADY_PRESENT")
    result = subprocess.check_output([
        "docker", "inspect", "jason-runtime", "jason-mcp-pilot",
        "--format", "{{.Name}} {{.Image}} {{.State.Status}}",
    ], text=True, timeout=15)
    _require(("/jason-runtime "+RUNTIME_IMAGE+" running") in result
             and ("/jason-mcp-pilot "+MCP_IMAGE+" running") in result,
             "OWNER_PLAN_REVIEW_PRODUCTION_IMAGES_CHANGED")


def verify_review(*, repo: Path = ROOT, live: bool = False) -> dict[str, Any]:
    exact_contract()
    read_source_evidence(git=repo)
    if live:
        read_archive_proof()
        _read_live_host()
    return {
        "status": "verified_source_only_no_root_authority",
        "contract_sha256": CONTRACT_SHA256,
        "source_sha": SOURCE, "lkg_sha": LKG,
        "steps": len(REVIEWED_ACTIONS),
        "owner_decisions_in_future": 1,
        "native_breaker_live_preflight": "pass" if live else "not_requested",
        "production_approval_issued": False, "root_mutations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--live-readonly", action="store_true")
    args = parser.parse_args()
    if not args.check_only:
        raise SystemExit("DENIED: only --check-only supported")
    print(json.dumps(verify_review(live=args.live_readonly),sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
