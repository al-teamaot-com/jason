#!/usr/bin/env python3
"""Refresh exact Stage E CI evidence using the existing pinned GitHub verifier.

This read-only GitHub verification writes only the native root CI evidence file.
It grants no Owner authority and cannot execute or approve a cutover.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable
from uuid import uuid4

SOURCE = Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo/tools/pmv4_e_canary_oneowner_root.py")
SOURCE_SHA256 = "854fc7ade2fecf2e9cbddee6b4cb0c0aaca7d3f2cf4b97617e9bc1fcfab81c3b"
TARGET = Path("/var/lib/jason/independent-component-release/control/protected-ci.json")
ENTRY = Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted/tools/pmv4_e_ci_refresh.py")
CHECK_POLICY = "repos/al-teamaot-com/jason/branches/main/protection/required_status_checks"
SHA = re.compile(r"^[0-9a-f]{40}$")


class StageECIDenied(PermissionError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise StageECIDenied("PMV4_E_CI_REFRESH_" + reason)


def load_pinned_attestor(source: Path, *, production: bool) -> dict[str, Any]:
    try:
        meta = source.lstat()
        need(not source.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_nlink == 1 and not meta.st_mode & 0o022
             and 0 < meta.st_size < 200000
             and (not production or meta.st_uid == 1000),
             "VERIFIER_FILE_UNTRUSTED")
        raw = source.read_bytes()
        need(len(raw) == meta.st_size and sha256(raw).hexdigest() == SOURCE_SHA256,
             "VERIFIER_DIGEST_CHANGED")
        namespace = {"__name__": "pinned_stage_e_ci_verifier", "__file__": str(source)}
        exec(compile(raw, str(source), "exec"), namespace)
        need(callable(namespace.get("gh_api")) and callable(namespace.get("verify_ci")),
             "VERIFIER_FUNCTIONS_MISSING")
        return namespace
    except StageECIDenied:
        raise
    except (OSError, ValueError, TypeError, SyntaxError) as exc:
        raise StageECIDenied("PMV4_E_CI_REFRESH_VERIFIER_UNAVAILABLE") from exc


def paginate_required_checks(namespace: dict[str, Any]) -> None:
    """Pass the original verifier the complete set of required check runs."""
    original = namespace["gh_api"]
    state: dict[str, Any] = {"contexts": None}

    def paginated(endpoint: str, query: str) -> dict:
        if endpoint == CHECK_POLICY:
            policy = original(endpoint, query)
            checks = policy.get("checks") if isinstance(policy, dict) else None
            need(isinstance(checks, list), "REQUIRED_POLICY_INVALID")
            contexts = [row.get("context") for row in checks if isinstance(row, dict)]
            need(len(contexts) == len(checks)
                 and all(isinstance(name, str) and name for name in contexts)
                 and len(set(contexts)) == len(contexts), "REQUIRED_CONTEXT_INVALID")
            state["contexts"] = set(contexts)
            return policy
        if not endpoint.endswith("/check-runs?per_page=100"):
            return original(endpoint, query)
        need(state["contexts"] is not None, "REQUIRED_POLICY_NOT_LOADED")
        base = endpoint.split("?", 1)[0]
        rows: list[dict] = []
        expected = None
        for page in range(1, 11):
            result = original(f"{base}?per_page=100&page={page}", query)
            need(isinstance(result, dict) and type(result.get("count")) is int
                 and isinstance(result.get("rows"), list)
                 and all(isinstance(row, dict) for row in result["rows"]),
                 "CHECK_PAGE_INVALID")
            count = result["count"]
            need(0 <= count <= 1000 and (expected is None or count == expected),
                 "CHECK_COUNT_CHANGED")
            expected = count
            part = result["rows"]
            need(len(part) <= 100, "CHECK_PAGE_OVERFLOW")
            rows.extend(part)
            need(len(rows) <= count, "CHECK_COUNT_OVERFLOW")
            if len(rows) == count:
                break
            need(len(part) == 100, "CHECK_SET_INCOMPLETE")
        need(expected is not None and len(rows) == expected, "CHECK_SET_INCOMPLETE")
        required = [row for row in rows if row.get("name") in state["contexts"]]
        need(8 <= len(required) <= 100, "REQUIRED_CHECK_PROJECTION_INVALID")
        return {"count": len(required), "rows": required}

    namespace["gh_api"] = paginated


def _root_directory(path: Path, *, production: bool) -> None:
    meta = path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(meta.st_mode)
         and not meta.st_mode & 0o022
         and (not production or
              (meta.st_uid, meta.st_gid, stat.S_IMODE(meta.st_mode)) == (0, 0, 0o700)),
         "CONTROL_DIRECTORY_UNTRUSTED")


def _existing_evidence(path: Path, *, production: bool) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1
             and stat.S_IMODE(meta.st_mode) == 0o400
             and 0 < meta.st_size <= 32768
             and (not production or (meta.st_uid, meta.st_gid) == (0, 0)),
             "EXISTING_EVIDENCE_UNTRUSTED")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(32769)
        need(len(raw) == meta.st_size and isinstance(json.loads(raw), dict),
             "EXISTING_EVIDENCE_INVALID")
        return raw
    finally:
        os.close(fd)


def write_evidence(target: Path, evidence: dict[str, Any], *, production: bool) -> str | None:
    """Atomically replace evidence after preserving any previous root file."""
    parent = target.parent
    _root_directory(parent, production=production)
    raw = json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8") + b"\n"
    need(0 < len(raw) <= 32768, "EVIDENCE_SIZE_INVALID")
    previous = None
    if target.exists() or target.is_symlink():
        _existing_evidence(target, production=production)
        previous = parent / (target.name + ".previous." +
                             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                             "." + uuid4().hex)
    temp = parent / ("." + target.name + "." + uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o400)
    linked = False
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        if previous is not None:
            os.link(target, previous, follow_symlinks=False)
            linked = True
        try:
            os.replace(temp, target)
        except BaseException:
            if linked:
                previous.unlink(missing_ok=True)
            raise
        dirfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        temp.unlink(missing_ok=True)
    need(_existing_evidence(target, production=production) == raw,
         "EVIDENCE_READBACK_FAILED")
    return str(previous) if previous else None


def refresh(candidate: str, *, production: bool = True,
            source: Path = SOURCE, target: Path = TARGET) -> dict[str, Any]:
    if production:
        need(os.geteuid() == 0 and Path(__file__) == ENTRY
             and ENTRY.resolve() == ENTRY and not ENTRY.is_symlink()
             and source == SOURCE and target == TARGET,
             "ROOT_INSTALL_REQUIRED")
    need(isinstance(candidate, str) and SHA.fullmatch(candidate) is not None,
         "CANDIDATE_INVALID")
    namespace = load_pinned_attestor(source, production=production)
    paginate_required_checks(namespace)
    evidence = namespace["verify_ci"](candidate)
    need(type(evidence) is dict and evidence.get("candidate_sha") == candidate
         and evidence.get("protected_main_ancestor") is True
         and evidence.get("required_ci_passed") is True
         and isinstance(evidence.get("protected_main"), str)
         and SHA.fullmatch(evidence["protected_main"]) is not None,
         "CI_NOT_VERIFIED")
    previous = write_evidence(target, evidence, production=production)
    return {
        "status": "fresh_protected_ci_verified",
        "candidate_sha": candidate, "protected_main": evidence["protected_main"],
        "verified_at": evidence["verified_at"], "previous_evidence": previous,
        "production_unit_changes": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args()
    print(json.dumps(refresh(args.candidate_sha), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PermissionError, OSError, ValueError, TypeError) as exc:
        print("DENIED:" + type(exc).__name__ + ":" + str(exc)[:180])
        raise SystemExit(1)
