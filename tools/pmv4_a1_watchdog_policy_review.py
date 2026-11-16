#!/usr/bin/env python3
"""Source-only A1 watchdog policy exact-delta reviewer.

No write method, no root installer, no Owner signer, no release authority.
Read-only proof output hides policy contents; root-only proof of the *actual*
protected overlay requires a separately hash-pinned, root-owned invocation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Any

SOURCE_SHA = "8c2064193d74cc41b52369681febbc0a74fa96f7"
NAME = "jason-pmv4-shadow-gateway"
ROOT_POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
SOURCE_REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")
ACTION = "pmv4-a1-exact-one-container-root-watchdog-admission-v1"
PROPOSED_SHA256 = "db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50"
STAGE_DIR = Path("/run/jason-pmv4-a1-watchdog-review-8c20")
PROPOSED = STAGE_DIR / "proposed-desired-state.json"
MAX_POLICY = 131072


class PolicyReviewDenied(PermissionError):
    pass


def need(value: bool, reason: str) -> None:
    if not value:
        raise PolicyReviewDenied(reason)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def decode(data: bytes) -> dict[str, Any]:
    need(isinstance(data, bytes) and 0 < len(data) <= MAX_POLICY,
         "A1_POLICY_SIZE_INVALID")
    try:
        policy = json.loads(data)
    except (TypeError, ValueError) as exc:
        raise PolicyReviewDenied("A1_POLICY_JSON_INVALID") from exc
    need(isinstance(policy, dict) and policy.get("schema_version") == "1.0",
         "A1_POLICY_SCHEMA_INVALID")
    for field in ("allowed_running_containers", "required_containers"):
        value = policy.get(field)
        need(isinstance(value, list)
             and all(isinstance(x, str) and x for x in value)
             and len(value) == len(set(value)),
             "A1_POLICY_CONTAINER_LIST_INVALID")
    need(set(policy["required_containers"]).issubset(
             set(policy["allowed_running_containers"])),
         "A1_POLICY_REQUIRED_CONTAINERS_NOT_ALLOWED")
    return policy


def exact_addition(before: dict[str, Any]) -> dict[str, Any]:
    need(NAME not in before["allowed_running_containers"]
         and NAME not in before["required_containers"],
         "A1_POLICY_SHADOW_ALREADY_DECLARED")
    candidate = {
        key: list(val) if isinstance(val, list) else val
        for key, val in before.items()
    }
    candidate["allowed_running_containers"].append(NAME)
    need(set(candidate) == set(before)
         and all(candidate[key] == before[key]
                 for key in before if key != "allowed_running_containers")
         and candidate["allowed_running_containers"] ==
             before["allowed_running_containers"] + [NAME],
         "A1_POLICY_NOT_EXACT_ONE_ADDITION")
    return candidate


def exact_source(source: bytes, proposed: bytes) -> dict[str, str]:
    old = decode(source)
    new = decode(proposed)
    need(new == exact_addition(old),
         "A1_GIT_SOURCE_DELTA_NOT_EXACT")
    return {
        "protected_source_sha": SOURCE_SHA,
        "protected_policy_blob_sha256": sha(source),
        "candidate_source_policy_sha256": sha(proposed),
        "only_one_optional_container": NAME,
    }


def live_readonly(fd: int, *, expected_uid: int=0,
                  expected_gid: int=0, expected_mode: int=0o600) -> bytes:
    info = os.fstat(fd)
    need(stat.S_ISREG(info.st_mode) and info.st_uid == expected_uid
         and info.st_gid == expected_gid and info.st_nlink == 1
         and stat.S_IMODE(info.st_mode) == expected_mode
         and 0 < info.st_size <= MAX_POLICY,
         "A1_ROOT_POLICY_INODE_UNTRUSTED")
    raw = os.read(fd, MAX_POLICY + 1)
    need(len(raw) == info.st_size,
         "A1_ROOT_POLICY_READ_LENGTH_CHANGED")
    decode(raw)
    return raw


@contextmanager
def proposed_fd(path: Path, *, expected_mode: int=0o400):
    need(path in (PROPOSED, ROOT_POLICY), "A1_ROOT_POLICY_PATH_NOT_PINNED")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_CLOEXEC", 0))
    try:
        yield live_readonly(fd, expected_mode=expected_mode)
    finally:
        os.close(fd)


def review_live(policy_bytes: bytes, source_old: bytes,
                source_new: bytes) -> dict[str, Any]:
    upstream = exact_source(source_old,source_new)
    before = decode(policy_bytes)
    after = exact_addition(before)
    # The root overlay may have independently authorized historical unit
    # declarations; unlike overwriting from Git, preserve them byte-for-field.
    need(after["required_containers"] == before["required_containers"],
         "A1_REQUIRED_CONTAINER_WEAKENING")
    candidate_raw = (
        json.dumps(after,sort_keys=True,indent=2,
                   separators=(",", ": "))+"\n"
    ).encode()
    need(decode(candidate_raw) == after,
         "A1_CANDIDATE_POLICY_SERIALIZATION_INVALID")
    return {
        "status":"root_policy_exact_addition_reviewed",
        "action":ACTION,
        **upstream,
        "root_original_sha256":sha(policy_bytes),
        "root_exact_candidate_sha256":sha(candidate_raw),
        "root_policy_changes":1,
        "added_to":"allowed_running_containers",
        "required_containers_changed":False,
        "other_root_policy_fields_changed":False,
        "root_rollback_exact_original_bytes_required":True,
        "owner_authorization_issued":False,
        "root_writes":False,
        "production_mutations":False,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--read-only", action="store_true",required=True)
    args=parser.parse_args()
    need(os.geteuid()==0,"A1_READONLY_ROOT_REQUIRED")
    script=Path(__file__)
    info=script.lstat()
    need(script.is_absolute() and not script.is_symlink()
         and info.st_uid==0 and info.st_gid==0
         and stat.S_IMODE(info.st_mode)==0o400,
         "A1_READONLY_SCRIPT_NOT_ROOT_INSTALLED")
    command=["/usr/sbin/runuser","-u","al","--","/usr/bin/git",
             "-C",str(SOURCE_REPO),
             "show",SOURCE_SHA+":config/production-desired-state.json"]
    old=subprocess.run(command,capture_output=True,check=False,timeout=20)
    need(old.returncode==0 and len(old.stdout)<=MAX_POLICY,
         "A1_PROTECTED_SOURCE_UNAVAILABLE")
    need(STAGE_DIR.is_dir() and not STAGE_DIR.is_symlink()
         and STAGE_DIR.stat().st_uid == 0
         and stat.S_IMODE(STAGE_DIR.stat().st_mode) == 0o700,
         "A1_READONLY_STAGE_NOT_ROOT_PROTECTED")
    need(script.parent == STAGE_DIR,
         "A1_READONLY_EXECUTOR_NOT_FIXED_STAGE")
    with proposed_fd(PROPOSED) as source_candidate:
        need(sha(source_candidate) == PROPOSED_SHA256,
             "A1_PROPOSED_SOURCE_BYTES_CHANGED")
        with proposed_fd(ROOT_POLICY, expected_mode=0o600) as live_bytes:
            report = review_live(live_bytes, old.stdout, source_candidate)
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PolicyReviewDenied as exc:
        print("A1_WATCHDOG_REVIEW=DENIED "+str(exc))
        raise SystemExit(2)
