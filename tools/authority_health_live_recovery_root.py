#!/usr/bin/env python3
"""One-use, exact Owner-signed health-journal relocation repair.

This source is not installed or executable as production authority by itself.
The Owner must authenticate with Entra and sign the exact manifest using the
pinned, separated UID-1000 issuer. A separate hash-pinned, isolated root
bootstrap invocation verifies the signed proof BEFORE any mutation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ACTION = "owner-authority-health-relocated-audit-oneuse-20261117"
ROOT_BASE = Path("/usr/local/lib/jason/authority-health-live-audit")
FAST_DROP = Path("/etc/systemd/system/jason-openclaw-authority-health.service.d/92-owner-live-audit-location.conf")
FULL_DROP = Path("/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d/92-owner-live-audit-location.conf")
EMERGENCY = Path("/etc/systemd/system/jason-openclaw-authority-health.service.d/91-owner-emergency-full-proof-degraded.conf")
LEDGER = Path("/etc/jason-owner-release/authority-health-live-audit-ledger")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
NATIVE_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
FULL = Path("/var/lib/jason/openclaw/operational-full-health.json")
FAST = Path("/var/lib/jason/openclaw/operational-health.json")
ROOT_PIN = Path("/etc/jason-owner-release/verified-owner-public-key.json")
OWNER_LIB = Path("/usr/local/lib/jason/owner_signed_release.py")
ROOT_RUNNER_FILE = "authority_health_live_recovery_root.py"
AUDIT = Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
RUNTIME_IMAGE = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
EMERGENCY_SHA = "5149a723e8e85bb825807b9fadd674b957b578eca4e354f5b2c9f33459e4f64b"
FULL_EXPECTED_PATH = str(AUDIT)
FILES = {
    "openclaw_authority_live_audit_full_snapshot.py": ROOT_BASE / "openclaw_authority_live_audit_full_snapshot.py",
    "openclaw_authority_health_snapshot.py": ROOT_BASE / "openclaw_authority_health_snapshot.py",
    "openclaw_authority_operational_health.py": ROOT_BASE / "openclaw_authority_operational_health.py",
    "openclaw_authority_fast_health.py": ROOT_BASE / "openclaw_authority_fast_health.py",
    "full-dropin.conf": FULL_DROP,
    "fast-dropin.conf": FAST_DROP,
}
MAX_FILE_SIZE = 100_000
REVIEWED_FILE_HASHES = {
    "openclaw_authority_live_audit_full_snapshot.py":
        "e3b709bab3d16a69e461af8741ea2ef41fad45030dd8a7349a10597fa5e680e8",
    "openclaw_authority_health_snapshot.py":
        "fe050a8a5f38d088793650bae8a852a07779a54ced4ae5307366f6bf1c967e1a",
    "openclaw_authority_operational_health.py":
        "4d9aec6c2d8a3695cd88b3abfadcf4e66f35c45376550c0d5f4a8fd762896781",
    "openclaw_authority_fast_health.py":
        "1cad74a8288e0daf1293c17e060ca13fc2485cd1c303e25977eb19d7b7565788",
    "full-dropin.conf":
        "06bce21acc3ebbbfd4314c62c442f221c697daae02784d2d99753873677629da",
    "fast-dropin.conf":
        "12173fbb4207f1b435e2aebfac066d07e33198761ab4baeb359e647092d65bc3",
}
OWNER_VERIFIER_SHA = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"

class Denied(PermissionError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Denied(code)


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def secure_stage_bytes(path: Path, *, expected_uid: int = 1000) -> bytes:
    info = path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_uid == expected_uid and info.st_nlink == 1
         and stat.S_IMODE(info.st_mode) == 0o400
         and 0 < info.st_size <= MAX_FILE_SIZE, "STAGING_FILE_UNTRUSTED")
    return path.read_bytes()


def read_manifest(directory: Path, *, require_proof: bool = True) -> tuple[dict, dict[str, bytes]]:
    need(directory.parent == Path("/home/al/.local/share/jason")
         and directory.name.startswith("authority-health-live-root-")
         and directory.is_dir() and not directory.is_symlink(),
         "STAGING_DIRECTORY_NOT_EXACT")
    root_info = directory.lstat()
    need(root_info.st_uid == 1000 and stat.S_IMODE(root_info.st_mode) == 0o700,
         "STAGING_DIRECTORY_UNTRUSTED")
    manifest_bytes = secure_stage_bytes(directory / "manifest.json")
    manifest = json.loads(manifest_bytes)
    required = {"schema_version", "action", "source_sha", "rollback_sha",
                "scope_sha256", "root_script_sha256", "files_sha256",
                "freeze_sha256", "hold_sha256", "old_emergency_sha256",
                "runtime_image", "mcp_image", "requires_owner_signature",
                "provider_mutations", "financial_scheduler_activation",
                "no_protected_service_restarts", "one_use", "full_scan_seconds"}
    need(isinstance(manifest, dict) and set(manifest) == required
         and manifest["schema_version"] == "1.0"
         and manifest["action"] == ACTION
         and manifest["rollback_sha"] == LKG
         and manifest["freeze_sha256"] == FREEZE_SHA
         and manifest["old_emergency_sha256"] == EMERGENCY_SHA
         and manifest["runtime_image"] == RUNTIME_IMAGE
         and manifest["mcp_image"] == MCP_IMAGE
         and manifest["requires_owner_signature"] is True
         and manifest["provider_mutations"] == 0
         and manifest["financial_scheduler_activation"] is False
         and manifest["no_protected_service_restarts"] is True
         and manifest["one_use"] is True
         and manifest["full_scan_seconds"] == 5400,
         "RELEASE_MANIFEST_CONTRACT_CHANGED")
    sha = manifest["source_sha"]
    need(isinstance(sha, str) and len(sha) == 40
         and set(sha) <= set("0123456789abcdef"), "SOURCE_SHA_INVALID")
    unsigned = dict(manifest)
    unsigned.pop("scope_sha256")
    need(manifest["scope_sha256"] == digest(canonical(unsigned)),
         "RELEASE_SCOPE_HASH_INVALID")
    hashes = manifest["files_sha256"]
    need(isinstance(hashes, dict) and
         set(hashes) == set(FILES) | {ROOT_RUNNER_FILE},
         "RELEASE_FILE_SET_CHANGED")
    need(all(hashes.get(k) == h for k, h in REVIEWED_FILE_HASHES.items()),
         "RELEASE_NOT_THE_REVIEWED_SOURCE_AND_UNIT_BYTES")
    want = {"manifest.json", *hashes}
    if require_proof:
        want.add("owner-proof.json")
    elif (directory / "owner-proof.json").exists():
        want.add("owner-proof.json")
    have = {p.name for p in directory.iterdir()}
    need(have == want, "RELEASE_DIRECTORY_EXTRA_OR_MISSING")
    blobs = {key: secure_stage_bytes(directory / key) for key in hashes}
    need(all(digest(blobs[k]) == hashes[k] for k in hashes),
         "RELEASE_SOURCE_HASH_MISMATCH")
    need(digest(blobs[ROOT_RUNNER_FILE]) == manifest["root_script_sha256"],
         "ROOT_SCRIPT_HASH_MISMATCH")
    return manifest, blobs


def read_pinned_owner_module():
    meta = OWNER_LIB.lstat()
    need(meta.st_uid == 0 and stat.S_ISREG(meta.st_mode)
         and not meta.st_mode & 0o022 and not OWNER_LIB.is_symlink()
         and digest(OWNER_LIB.read_bytes()) == OWNER_VERIFIER_SHA,
         "PINNED_OWNER_VERIFIER_UNTRUSTED")
    spec = importlib.util.spec_from_file_location("root_pinned_owner", OWNER_LIB)
    need(spec and spec.loader, "PINNED_OWNER_VERIFIER_MISSING")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def verify_owner(directory: Path, manifest: dict) -> str:
    mod = read_pinned_owner_module()
    signer = mod.read_pinned_root_owner_public_key(
        ROOT_PIN, require_root_owned=True)
    raw = secure_stage_bytes(directory / "owner-proof.json")
    signed = json.loads(raw)
    need(set(signed) == {"schema_version", "action", "manifest_sha256",
                        "signed_owner_proof"}
         and signed["schema_version"] == "1.0"
         and signed["action"] == ACTION
         and signed["manifest_sha256"] == digest(canonical(manifest)),
         "OWNER_DECISION_NOT_EXACT")
    payload = mod.verify_exact_owner_release(
        signed["signed_owner_proof"], public_key=signer,
        expected_candidate_sha=manifest["source_sha"],
        expected_rollback_sha=LKG,
        expected_release_id="release-" + manifest["source_sha"][:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=digest(canonical(manifest)),
        expected_freeze_sha256=FREEZE_SHA,
        at=datetime.now(timezone.utc),
    )
    return str(payload["approval_id"])


def inspect_container(name: str) -> dict:
    x = json.loads(subprocess.check_output(
        ["docker", "inspect", name], text=True, timeout=15))
    need(isinstance(x, list) and len(x) == 1, "CONTAINER_CARDINALITY_CHANGED")
    return x[0]


def read_json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def live_gate(manifest: dict) -> dict:
    need(os.geteuid() == 0, "TRUSTED_ROOT_REQUIRED")
    need(Path("/opt/jason/current").resolve(strict=True).name == LKG,
         "PRODUCTION_LKG_CHANGED")
    need(digest(FREEZE.read_bytes()) == FREEZE_SHA
         and digest(HOLD.read_bytes()) == manifest["hold_sha256"],
         "PRODUCTION_HOLD_OR_FREEZE_CHANGED")
    control = read_json(CONTROL)
    drift = read_json(DRIFT)
    need(control.get("circuit_breaker", {}).get("state") == "open"
         and drift.get("status") == "drift_detected"
         and drift.get("problems") == [{
             "kind": "failed_system_unit", "state": "failed",
             "unit": "jason-openclaw-authority-health.service"}],
         "PROTECTED_BREAKER_UNRELATED")
    need(digest(EMERGENCY.read_bytes()) == EMERGENCY_SHA,
         "EMERGENCY_OVERLAY_DRIFT")
    need(not ROOT_BASE.exists() and not ROOT_BASE.is_symlink()
         and not FULL_DROP.exists() and not FAST_DROP.exists(),
         "RELEASE_SCOPE_ALREADY_INSTALLED")
    audit = AUDIT.lstat()
    need(not AUDIT.is_symlink() and stat.S_ISREG(audit.st_mode)
         and audit.st_uid == 1000 and stat.S_IMODE(audit.st_mode) == 0o600,
         "REAL_AUDIT_FILE_NOT_TRUSTED")
    full = read_json(FULL)
    need(full.get("status") == "pass"
         and full.get("files", {}).get("orchestration_audit", {}).get("path")
             != str(AUDIT),
         "NOT_REVIEWED_OLD_PATH_INCIDENT")
    before = {}
    for name, image in [
        ("jason-runtime", RUNTIME_IMAGE),
        ("jason-mcp-pilot", MCP_IMAGE),
    ]:
        value = inspect_container(name)
        need(value["Image"] == image
             and value["State"]["Running"]
             and (name != "jason-runtime" or
                  value["State"].get("Health", {}).get("Status") == "healthy"),
             "PROTECTED_CONTAINER_CHANGED:" + name)
        before[name] = {
            "id": value["Id"], "image": value["Image"],
            "started_at": value["State"]["StartedAt"],
        }
    for name in ("jason-pmv4-shadow-gateway", "jason-teams-gateway", "openbao"):
        value = inspect_container(name)
        need(value["State"]["Running"], "PROTECTED_SERVICE_DOWN:" + name)
        before[name] = {
            "id": value["Id"], "image": value["Image"],
            "started_at": value["State"]["StartedAt"],
        }
    return before


def native_lock():
    fd = os.open(NATIVE_LOCK, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    meta = os.fstat(fd)
    need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 1000
         and not meta.st_mode & 0o002, "RELEASE_LOCK_UNTRUSTED")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise Denied("NATIVE_RELEASE_LOCK_BUSY") from exc
    return fd


def native_unlock(fd: int):
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def root_record(path: Path, value: dict) -> None:
    payload = json.dumps(value, sort_keys=True, indent=2).encode() + b"\n"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def root_install(blobs: dict[str, bytes], installed: list[Path]) -> None:
    need(not ROOT_BASE.exists() and not ROOT_BASE.is_symlink(),
         "INSTALL_OBJECT_PREEXISTS")
    ROOT_BASE.mkdir(mode=0o755, parents=False, exist_ok=False)
    for name, target in FILES.items():
        data = blobs[name]
        need(not target.exists() and not target.is_symlink(),
             "INSTALL_OBJECT_PREEXISTS")
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     getattr(os, "O_NOFOLLOW", 0), 0o644 if name.endswith(".conf") else 0o444)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        installed.append(target)
        need(digest(target.read_bytes()) == digest(data), "INSTALL_READBACK_FAIL")


def system(*args: str, timeout: int = 120) -> str:
    value = subprocess.run(
        ["systemctl", *args], check=False, text=True,
        capture_output=True, timeout=timeout)
    need(value.returncode == 0, "SYSTEMD_ACTION_DENIED:" + args[0])
    return value.stdout.strip()


def verify_full_since(started: float):
    info = FULL.stat()
    need(info.st_uid == 1000 and stat.S_IMODE(info.st_mode) == 0o600
         and info.st_mtime >= started, "FRESH_FULL_EVIDENCE_NOT_PRESENT")
    value = read_json(FULL)
    need(value.get("status") == "pass"
         and value.get("failures") == []
         and value.get("snapshot_source_exit_code") == 0
         and value.get("provider_contacted") is False
         and value.get("provider_credentials_used") is False
         and value.get("files", {}).get("orchestration_audit", {}).get("path")
             == FULL_EXPECTED_PATH,
         "LIVE_FULL_INTEGRITY_NOT_PASS")
    for key in ("authority", "replay", "security_audit", "orchestration_audit"):
        x = value.get("files", {}).get(key, {})
        need(x.get("present") is True and x.get("integrity") == "ok"
             and x.get("mode") == "0o600", "FULL_INTEGRITY_ITEM_NOT_PASS:" + key)
    backup = value.get("backup_restore_proof", {})
    need(backup.get("backup_integrity") == "ok"
         and backup.get("restore_integrity") == "ok"
         and backup.get("counts_match") is True,
         "FULL_BACKUP_RESTORE_NOT_PASS")


def verify_fast_since(started: float):
    info = FAST.stat()
    need(info.st_uid == 1000 and stat.S_IMODE(info.st_mode) == 0o600
         and info.st_mtime >= started, "FRESH_FAST_EVIDENCE_NOT_PRESENT")
    value = read_json(FAST)
    need(value.get("status") == "pass" and value.get("failures") == [],
         "FRESH_FAST_HEALTH_NOT_PASS")


def protected_unchanged(before: dict) -> None:
    for name, old in before.items():
        current = inspect_container(name)
        need(current["Id"] == old["id"]
             and current["Image"] == old["image"]
             and current["State"]["StartedAt"] == old["started_at"]
             and current["State"]["Running"],
             "PROTECTED_CONTAINER_MODIFIED:" + name)
    need(digest(FREEZE.read_bytes()) == FREEZE_SHA,
         "PRODUCTION_FREEZE_CHANGED")


def native_revalidate():
    cmd = (
        "import sys;from pathlib import Path;"
        "sys.path.insert(0,'/home/al/.local/lib/jason');"
        "import release_manager_host_runner as r;"
        "r.revalidate_circuit_breaker("
        "Path('/var/lib/jason/openclaw/release-manager'))"
    )
    subprocess.run(["runuser", "-u", "al", "--", "/usr/bin/python3",
                    "-c", cmd], check=True, capture_output=True, timeout=135)
    need(read_json(CONTROL).get("circuit_breaker", {}).get("state") == "closed",
         "NATIVE_ROOT_BREAKER_STILL_OPEN")


def rollback(installed: list[Path], *, full_pass: bool, emergency: bytes,
             emergency_removed: bool) -> None:
    # A real full PASS is preserved as evidence even after later failure.
    # Restore the prior fail-closed service if it was disabled for native fast.
    if emergency_removed and not EMERGENCY.exists():
        fd = os.open(EMERGENCY, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "wb") as out:
            out.write(emergency)
            out.flush()
            os.fsync(out.fileno())
    for target in reversed(installed):
        if target.exists():
            target.unlink()
    if ROOT_BASE.exists() and not any(ROOT_BASE.iterdir()):
        ROOT_BASE.rmdir()
    system("daemon-reload")
    # A fresh full-proof PASS is not rolled back to a stale historic PASS.


def execute(directory: Path):
    need(os.geteuid() == 0 and sys.flags.isolated == 1,
         "ISOLATED_TRUSTED_ROOT_REQUIRED")
    manifest, blobs = read_manifest(directory)
    need(digest(Path(__file__).read_bytes()) == manifest["root_script_sha256"],
         "EXECUTED_ROOT_SOURCE_NOT_PINNED")
    need(digest(blobs[ROOT_RUNNER_FILE]) == digest(Path(__file__).read_bytes()),
         "RUNNER_BYTE_DRIFT")
    need(not LEDGER.exists() and not LEDGER.is_symlink(),
         "ONE_USE_ROOT_RECEIPT_ALREADY_EXISTS")
    before = live_gate(manifest)
    approval_id = verify_owner(directory, manifest)
    need(all(approval_id not in p.read_text() for p in LEDGER.glob("*.json"))
         if LEDGER.exists() else True, "OWNER_PROOF_REPLAY")
    # All authentication, source, scope, and protected host gates completed.
    lockfd = native_lock()
    installed: list[Path] = []
    emergency = EMERGENCY.read_bytes()
    emergency_removed = False
    full_pass = False
    outcome = {
        "action": ACTION, "status": "failed",
        "approval_id": approval_id, "candidate_sha": manifest["source_sha"],
        "scope_sha256": manifest["scope_sha256"],
        "freeze_sha256": manifest["freeze_sha256"],
        "runtime_mcp_pmv4_unchanged": False, "full_integrity_pass": False,
        "native_breaker_closed": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        live_gate(manifest)
        LEDGER.mkdir(mode=0o700, exist_ok=False)
        root_record(LEDGER / "attempt.json", outcome)
        root_install(blobs, installed)
        protected_unchanged(before)
        system("daemon-reload")
        # The native lock must be released during the long bounded proof;
        # otherwise the independent drift watchdog cannot obtain it.
        native_unlock(lockfd)
        lockfd = None
        started = time.time()
        system("reset-failed", "jason-openclaw-authority-full-integrity.service")
        system("start", "jason-openclaw-authority-full-integrity.service", timeout=5760)
        verify_full_since(started)
        full_pass = True
        outcome["full_integrity_pass"] = True
        need(digest(EMERGENCY.read_bytes()) == EMERGENCY_SHA,
             "EMERGENCY_CHANGED_DURING_PROOF")
        EMERGENCY.unlink()
        emergency_removed = True
        system("daemon-reload")
        system("reset-failed", "jason-openclaw-authority-health.service")
        started_fast = time.time()
        system("start", "jason-openclaw-authority-health.service", timeout=150)
        verify_fast_since(started_fast)
        for _ in range(3):
            system("reset-failed", "jason-production-drift-watchdog.service")
            system("start", "jason-production-drift-watchdog.service", timeout=140)
            drift = read_json(DRIFT)
            need(drift.get("status") == "pass" and drift.get("problems") == [],
                 "NATIVE_DRIFT_NOT_PASS")
            if _ != 2:
                time.sleep(17)
        native_revalidate()
        protected_unchanged(before)
        outcome["runtime_mcp_pmv4_unchanged"] = True
        outcome["native_breaker_closed"] = True
        outcome["status"] = "verified"
    except BaseException:
        try:
            rollback(installed, full_pass=full_pass, emergency=emergency,
                     emergency_removed=emergency_removed)
            outcome["source_rollback"] = "completed"
        except Exception:
            outcome["source_rollback"] = "failed_closed_manual_review_required"
        raise
    finally:
        outcome["completed_at"] = datetime.now(timezone.utc).isoformat()
        if LEDGER.exists():
            root_record(LEDGER / "result.json", outcome)
        if lockfd is not None:
            native_unlock(lockfd)
    print("LIVE_AUTHORITY_FULL_AND_FAST_HEALTH=PASS")
    print("NATIVE_ROOT_BREAKER=CLOSED")
    print("PROTECTED_RUNTIME_MCP_PMV4_UNCHANGED=True")
    print("PRODUCTION_FREEZE_UNCHANGED=True")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--packet", type=Path)
    args = parser.parse_args()
    need(args.check_only != args.execute, "MODE_REQUIRED")
    if args.check_only:
        need(args.packet is not None, "PACKET_REQUIRED")
        manifest, _ = read_manifest(args.packet, require_proof=False)
        print("SOURCE_BYTES_AND_SCOPE_CHECK=PASS")
        print("SIGNED_OWNER_AND_ROOT_PRODUCTION_GATES=NOT_EXECUTED")
        return 0
    need(args.packet is not None, "PACKET_REQUIRED")
    execute(args.packet)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("AUTHORITY_HEALTH_RELOCATION=DENIED " +
              type(exc).__name__ + ":" +
              (str(exc)[:180] if isinstance(exc, Denied)
               else "SENSITIVE_DETAILS_REDACTED"), file=sys.stderr)
        raise SystemExit(2)
