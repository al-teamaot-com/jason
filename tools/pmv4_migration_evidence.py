#!/usr/bin/env python3
"""Read-only exact-source PMv4 migration evidence packet (never a release).

Uses authoritative protected GitHub, local Docker image provenance and host
control-file hashes. It *never* issues Owner approvals, deploys containers,
modifies production, reads provider tokens or treats PR CI as release authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

REPO = "al-teamaot-com/jason"
EXPECTED_PRS = {
    "dependency_audit": 2436,
    "runbook_management": 2437,
    "ticket_core": 2438,
    "independent_release_recovery": 2440,
}
IMAGE_NAMES = (
    "jason-runtime:production", "jason-runtime:rollback-current",
    "jason-mcp:production", "jason-mcp:rollback-current",
)
HASHED_HOLDS = {
    "pmv3_engineering_owner_pause":
        "/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json",
    "automatic_promotion_hold":
        "/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold",
    "protected_production_control_state":
        "/var/lib/jason/openclaw/release-manager/production-control-state.json",
}
SHA = re.compile(r"\A[0-9a-f]{40}\Z")
REQUIRED_SOURCE_CHECKS = frozenset((
    "cap-001", "cap-003", "cap-007", "system-registry",
    "runtime-service", "repository-hygiene",
    "conversation-experience", "teams-gateway",
))


class MigrationEvidenceDenied(RuntimeError):
    pass


def _call(argv: list[str]) -> Any:
    result = subprocess.run(
        argv, shell=False, check=False,
        capture_output=True, text=True, timeout=40,
    )
    if result.returncode != 0 or len(result.stdout) > 2 * 1024 * 1024:
        raise MigrationEvidenceDenied("PMV4_MIGRATION_AUTHORITATIVE_READ_UNAVAILABLE")
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise MigrationEvidenceDenied("PMV4_MIGRATION_JSON_INVALID") from exc


def _github_pr(number: int) -> dict[str, Any]:
    item = _call([
        "/usr/bin/gh", "pr", "view", str(number), "--repo", REPO,
        "--json", "state,isDraft,headRefOid,baseRefName,files",
    ])
    checks = _call([
        "/usr/bin/gh", "pr", "checks", str(number), "--repo", REPO,
        "--json", "name,bucket",
    ])
    sha = item.get("headRefOid")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise MigrationEvidenceDenied("PMV4_MIGRATION_PR_SHA_UNVERIFIED")
    files = item.get("files")
    if not isinstance(files, list) or not files or len(files) > 150:
        raise MigrationEvidenceDenied("PMV4_MIGRATION_SCOPE_UNAVAILABLE")
    names = sorted({str(f["path"]) for f in files if isinstance(f, dict) and "path" in f})
    if len(names) != len(files) or any(
        not path or path.startswith("/") or ".." in path.split("/") for path in names
    ):
        raise MigrationEvidenceDenied("PMV4_MIGRATION_SCOPE_UNTRUSTED")
    if not isinstance(checks, list) or not checks:
        raise MigrationEvidenceDenied("PMV4_MIGRATION_CI_UNAVAILABLE")
    buckets = {key: sum(i.get("bucket") == key for i in checks)
               for key in ("pass", "fail", "pending", "skipping", "cancel")}
    check_names = {str(item.get("name")) for item in checks if isinstance(item, dict)}
    complete_source_checks = REQUIRED_SOURCE_CHECKS.issubset(check_names)
    green = (
        complete_source_checks
        and buckets["fail"] == buckets["pending"] == buckets["cancel"] == 0
        and all(
            item.get("bucket") == "pass"
            for item in checks if item.get("name") in REQUIRED_SOURCE_CHECKS
        )
    )
    return {
        "pr": number, "source_sha": sha,
        "state": item.get("state"), "draft": item.get("isDraft"),
        "base_branch": item.get("baseRefName"),
        "scope_files": names,
        "scope_sha256": sha256(json.dumps(
            {"source_sha": sha, "files": names}, sort_keys=True,
            separators=(",", ":"),
        ).encode()).hexdigest(),
        "ci": buckets,
        "required_source_checks_present": complete_source_checks,
        "preproduction_checks_green": green,
    }


def _image(name: str) -> dict[str, str]:
    raw = _call(["/usr/bin/docker", "image", "inspect", name])
    if not isinstance(raw, list) or len(raw) != 1:
        raise MigrationEvidenceDenied("PMV4_MIGRATION_IMAGE_INSPECT_INVALID")
    item = raw[0]
    digest = item.get("Id")
    revision = (item.get("Config") or {}).get("Labels", {}).get(
        "com.teamaot.jason.source_revision"
    )
    if (not isinstance(digest, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        or not isinstance(revision, str) or not SHA.fullmatch(revision)):
        raise MigrationEvidenceDenied("PMV4_MIGRATION_IMAGE_PROVENANCE_INVALID")
    return {"image_id": digest, "source_revision": revision}


def _file_status(name: str, path: str) -> dict[str, Any]:
    file = Path(path)
    try:
        if file.is_symlink() or not file.is_file():
            return {"name": name, "status": "absent_or_untrusted"}
        return {"name": name, "status": "readable",
                "sha256": sha256(file.read_bytes()).hexdigest()}
    except OSError:
        return {"name": name, "status": "restricted_root_readback_needed"}


def _main_sha() -> str:
    obj = _call(["/usr/bin/gh", "api", f"repos/{REPO}/branches/main"])
    rev = (obj.get("commit") or {}).get("sha")
    if obj.get("name") != "main" or obj.get("protected") is not True:
        raise MigrationEvidenceDenied("PMV4_MIGRATION_PROTECTED_MAIN_UNVERIFIED")
    if not isinstance(rev, str) or not SHA.fullmatch(rev):
        raise MigrationEvidenceDenied("PMV4_MIGRATION_MAIN_SHA_UNVERIFIED")
    return rev


def build_packet() -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    main_sha = _main_sha()
    current = Path("/opt/jason/current")
    if not current.is_symlink():
        raise MigrationEvidenceDenied("PMV4_MIGRATION_LIVE_SOURCE_POINTER_UNVERIFIED")
    active = current.resolve(strict=True)
    if active.parent != Path("/opt/jason/releases") or not SHA.fullmatch(active.name):
        raise MigrationEvidenceDenied("PMV4_MIGRATION_LIVE_SOURCE_POINTER_MISMATCH")
    images = {name: _image(name) for name in IMAGE_NAMES}
    installed_sha = active.name
    if (images["jason-runtime:production"]["source_revision"] != installed_sha
        or images["jason-mcp:production"]["source_revision"] != installed_sha
        or images["jason-runtime:rollback-current"]["source_revision"]
        != images["jason-mcp:rollback-current"]["source_revision"]):
        raise MigrationEvidenceDenied("PMV4_MIGRATION_RUNTIME_OR_ROLLBACK_DRIFT")
    candidates = {name: _github_pr(pr) for name, pr in EXPECTED_PRS.items()}
    holds = {name: _file_status(name, path) for name, path in HASHED_HOLDS.items()}
    # These are immutable SOURCE candidates, not a combined release SHA.
    # The protected-main SHA changes after merges and must be re-attested.
    controls_root = Path("/var/lib/jason/pmv4-shadow/control")
    control_lock = controls_root / "host-mutation.lock"
    owner_trust = Path("/etc/jason/pmv4-shadow/owner-release-trust.json")
    controls_provisioned = (
        controls_root.is_dir() and control_lock.is_file()
        and owner_trust.is_file()
    )
    return {
        "schema_version": "1.0",
        "status": "preproduction_evidence_only_not_release_authorized",
        "observed_at": now,
        "repository": REPO,
        "protected_main_sha": main_sha,
        "production_active_source_sha": installed_sha,
        "production_source_aligned_with_main": installed_sha == main_sha,
        "production_current_and_rollback_images": images,
        "rollback_image_source_sha":
            images["jason-runtime:rollback-current"]["source_revision"],
        "source_candidates": candidates,
        "protected_control_files": holds,
        "independent_host_control_provisioned": controls_provisioned,
        "exact_production_release_candidate_sha": None,
        "owner_exact_action_approval_recorded": False,
        "production_changes_made": False,
        "migration_order": [
            "M0 source/CI/scope/rollback/Owner release evidence",
            "M1 standalone PMv4 disconnected shadow release and rollback",
            "M2 lock-aware embedded Ticket Core first, external owner cutover second",
            "M3 Runbook Management independent JSON lifecycle",
            "M4 legacy PMv3 service and policy retirement after new controller parity",
        ],
        "blocking_release_gates": [
            "candidate PRs must merge through protected main and receive new exact SHA/CI",
            "trusted Owner Entra issuer and exact signed release scope not provisioned",
            "PMv4 host-control lock, independent signed trust and adapter not installed",
            "root-protected production control/readback evidence required",
            "legacy embedded worker does not honor new lock until governed M2 bootstrap",
            "two live post-cutover ticket scans and controlled provider readback not yet verified",
            "component-scoped live PMv4 release/rollback parity not yet accepted",
            "protected desired-state PMv3 unit retirement requires later exact scoped approval",
        ],
    }


def main() -> int:
    print(json.dumps(build_packet(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
