from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from jason_runtime.pm_v2_runtime import (
    ALLOWED_CONTROLS,
    PM_V2_CONTROL,
    PM_V2_PROVIDER,
    PM_V2_STATUS,
    PMV2RuntimeInvoker,
    _control_capability,
    _status_capability,
)


def _resolution(capability):
    return SimpleNamespace(
        selected_provider_id=PM_V2_PROVIDER,
        capability_name=capability,
    )


def _request(capability, *, mode, arguments=None, idem="idem-1"):
    return SimpleNamespace(
        capability_name=capability,
        permission_mode=mode,
        arguments=arguments or {},
        idempotency_key=idem,
        execution_id="exec-1",
        principal_id="owner",
        organization_id="aot",
        correlation_id="corr-1",
    )


def test_status_read_returns_bounded_snapshot(tmp_path):
    status = tmp_path / "status.json"
    status.write_text(
        '{"schema_version":"1.0","generated_at":"now",'
        '"summary":{"assignment_count":1},'
        '"assignments":[{"assignment_id":"a1","state":"running"}],'
        '"components":[],"nodes":[]}'
    )
    invoker = PMV2RuntimeInvoker(
        status_path=status,
        control_request_dir=tmp_path / "requests",
    )
    result = invoker.invoke(
        request=_request(PM_V2_STATUS, mode="observe"),
        resolution=_resolution(PM_V2_STATUS),
    )
    assert result.output["summary"]["assignment_count"] == 1
    exact = invoker.invoke(
        request=_request(
            PM_V2_STATUS,
            mode="observe",
            arguments={"assignment_id": "a1"},
        ),
        resolution=_resolution(PM_V2_STATUS),
    )
    assert exact.output["assignment"]["assignment_id"] == "a1"


def test_control_queues_exact_idempotent_request(tmp_path):
    invoker = PMV2RuntimeInvoker(
        status_path=tmp_path / "status.json",
        control_request_dir=tmp_path / "requests",
    )
    request = _request(
        PM_V2_CONTROL,
        mode="execute",
        arguments={"assignment_id": "a1", "action": "pause"},
    )
    first = invoker.invoke(
        request=request, resolution=_resolution(PM_V2_CONTROL)
    )
    second = invoker.invoke(
        request=request, resolution=_resolution(PM_V2_CONTROL)
    )
    assert first.output["status"] == "queued"
    assert second.output["status"] == "already_queued"
    path = tmp_path / "requests" / f"{first.output['request_id']}.json"
    payload = __import__("json").loads(path.read_text())
    assert payload["source"] == "governed_runtime_authenticated_request"
    assert payload["principal_id"] == "owner"
    assert payload["action"] == "pause"


def test_control_rejects_wrong_mode_and_priority_shape(tmp_path):
    invoker = PMV2RuntimeInvoker(
        status_path=tmp_path / "status.json",
        control_request_dir=tmp_path / "requests",
    )
    with pytest.raises(PermissionError):
        invoker.invoke(
            request=_request(
                PM_V2_CONTROL,
                mode="observe",
                arguments={"assignment_id": "a1", "action": "cancel"},
            ),
            resolution=_resolution(PM_V2_CONTROL),
        )
    with pytest.raises(ValueError):
        invoker.invoke(
            request=_request(
                PM_V2_CONTROL,
                mode="execute",
                arguments={
                    "assignment_id": "a1",
                    "action": "priority",
                    "priority": "high",
                },
            ),
            resolution=_resolution(PM_V2_CONTROL),
        )


def test_capability_metadata_is_provider_neutral_and_self_describing():
    now = datetime.now(timezone.utc)
    read = _status_capability(now)
    control = _control_capability(now)
    assert read.metadata["operation"] == "read"
    assert read.metadata["read_only"] == "true"
    assert control.metadata["operation"] == "update"
    assert control.metadata["conversation_authenticated_imperative_is_approval"] == "true"
    assert ALLOWED_CONTROLS == {"priority", "pause", "resume", "cancel"}
