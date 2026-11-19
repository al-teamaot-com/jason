#!/usr/bin/env python3
"""Single exact-Owner correction for four already-installed scoped release units.

Source-only until reviewed CI, protected-main merge and interactive Owner
authentication. Changes only the existing root-owned desired-state allowlist;
never restarts Jason containers, unfreezes production, writes Graph, edits
service files, or force-closes the circuit breaker.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time

SOURCE_REPO = Path(__file__).resolve().parents[1]
ROOT_POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
ROOT_INSTALL = Path("/etc/jason-owner-release/scoped-backport-installed.json")
ROOT_INSTALL_DIR = Path("/usr/local/lib/jason/scoped-backport")
ROOT_PUBLIC_ATTEST = Path(
    "/etc/jason-owner-release/scoped-backport-public-attestation.json")
ROOT_PATCH = {
    "tools/scoped_backport_release.py": "core_sha256",
    "tools/scoped_backport_native_root.py": "root_handler_sha256",
}
SCOPED_REQUESTS = Path("/var/lib/jason/authority/scoped-backport-release/requests")
SCOPED_TRANSACTIONS = Path("/var/lib/jason-scoped-backport/transactions")
SCOPED_OFFERS = Path("/var/lib/jason-scoped-backport/offers")
SCOPED_PATH = "jason-scoped-backport-requests.path"
SCOPED_TIMER = "jason-scoped-backport-recovery.timer"
ROOT_AUDIT = Path("/etc/jason-owner-release/scoped-backport-four-unit-drift")
ROOT_CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
ROOT_DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
VERIFIER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
VERIFIER_SHA256 = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
OWNER_OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
GUARD = Path("/opt/jason/current/tools/production_drift_guard.py")
INSTALLED_SHA = "6adc19744fc7464ef3ba34d1ce0b3b20e9e69684"
ROLLBACK_SHA = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE_SHA256 = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
CONFIRM = "APPROVE-FOUR-UNIT-SCOPED-BACKPORT-DRIFT-RECONCILE"
UNIT_NAMES = (
    "jason-scoped-backport-recovery.service",
    "jason-scoped-backport-recovery.timer",
    "jason-scoped-backport-requests.path",
    "jason-scoped-backport-requests.service",
)
ROOT_UNIT_DIGESTS = {
    UNIT_NAMES[0]: "recovery_unit_sha256",
    UNIT_NAMES[1]: "recovery_timer_sha256",
    UNIT_NAMES[2]: "request_path_sha256",
    UNIT_NAMES[3]: "request_unit_sha256",
}
PROTECTED = (
    "jason-runtime", "jason-mcp-pilot", "jason-pmv4-ticket-core",
    "jason-pmv4-shadow-gateway", "jason-teams-gateway", "openbao",
)
SHA = re.compile(r"^[0-9a-f]{40}$")


class DriftCorrectionDenied(PermissionError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise DriftCorrectionDenied("SCOPED_DRIFT_" + reason)


def canonical(v) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def git(*args: str) -> bytes:
    p = subprocess.run(["git", "-c", f"safe.directory={SOURCE_REPO}",
                        "-C", str(SOURCE_REPO), *args],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       check=False, timeout=25)
    need(p.returncode == 0, "SOURCE_GIT_UNAVAILABLE")
    return p.stdout


def require_ci_green(reviewed_sha: str) -> None:
    """Never run a privileged correction from an unreviewed commit."""
    import urllib.request
    required = frozenset((
        "repository-hygiene", "documentation", "runtime-service",
        "governed-security-regressions", "GitGuardian Security Checks",
    ))
    url = ("https://api.github.com/repos/al-teamaot-com/jason/commits/"
           + reviewed_sha + "/check-runs?per_page=100")
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": "jason-scoped-drift-source-admission"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read(524288))
    except (OSError, ValueError) as exc:
        raise DriftCorrectionDenied("SCOPED_DRIFT_CI_EVIDENCE_UNAVAILABLE") from exc
    runs = data.get("check_runs") if isinstance(data, dict) else None
    need(isinstance(runs, list) and len(runs) <= 100,
         "CI_EVIDENCE_FORMAT_INVALID")
    checks = {}
    for item in runs:
        if isinstance(item, dict) and item.get("name") in required:
            name = item["name"]
            if name not in checks or item.get("id", 0) > checks[name].get("id", 0):
                checks[name] = item
    need(required.issubset(checks), "REQUIRED_CI_CHECK_UNAVAILABLE")
    need(all(checks[n].get("conclusion") == "success"
             and checks[n].get("status") == "completed" for n in required),
         "REQUIRED_CI_NOT_GREEN")


def verify_source(source_sha: str, reviewed_sha: str) -> None:
    need(SHA.fullmatch(source_sha) is not None and
         SHA.fullmatch(reviewed_sha) is not None,
         "SOURCE_IDENTITIES_INVALID")
    need(git("rev-parse", "HEAD").decode().strip() == source_sha
         and git("status", "--porcelain") == b"", "SOURCE_NOT_EXACT_CLEAN")
    main = git("ls-remote", "origin", "refs/heads/main").decode().strip()
    need(main == source_sha + "\trefs/heads/main", "PROTECTED_MAIN_MOVED")
    need(git("remote", "get-url", "origin").decode().strip() in {
        "https://github.com/al-teamaot-com/jason.git",
        "https://github.com/al-teamaot-com/jason",
    }, "SOURCE_ORIGIN_NOT_AOT")
    rel = "tools/scoped_backport_four_unit_drift_reconcile.py"
    need((SOURCE_REPO / rel).read_bytes() ==
         git("show", source_sha + ":" + rel) ==
         git("show", reviewed_sha + ":" + rel),
         "ROOT_BOOTSTRAP_NOT_CI_REVIEWED")
    require_ci_green(reviewed_sha)


def read_root(path: Path, *, mode=0o600, maxsize=131072) -> bytes:
    need(not path.is_symlink() and path.is_file(), "ROOT_FILE_MISSING")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0
             and stat.S_IMODE(meta.st_mode) == mode and meta.st_nlink == 1
             and 0 < meta.st_size <= maxsize, "ROOT_FILE_META_INVALID")
        raw = os.read(fd, maxsize + 1)
        need(len(raw) == meta.st_size, "ROOT_FILE_CHANGED")
        return raw
    finally:
        os.close(fd)


def root_json(path: Path) -> dict:
    d = json.loads(read_root(path))
    need(isinstance(d, dict) and d.get("schema_version") == "1.0",
         "ROOT_SCHEMA_INVALID")
    return d


def candidate_policy(baseline: bytes) -> tuple[dict, bytes]:
    doc = json.loads(baseline)
    need(isinstance(doc, dict) and doc.get("schema_version") == "1.0",
         "POLICY_SCHEMA_INVALID")
    allowed = doc.get("allowed_system_units")
    required = doc.get("required_system_units")
    need(isinstance(allowed, list) and isinstance(required, list)
         and len(allowed) == len(set(allowed))
         and len(required) == len(set(required))
         and all(isinstance(k, str) for k in allowed + required)
         and all(k not in allowed + required for k in UNIT_NAMES),
         "POLICY_EXACT_FOUR_UNIT_GAP_NOT_PRESENT")
    # The governed PMv4-D root overlay approved 21 retained rollback images.
    # Preserve this exact baseline and reject obsolete or relaxed values.
    need(doc.get("max_stopped_rollback_containers") == 21,
         "POLICY_ROLLBACK_CAPACITY_CHANGED")
    doc["allowed_system_units"] = sorted(allowed + list(UNIT_NAMES))
    return doc, (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode()


def eval_guard(config: Path) -> dict:
    p = subprocess.run(["/usr/bin/python3", str(GUARD), "--config", str(config)],
                       capture_output=True, text=True, timeout=90)
    need(p.returncode in (0, 2) and len(p.stdout) < 200_000,
         "INDEPENDENT_DRIFT_GUARD_UNAVAILABLE")
    doc = json.loads(p.stdout)
    need(isinstance(doc, dict) and doc.get("schema_version") == "1.0"
         and isinstance(doc.get("problems"), list),
         "INDEPENDENT_DRIFT_GUARD_INVALID")
    return doc


def check_only_expected_drift(report: dict) -> None:
    actual = {(p.get("kind"), p.get("unit"))
              for p in report.get("problems", []) if isinstance(p, dict)}
    expected = {("undeclared_installed_system_unit", name)
                for name in UNIT_NAMES}
    allowed_extra = {("failed_system_unit", "jason-production-drift-watchdog.service")}
    need(report["status"] == "drift_detected"
         and expected.issubset(actual)
         and actual.issubset(expected | allowed_extra)
         and len(actual) == len(report["problems"]),
         "UNRELATED_PRODUCTION_DRIFT_PRESENT")


def live_snapshot() -> dict:
    p = subprocess.run(["docker", "inspect", *PROTECTED],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       timeout=25, check=False)
    need(p.returncode == 0, "LIVE_CONTAINERS_UNAVAILABLE")
    rows = json.loads(p.stdout)
    need(len(rows) == len(PROTECTED), "LIVE_CONTAINER_COUNT_INVALID")
    result = {}
    for item in rows:
        name = item["Name"].lstrip("/")
        need(name in PROTECTED and item["State"]["Running"],
             "PRODUCTION_CONTAINER_UNEXPECTED")
        result[name] = {
            "id": item["Id"], "image": item["Image"],
            "started_at": item["State"]["StartedAt"],
        }
    need(set(result) == set(PROTECTED), "LIVE_CONTAINERS_NOT_EXACT")
    return result


def public_attestation(policy: dict) -> dict:
    fields = ("trusted_source_sha", "reviewed_ci_sha",
              "root_handler_sha256")
    need(policy.get("profile") == "governed-scoped-backport-v1"
         and all(isinstance(policy.get(k), str) for k in fields),
         "ROOT_CONTROL_ATTESTATION_SCHEMA_INVALID")
    return {
        "schema_version": "1.0", "profile": policy["profile"],
        **{name: policy[name] for name in fields},
        "native_root_control_supported": True,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
    }


def root_control_upgrade(old_policy: dict, *, source_sha: str,
                         reviewed_sha: str) -> dict:
    """Only two installed code files and their exact trust receipts change."""
    private = dict(old_policy)
    need(private.get("trusted_source_sha") == INSTALLED_SHA
         and private.get("profile") == "governed-scoped-backport-v1"
         and private.get("automatic_rollback_recovery_installed") is True
         and private.get("exact_signed_owner_approval_required") is True,
         "INSTALLED_ROOT_CONTROL_SOURCE_NOT_PREAPPROVED")
    before = {}
    after = {}
    for rel, field in ROOT_PATCH.items():
        installed = ROOT_INSTALL_DIR / rel
        raw = read_root(installed, mode=0o444, maxsize=1_000_000)
        need(sha256(raw).hexdigest() == private.get(field),
             "PINNED_ROOT_INSTALLED_FILE_DRIFT")
        changed = (SOURCE_REPO / rel).read_bytes()
        need(changed == git("show", source_sha + ":" + rel)
             == git("show", reviewed_sha + ":" + rel),
             "ROOT_PATCH_NOT_REVIEWED_IN_CI")
        need(changed != raw, "ROOT_CORRECTIVE_PATCH_NOT_PRESENT")
        before[installed] = raw
        after[installed] = changed
        private[field] = sha256(changed).hexdigest()
    private["trusted_source_sha"] = source_sha
    private["reviewed_ci_sha"] = reviewed_sha
    old_private_raw = read_root(ROOT_INSTALL)
    old_public_raw = read_root(ROOT_PUBLIC_ATTEST, mode=0o644)
    old_public = json.loads(old_public_raw)
    need(old_public == public_attestation(old_policy),
         "INSTALLED_PUBLIC_PRIVATE_POLICY_DIFFERENT")
    after_public = public_attestation(private)
    return {
        "old_private": old_policy, "old_private_raw": old_private_raw,
        "new_private": private,
        "new_private_raw": (json.dumps(
            private, sort_keys=True, indent=2) + "\n").encode(),
        "old_public": old_public, "old_public_raw": old_public_raw,
        "new_public": after_public,
        "new_public_raw": (json.dumps(
            after_public, sort_keys=True, indent=2) + "\n").encode(),
        "before_files": before,
        "after_files": after,
    }


def inspect(*, source_sha: str, reviewed_sha: str) -> dict:
    need(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "al",
         "LOCAL_AUTHENTICATED_ROOT_REQUIRED")
    verify_source(source_sha, reviewed_sha)
    installed = root_json(ROOT_INSTALL)
    need(installed.get("trusted_source_sha") == INSTALLED_SHA
         and installed.get("profile") == "governed-scoped-backport-v1",
         "SCOPED_ROOT_INSTALL_IDENTITY_DRIFT")
    for unit in UNIT_NAMES:
        p = Path("/etc/systemd/system") / unit
        expected = installed[ROOT_UNIT_DIGESTS[unit]]
        # The approved root installer deliberately materialized read-only
        # systemd units as root:root 0444. Enforce the ACTUAL reviewed mode.
        need(sha256(read_root(p, mode=0o444)).hexdigest() == expected,
             "INSTALLED_UNIT_BYTES_CHANGED")
    upgrade = root_control_upgrade(
        installed, source_sha=source_sha, reviewed_sha=reviewed_sha)
    for folder in (SCOPED_REQUESTS, SCOPED_TRANSACTIONS, SCOPED_OFFERS):
        need(folder.is_dir() and not folder.is_symlink()
             and not any(folder.iterdir()), "UNRESOLVED_SCOPED_RELEASE_WORK")
    for name in (SCOPED_PATH, SCOPED_TIMER):
        need(subprocess.run(["systemctl", "is-enabled", name],
                            capture_output=True, timeout=12).stdout.strip() == b"enabled"
             and subprocess.run(["systemctl", "is-active", name],
                                capture_output=True, timeout=12).stdout.strip() == b"active",
             "SCOPED_ROOT_LISTENER_NOT_HEALTHY")
    need(Path("/opt/jason/current").resolve(strict=True).name == ROLLBACK_SHA,
         "PRODUCTION_LKG_CHANGED")
    need(sha256(FREEZE.read_bytes()).hexdigest() == FREEZE_SHA256,
         "PRODUCTION_FREEZE_CHANGED")
    hold_sha = sha256(HOLD.read_bytes()).hexdigest()
    # The root evaluator must remain identical to the independently
    # deployed LKG source; a mutable helper is never an authority boundary.
    guard_bytes = git("show", ROLLBACK_SHA + ":tools/production_drift_guard.py")
    need(GUARD.read_bytes() == guard_bytes, "IMMUTABLE_LKG_GUARD_DRIFT")
    current = root_json(ROOT_CONTROL)
    breaker = current.get("circuit_breaker") or {}
    need(breaker.get("state") == "open"
         and breaker.get("source") == "production_drift_watchdog"
         and (current.get("last_known_good") or {}).get("manifest", {}).get("revision") == ROLLBACK_SHA,
         "UNEXPECTED_OPEN_BREAKER_SOURCE")
    baseline = read_root(ROOT_POLICY)
    proposal, candidate = candidate_policy(baseline)
    check_only_expected_drift(eval_guard(ROOT_POLICY))
    original = live_snapshot()
    plan = {
        "schema_version": "1.0", "action": "scoped-backport-four-unit-and-source-trust-correction",
        "source_sha": source_sha, "reviewed_sha": reviewed_sha,
        "installed_source_sha": INSTALLED_SHA,
        "baseline_policy_sha256": sha256(baseline).hexdigest(),
        "candidate_policy_sha256": sha256(candidate).hexdigest(),
        "freeze_sha256": FREEZE_SHA256, "hold_sha256": hold_sha,
        "rollback_sha": ROLLBACK_SHA,
        "unit_names": list(UNIT_NAMES),
        "allowed_change": "root_desired_state_allowlist_four_names_only",
        "root_trust_change": "two_exact_reviewed_source_files_and_policy_receipts",
        "root_source_file_sha256_after": {
            rel: sha256(upgrade["after_files"][ROOT_INSTALL_DIR / rel]).hexdigest()
            for rel in ROOT_PATCH
        },
        "root_private_policy_sha256_before":
            sha256(upgrade["old_private_raw"]).hexdigest(),
        "root_private_policy_sha256_after":
            sha256(upgrade["new_private_raw"]).hexdigest(),
        "root_public_policy_sha256_before":
            sha256(upgrade["old_public_raw"]).hexdigest(),
        "root_public_policy_sha256_after":
            sha256(upgrade["new_public_raw"]).hexdigest(),
        "listener_pause_resume": [SCOPED_PATH, SCOPED_TIMER],
        "watchdog_oneshot": True, "rollback_on_failure": True,
        "manual_breaker_override": False, "release_approval": False,
        "graph_mutations": False, "runtime_mcp_restarts": False,
        "standing_authority": False,
    }
    plan["scope_sha256"] = sha256(canonical(plan)).hexdigest()
    return {"plan": plan, "baseline": baseline, "candidate": candidate,
            "before": original, "policy": proposal, "upgrade": upgrade}


@contextmanager
def production_lock():
    fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == pwd.getpwnam("al").pw_uid,
             "TRANSACTION_LOCK_UNTRUSTED")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_policy(raw: bytes) -> None:
    old = read_root(ROOT_POLICY)
    need(bool(old), "ROOT_POLICY_DISAPPEARED")
    fd, temp = tempfile.mkstemp(prefix=".scoped-backport-drift-", dir=ROOT_POLICY.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.chown(temp, 0, 0)
        os.chmod(temp, 0o600)
        os.replace(temp, ROOT_POLICY)
        dfd = os.open(ROOT_POLICY.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def approved_root_file_changes(preflight: dict):
    """Immutable in-memory exact old/new bytes; no caller supplied paths."""
    u = preflight["upgrade"]
    paths = []
    for path in sorted(u["before_files"]):
        paths.append((path, u["before_files"][path],
                      u["after_files"][path], 0o444))
    paths.extend([
        (ROOT_INSTALL, u["old_private_raw"], u["new_private_raw"], 0o600),
        (ROOT_PUBLIC_ATTEST, u["old_public_raw"], u["new_public_raw"], 0o644),
        (ROOT_POLICY, preflight["baseline"], preflight["candidate"], 0o600),
    ])
    need(len(paths) == 5 and len({p for p, *_ in paths}) == 5,
         "ROOT_UPDATE_FILE_SCOPE_NOT_EXACT")
    return paths


def atomic_exact_root_file(path: Path, expected: bytes, target: bytes,
                           mode: int) -> None:
    """Replace one root-owned file, only when its expected bytes still match."""
    need(mode in (0o444, 0o600, 0o644), "ROOT_FILE_MODE_NOT_ALLOWLISTED")
    need(read_root(path, mode=mode, maxsize=1_000_000) == expected,
         "ROOT_FILE_CHANGED_UNDER_TRANSACTION")
    fd, temp = tempfile.mkstemp(prefix=".scoped-root-correct-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(target)
            out.flush()
            os.fsync(out.fileno())
        os.chown(temp, 0, 0)
        os.chmod(temp, mode)
        os.replace(temp, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        need(read_root(path, mode=mode, maxsize=1_000_000) == target,
             "ROOT_CORRECTIVE_READBACK_FAILED")
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def restore_attempted_root_files(attempted_changes) -> None:
    """Restore only recorded prior bytes, never overwrite foreign changes."""
    for path, old_bytes, new_bytes, mode in reversed(attempted_changes):
        current = read_root(path, mode=mode, maxsize=1_000_000)
        if current == new_bytes:
            atomic_exact_root_file(path, new_bytes, old_bytes, mode)
        else:
            need(current == old_bytes,
                 "FOREIGN_ROOT_CHANGE_PREVENTS_ROLLBACK")


def listener_action(action: str) -> None:
    need(action in ("start", "stop"), "SCOPED_LISTENER_ACTION_UNSUPPORTED")
    cmd = ["/usr/bin/systemctl", action, SCOPED_PATH, SCOPED_TIMER]
    p = subprocess.run(cmd, capture_output=True, timeout=45)
    need(p.returncode == 0, "SCOPED_LISTENER_" + action.upper() + "_FAILED")
    expected = "active" if action == "start" else "inactive"
    for name in (SCOPED_PATH, SCOPED_TIMER):
        result = subprocess.run(["systemctl", "is-active", name],
                                capture_output=True, timeout=12)
        need(result.stdout.strip() == expected.encode(),
             "SCOPED_LISTENER_STATE_NOT_" + expected.upper())


def ensure_scoped_oneshots_quiescent() -> None:
    """Never replace root code while either scoped root worker is executing."""
    for name in ("jason-scoped-backport-requests.service",
                 "jason-scoped-backport-recovery.service"):
        result = subprocess.run(["/usr/bin/systemctl", "is-active", name],
                                capture_output=True, timeout=12)
        need(result.stdout.strip() == b"inactive",
             "ROOT_WORKER_NOT_QUIESCENT")


def read_only_stage_probe() -> str:
    """Run ONLY the independently installed root worker's read-only probe.

    Never import caller-worktree code in the root process or treat a
    developer-owned PYTHONPATH as trusted code. The root-installed handler
    independently re-verifies pinned SHA policy and all source/images.
    """
    path = ROOT_INSTALL_DIR / "tools/scoped_backport_native_root.py"
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "-I", str(path), "--probe-stage"],
            capture_output=True, timeout=130, check=False)
        if len(result.stdout) > 4096:
            return "SCOPED_BACKPORT_STAGE_PROBE_RESULT_TOO_LARGE"
        doc = json.loads(result.stdout)
        if (not isinstance(doc, dict)
                or doc.get("production_mutations") is not False
                or doc.get("provider_writes") is not False):
            return "SCOPED_BACKPORT_STAGE_PROBE_OUTPUT_UNTRUSTED"
        if (result.returncode == 0 and
                doc.get("status") == "scoped_native_readonly_stage_preflight_pass"
                and doc.get("release_eligibility_created") is False
                and doc.get("owner_approval_recorded") is False):
            return "pass_nonmutating_scoped_source_and_docker_preflights"
        if (result.returncode == 2 and
                doc.get("status") == "scoped_native_readonly_stage_preflight_denied"):
            reason = doc.get("denial_code")
            if isinstance(reason, str) and re.fullmatch(
                    r"SCOPED_BACKPORT_[A-Z0-9_]{2,96}", reason):
                return reason
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return "SCOPED_BACKPORT_UNCLASSIFIED_STAGE_PROBE_DENIAL"


def audit_once(path: Path, doc: dict) -> None:
    raw = canonical(doc) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def owner_sign_in() -> str:
    meta = VERIFIER.lstat()
    need(not VERIFIER.is_symlink() and stat.S_ISREG(meta.st_mode)
         and meta.st_uid == 0 and not meta.st_mode & 0o022
         and sha256(VERIFIER.read_bytes()).hexdigest() == VERIFIER_SHA256,
         "PINNED_OWNER_VERIFIER_DRIFT")
    spec = importlib.util.spec_from_file_location("scoped_unit_drift_owner", VERIFIER)
    need(spec is not None and spec.loader is not None,
         "OWNER_VERIFIER_UNAVAILABLE")
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    need(auth.TENANT == TENANT and
         OWNER_OID in frozenset(auth.OWNERS)
         and auth.CLIENT_ID == "9b9996e9-5c34-48b7-948c-f44f89352f89",
         "OWNER_VERIFIER_TENANT_MISMATCH")
    uri = "https://login.microsoftonline.com/" + TENANT + "/oauth2/v2.0/"
    challenge = auth._form(uri + "devicecode", {"client_id": auth.CLIENT_ID,
                                                 "scope": auth.SCOPE})
    need(all(isinstance(challenge.get(x), str) for x in
             ("device_code", "user_code", "verification_uri")),
         "OWNER_DEVICE_FLOW_UNAVAILABLE")
    lifetime = min(600, int(challenge.get("expires_in") or 0))
    need(lifetime >= 60, "OWNER_LOGIN_TOO_SHORT")
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    until = time.monotonic() + lifetime
    interval = max(5, min(20, int(challenge.get("interval") or 5)))
    while time.monotonic() < until:
        time.sleep(interval)
        response = auth._form(uri + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": auth.CLIENT_ID,
            "device_code": challenge["device_code"],
        })
        if isinstance(response.get("access_token"), str):
            oid = auth.jwt_owner(response["access_token"])
            need(oid == OWNER_OID and oid in auth.OWNERS,
                 "OWNER_NOT_AUTHORITATIVE_AOT_OWNER")
            return oid
        if response.get("error") == "slow_down":
            interval = min(20, interval + 5)
        elif response.get("error") != "authorization_pending":
            need(False, "OWNER_LOGIN_REJECTED")
    need(False, "OWNER_LOGIN_EXPIRED")


def apply(*, source_sha: str, reviewed_sha: str) -> dict:
    before = inspect(source_sha=source_sha, reviewed_sha=reviewed_sha)
    plan = before["plan"]
    print("ACTION=" + plan["action"], flush=True)
    print("SOURCE_SHA=" + source_sha, flush=True)
    print("ROOT_POLICY_BEFORE_SHA256=" + plan["baseline_policy_sha256"], flush=True)
    print("ROOT_POLICY_AFTER_SHA256=" + plan["candidate_policy_sha256"], flush=True)
    print("ROOT_TRUST_PATCH_SHA256=" +
          plan["root_private_policy_sha256_after"], flush=True)
    print("ONE_USE_SCOPE_SHA256=" + plan["scope_sha256"], flush=True)
    print("UNITS=" + ",".join(UNIT_NAMES), flush=True)
    print("CONTAINER_RESTARTS=none; GRAPH_POST=false; UNFREEZE=false", flush=True)
    need(sys.stdin.isatty() and sys.stdout.isatty(),
         "OWNER_LOCAL_INTERACTIVE_TERMINAL_REQUIRED")
    oid = owner_sign_in()
    typed = input("Type " + CONFIRM +
                  " to authorize the four-unit policy and exact installed root trust correction: ")
    need(typed.strip() == CONFIRM, "OWNER_EXACT_DECISION_NOT_CONFIRMED")
    new = inspect(source_sha=source_sha, reviewed_sha=reviewed_sha)
    need(new["plan"] == plan and new["before"] == before["before"]
         and new["baseline"] == before["baseline"],
         "SCOPE_CHANGED_SINCE_OWNER_SIGN_IN")
    if not ROOT_AUDIT.exists():
        ROOT_AUDIT.mkdir(mode=0o700)
        os.chown(ROOT_AUDIT, 0, 0)
        os.chmod(ROOT_AUDIT, 0o700)
    need(not ROOT_AUDIT.is_symlink() and ROOT_AUDIT.is_dir()
         and ROOT_AUDIT.stat().st_uid == 0
         and stat.S_IMODE(ROOT_AUDIT.stat().st_mode) == 0o700,
         "ROOT_AUDIT_DIRECTORY_UNTRUSTED")
    attempted = ROOT_AUDIT / (source_sha + ".attempt.json")
    completed = ROOT_AUDIT / (source_sha + ".complete.json")
    need(not attempted.exists() and not completed.exists(),
         "APPROVAL_ALREADY_CONSUMED")
    # The Owner approval is consumed *before* any root policy mutation.
    audit_once(attempted, {
        "schema_version": "1.0", "status": "exact_owner_approval_consumed",
        "owner_oid": oid, "tenant": TENANT,
        "action": plan["action"], "scope_sha256": plan["scope_sha256"],
        "before_sha256": plan["baseline_policy_sha256"],
        "after_sha256": plan["candidate_policy_sha256"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    changes = approved_root_file_changes(before)
    attempted_changes = []
    listeners_stopped = False
    success = False
    try:
        with production_lock():
            need(read_root(ROOT_POLICY) == before["baseline"],
                 "ROOT_POLICY_DRIFTED_UNDER_LOCK")
            need(live_snapshot() == before["before"],
                 "PROTECTED_CONTAINERS_CHANGED")
            need(sha256(FREEZE.read_bytes()).hexdigest() == FREEZE_SHA256,
                 "FREEZE_CHANGED_UNDER_LOCK")
            # Only the newly installed scoped release-controller listeners
            # are paused. Existing Ticket Core, runtime, MCP, OpenBao,
            # release manager, and network remain untouched.
            listeners_stopped = True
            listener_action("stop")
            ensure_scoped_oneshots_quiescent()
            for path, old_bytes, new_bytes, mode in changes:
                attempted_changes.append((path, old_bytes, new_bytes, mode))
                atomic_exact_root_file(path, old_bytes, new_bytes, mode)
        listener_action("start")
        listeners_stopped = False
        # Verify root-installed policy and private/public digest pairing using
        # the actual immutable root worker, without submitting a release.
        probe = subprocess.run(
            ["/usr/bin/python3", "-I",
             str(ROOT_INSTALL_DIR / "tools/scoped_backport_native_root.py"),
             "--drain"], capture_output=True, timeout=45)
        need(probe.returncode == 0,
             "PATCHED_ROOT_NATIVE_SELF_ATTESTATION_FAILED")
        watchdog = subprocess.run(
            ["/usr/bin/systemctl", "start",
             "jason-production-drift-watchdog.service"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=120, check=False)
        observed = eval_guard(ROOT_POLICY)
        need(watchdog.returncode == 0 and
             observed["status"] == "pass" and observed["problems"] == [],
             "INDEPENDENT_WATCHDOG_NOT_PASS")
        need(live_snapshot() == before["before"]
             and sha256(FREEZE.read_bytes()).hexdigest() == FREEZE_SHA256
             and sha256(HOLD.read_bytes()).hexdigest() == plan["hold_sha256"],
             "PRODUCTION_CONTROLS_CHANGED")
        success = True
    finally:
        if not success:
            with production_lock():
                restore_attempted_root_files(attempted_changes)
            if listeners_stopped:
                listener_action("start")
    # The breaker remains open. The existing root transition controller
    # independently revalidates protected drift + LKG before closing it.
    stage_probe = read_only_stage_probe()
    audit_once(completed, {
        "schema_version": "1.0",
        "status": "four_scoped_backport_units_and_root_control_verified",
        "source_sha": source_sha, "reviewed_sha": reviewed_sha,
        "scope_sha256": plan["scope_sha256"], "owner_oid": oid,
        "root_policy_sha256": plan["candidate_policy_sha256"],
        "root_private_policy_sha256": plan["root_private_policy_sha256_after"],
        "read_only_stage_probe": stage_probe,
        "added_allowed_system_units": list(UNIT_NAMES),
        "breaker_force_closed": False,
        "provider_writes": False, "runtime_mcp_restarts": False,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "status": "four_scoped_backport_units_and_root_control_verified",
        "source_sha": source_sha, "scope_sha256": plan["scope_sha256"],
        "read_only_stage_probe": stage_probe, "owner_verified": True,
        "breaker_force_closed": False,
        "production_containers_changed": False, "provider_writes": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--reviewed-ci-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    need(args.apply != args.check, "CHOOSE_CHECK_OR_APPLY")
    if args.check:
        state = inspect(source_sha=args.source_sha, reviewed_sha=args.reviewed_ci_sha)
        print(json.dumps({"status": "exact_four_unit_drift_correction_admitted",
                          "plan": state["plan"], "production_mutations": False},
                         sort_keys=True, indent=2))
    else:
        print(json.dumps(apply(source_sha=args.source_sha,
                               reviewed_sha=args.reviewed_ci_sha),
                         sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
