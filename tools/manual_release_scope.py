"""Read-only manual release scope: protect other development from implicit release bundling.

No checkout, branch, service or release record is mutated by this module.
A reviewed scope is NOT an Owner's exact-SHA deployment authorization.
"""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SHA = re.compile(r"^[0-9a-f]{40}$")
PR = re.compile(r"#([0-9]+)")
# 2026-10-28: production registered 1,020 parallel worktrees, exceeding
# the historical 600-worktree ceiling. Every registered checkout still must
# be inspected. 2,000 is a bounded fail-closed ceiling, not permission to
# skip, prune or implicitly acknowledge other developers' changes.
MAX_REGISTERED_WORKTREES = 2000
# Only the canonical native Release Manager may own these transient, detached
# checkouts. They are created AFTER owner scope review and BEFORE its final
# revalidation, so counting one as unrelated developer work makes *every*
# promotion reject itself. No ordinary development checkout qualifies.
INTERNAL_RELEASE_WORKTREE_ROOT = Path(
    "/var/lib/jason/openclaw/release-manager/worktrees"
)


class ScopeBlocked(ValueError):
    pass


def command(args, cwd=None):
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=45,
                                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScopeBlocked("required read-only evidence unavailable") from exc
    if result.returncode or len(result.stdout) > 6000000:
        raise ScopeBlocked("required read-only evidence incomplete")
    return result.stdout


def repository_from_origin(repo):
    """Resolve the actual Git remote identity, never a caller-selected PR scope."""
    from urllib.parse import urlparse
    url = command(["git", "remote", "get-url", "origin"], repo).strip()
    if "://" in url:
        path = urlparse(url).path.strip("/")
    elif ":" in url and "@" in url.split(":", 1)[0]:
        path = url.split(":", 1)[1]
    else:
        raise ScopeBlocked("GitHub repository origin is not verifiable")
    if path.endswith(".git"):
        path = path[:-4]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        raise ScopeBlocked("GitHub repository origin does not identify owner/name")
    return path


def verify_pinned_candidate_against_main(repo, baseline, candidate, current_main=None):
    """Allow a manual pinned candidate only when newer protected commits are unrelated.

    This is read-only verification, not approval. Every path touched since the
    candidate (including subsequently reverted edits) is considered. Runtime
    release-control and policy paths always force a new review/release.
    """
    if not SHA.fullmatch(candidate) or not SHA.fullmatch(baseline):
        raise ScopeBlocked("exact SHA required")
    if current_main is None:
        remote = command(["git", "ls-remote", "origin", "refs/heads/main"], repo).split()
        if len(remote) != 2 or remote[1] != "refs/heads/main" or not SHA.fullmatch(remote[0]):
            raise ScopeBlocked("protected main cannot be verified")
        current_main = remote[0]
    if not SHA.fullmatch(current_main):
        raise ScopeBlocked("protected main revision invalid")
    command(["git", "merge-base", "--is-ancestor", baseline, candidate], repo)
    command(["git", "merge-base", "--is-ancestor", candidate, current_main], repo)
    if current_main == candidate:
        return
    policy_file = Path(repo) / "config/release-manager-policy.json"
    if not policy_file.is_file() or policy_file.is_symlink():
        raise ScopeBlocked("protected release policy unavailable")
    try:
        policy = json.loads(policy_file.read_text(encoding="utf-8"))
        patterns = policy["protected_core_globs"]
        if not isinstance(patterns, list) or not patterns or not all(
            isinstance(x, str) and x for x in patterns
        ):
            raise ValueError("invalid protected patterns")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScopeBlocked("protected release policy invalid") from exc
    candidate_paths = set(command(["git", "diff", "--no-renames", "--name-only",
                                   baseline, candidate], repo).splitlines())
    newer_paths = set(command(["git", "log", "--format=", "--name-only",
                               "--no-renames", candidate + ".." + current_main],
                              repo).splitlines())
    control_paths = {
        "tools/manual_release_scope.py",
        "config/release-manager-policy.json",
        "config/production-desired-state.json",
    }
    conflicts = sorted(path for path in newer_paths if path in candidate_paths
                       or path in control_paths
                       or any(fnmatch.fnmatch(path, pat) for pat in patterns))
    if conflicts:
        raise ScopeBlocked("newer protected commits affect pinned release scope or controls: "
                           + ", ".join(conflicts[:6]))


def source_scope(repo, baseline, candidate):
    if not SHA.fullmatch(baseline) or not SHA.fullmatch(candidate):
        raise ScopeBlocked("exact SHA required")
    verify_pinned_candidate_against_main(repo, baseline, candidate)
    commits = []
    lines = command(["git", "log", "--first-parent", "--reverse",
                     "--format=%H%x09%s", baseline + ".." + candidate], repo).splitlines()
    for line in lines:
        sha, separator, subject = line.partition("\t")
        if not separator or not SHA.fullmatch(sha):
            raise ScopeBlocked("unverifiable commit history")
        commits.append({"sha": sha, "subject": subject[:240],
                        "prs": sorted({int(x) for x in PR.findall(subject)})})
    files = sorted(set(command(["git", "diff", "--no-renames", "--name-only",
                                baseline, candidate], repo).splitlines()))
    if not 1 <= len(commits) <= 250 or not 1 <= len(files) <= 800:
        raise ScopeBlocked("release history or file scope outside bounds")
    return commits, files


def _verified_ephemeral_release_worktree(path, record, candidate_sha):
    """Exclude ONLY this candidate's immutable native temporary checkout.

    The path must be a canonical release-owned per-run worktree, detached at
    exactly the reviewed candidate, clean across ALL files (not just files
    overlapping this release), with a Git registry HEAD agreeing with disk.
    A corrupt or dirty candidate-shaped path denies the review, never silently
    becomes an ignored worktree. Ordinary developer worktrees are not ignored.
    """
    if not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha):
        return False
    root = INTERNAL_RELEASE_WORKTREE_ROOT
    if (path.parent != root or not re.fullmatch(
            re.escape(candidate_sha) + r"-[0-9a-f]{12}", path.name)):
        return False
    if root.is_symlink() or not root.is_dir():
        raise ScopeBlocked("canonical release worktree root invalid")
    if not record or record[0] != "worktree " + str(path):
        raise ScopeBlocked("canonical release worktree registry invalid")
    if "HEAD " + candidate_sha not in record[1:] or "detached" not in record[1:]:
        raise ScopeBlocked("native release worktree is not detached at reviewed SHA")
    if any(line.startswith(("branch ", "locked")) for line in record[1:]):
        raise ScopeBlocked("native release worktree has unexpected branch or lock")
    prune = [line for line in record[1:] if line.startswith("prunable ")]
    if not path.is_dir():
        if (prune != ["prunable gitdir file points to non-existent location"]
                or path.is_symlink()):
            raise ScopeBlocked("unverified stale native release worktree registration")
        return True
    if prune or path.is_symlink() or path.resolve() != path:
        raise ScopeBlocked("native release worktree filesystem is untrusted")
    if path.stat().st_uid != os.getuid():
        raise ScopeBlocked("native release worktree owner mismatch")
    if command(["git", "rev-parse", "HEAD"], path).strip() != candidate_sha:
        raise ScopeBlocked("native release worktree Git revision mismatch")
    if command(["git", "status", "--porcelain=v1", "--untracked-files=all"], path).strip():
        raise ScopeBlocked("native release worktree has local modifications")
    return True


def dirty_worktrees(repo, changed, candidate_sha=None):
    # The authoritative Git registry may retain orphaned entries for worktree
    # paths which no longer exist. Do not mutate any development checkout or
    # registry just to complete an owner's release review. Only Git's exact
    # "prunable gitdir file points to non-existent location" evidence allows
    # a missing directory to be classified as stale; every real checkout
    # must still be inspected, including ones after a stale entry.
    raw = command(["git", "worktree", "list", "--porcelain"], repo)
    records = [part.splitlines() for part in raw.strip().split("\n\n") if part.strip()]
    if not 1 <= len(records) <= MAX_REGISTERED_WORKTREES:
        raise ScopeBlocked("incomplete registered worktree set")
    paths = []
    for record in records:
        if not record or not record[0].startswith("worktree "):
            raise ScopeBlocked("unparseable registered worktree")
        p = Path(record[0][9:])
        if not p.is_absolute() or p in paths:
            raise ScopeBlocked("duplicated or relative worktree path")
        paths.append(p)
    overlaps = []
    stale = []
    inspected = 0
    verified_internal = 0
    for path, record in zip(paths, records):
        if _verified_ephemeral_release_worktree(path, record, candidate_sha):
            # This exact-SHA pristine internal worktree was created BY the
            # transaction under review. Deduct it from the digest-bearing
            # registry count so it cannot invalidate its own prior review.
            # All unrelated worktrees are still counted and fully inspected.
            verified_internal += 1
            continue
        prune_markers = [line for line in record[1:] if line.startswith("prunable ")]
        if not path.is_dir():
            if (prune_markers !=
                    ["prunable gitdir file points to non-existent location"]
                    or any(line.startswith("locked") for line in record[1:])):
                raise ScopeBlocked("registered development worktree unavailable")
            stale.append(str(path))
            continue
        if prune_markers:
            raise ScopeBlocked("Git worktree unexpectedly marked prunable while present")
        inspected += 1
        status = command(["git", "status", "--porcelain=v1", "--untracked-files=normal",
                          "--", *sorted(changed)], path)
        dirty = set()
        for line in status.splitlines():
            if len(line) < 4 or line[2] != " ":
                raise ScopeBlocked("unparseable worktree status")
            filename = line[3:]
            if filename.startswith('"') or " -> " in filename:
                raise ScopeBlocked("worktree path requires explicit review")
            dirty.add(filename)
        common = sorted(changed.intersection(dirty))
        if common:
            overlaps.append({"path": str(path), "changed_files": common})
    return overlaps, inspected, stale, len(paths) - verified_internal


def open_pr_overlaps(repository, changed, reader=command):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ScopeBlocked("exact repository required")
    raw = reader(["gh", "pr", "list", "--repo", repository, "--state", "open",
                  "--limit", "250", "--json", "number,headRefName,files"])
    try:
        rows = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ScopeBlocked("unverifiable open PR inventory") from exc
    if not isinstance(rows, list) or len(rows) >= 250:
        raise ScopeBlocked("open PR listing truncated")
    overlaps = []
    for row in rows:
        files = row.get("files")
        if not isinstance(files, list):
            raise ScopeBlocked("unverifiable open PR changed files")
        if len(files) >= 100:
            # GitHub's GraphQL PR summary caps the file list. Retrieve every
            # page instead of silently trusting its first 100 filenames.
            number = row.get("number")
            if not isinstance(number, int) or number < 1:
                raise ScopeBlocked("invalid open PR identifier")
            raw_pages = command([
                "gh", "api", "--paginate", "--slurp",
                "repos/" + repository + "/pulls/" + str(number) + "/files?per_page=100",
            ])
            try:
                pages = json.loads(raw_pages)
                full = [file for page in pages for file in page]
                if not isinstance(pages, list) or not 100 <= len(full) < 3000:
                    raise ScopeBlocked("open PR full file list incomplete")
                files = [{"path": item["filename"]} for item in full]
            except (TypeError, KeyError, ValueError) as exc:
                raise ScopeBlocked("open PR full file list unverified") from exc
        common = sorted(changed.intersection(x["path"] for x in files))
        if common:
            overlaps.append({"number": row["number"], "branch": row["headRefName"],
                             "changed_files": common})
    return sorted(overlaps, key=lambda x: x["number"]), len(rows)


def review(repo, repository, baseline, candidate, allowed_prs=(),
           allowed_commits=(), acknowledged_prs=(), acknowledged_worktrees=(),
           pr_reader=command, worktree_repo=None):
    repo = Path(repo).resolve(strict=True)
    commits, paths = source_scope(repo, baseline, candidate)
    dirty, worktree_count, stale, registrations = dirty_worktrees(
        Path(worktree_repo or repo), set(paths), candidate)
    prs, pr_count = open_pr_overlaps(repository, set(paths), reader=pr_reader)
    allowed_prs, allowed_commits = set(allowed_prs), set(allowed_commits)
    acknowledged_prs, acknowledged_worktrees = set(acknowledged_prs), set(acknowledged_worktrees)
    missing = [c["sha"] for c in commits
               if c["sha"] not in allowed_commits and not allowed_prs.intersection(c["prs"])]
    unreviewed_prs = [p["number"] for p in prs if p["number"] not in acknowledged_prs]
    unreviewed_worktrees = [w["path"] for w in dirty if w["path"] not in acknowledged_worktrees]
    valid = (allowed_prs.issubset({n for c in commits for n in c["prs"]})
             and allowed_commits.issubset({c["sha"] for c in commits})
             and acknowledged_prs.issubset({p["number"] for p in prs})
             and acknowledged_worktrees.issubset({w["path"] for w in dirty}))
    digest = hashlib.sha256(json.dumps(
        [baseline, candidate, commits, paths, prs, dirty, stale, registrations],
        sort_keys=True).encode()).hexdigest()
    ready = valid and not missing and not unreviewed_prs and not unreviewed_worktrees
    return {"status": "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED" if ready else "BLOCKED_SCOPE",
            "candidate_sha": candidate, "baseline_sha": baseline,
            "scope_sha256": digest, "commits": commits, "changed_files": paths,
            "unreviewed_commit_shas": missing, "open_pr_overlaps": prs,
            "unreviewed_open_prs": unreviewed_prs, "dirty_worktree_overlaps": dirty,
            "unreviewed_worktrees": unreviewed_worktrees, "acknowledgments_valid": valid,
            "worktrees_inspected": worktree_count,
            "registered_worktrees": registrations,
            "git_verified_stale_registrations": stale,
            "open_prs_inspected": pr_count,
            "deployment_authorized": False,
            "scope_limitation": "Whole protected-main revision, not selected cherry-picked fixes"}


def main():
    p = argparse.ArgumentParser(description="Review full manual release scope without mutation")
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--worktree-repo", type=Path)
    p.add_argument("--baseline-sha", required=True)
    p.add_argument("--candidate-sha", required=True)
    p.add_argument("--include-pr", type=int, action="append", default=[])
    p.add_argument("--include-commit", action="append", default=[])
    p.add_argument("--acknowledge-overlapping-pr", type=int, action="append", default=[])
    p.add_argument("--acknowledge-dirty-worktree", action="append", default=[])
    a = p.parse_args()
    try:
        result = review(a.repo, a.repository, a.baseline_sha, a.candidate_sha,
                        a.include_pr, a.include_commit, a.acknowledge_overlapping_pr,
                        a.acknowledge_dirty_worktree, worktree_repo=a.worktree_repo)
    except (ScopeBlocked, OSError, ValueError) as e:
        print(json.dumps({"status": "BLOCKED_EVIDENCE", "error_type": type(e).__name__,
                          "reason": str(e)[:160] if isinstance(e, ScopeBlocked) else "unclassified",
                          "deployment_authorized": False}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
