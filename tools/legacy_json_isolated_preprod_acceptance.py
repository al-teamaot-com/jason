"""One-shot, source-only PMv4 JSON isolated draft acceptance.

Only opens a *private* output directory under the migration worktree's
ignored tmp directory. Never addresses a production JSON registry, changes
active versions, or connects to provider/Owner approval endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os

from implementation.autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from tools.legacy_json_acceptance_ledger import ROOT, build


BASE = ROOT.resolve()
ISOLATED = BASE / "tmp" / "json-isolated-preprod-validation"


def run(*, output_root: Path = ISOLATED) -> dict:
    target = Path(output_root)
    if target != ISOLATED or target.is_symlink():
        raise ValueError("ISOLATED_PREPROD_OUTPUT_DIRECTORY_FIXED")
    if not (BASE / "docs/playbooks/json/migration/candidates").is_dir():
        raise ValueError("SOURCE_CANDIDATE_PATH_MISSING")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.mkdir(mode=0o700, exist_ok=True)
    if target.resolve() != ISOLATED:
        raise ValueError("ISOLATED_PREPROD_DIR_REPARSED")
    for path in (target, target.parent):
        if path.is_symlink():
            raise ValueError("ISOLATED_PREPROD_SYMLINK_PATH")
    database = target / "draft-only-json-playbook-registry.sqlite3"
    if database.is_symlink():
        raise ValueError("ISOLATED_PREPROD_REGISTRY_SYMLINK")
    ledger = build()
    if (ledger["verified_inventory"] != 19 or
        ledger["canonical_json_source_artifacts"] != 19 or
        ledger["fully_accepted_migrations"] != 0):
        raise ValueError("ISOLATED_PREPROD_LEDGER_UNEXPECTED")
    store = SQLitePlaybookRegistry(database)
    try:
        seen = []
        for row in ledger["entries"]:
            path = BASE / row["json_source_path"]
            source = path.read_bytes()
            doc = json.loads(source)
            staged = store.stage(
                doc, actor="isolated-source-acceptance-no-owner-grants"
            )
            if (staged.state != "draft" or
                staged.document.fingerprint != row["json_fingerprint"]):
                raise ValueError("ISOLATED_PREPROD_SOURCE_FINGERPRINT_MISMATCH")
            seen.append({
                "id": row["id"], "version": row["json_version"],
                "fingerprint": staged.document.fingerprint,
                "source_sha256": sha256(source).hexdigest(),
                "state": staged.state,
                "governed_action_approved": False,
                "runtime_provider_bound": False,
                "live_preprod_accepted": False,
            })
        if (store.generation() != 19 or
            store.active_snapshot()[1] != ()):
            raise ValueError("ISOLATED_PREPROD_ACTIVE_VERSION_FORBIDDEN")
    finally:
        store.close()
    checked = SQLitePlaybookRegistry(database, read_only=True)
    try:
        if checked.generation() != 19 or checked.active_snapshot()[1] != ():
            raise ValueError("ISOLATED_PREPROD_REOPEN_STATE_CHANGED")
        for row in seen:
            if checked.get(row["id"], row["version"]).state != "draft":
                raise ValueError("ISOLATED_PREPROD_SOURCE_NOT_DRAFT")
    finally:
        checked.close()
    result = {
        "status": "source_draft_registry_acceptance_only",
        "candidate_count": 19,
        "generation": 19,
        "active_json_versions": 0,
        "production_registry_modified": False,
        "production_core_modified": False,
        "provider_calls": 0,
        "provider_writes": 0,
        "live_provider_preproduction_acceptance": False,
        "full_legacy_parity_accepted": 0,
        "versions": sorted(seen, key=lambda r:r["id"]),
    }
    report = target / "isolated-preprod-evidence.json"
    report.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    os.chmod(report,0o600)
    return result


if __name__ == "__main__":
    outcome = run()
    print(
        "isolated_source_preprod_drafts=%d generation=%d active=%d "
        "provider_writes=%d live_provider_preprod_accepted=%s"
        % (
            outcome["candidate_count"],outcome["generation"],
            outcome["active_json_versions"],outcome["provider_writes"],
            outcome["live_provider_preproduction_acceptance"],
        )
    )
