"""Output pagination proves bounded, exact, read-only evidence retrieval."""
import pytest

from jason_mcp import server


JOB = "e523dd87-c050-4528-9e95-2fcc3addeff8"
DEVICE = "69571572-83f7-1e33-9cdf-01717d4e74a4"
COMPONENT = "79943f0c-e614-4fcc-a5da-e396feab0a34"
SELECTORS = {"resource_id": JOB, "device_uid": DEVICE, "component_uid": COMPONENT, "stream": "stdout"}


def provider_output(text: str, *, truncated: bool = False):
    return {
        "provider": "datto_rmm",
        "provider_capability": "datto_rmm.job.output.read",
        "data": {
            **SELECTORS,
            "outputs": [{"component_uid": COMPONENT, "stream": "stdout", "component_name": "Windows Diagnostic Snapshot - AOT",
                         "text": text, "truncated": truncated}],
            "match_count": 1,
            "output_bounded": truncated,
            "discovery_complete": True,
        },
    }


def test_reconstruct_large_diagnostic_json_from_read_only_pages():
    payload = "AOT DIAGNOSTIC | fixture | PC\nAOT_DIAGNOSTIC_JSON_BEGIN\n" + '{"long":"' + ("a" * 9800) + '"}' + "\nAOT_DIAGNOSTIC_JSON_END"
    pages = []
    for start in range(0, len(payload), 1600):
        result = server._project_datto_job_output_window(provider_output(payload), offset=start,
                                                         maximum_chars=1600, selectors=SELECTORS)
        window = result["data"]["window"]
        pages.extend(row["text"] for row in result["data"]["outputs"])
        assert window["offset"] == start
        assert window["returned_chars"] <= 1600
        assert window["available_chars"] == len(payload)
        assert window["has_more"] == (start + window["returned_chars"] < len(payload))
        assert window["provider_output_truncated"] is False
        assert len(result["data"]["outputs"]) <= 1
    assert "".join(pages) == payload


def test_datto_bounded_record_is_never_claimed_complete():
    prefix = "AOT DIAGNOSTIC | fixture | PC\nAOT_DIAGNOSTIC_JSON_BEGIN\n"
    truncated_output = prefix + ("x" * (65536 - len(prefix)))
    result = server._project_datto_job_output_window(provider_output(truncated_output, truncated=True),
                                                     offset=65000, maximum_chars=800, selectors=SELECTORS)
    window = result["data"]["window"]
    assert window["returned_chars"] == 536
    assert window["has_more"] is False
    assert window["provider_output_truncated"] is True
    assert result["data"]["output_bounded"] is True


def test_provider_output_selector_mismatch_fails_closed():
    evil = provider_output("private data")
    evil["data"]["component_uid"] = "other-component"
    with pytest.raises(ValueError, match="SELECTOR_MISMATCH"):
        server._project_datto_job_output_window(evil, offset=0, maximum_chars=1000, selectors=SELECTORS)
    evil = provider_output("private data")
    evil["data"]["outputs"][0]["stream"] = "stderr"
    with pytest.raises(ValueError, match="STREAM_MISMATCH"):
        server._project_datto_job_output_window(evil, offset=0, maximum_chars=1000, selectors=SELECTORS)



def test_job_and_device_selector_identity_cannot_be_substituted():
    for key in ("resource_id", "device_uid"):
        source = provider_output("AOT DIAGNOSTIC | fixture | PC\\nAOT_DIAGNOSTIC_JSON_BEGIN\\n{}")
        source["data"][key] = "different-" + key
        with pytest.raises(ValueError, match="SELECTOR_MISMATCH"):
            server._project_datto_job_output_window(
                source, offset=0, maximum_chars=500, selectors=SELECTORS,
            )


def test_window_crosses_record_boundary_without_leaking_other_components():
    a = "AOT DIAGNOSTIC | fixture | PC\\nAOT_DIAGNOSTIC_JSON_BEGIN\\n"
    b = '{"a":1}\\nAOT_DIAGNOSTIC_JSON_END'
    source = provider_output(a)
    source["data"]["outputs"].append({
        "component_uid": COMPONENT, "stream": "stdout",
        "component_name": "Windows Diagnostic Snapshot - AOT",
        "text": b, "truncated": False,
    })
    start = len(a) - 8
    page = server._project_datto_job_output_window(
        source, offset=start, maximum_chars=30, selectors=SELECTORS,
    )
    combined = "".join(item["text"] for item in page["data"]["outputs"])
    assert combined == (a + b)[start:start + 30]
    assert page["data"]["window"]["returned_chars"] == 30
    assert page["data"]["window"]["has_more"] == (start + 30 < len(a + b))


def test_disabled_flag_rejects_before_governed_or_provider_read(monkeypatch):
    monkeypatch.delenv("JASON_DATTO_JOB_OUTPUT_PAGING_ENABLED", raising=False)
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda capability: True)
    calls = []
    monkeypatch.setattr(server, "_governed_read", lambda **kwargs: calls.append(kwargs))
    result = server.execute_read_capability(capability="automation.job.output.read",
        arguments={**SELECTORS, "output_offset": 2000, "output_chars": 1000})
    assert result["error_code"] == "AUTOMATION_JOB_OUTPUT_PAGING_DISABLED"
    assert result["provider_called"] is False
    assert calls == []


@pytest.mark.parametrize("offset,size", [(True,1000), (-1,1000), (65537,1000),
                                          (0,False), (0,0), (0,1801), ("0",1000)])
def test_invalid_window_rejected_before_provider(monkeypatch, offset, size):
    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_ENABLED", "true")
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda capability: True)
    calls = []
    monkeypatch.setattr(server, "_governed_read", lambda **kwargs: calls.append(kwargs))
    result = server.execute_read_capability(capability="automation.job.output.read",
        arguments={**SELECTORS, "output_offset": offset, "output_chars": size})
    assert result["error_code"] == "AUTOMATION_JOB_OUTPUT_WINDOW_INVALID"
    assert result["provider_called"] is False
    assert calls == []


def test_exact_selectors_forwarded_and_window_not_sent_to_provider(monkeypatch):
    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_ENABLED", "true")
    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_COMPONENT_UIDS", COMPONENT)
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda capability: True)
    captured = []

    def fake_governed_read(**kwargs):
        captured.append(kwargs)
        window = server._project_datto_job_output_window(
            provider_output("AOT DIAGNOSTIC | fixture | PC\nAOT_DIAGNOSTIC_JSON_BEGIN\n" + "a" * 4000), offset=1234,
                                                          maximum_chars=1600, selectors=SELECTORS)
        return {"status":"succeeded", "evidence": window}

    monkeypatch.setattr(server, "_governed_read", fake_governed_read)
    result = server.execute_read_capability(capability="automation.job.output.read",
        arguments={**SELECTORS, "output_offset": 1234, "output_chars": 1600})
    assert captured[0]["capability_name"] == "automation.job.output.read"
    assert captured[0]["arguments"] == SELECTORS
    assert captured[0]["job_output_window"] == (1234,1600)
    assert result["status"] == "succeeded"
    assert result["evidence"]["data"]["window"]["returned_chars"] == 1600
    assert result["evidence"]["data"]["outputs"][0]["text"] == "a" * 1600


def test_not_enrolled_component_rejected_before_provider(monkeypatch):
    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_ENABLED", "true")
    monkeypatch.delenv("JASON_DATTO_JOB_OUTPUT_PAGING_COMPONENT_UIDS", raising=False)
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda capability: True)
    calls = []
    monkeypatch.setattr(server, "_governed_read", lambda **kwargs: calls.append(kwargs))
    result = server.execute_read_capability(
        capability="automation.job.output.read",
        arguments={**SELECTORS, "output_offset": 0, "output_chars": 1600},
    )
    assert result["error_code"] == "AUTOMATION_JOB_OUTPUT_COMPONENT_NOT_ENROLLED"
    assert result["provider_called"] is False
    assert calls == []


def test_unrecognized_diagnostic_envelope_refused():
    with pytest.raises(ValueError, match="DIAGNOSTIC_CONTRACT_REQUIRED"):
        server._project_datto_job_output_window(
            provider_output("arbitrary stdout may contain a password"),
            offset=0, maximum_chars=1400, selectors=SELECTORS,
        )


def test_projection_error_not_returned_as_success(monkeypatch):
    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_ENABLED", "true")
    monkeypatch.setenv("JASON_DATTO_JOB_OUTPUT_PAGING_COMPONENT_UIDS", COMPONENT)
    monkeypatch.setattr(server, "_dynamic_read_capability_allowed", lambda capability: True)

    def governed(**kwargs):
        raise ValueError("AUTOMATION_JOB_OUTPUT_DIAGNOSTIC_CONTRACT_REQUIRED")

    monkeypatch.setattr(server, "_governed_read", governed)
    response = server.execute_read_capability(
        capability="automation.job.output.read",
        arguments={**SELECTORS, "output_offset": 0, "output_chars": 1500},
    )
    assert response["status"] == "rejected"
    assert response["error_code"] == "AUTOMATION_JOB_OUTPUT_DIAGNOSTIC_CONTRACT_REQUIRED"
    assert response["do_not_redispatch"] is True
