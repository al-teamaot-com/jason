"""Read-only Workboard release scope guard for Jason's existing governed release workflow.

This module deliberately NEVER issues approval, unfreezes production, rewrites
a configuration, restarts OpenClaw, or invents another release manager.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


class WorkboardScopeError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def candidate_for(baseline: dict[str, Any]) -> dict[str, Any]:
    """Return only the explicitly authorized Workboard allowlist delta."""
    if not isinstance(baseline, dict):
        raise WorkboardScopeError("baseline must be object")
    # Serialization copy avoids mutation of the input.
    result = json.loads(json.dumps(baseline))
    plugins = result.get("plugins")
    if not isinstance(plugins, dict):
        raise WorkboardScopeError("existing plugins config required")
    allow = plugins.get("allow")
    entries = plugins.get("entries")
    if not isinstance(allow, list) or not all(isinstance(v, str) for v in allow):
        raise WorkboardScopeError("existing explicit plugin allowlist required")
    if not isinstance(entries, dict):
        raise WorkboardScopeError("existing plugin entries required")
    if "workboard" in allow or "workboard" in entries:
        raise WorkboardScopeError("Workboard already configured; do not double apply")
    allow.append("workboard")
    entries["workboard"] = {"enabled": True, "config": {}}
    return result


def verify(
    baseline_bytes: bytes,
    manifest: dict[str, Any],
    *,
    candidate_bytes: bytes | None = None,
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise WorkboardScopeError("manifest must be JSON object")
    base_sha = manifest.get("base_config_sha256")
    cand_sha = manifest.get("candidate_config_sha256")
    rollback_sha = manifest.get("rollback_config_sha256")
    scope_sha = manifest.get("reviewed_scope_sha256")
    if not all(isinstance(x, str) and len(x) == 64
               and all(c in "0123456789abcdef" for c in x)
               for x in (base_sha, cand_sha, rollback_sha, scope_sha)):
        raise WorkboardScopeError("exact immutable hashes required")
    if sha(baseline_bytes) != base_sha or rollback_sha != base_sha:
        raise WorkboardScopeError("configuration baseline drift; stop")
    if manifest.get("candidate_id") != "jman-workboard-activation-20261109":
        raise WorkboardScopeError("unknown activation scope")
    baseline = json.loads(baseline_bytes)
    expected = candidate_for(baseline)
    if candidate_bytes is not None:
        candidate = json.loads(candidate_bytes)
        if candidate != expected:
            raise WorkboardScopeError("candidate contains unauthorized differences")
        if sha(candidate_bytes) != cand_sha:
            raise WorkboardScopeError("candidate byte hash differs from sealed approval subject")
    return {
        "status": "preflight_passed",
        "baseline_config_sha256": base_sha,
        "candidate_config_sha256": cand_sha,
        "reviewed_scope_sha256": scope_sha,
        "requires_authenticated_teams_release_approval": True,
        "production_authority_granted": False,
        "gateway_restart_authorized": False,
        "automatic_dispatch_authorized": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight Workboard activation without mutation")
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--scope", type=Path, required=True)
    args = ap.parse_args()
    # Files have private content. Never display config or secret values.
    for p in (args.baseline, args.candidate, args.scope):
        if not p.is_file() or p.is_symlink() or p.stat().st_size > 1048576:
            ap.error("invalid source input")
    manifest = json.loads(args.scope.read_text())
    result = verify(args.baseline.read_bytes(), manifest,
                    candidate_bytes=args.candidate.read_bytes())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
