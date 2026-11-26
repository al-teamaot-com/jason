#!/usr/bin/env python3
"""Prepare/verify immutable unprivileged inputs for a signed live-audit root repair.

The output is NOT trusted root code. The separate bootstrap requires an
externally pinned root-runner digest and independent exact Owner proof.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ACTION = "owner-authority-health-relocated-audit-oneuse-20261117"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
EMERGENCY_SHA = "5149a723e8e85bb825807b9fadd674b957b578eca4e354f5b2c9f33459e4f64b"
RUNTIME = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
MCP = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
DEST_ROOT = Path("/home/al/.local/share/jason")
REVIEWED = {
    "openclaw_authority_live_audit_full_snapshot.py": "e3b709bab3d16a69e461af8741ea2ef41fad45030dd8a7349a10597fa5e680e8",
    "openclaw_authority_health_snapshot.py": "fe050a8a5f38d088793650bae8a852a07779a54ced4ae5307366f6bf1c967e1a",
    "openclaw_authority_operational_health.py": "4d9aec6c2d8a3695cd88b3abfadcf4e66f35c45376550c0d5f4a8fd762896781",
    "openclaw_authority_fast_health.py": "1cad74a8288e0daf1293c17e060ca13fc2485cd1c303e25977eb19d7b7565788",
    "full-dropin.conf": "06bce21acc3ebbbfd4314c62c442f221c697daae02784d2d99753873677629da",
    "fast-dropin.conf": "12173fbb4207f1b435e2aebfac066d07e33198761ab4baeb359e647092d65bc3",
}
SOURCE_GIT = {
    "authority_health_live_recovery_root.py": "tools/authority_health_live_recovery_root.py",
    "openclaw_authority_live_audit_full_snapshot.py": "tools/openclaw_authority_live_audit_full_snapshot.py",
    "openclaw_authority_health_snapshot.py": "tools/openclaw_authority_health_snapshot.py",
    "openclaw_authority_operational_health.py": "tools/openclaw_authority_operational_health.py",
    "openclaw_authority_fast_health.py": "tools/openclaw_authority_fast_health.py",
}
ROOT_BASE = "/usr/local/lib/jason/authority-health-live-audit"
FULL_UNIT = (
    "[Service]\nExecStart=\n"
    "ExecStart=/usr/bin/python3 " + ROOT_BASE +
    "/openclaw_authority_live_audit_full_snapshot.py "
    "--output /var/lib/jason/openclaw/operational-full-health.json\n"
    "TimeoutStartSec=5700\nNice=19\nIOSchedulingClass=idle\n"
    "ReadOnlyPaths=" + ROOT_BASE + "\n"
).encode()
FAST_UNIT = (
    "[Service]\nExecStart=\n"
    "ExecStart=/usr/bin/python3 " + ROOT_BASE +
    "/openclaw_authority_fast_health.py "
    "--output /var/lib/jason/openclaw/operational-health.json "
    "--full-evidence /var/lib/jason/openclaw/operational-full-health.json\n"
    "ReadOnlyPaths=" + ROOT_BASE + "\n"
).encode()


class Denied(PermissionError):
    pass


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def read_source(repo: Path, source: str) -> dict[str, bytes]:
    if re.fullmatch("[0-9a-f]{40}", source) is None:
        raise Denied("INVALID_EXACT_GIT_SOURCE")
    base = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-t", source],
        capture_output=True, text=True, check=False)
    if base.returncode != 0 or base.stdout.strip() != "commit":
        raise Denied("EXACT_SOURCE_COMMIT_NOT_AVAILABLE")
    merged = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", source,
         "origin/main"], check=False, capture_output=True)
    if merged.returncode != 0:
        raise Denied("EXACT_SOURCE_NOT_MERGED_IN_PROTECTED_MAIN")
    blobs = {}
    for name, ref in SOURCE_GIT.items():
        obj = subprocess.run(["git", "-C", str(repo), "show",
                              source + ":" + ref], check=False, capture_output=True)
        if obj.returncode != 0 or not 0 < len(obj.stdout) < 100_000:
            raise Denied("REVIEWED_SOURCE_BLOB_UNAVAILABLE:" + name)
        blobs[name] = obj.stdout
    blobs["full-dropin.conf"] = FULL_UNIT
    blobs["fast-dropin.conf"] = FAST_UNIT
    if any(digest(blobs[k]) != expected for k, expected in REVIEWED.items()):
        raise Denied("SOURCE_BYTES_NOT_FROM_EXACT_REVIEWED_HEALTH_RELEASE")
    return blobs


def create_manifest(source: str, blobs: dict[str, bytes]) -> dict:
    if digest(FREEZE.read_bytes()) != FREEZE_SHA:
        raise Denied("PRODUCTION_FREEZE_CHANGED")
    assert source and len(source) == 40
    value = {
        "schema_version": "1.0", "action": ACTION,
        "source_sha": source, "rollback_sha": LKG,
        "root_script_sha256": digest(blobs["authority_health_live_recovery_root.py"]),
        "files_sha256": {k: digest(v) for k, v in sorted(blobs.items())},
        "freeze_sha256": FREEZE_SHA,
        "hold_sha256": digest(HOLD.read_bytes()),
        "old_emergency_sha256": EMERGENCY_SHA,
        "runtime_image": RUNTIME, "mcp_image": MCP,
        "requires_owner_signature": True, "provider_mutations": 0,
        "financial_scheduler_activation": False,
        "no_protected_service_restarts": True,
        "one_use": True, "full_scan_seconds": 5400,
    }
    value["scope_sha256"] = digest(canonical(value))
    return value


def prepare(repo: Path, source: str, dest: Path, verify_only: bool) -> dict:
    if dest != DEST_ROOT / ("authority-health-live-root-" + source[:12]):
        raise Denied("STAGING_DESTINATION_NOT_EXACT")
    blobs = read_source(repo, source)
    manifest = create_manifest(source, blobs)
    blobs["manifest.json"] = json.dumps(
        manifest, indent=2, sort_keys=True).encode() + b"\n"
    if not verify_only:
        dest.mkdir(mode=0o700, parents=False, exist_ok=False)
        for name, data in blobs.items():
            p = dest / name
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o400)
            with os.fdopen(fd, "wb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
    if (dest.is_symlink() or not dest.is_dir()
            or stat.S_IMODE(dest.stat().st_mode) != 0o700
            or dest.stat().st_uid != 1000):
        raise Denied("STAGING_DIRECTORY_UNTRUSTED")
    actual = {p.name for p in dest.iterdir()}
    expected = set(blobs)
    if (dest / "owner-proof.json").exists():
        expected.add("owner-proof.json")
    if actual != expected:
        raise Denied("STAGING_OBJECTS_ADDED_OR_MISSING")
    for name, data in blobs.items():
        p = dest / name
        info = p.lstat()
        if (p.is_symlink() or info.st_uid != 1000
                or stat.S_IMODE(info.st_mode) != 0o400
                or info.st_nlink != 1 or p.read_bytes() != data):
            raise Denied("STAGING_CONTENT_OR_MODE_CHANGED:" + name)
    return {
        "status": "verified_source_only",
        "source_sha": source,
        "manifest_sha256": digest(canonical(manifest)),
        "scope_sha256": manifest["scope_sha256"],
        "root_script_sha256": manifest["root_script_sha256"],
        "directory": str(dest),
        "provider_mutations": 0,
        "root_install_performed": False,
        "owner_proof_present": "owner-proof.json" in actual,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("prepare", "verify"))
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--source-sha", required=True)
    ap.add_argument("--destination", type=Path, required=True)
    args = ap.parse_args()
    try:
        x = prepare(args.repo, args.source_sha, args.destination,
                    verify_only=args.command == "verify")
        print(json.dumps(x, sort_keys=True))
        return 0
    except (Denied, OSError, ValueError) as exc:
        print("ROOT_BUNDLE_PREPARATION=DENIED " + str(exc)[:200])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
