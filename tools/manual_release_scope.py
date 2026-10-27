"""Read-only manual release scope: protect other development from implicit release bundling.

No checkout, branch, service or release record is mutated by this module.
A reviewed scope is NOT an Owner's exact-SHA deployment authorization.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

SHA = re.compile(r"^[0-9a-f]{40}$")
PR = re.compile(r"#([0-9]+)")


class ScopeBlocked(ValueError):
    pass


def command(args, cwd=None):
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScopeBlocked("required read-only evidence unavailable") from exc
    if result.returncode or len(result.stdout) > 6000000:
        raise ScopeBlocked("required read-only evidence incomplete")
    return result.stdout


def source_scope(repo, baseline, candidate):
    if not SHA.fullmatch(baseline) or not SHA.fullmatch(candidate):
        raise ScopeBlocked("exact SHA required")
    remote = command(["git", "ls-remote", "origin", "refs/heads/main"], repo).split()
    if len(remote) != 2 or remote != [candidate, "refs/heads/main"]:
        raise ScopeBlocked("candidate differs from current protected main")
    command(["git", "merge-base", "--is-ancestor", baseline, candidate], repo)
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


def dirty_worktrees(repo, changed):
    lines = command(["git", "worktree", "list", "--porcelain"], repo).splitlines()
    paths = [Path(line[9:]) for line in lines if line.startswith("worktree ")]
    if not 1 <= len(paths) <= 600:
        raise ScopeBlocked("incomplete registered worktree set")
    overlaps = []
    for path in paths:
        if not path.is_dir():
            raise ScopeBlocked("registered development worktree unavailable")
        status = command(["git", "status", "--porcelain=v1", "--untracked-files=normal"], path)
        dirty = set()
        for line in status.splitlines():
            if len(line) < 4 or line[2] != " ":
                raise ScopeBlocked("unparseable worktree status")
            # Git can quote exotic paths. Fail closed instead of guessing.
            filename = line[3:]
            if filename.startswith('"') or " -> " in filename:
                raise ScopeBlocked("worktree path requires explicit review")
            dirty.add(filename)
        common = sorted(changed.intersection(dirty))
        if common:
            overlaps.append({"path": str(path), "changed_files": common})
    return overlaps, len(paths)


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
        if not isinstance(files, list) or len(files) >= 100:
            raise ScopeBlocked("unverifiable open PR changed files")
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
    dirty, worktree_count = dirty_worktrees(Path(worktree_repo or repo), set(paths))
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
    digest = hashlib.sha256(json.dumps([baseline, candidate, commits, paths, prs, dirty],
                                        sort_keys=True).encode()).hexdigest()
    ready = valid and not missing and not unreviewed_prs and not unreviewed_worktrees
    return {"status": "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED" if ready else "BLOCKED_SCOPE",
            "candidate_sha": candidate, "baseline_sha": baseline,
            "scope_sha256": digest, "commits": commits, "changed_files": paths,
            "unreviewed_commit_shas": missing, "open_pr_overlaps": prs,
            "unreviewed_open_prs": unreviewed_prs, "dirty_worktree_overlaps": dirty,
            "unreviewed_worktrees": unreviewed_worktrees, "acknowledgments_valid": valid,
            "worktrees_inspected": worktree_count, "open_prs_inspected": pr_count,
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
                          "deployment_authorized": False}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
