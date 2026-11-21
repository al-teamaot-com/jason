"""Current protected CI and exact installed code closure for an Owner objective."""
from __future__ import annotations

import fnmatch
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

TRUSTED = Path("/usr/local/lib/jason/owner-objective/trusted")
SOURCE_REPO = Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo")
DERIVED_OUTPUTS = frozenset({
    "docs/control/AUTOMATED-CHANGE-STATE.json",
    "docs/control/AUTOMATED-CHANGE-STATE.md",
})
OWNER = ["/usr/sbin/runuser", "-u", "al", "--", "/usr/bin/env", "-i",
         "PATH=/usr/bin:/bin", "HOME=/home/al", "GIT_CONFIG_NOSYSTEM=1",
         "GIT_CONFIG_GLOBAL=/dev/null", "GIT_OPTIONAL_LOCKS=0",
         "GIT_NO_REPLACE_OBJECTS=1", "GIT_GRAFT_FILE=/dev/null",
         "GIT_CONFIG_COUNT=2", "GIT_CONFIG_KEY_0=core.fsmonitor", "GIT_CONFIG_VALUE_0=false",
         "GIT_CONFIG_KEY_1=core.hooksPath", "GIT_CONFIG_VALUE_1=/dev/null"]


def git(*args):
    p = subprocess.run([*OWNER, "/usr/bin/git", "-C", str(SOURCE_REPO), *args],
                       capture_output=True, text=True, timeout=45)
    if p.returncode:
        raise PermissionError("OBJECTIVE_PROTECTED_SOURCE_UNAVAILABLE")
    return p.stdout.strip()


def newer_touched_paths(namespace, candidate, head):
    """Complete read-only per-commit evidence, including subsequently reverted paths."""
    if candidate == head:
        return set()
    api = namespace["gh_api"]
    commits = []
    expected = None
    for page in range(1, 11):
        result = api("repos/al-teamaot-com/jason/compare/" + candidate + "..." + head
                     + "?per_page=100&page=" + str(page),
                     "{total:.total_commits,base:.merge_base_commit.sha,status,commits:[.commits[].sha]}")
        total, part = result.get("total"), result.get("commits")
        if (type(total) is not int or not 1 <= total <= 1000
                or (expected is not None and total != expected)
                or result.get("base") != candidate or result.get("status") != "ahead"
                or not isinstance(part, list) or not 1 <= len(part) <= 100
                or any(type(sha) is not str or not re.fullmatch("[0-9a-f]{40}", sha) for sha in part)):
            raise PermissionError("OBJECTIVE_NEWER_COMMIT_EVIDENCE_INCOMPLETE")
        expected = total
        commits.extend(part)
        if len(commits) == expected:
            break
        if len(part) != 100 or len(commits) > expected:
            raise PermissionError("OBJECTIVE_NEWER_COMMIT_PAGE_INCOMPLETE")
    if (len(commits) != expected or len(set(commits)) != expected or head not in commits):
        raise PermissionError("OBJECTIVE_NEWER_COMMIT_SET_INCOMPLETE")
    changed = set()
    for commit in commits:
        for page in range(1, 31):
            result = api("repos/al-teamaot-com/jason/commits/" + commit
                         + "?per_page=100&page=" + str(page),
                         "{sha,files:[.files[]|{name:.filename,previous:.previous_filename}]}")
            rows = result.get("files")
            if result.get("sha") != commit or not isinstance(rows, list) or len(rows) > 100:
                raise PermissionError("OBJECTIVE_NEWER_FILE_EVIDENCE_INCOMPLETE")
            for row in rows:
                for value in (row.get("name"), row.get("previous")):
                    if value is None:
                        continue
                    if (type(value) is not str or not 0 < len(value) <= 4096
                            or value.startswith("/") or ".." in value.split("/") or "\x00" in value):
                        raise PermissionError("OBJECTIVE_NEWER_FILE_NAME_INVALID")
                    changed.add(value)
            if len(changed) > 10000:
                raise PermissionError("OBJECTIVE_NEWER_SOURCE_OVER_LIMIT")
            if len(rows) < 100:
                break
        else:
            raise PermissionError("OBJECTIVE_NEWER_FILE_LIMIT_EXCEEDED")
    return changed


def verify(config, candidate):
    if (os.geteuid() != 0
            or Path(__file__).resolve() != TRUSTED / "tools/owner_objective_source_verifier.py"
            or candidate != config["source_sha"] or not re.fullmatch(r"[0-9a-f]{40}", candidate)):
        raise PermissionError("OBJECTIVE_SOURCE_VERIFIER_NOT_INSTALLED")
    from tools import pmv4_e_ci_refresh as ci
    namespace = ci.load_pinned_attestor(ci.SOURCE, production=True)
    original_api = namespace["gh_api"]
    ci.paginate_required_checks(namespace)
    evidence = namespace["verify_ci"](candidate)
    from tools.owner_objective_ci import require_acceptance
    require_acceptance(original_api, candidate)
    if (evidence["required_ci_passed"] is not True
            or evidence["protected_main_ancestor"] is not True):
        raise PermissionError("OBJECTIVE_REQUIRED_CI_NOT_PASSED")
    head = evidence["protected_main"]
    # The reviewed source repository is READ ONLY in this Root service.
    # Its exact candidate objects are prepared before governed installation.
    for name, expected in config["files_sha256"].items():
        raw = subprocess.run([*OWNER, "/usr/bin/git", "-C", str(SOURCE_REPO),
                              "show", candidate + ":" + name],
                             capture_output=True, timeout=15, check=True).stdout
        if sha256(raw).hexdigest() != expected:
            raise PermissionError("OBJECTIVE_IMMUTABLE_CODE_DIFFERS_FROM_GIT")
    changed = newer_touched_paths(namespace, candidate, head)
    policy = json.loads(git("show", candidate + ":config/release-manager-policy.json"))
    patterns = policy["protected_core_globs"]
    controls = {"config/release-manager-policy.json", "config/production-desired-state.json",
                "tools/manual_release_scope.py"}
    for path in changed:
        if path in DERIVED_OUTPUTS:
            continue
        if path in config["files_sha256"] or path in controls or any(
                fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            raise PermissionError("OBJECTIVE_NEWER_SOURCE_CHANGED_SCOPE_OR_CONTROLS")
    return True
