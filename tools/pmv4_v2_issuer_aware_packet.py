#!/usr/bin/env python3
"""Source-only exact two-file root health-code update packet verifier.

Rebuilds the reviewed archive deterministically from the historically pinned
original root files (protected Git) plus this PR's precise V2 helper/policy.
Neither this tool nor its CI performs any production root modification.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import stat
import subprocess
import tarfile

MAIN = "7b42ce983896711525de4c7955bf9fc43ac003d0"
OLD = "45e52de4803a6f0768187793bba4990ed1d11a07"
ACTION = "owner-v2-issuer-attested-root-code-policy-replace-v2-20261115"
SCOPE = "6892f490c4632a95825240110ead9193ae1269d6624a70dbfe992b9a537ae22e"
MANIFEST_SHA256 = "b1b3dd1c49d74ffc33597081d955d7b68341bdca9b504828b5ea822df39a6aca"
PACKAGE_SHA256 = "db8fc31ec8dcdfce78fc602dffba36e856cd19c03c81265e90978ba6c1364135"
PATH = "config/pmv4-stage-a0/issuer-aware-v2-root-upgrade-manifest-review.json"
ROOT_PATHS = {
    "tools/owner_full_integrity_v2_root_repair.py":
        "/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py",
    "config/owner-full-integrity-v2-repair-policy.json":
        "/etc/jason-owner-release/owner-full-integrity-v2-repair-policy.json",
}


class PacketDenied(PermissionError):
    pass


def check(value: bool, reason: str) -> None:
    if not value:
        raise PacketDenied(reason)


def hash_bytes(blob: bytes) -> str:
    return sha256(blob).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def git_blob(repo: Path, revision: str, relative: str) -> bytes:
    return subprocess.check_output([
        "git", "-c", "safe.directory=" + str(repo), "-C", str(repo),
        "show", revision + ":" + relative,
    ], timeout=15)


def verify(repo: Path, *, produced_tar: Path | None = None,
           produced_manifest: Path | None = None) -> dict[str, str]:
    manifest_path = repo / PATH
    data = manifest_path.read_bytes()
    check(hash_bytes(data) == MANIFEST_SHA256, "PINNED_MANIFEST_CHANGED")
    doc = json.loads(data)
    scope = doc.get("scope_sha256")
    unsigned = {key: val for key, val in doc.items() if key != "scope_sha256"}
    check(scope == SCOPE and hash_bytes(canonical(unsigned)) == scope,
          "ROOT_TWO_FILE_SCOPE_CHANGED")
    check(doc.get("exact_action") == ACTION
          and doc.get("reviewed_merged_main_sha") == MAIN
          and doc.get("rollback_protected_main_sha") == OLD
          and doc.get("production_root_replacement_authorized") is False
          and doc.get("no_full_integrity_scan") is True
          and doc.get("no_unit_reload_or_restart") is True
          and doc.get("no_breaker_override") is True
          and doc.get("production_lkg") == "d1b8c196dadd4b672ec8ba47075f27bb61c98d63",
          "ROOT_TWO_FILE_EXACT_CONTRACT_CHANGED")
    rows = doc.get("exact_replacements", [])
    check(isinstance(rows, list) and len(rows) == 2
          and {row.get("git_path"): row.get("root_target") for row in rows}
          == ROOT_PATHS, "ROOT_TWO_FILE_TARGETS_CHANGED")
    receipts = doc.get("immutable_root_audit_outputs", {})
    check(receipts.get("root_attempt_path") ==
          "/etc/jason-owner-release/owner-v2-issuer-attested-v2-" + MAIN[:12] + ".attempt.json"
          and receipts.get("root_result_path") ==
          "/etc/jason-owner-release/owner-v2-issuer-attested-v2-" + MAIN[:12] + ".result.json",
          "ROOT_UPDATE_ONE_USE_AUDIT_CHANGED")
    items = {}
    for row in rows:
        rel = row["git_path"]
        old = git_blob(repo, OLD, rel)
        new = (repo / rel).read_bytes()
        check(hash_bytes(old) == row["old_sha256"]
              and hash_bytes(new) == row["new_sha256"]
              and len(old) == row["old_size"]
              and len(new) == row["new_size"],
              "ROOT_OLD_OR_NEW_SOURCE_CHANGED")
        mode = int(row["mode"], 8)
        check(mode == (0o444 if rel.endswith(".py") else 0o400)
              and row["owner_uid"] == row["owner_gid"] == 0,
              "ROOT_FILE_OWNER_MODE_CHANGED")
        items[row["archive_old"]] = (old, mode)
        items[row["archive_new"]] = (new, mode)
    items["_metadata/owner-exact-root-replacement.json"] = (data, 0o400)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:", format=tarfile.USTAR_FORMAT) as tar:
        for name, (blob, mode) in items.items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.REGTYPE
            info.mode = mode
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    bundle = buffer.getvalue()
    check(hash_bytes(bundle) == PACKAGE_SHA256, "ROOT_PACKAGED_SOURCE_DRIFT")
    if produced_tar is not None:
        check(hash_bytes(produced_tar.read_bytes()) == PACKAGE_SHA256
              and produced_tar.read_bytes() == bundle,
              "REVIEWED_ARCHIVE_NOT_DETERMINISTIC")
    if produced_manifest is not None:
        check(produced_manifest.read_bytes() == data,
              "REVIEWED_MANIFEST_NOT_DETERMINISTIC")
    return {
        "status": "verified", "action": ACTION, "source_main": MAIN,
        "original_root_source": OLD, "scope_sha256": SCOPE,
        "manifest_sha256": MANIFEST_SHA256,
        "package_sha256": PACKAGE_SHA256,
        "exact_root_files": "2", "production_apply_supported": "false",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path,
                        default=Path(__file__).resolve().parents[1])
    parser.add_argument("--verify-tar", type=Path)
    parser.add_argument("--verify-manifest", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.repo.resolve(),
                                produced_tar=args.verify_tar,
                                produced_manifest=args.verify_manifest),
                         sort_keys=True))
        return 0
    except (PacketDenied, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print("PMV4_V2_ISSUER_AWARE_PACKET=DENIED "
              + type(exc).__name__ + ":" + str(exc)[:130])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
