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
        "correlation_id": "corr-governed-qbo-read",
        "capability": "accounting.company.read", "provider": "quickbooks",
        "evidence": {
            "provider": "quickbooks",
            "provider_capability": "quickbooks.company.read",
            "data": {"CompanyInfo": {
                "CompanyName": company, "LegalName": legal, "domain": "QBO"
            }}
        }
    }


def oauth_status():
    return {
        "provider": "quickbooks", "environment": "production",
        "connected": True, "realm_bound": True, "has_refresh_token": True,
        "pending_authorization": False, "secret_values_printed": False,
    }


def evaluate(payload, *, runtime=accept.PRODUCTION_PROFILE, mcp=accept.PRODUCTION_PROFILE, oauth=None, aligned=True):
    return accept.assess(
        payload, runtime_profile=runtime, mcp_profile=mcp,
        oauth_status=oauth if oauth is not None else oauth_status(), services_aligned=aligned,
    )


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
    oauth = tmp_path / "oauth.json"
    oauth.write_text(json.dumps(oauth_status()), encoding="utf-8")
    run = subprocess.run([
        sys.executable, str(SOURCE), "--result-json", str(p),
        "--oauth-status-json", str(oauth),
    ], capture_output=True, text=True, check=False)
    assert run.returncode == 1
    assert '"status": "fail"' in run.stdout
    assert "Unrecognized" not in run.stdout
    assert "Not AOT" not in run.stdout


def test_expired_access_token_is_not_accepted_as_connected():
    status = oauth_status()
    status["connected"] = False
    assert evaluate(result(), oauth=status)["status"] == "fail"


def test_refresh_token_presence_and_realm_binding_are_both_required():
    for key in ("has_refresh_token", "realm_bound"):
        status = oauth_status()
        status[key] = False
        assert evaluate(result(), oauth=status)["status"] == "fail"


def test_sandbox_oauth_status_cannot_validate_production():
    status = oauth_status()
    status["environment"] = "sandbox"
    assert evaluate(result(), oauth=status)["status"] == "fail"


def test_unauthorized_credential_logging_or_pending_auth_fails():
    for field, value in (("secret_values_printed", True), ("pending_authorization", True)):
        status = oauth_status()
        status[field] = value
        assert evaluate(result(), oauth=status)["status"] == "fail"


def test_conflicting_legal_name_requires_review():
    assert evaluate(result(company="Atlantic Office Technologies", legal="Different Business"))["status"] == "fail"


def test_one_verified_name_with_optional_empty_legal_name_is_allowed():
    assert evaluate(result(company="Atlantic Office Machines, Inc.", legal=""))["status"] == "pass"


def test_missing_correlation_id_cannot_pass():
    payload = result()
    del payload["correlation_id"]
    assert evaluate(payload)["status"] == "fail"


def test_missing_oauth_attestation_fails():
    report = accept.assess(result(), runtime_profile=accept.PRODUCTION_PROFILE,
                           mcp_profile=accept.PRODUCTION_PROFILE, oauth_status=None,
                           services_aligned=True)
    assert report["status"] == "fail"


def test_misaligned_or_unhealthy_live_services_cannot_pass():
    assert evaluate(result(), aligned=False)["status"] == "fail"


def _docker_output(*, runtime_profile="production", mcp_profile="production",
                   runtime_health="healthy", runtime_sha="a" * 40,
                   mcp_sha="a" * 40, running="true"):
    return "\n".join((
        f"/jason-runtime|{running}|{runtime_health}|{runtime_sha}|{runtime_profile}",
        f"/jason-mcp-pilot|true|none|{mcp_sha}|{mcp_profile}",
    )) + "\n"


def test_live_docker_readback_parses_only_profiles_and_source(monkeypatch):
    class Completed:
        stdout = _docker_output()
    def runner(args, **kwargs):
        assert args[:4] == ["docker", "inspect", "jason-runtime", "jason-mcp-pilot"]
        assert "quickbooks-production-read-v1" in args[-1]
        assert kwargs["capture_output"] is True
        return Completed()
    monkeypatch.setattr(accept.subprocess, "run", runner)
    assert accept.inspect_live_services() == (
        accept.PRODUCTION_PROFILE, accept.PRODUCTION_PROFILE, True,
    )


def test_live_docker_readback_rejects_mismatched_source(monkeypatch):
    class Completed:
        stdout = _docker_output(mcp_sha="b" * 40)
    monkeypatch.setattr(accept.subprocess, "run", lambda *a, **k: Completed())
    assert accept.inspect_live_services()[2] is False


def test_live_docker_readback_rejects_unhealthy_runtime(monkeypatch):
    class Completed:
        stdout = _docker_output(runtime_health="unhealthy")
    monkeypatch.setattr(accept.subprocess, "run", lambda *a, **k: Completed())
    assert accept.inspect_live_services()[2] is False


def test_live_docker_readback_rejects_unknown_profile(monkeypatch):
    class Completed:
        stdout = _docker_output(mcp_profile="unknown")
    monkeypatch.setattr(accept.subprocess, "run", lambda *a, **k: Completed())
    import pytest
    with pytest.raises(ValueError):
        accept.inspect_live_services()


def test_live_docker_readback_rejects_duplicate_container(monkeypatch):
    class Completed:
        stdout = _docker_output().replace("/jason-mcp-pilot", "/jason-runtime")
    monkeypatch.setattr(accept.subprocess, "run", lambda *a, **k: Completed())
    import pytest
    with pytest.raises(ValueError):
        accept.inspect_live_services()
