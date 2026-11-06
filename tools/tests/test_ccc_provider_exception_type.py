"""The CCC report may include only a bounded exception class, not provider secrets."""
from __future__ import annotations

import json
from types import SimpleNamespace

from tools import ccc_runner


def test_ccc_sanitizes_exception_type_and_excludes_error_text(monkeypatch):
    checks = (
        {"name":"datto_edr", "capability":"endpoint.security.status.read",
         "expected_provider":"datto_edr", "expected_status":"succeeded"},
        {"name":"dnsfilter", "capability":"dns.protection.organization.read",
         "expected_provider":"dnsfilter", "expected_status":"succeeded"},
    )
    runner = object.__new__(ccc_runner.CCCRunner)
    runner.config = SimpleNamespace(provider_canaries=checks,
                                    ccc_principal_id="jason-ccc-worker",organization_id="aot")
    model_rows=[
        {"name":"datto_edr","status":"exception","error_type":"TimeoutError",
         "error":"secret-token-must-not-leak"},
        {"name":"dnsfilter","status":"exception","error_type":"RuntimeError",
         "error":"another-secret"},
    ]
    monkeypatch.setattr(ccc_runner,"_run",lambda *a,**kw:
                        SimpleNamespace(returncode=0,stdout=json.dumps(model_rows)))
    result = runner._provider_canary_check()
    assert result.status == "FAIL"
    assert len(result.evidence["failures"]) == 2
    assert result.evidence["expected_canary_count"] == 2
    assert [x["exception_type"] for x in result.evidence["results"]] == [
        "TimeoutError","RuntimeError"]
    assert "secret-token-must-not-leak" not in json.dumps(result.evidence)
    assert "another-secret" not in json.dumps(result.evidence)
