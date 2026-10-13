from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools" / "quickbooks_production_read_acceptance.py"
spec = importlib.util.spec_from_file_location("quickbooks_prod_acceptance_test", SOURCE)
accept = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(accept)


def result(*, company="Atlantic Office Technologies", legal="Atlantic Office Machines, Inc."):
    return {
        "status": "succeeded", "stage": "completed",
        "capability": "accounting.company.read", "provider": "quickbooks",
        "evidence": {
            "provider": "quickbooks",
            "provider_capability": "quickbooks.company.read",
            "data": {"CompanyInfo": {
                "CompanyName": company, "LegalName": legal, "domain": "QBO"
            }}
        }
    }


def evaluate(payload, *, runtime=accept.PRODUCTION_PROFILE, mcp=accept.PRODUCTION_PROFILE):
    return accept.assess(payload, runtime_profile=runtime, mcp_profile=mcp)


def test_exact_aot_result_and_both_production_profiles_pass():
    report = evaluate(result())
    assert report["status"] == "pass"
    assert all(report["checks"].values())


def test_sandbox_company_fails_even_with_production_profile():
    assert evaluate(result(company="Sandbox Company US 3e3b", legal="Sandbox Company US 3e3b"))["status"] == "fail"


def test_mismatched_container_profiles_fail_closed():
    assert evaluate(result(), mcp="quickbooks-sandbox-read-v1")["status"] == "fail"
    assert evaluate(result(), runtime="quickbooks-sandbox-read-v1")["status"] == "fail"


def test_wrong_company_or_weak_substring_match_fails():
    assert evaluate(result(company="Atlantic Office Machines West", legal="Unknown"))["status"] == "fail"


def test_provider_error_fails():
    broken = result()
    broken["status"] = "failed"
    assert evaluate(broken)["status"] == "fail"


def test_missing_provider_evidence_fails():
    broken = result()
    broken["evidence"].pop("provider_capability")
    assert evaluate(broken)["status"] == "fail"


def test_wrong_provider_or_operation_fails():
    broken = result()
    broken["provider"] = "sandbox_mock"
    assert evaluate(broken)["status"] == "fail"


def test_non_qbo_company_payload_fails():
    broken = result()
    broken["evidence"]["data"]["CompanyInfo"]["domain"] = "TEST"
    assert evaluate(broken)["status"] == "fail"


def test_command_line_json_fails_without_echoing_financial_payload(tmp_path):
    p = tmp_path / "output.json"
    p.write_text(json.dumps(result(company="Unrecognized, Inc.", legal="Not AOT")), encoding="utf-8")
    run = subprocess.run([
        sys.executable, str(SOURCE), "--result-json", str(p),
        "--runtime-profile", accept.PRODUCTION_PROFILE,
        "--mcp-profile", accept.PRODUCTION_PROFILE,
    ], capture_output=True, text=True, check=False)
    assert run.returncode == 1
    assert '"status": "fail"' in run.stdout
    assert "Unrecognized" not in run.stdout
    assert "Not AOT" not in run.stdout
