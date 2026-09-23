from jason_mcp import server


def allow_reads(monkeypatch):
    monkeypatch.setattr(
        server,
        "_dynamic_read_capability_allowed",
        lambda name: True,
    )


def test_incomplete_output_read_never_reaches_provider(
    monkeypatch,
):
    allow_reads(monkeypatch)

    called = []

    def governed_read(**kwargs):
        called.append(kwargs)
        raise AssertionError(
            "provider path must not be called"
        )

    monkeypatch.setattr(
        server,
        "_governed_read",
        governed_read,
    )

    result = server.execute_read_capability(
        capability="automation.job.output.read",
        arguments={
            "resource_id": "job-123",
        },
    )

    assert result["status"] == "rejected"
    assert (
        result["error_code"]
        == "AUTOMATION_JOB_OUTPUT_SELECTORS_REQUIRED"
    )
    assert result["provider_called"] is False
    assert result["failure_domain"] == (
        "request_construction"
    )
    assert result["do_not_redispatch"] is True
    assert result["missing_arguments"] == [
        "device_uid",
        "component_uid",
    ]
    assert called == []


def test_complete_output_read_forwards_exact_selectors(
    monkeypatch,
):
    allow_reads(monkeypatch)

    captured = {}

    def governed_read(
        *,
        capability_name,
        arguments,
    ):
        captured["capability"] = capability_name
        captured["arguments"] = arguments

        return {
            "status": "succeeded",
            "evidence": {
                "data": {
                    "match_count": 1,
                }
            },
        }

    monkeypatch.setattr(
        server,
        "_governed_read",
        governed_read,
    )

    result = server.execute_read_capability(
        capability="automation.job.output.read",
        arguments={
            "resource_id": "job-123",
            "device_uid": "device-123",
            "component_uid": "component-123",
        },
    )

    assert result["status"] == "succeeded"

    assert captured == {
        "capability": (
            "automation.job.output.read"
        ),
        "arguments": {
            "resource_id": "job-123",
            "device_uid": "device-123",
            "component_uid": "component-123",
            "stream": "stdout",
        },
    }


def test_execution_projection_returns_followup_bundle():
    projected = server._project_action_result(
        "automation.component.execute",
        {
            "data": {
                "status": "accepted",
                "job_uid": "job-123",
                "job_status": "active",
                "device_uid": "device-123",
                "component_uid": "component-123",
                "component_name": "Example Component",
            }
        },
    )

    assert projected["job_read_arguments"] == {
        "resource_id": "job-123",
    }

    assert projected["output_read_arguments"] == {
        "resource_id": "job-123",
        "device_uid": "device-123",
        "component_uid": "component-123",
        "stream": "stdout",
    }

    assert (
        projected["follow_up_contract"][
            "do_not_redispatch"
        ]
        is True
    )


def test_nested_followup_bundle_is_accepted(
    monkeypatch,
):
    allow_reads(monkeypatch)

    captured = {}

    def governed_read(
        *,
        capability_name,
        arguments,
    ):
        captured.update(arguments)

        return {
            "status": "succeeded",
            "evidence": {
                "data": {}
            },
        }

    monkeypatch.setattr(
        server,
        "_governed_read",
        governed_read,
    )

    result = server.execute_read_capability(
        capability="automation.job.output.read",
        arguments={
            "output_read_arguments": {
                "resource_id": "job-123",
                "device_uid": "device-123",
                "component_uid": "component-123",
                "stream": "stdout",
            }
        },
    )

    assert result["status"] == "succeeded"
    assert captured["resource_id"] == "job-123"
    assert captured["device_uid"] == "device-123"
    assert (
        captured["component_uid"]
        == "component-123"
    )
