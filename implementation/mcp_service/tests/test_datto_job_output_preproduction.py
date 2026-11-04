"""Isolated preproduction fixture: full governed read path, no live provider I/O."""
import json
from types import SimpleNamespace

from jason_mcp import server
from test_datto_job_output_paging import COMPONENT, JOB, DEVICE, SELECTORS, provider_output


def run_preprod(monkeypatch, *, granted: bool = True):
    header = "AOT DIAGNOSTIC | windows-diagnostic-snapshot | AL\nAOT_DIAGNOSTIC_JSON_BEGIN\n"
    payload = json.dumps({
        "schema_version": "1.0",
        "component": "windows-diagnostic-snapshot",
        "computer": "AL",
        "read_only": True,
        "sections": [{"name": "sample", "status": "complete", "data": {"large": "x" * 10500}}],
    }, separators=(",", ":"))
    original = header + payload + "\nAOT_DIAGNOSTIC_JSON_END\n"
    calls = []
    authorizations = []

    class Authority:
        def evaluate(self, request):
            authorizations.append(request)
            return SimpleNamespace(
                outcome=(server.AuthorityOutcome.ALLOWED if granted else server.AuthorityOutcome.DENIED),
                reason_codes=(() if granted else ("test_scope_denied",)),
                execution_context=SimpleNamespace(
                    context_id="test_preprod_authorized_context",
                    approval_required=False,
                ) if granted else None,
            )

    class Orchestrator:
        def execute(self, request):
            calls.append(request)
            assert request.capability_name == "automation.job.output.read"
            assert request.arguments == SELECTORS
            assert request.permission_mode == "observe"
            return SimpleNamespace(
                status=SimpleNamespace(value="succeeded"),
                stage=SimpleNamespace(value="completed"),
                capability_name=request.capability_name,
                provider_id="datto_rmm",
                reason_codes=("capability_completed",),
                error_code=None,
                correlation_id=request.correlation_id,
                output=provider_output(original),
            )

    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_ENABLED", "true")
    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_COMPONENT_UIDS", COMPONENT)
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed",
                        lambda capability: capability == "automation.job.output.read")
    monkeypatch.setattr(server, "_authenticated_identity",
                        lambda: ("owner-test-principal", "aot-test-organization", "authenticated", None))
    monkeypatch.setattr(server, "_runtime", lambda: SimpleNamespace(
        identity_authority=Authority(), governed_orchestrator=Orchestrator(),
    ))
    return original, calls, authorizations


def test_preproduction_reconstructs_full_diagnostic_over_exact_governed_reads(monkeypatch):
    original, calls, authorizations = run_preprod(monkeypatch)
    fragments = []
    for offset in range(0, len(original), 1600):
        response = server.execute_read_capability(
            capability="automation.job.output.read",
            arguments={**SELECTORS, "output_offset": offset, "output_chars": 1600},
        )
        assert response["status"] == "succeeded"
        assert response["error_code"] is None
        page = response["evidence"]["data"]
        assert page["device_uid"] == DEVICE
        assert page["resource_id"] == JOB
        assert page["component_uid"] == COMPONENT
        assert page["window"]["offset"] == offset
        assert page["window"]["provider_output_truncated"] is False
        fragments.extend(item["text"] for item in page["outputs"])
    assembled = "".join(fragments)
    assert assembled == original
    document = assembled.split("AOT_DIAGNOSTIC_JSON_BEGIN\n", 1)[1].split(
        "\nAOT_DIAGNOSTIC_JSON_END", 1
    )[0]
    parsed = json.loads(document)
    assert parsed["read_only"] is True
    assert parsed["sections"][0]["data"]["large"] == "x" * 10500
    assert len(calls) == len(authorizations) == 7
    assert all(request.requested_mode is server.PermissionMode.OBSERVE
               for request in authorizations)


def test_preproduction_denied_authority_returns_no_provider_content(monkeypatch):
    _, calls, authorizations = run_preprod(monkeypatch, granted=False)
    response = server.execute_read_capability(
        capability="automation.job.output.read",
        arguments={**SELECTORS, "output_offset": 0, "output_chars": 1600},
    )
    assert response["status"] == "denied"
    assert response["reason_codes"] == ["test_scope_denied"]
    assert len(authorizations) == 1
    assert calls == []
    assert "evidence" not in response or not response["evidence"]
