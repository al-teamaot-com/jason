"""Execute actual isolated, non-provider JSON parity/recovery suites for all 19.

No production API is called. The matrix never changes source acceptance bits,
claims live preproduction, stages the production registry, or promotes a JSON
version. Exact provider target acceptance is an independent subsequent gate.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from tools.legacy_json_acceptance_ledger import ROOT, build


# Each candidate is paired with actual, separately maintained pytest suites.
# Shared source tests cover previous minimal candidate workflows, rather than
# inventing source-specific behavioral assertions where none exist.
CASE_TESTS = {
    "backupiq_endpoint_backup": ("implementation/runtime_service/tests/test_json_backupiq_classifier.py",),
    "client_information_request": ("implementation/runtime_service/tests/test_json_client_question_plan.py",),
    "datto_edr_av": ("implementation/runtime_service/tests/test_json_edr_av_planner.py",),
    "disk_bad_block_event_7": ("implementation/runtime_service/tests/test_json_hardware_triage.py",),
    "dns_agent_diagnostic": ("implementation/runtime_service/tests/test_json_dns_agent_classifier.py",),
    "drmm_recent_alert_reconciliation": ("tests/test_legacy_json_behavioral_parity.py", "tests/test_json_readonly_shadow_pilot_acceptance.py"),
    "gpt_insights_tech_assist": ("implementation/runtime_service/tests/test_json_gpt_insights_projection.py",),
    "idle_log_off": ("implementation/runtime_service/tests/test_json_idle_logoff_classifier.py",),
    "jason_activity_log": ("implementation/runtime_service/tests/test_json_activity_projection.py",),
    "low_disk_space": ("implementation/runtime_service/tests/test_json_low_disk_classification.py",),
    "offline_ticket_context_augmentation": ("implementation/runtime_service/tests/test_json_offline_context_preprod.py", "implementation/runtime_service/tests/test_json_offline_context_shadow.py"),
    "post_error_investigation": ("implementation/runtime_service/tests/test_json_hardware_triage.py",),
    "security_log_self_heal": ("implementation/runtime_service/tests/test_json_security_log_classifier.py",),
    "unexpected_shutdown": ("implementation/runtime_service/tests/test_json_shutdown_classification.py",),
    "unsupported_readonly_triage_note": ("tests/test_legacy_json_behavioral_parity.py",),
    "unsupported_triage_human_review": ("tests/test_legacy_json_behavioral_parity.py",),
    "vulscan_missing_patch": ("implementation/runtime_service/tests/test_json_vulscan_patch_classifier.py",),
    "vulscan_multi_device_split": ("implementation/runtime_service/tests/test_json_vulscan_split_plan.py", "implementation/runtime_service/tests/test_ticket_split_runtime.py"),
    "windows_time_source": ("implementation/runtime_service/tests/test_json_windows_time_source_migration.py", "implementation/runtime_service/tests/test_json_windows_time_preprod.py", "implementation/runtime_service/tests/test_json_windows_time_sweep.py"),
}

SHARED_RECOVERY = (
    "tests/test_legacy_json_isolated_preprod_acceptance.py",
    "tests/test_all_legacy_json_candidates_isolated_registry.py",
    "tests/test_json_governed_shadow_integration.py",
    "tests/test_json_playbook_isolated_trace.py",
    "implementation/runtime_service/tests/test_json_governed_mutation_bridge.py",
    "implementation/runtime_service/tests/test_autonomy_indeterminate_recovery.py",
)
BOUNDARY_TESTS = ("tests/test_legacy_json_preprod_boundary.py",)


def _counts(junit: Path) -> tuple[dict[str, dict[str, int]], dict[str,int]]:
    root = ET.parse(junit).getroot()
    per_file: dict[str, dict[str,int]] = {}
    totals = {"passed":0,"failed":0,"errors":0,"skipped":0,"executed":0}
    for tc in root.iter("testcase"):
        # Pytest's junit family xunit2 omits the file attribute and uses
        # classname=tests.<module>; normalize to test module stem.
        file = Path(tc.attrib.get("file") or
                    tc.attrib.get("classname", "").replace(".", "/" )).stem
        row = per_file.setdefault(file, {"passed":0,"failed":0,"errors":0,"skipped":0,"executed":0})
        kind = "failed" if tc.find("failure") is not None else (
            "errors" if tc.find("error") is not None else (
            "skipped" if tc.find("skipped") is not None else "passed"))
        row[kind] += 1
        row["executed"] += 1
        totals[kind] += 1
        totals["executed"] += 1
    return per_file,totals


def run(*, root: Path = ROOT) -> dict:
    """Run private synthetic test matrix, fail closed on skipped/no tests/failures."""
    if root.resolve() != ROOT.resolve() or root.is_symlink():
        raise ValueError("PREPROD_MATRIX_SOURCE_ROOT_CHANGED")
    ledger=build()
    ids={entry["id"] for entry in ledger["entries"]}
    if ids!=set(CASE_TESTS) or len(ids)!=19 or ledger["fully_accepted_migrations"]!=0:
        raise ValueError("PREPROD_MATRIX_INVENTORY_OR_ACCEPTANCE_CHANGED")
    tests=set(SHARED_RECOVERY+BOUNDARY_TESTS)
    for values in CASE_TESTS.values():
        tests.update(values)
    for name in tests:
        full = root/name
        if (not full.is_file() or full.is_symlink() or
                root.resolve() not in full.resolve().parents):
            raise ValueError("PREPROD_MATRIX_TEST_MISSING_OR_ESCAPED:"+name)
    output=root/"tmp/json-preprod-parity-recovery"
    output.mkdir(mode=0o700,parents=True,exist_ok=True)
    if output.is_symlink():
        raise ValueError("PREPROD_MATRIX_OUTPUT_SYMLINK")
    junit=output/"pytest-matrix.xml"
    if junit.is_symlink():
        raise ValueError("PREPROD_MATRIX_JUNIT_SYMLINK")
    env=os.environ.copy()
    env["PYTHONPATH"]=".:implementation:implementation/runtime_service/src"
    cmd=[sys.executable,"-m","pytest","-q","-ra", "--disable-warnings",
         "--override-ini=junit_family=xunit1",
         "--junitxml",str(junit),*sorted(tests)]
    completed=subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,text=True,timeout=180)
    if not junit.is_file():
        raise ValueError("PREPROD_MATRIX_JUNIT_MISSING")
    file_counts, totals=_counts(junit)
    outcomes={}
    for entry in ledger["entries"]:
        names=CASE_TESTS[entry["id"]]
        numbers={k:sum(file_counts.get(Path(n).stem,{}).get(k,0) for n in names)
                 for k in totals}
        local_ok=bool(numbers["passed"]) and not numbers["failed"] and not numbers["errors"]
        outcomes[entry["id"]]={
            "json_fingerprint":entry["json_fingerprint"],
            "source_test_modules":list(names),
            "executed_test_cases":numbers,
            "isolated_source_tests": "pass" if local_ok else "fail_or_unverified",
            "full_behavior_parity": "NOT_ACCEPTED",
            "per_playbook_crash_recovery": "NOT_END_TO_END_VERIFIED",
            "live_provider_connected_preproduction": "NOT_RUN_UNAPPROVED",
            "owner_action_approval": "NOT_GRANTED",
            "production_activation":False,
            "legacy_retired":False,
        }
    shared={k:sum(file_counts.get(Path(n).stem,{}).get(k,0) for n in SHARED_RECOVERY)
            for k in totals}
    boundary={k:sum(file_counts.get(Path(n).stem,{}).get(k,0) for n in BOUNDARY_TESTS)
              for k in totals}
    result={
        "status": ("isolated_synthetic_matrix_pass" if completed.returncode==0
                   and all(x["isolated_source_tests"]=="pass" for x in outcomes.values())
                   and shared["passed"]>0 and boundary["passed"]>0
                   else "isolated_synthetic_matrix_failed"),
        "junit_test_totals":totals,
        "shared_recovery_test_totals":shared,
        "governance_boundary_test_totals":boundary,
        "cases":outcomes,
        "live_preproduction_provider_calls":0,
        "live_preproduction_provider_writes":0,
        "production_json_registry_modified":False,
        "legacy_retirement_actions":0,
        "fully_accepted":0,
        "pytest_exit_code":completed.returncode,
        "pytest_summary_tail":completed.stdout[-1200:],
    }
    evidence=output/"matrix-results.json"
    if evidence.is_symlink():
        raise ValueError("PREPROD_MATRIX_EVIDENCE_SYMLINK")
    evidence.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    os.chmod(evidence,0o600)
    return result


if __name__ == "__main__":
    report=run()
    print("matrix_status="+report["status"])
    print("pytest_total="+str(report["junit_test_totals"]))
    print("shared_recovery="+str(report["shared_recovery_test_totals"]))
    print("governance_boundary="+str(report["governance_boundary_test_totals"]))
    print("candidate_source_pass="+str(sum(x["isolated_source_tests"]=="pass" for x in report["cases"].values()))+"/19")
    if report["status"]!="isolated_synthetic_matrix_pass":
        raise SystemExit(1)
