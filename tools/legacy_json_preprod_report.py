"""Render redacted observed isolated parity/authorization evidence to markdown."""
from __future__ import annotations
import json
from pathlib import Path
from tools.legacy_json_acceptance_ledger import ROOT, build
from tools.legacy_json_preprod_boundary import redacted_boundary_summary


def generate() -> dict:
    root=ROOT
    folder=root/"tmp/json-preprod-parity-recovery"
    tests=json.loads((folder/"matrix-results.json").read_text())
    live=json.loads((folder/"live-auth-evidence.json").read_text())
    boundary=json.loads((root/"docs/playbooks/json/migration/governed-preprod-boundary-v1.json").read_text())
    registry={
        "status":live["live_json_registry"]["status"],
        "generation":live["live_json_registry"]["generation"],
        "playbooks":[] if live["live_json_registry"]["registered_count"]==0 else None,
    }
    owner={"status":live["owner_acceptance"]["status"],
           "error_code":live["owner_acceptance"]["error_code"]}
    audit=redacted_boundary_summary(boundary,
                                    main_sha=boundary["reviewed_main_sha"],
                                    owner_status=owner,
                                    registry_status=registry)
    if len(tests["cases"])!=19 or not audit["all_19_candidates_unactivated"]:
        raise ValueError("PREPROD_SOURCE_OR_PRODUCTION_BOUNDARY_CHANGED")
    if tests["status"]!="isolated_synthetic_matrix_pass":
        raise ValueError("SYNTHETIC_ACCEPTANCE_FAILED")
    if audit["live_provider_authorized_playbooks"]!=0:
        raise ValueError("UNEXPECTED_LIVE_PREPROD_AUTHORITY")
    lines=[
        "# Governed JSON migration — isolated parity and recovery execution",
        "",
        "## Verified execution basis",
        "- Test source baseline main SHA: `"+boundary["reviewed_main_sha"]+"` (pinned to this execution, not prospective authorization for any future merge SHA)",
        "- Verified production JSON registry: generation **0**, **0** registered JSON versions.",
        "- Owner-only acceptance/canary response: `"+live["owner_acceptance"]["error_code"]+"` / `"+live["owner_canary"]["error_code"]+"`.",
        "- Test target manifest: **0 explicitly approved isolated provider tenants/tickets/devices**.",
        "- Production JSON activation **NOT PERMITTED**; legacy retirement **NOT PERMITTED**.",
        "- No provider call, provider write, protected Core change, remote restart, or external client communication in this isolated run.",
        "",
        "## Executed non-provider parity/recovery matrix",
        "- Source-only / synthetic matrix: **"+tests["status"]+"**.",
        "- Total real executed pytest cases: **"+str(tests["junit_test_totals"]["passed"])+" passed**, "+str(tests["junit_test_totals"]["failed"])+" failed, "+str(tests["junit_test_totals"]["errors"])+" errors, "+str(tests["junit_test_totals"]["skipped"])+" skipped.",
        "- Shared isolated checkpoint/identity/recovery suites: **"+str(tests["shared_recovery_test_totals"]["passed"])+" passed**; these are cross-cutting, not 19 individual live crash-recovery certifications.",
        "- Governance-boundary negative tests: **"+str(tests["governance_boundary_test_totals"]["passed"])+" passed**.",
        "- Per-playbook synthetic source test files exercised: **19/19**. Real provider full behavioral parity: **0/19 accepted**.",
        "",
        "| Candidate | Executed associated synthetic tests | Isolated source tests | End-to-end restart / recovery | Provider-backed preproduction |",
        "|---|---:|---|---|---|",
    ]
    for k,v in sorted(tests["cases"].items()):
        lines.append("| `"+k+"` | "+str(v["executed_test_cases"]["passed"])+" | "+v["isolated_source_tests"]+" | Not fully verified | Blocked by Owner/target boundary |")
    lines.extend([
        "",
        "## Readiness and real blockers",
        "The live Owner admin status returned `AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`. No exact provider-bound isolated test target was independently verified. These two facts prevent running real modifying preproduction tests. A named client or device inferred from production search results is **not** equivalent to an authorized test target; no such production target was used.",
        "",
        "To open the live acceptance gate, Jason must independently validate an authenticated Owner session, test tenant/client/device/ticket identity and provider binding, legacy scheduler exclusion for exact targets, exact action arguments and TTL, immutable signed per-action receipts, and dedicated provider readback. This local boundary check is NOT a service-side authorization grant.",
        "",
        "## Continuing acceptance requirements",
        "Each legacy candidate still needs exact full positive/negative parity, source version/fixture binding, error and timeout paths, per-job interruption/restart/duplicate suppression, independent provider readback and a real isolated test-target audit. See `ALL-19-ACCEPTANCE-MATRIX.md`. The shared JSON shadow integration intentionally blocks mutations; successful synthetic results cannot be promoted into execution authority.",
        "",
        "**Overall: test boundary defined and enforced fail-closed, isolated synthetic matrix PASS, real governed provider preproduction acceptance NOT RUN, fully accepted replacements 0/19. Production activation and legacy retirement remain independently controlled.**",
        "",
    ])
    report=root/"docs/playbooks/json/migration/GOVERNED-PREPROD-PARITY-RECOVERY-20261119.md"
    report.write_text("\n".join(lines))
    (folder/"redacted-boundary-status.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    return {"report":str(report), "live_unapproved":audit["live_provider_blocked_playbooks"],
            "tests_passed":tests["junit_test_totals"]["passed"],
            "shared_recovery_passed":tests["shared_recovery_test_totals"]["passed"]}


if __name__=="__main__":
    print(generate())
