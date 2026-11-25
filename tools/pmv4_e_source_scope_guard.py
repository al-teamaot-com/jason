#!/usr/bin/env python3
"""Recheck protected Stage E source under the host and freeze boundaries.

Uses the existing JES-005 verifier as the unprivileged repository owner.
This module grants no release authority and performs no provider or host
mutation. The signed Stage E ledger still verifies the Owner proof.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable, Mapping

from tools.independent_component_release import trusted_file

TRUST = Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted")
NATIVE_TRUST = Path("/usr/local/lib/jason/pmv4-e-bootstrap/native")
ENTRIES = frozenset(root / "tools/pmv4_e_source_scope_guard.py"
                    for root in (TRUST, NATIVE_TRUST))
MANUAL = TRUST / "tools/manual_release_scope.py"
REPO = Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo")
CI = Path("/var/lib/jason/independent-component-release/control/protected-ci.json")
REMOTE = "https://github.com/al-teamaot-com/jason.git"
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
PASS = "PMV4_E_REVIEWED_SOURCE_SCOPE_VERIFIED"
CHILD = (
    "import importlib.util,sys; from pathlib import Path; "
    "s=importlib.util.spec_from_file_location('stage_e_scope',sys.argv[1]); "
    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
    "m.verify_pinned_candidate_against_main(Path(sys.argv[2]),"
    "sys.argv[3],sys.argv[4],sys.argv[5]); "
    "print('PMV4_E_REVIEWED_SOURCE_SCOPE_VERIFIED')"
)
SAFE_ENV = (
    "PATH=/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM=1",
    "GIT_CONFIG_GLOBAL=/dev/null", "GIT_TERMINAL_PROMPT=0",
    "GIT_OPTIONAL_LOCKS=0", "GIT_NO_REPLACE_OBJECTS=1",
    "GIT_GRAFT_FILE=/dev/null", "GIT_ATTR_NOSYSTEM=1",
    "GIT_CONFIG_COUNT=2", "GIT_CONFIG_KEY_0=core.fsmonitor",
    "GIT_CONFIG_VALUE_0=false", "GIT_CONFIG_KEY_1=core.hooksPath",
    "GIT_CONFIG_VALUE_1=/dev/null",
)


class StageESourceScopeDenied(PermissionError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise StageESourceScopeDenied("PMV4_E_SOURCE_SCOPE_" + reason)


def _trusted_code(path: Path, expected_sha256: str | None = None) -> bytes:
    try:
        meta = path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
             and (meta.st_uid, meta.st_gid, meta.st_nlink) == (0, 0, 1)
             and stat.S_IMODE(meta.st_mode) == 0o444
             and 0 < meta.st_size <= 1000000, "ROOT_CODE_UNTRUSTED")
        raw = path.read_bytes()
        need(len(raw) == meta.st_size and
             (expected_sha256 is None or
              sha256(raw).hexdigest() == expected_sha256),
             "ROOT_CODE_DIGEST_CHANGED")
        return raw
    except StageESourceScopeDenied:
        raise
    except OSError as exc:
        raise StageESourceScopeDenied(
            "PMV4_E_SOURCE_SCOPE_ROOT_CODE_UNAVAILABLE") from exc


def verify_under_lock(
    *, candidate: str, rollback: str, manual_sha256: str,
    host_lock_held: bool, freeze_lock_held: bool,
    production: bool = True,
    runner: Callable[..., Any] | None = None,
    ci_data: Mapping[str, Any] | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Verify CI, advertised main and JES-005 before accepting the signature."""
    manual_path = MANUAL
    if production:
        here = Path(__file__)
        need(os.geteuid() == 0 and here in ENTRIES
             and here.resolve() == here and not here.is_symlink()
             and runner is None and ci_data is None and at is None,
             "CANONICAL_ROOT_GUARD_REQUIRED")
        _trusted_code(here)
        manual_path = here.parent / "manual_release_scope.py"
        need(type(manual_sha256) is str and DIGEST.fullmatch(manual_sha256) is not None,
             "MANUAL_SCOPE_DIGEST_INVALID")
        _trusted_code(manual_path, manual_sha256)
        try:
            info = REPO.lstat()
            need(not REPO.is_symlink() and stat.S_ISDIR(info.st_mode)
                 and (info.st_uid, info.st_gid) == (1000, 1000)
                 and stat.S_IMODE(info.st_mode) == 0o700,
                 "REVIEW_REPOSITORY_UNTRUSTED")
            ci_data = json.loads(trusted_file(CI, production=True, max_bytes=32768))
        except StageESourceScopeDenied:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise StageESourceScopeDenied(
                "PMV4_E_SOURCE_SCOPE_EVIDENCE_UNAVAILABLE") from exc
    need(host_lock_held is True and freeze_lock_held is True,
         "NATIVE_LOCKS_REQUIRED")
    need(type(candidate) is str and SHA.fullmatch(candidate) is not None
         and type(rollback) is str and SHA.fullmatch(rollback) is not None
         and candidate != rollback, "RELEASE_IDENTITY_INVALID")
    need(type(manual_sha256) is str and DIGEST.fullmatch(manual_sha256) is not None,
         "MANUAL_SCOPE_DIGEST_INVALID")
    now = at or datetime.now(timezone.utc)
    try:
        observed = datetime.fromisoformat(str(ci_data["verified_at"]).replace("Z", "+00:00"))
        age = (now - observed).total_seconds()
        head = ci_data["protected_main"]
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise StageESourceScopeDenied(
            "PMV4_E_SOURCE_SCOPE_CI_EVIDENCE_INVALID") from exc
    need(now.tzinfo is not None and observed.tzinfo is not None
         and 0 <= age <= 600 and type(ci_data) is dict
         and ci_data.get("candidate_sha") == candidate
         and ci_data.get("protected_main_ancestor") is True
         and ci_data.get("required_ci_passed") is True
         and type(head) is str and SHA.fullmatch(head) is not None,
         "CI_EVIDENCE_STALE_OR_MISMATCHED")

    invoke = runner or subprocess.run
    prefix = ["/usr/sbin/runuser", "-u", "al", "--", "/usr/bin/env", "-i", *SAFE_ENV]
    try:
        remote = invoke(
            prefix + ["/usr/bin/git", "ls-remote", REMOTE, "refs/heads/main"],
            cwd="/", env={"PATH": "/usr/bin:/bin"}, capture_output=True,
            text=True, timeout=45, check=False,
        )
        need(remote.returncode == 0 and len(remote.stdout) <= 256
             and remote.stdout.split() == [head, "refs/heads/main"],
             "PROTECTED_MAIN_CHANGED")
        shallow = invoke(
            prefix + ["/usr/bin/git", "-C", str(REPO), "rev-parse",
                      "--is-shallow-repository"],
            cwd="/", env={"PATH": "/usr/bin:/bin"}, capture_output=True,
            text=True, timeout=30, check=False,
        )
        need(shallow.returncode == 0 and shallow.stdout.strip() == "false",
             "REVIEW_REPOSITORY_SHALLOW")
        scoped = invoke(
            prefix + ["/usr/bin/python3", "-I", "-B", "-c", CHILD,
                      str(manual_path), str(REPO), rollback, candidate, head],
            cwd="/", env={"PATH": "/usr/bin:/bin"}, capture_output=True,
            text=True, timeout=120, check=False,
        )
        need(scoped.returncode == 0 and scoped.stdout.strip() == PASS,
             "PROTECTED_SCOPE_NOT_REVIEWED")
    except StageESourceScopeDenied:
        raise
    except (OSError, subprocess.SubprocessError, TypeError, AttributeError) as exc:
        raise StageESourceScopeDenied(
            "PMV4_E_SOURCE_SCOPE_VERIFICATION_UNAVAILABLE") from exc
    return {
        "status": "protected_stage_e_source_scope_verified_under_lock",
        "candidate_sha": candidate, "rollback_sha": rollback,
        "protected_main": head, "production_mutations": False,
    }
