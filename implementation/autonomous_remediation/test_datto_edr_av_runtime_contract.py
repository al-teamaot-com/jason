import pytest

from datto_edr_av_playbook import (
    ActionKind,
    ApprovalClass,
    PlannedAction,
    RepairStep,
)
from datto_edr_av_runtime_contract import (
    AUTOMATION_COMPONENT_EXECUTE,
    AUTOMATION_JOB_OUTPUT_READ,
    AUTOMATION_JOB_READ,
    RuntimeBindingError,
    VERIFIED_COMPONENTS,
    bind_execution,
    bind_job_output_read,
    bind_job_read,
)


def action(operation: str, *, kind: ActionKind = ActionKind.COMPONENT) -> PlannedAction:
    return PlannedAction(
        step=RepairStep.HEALTH_CHECK,
        kind=kind,
        approval_class=ApprovalClass.STANDING_SAFE,
        operation=operation,
        idempotency_key="run:T1:device:1.1.0:health_check",
    )


def test_verified_health_component_binds_to_governed_execution():
    name = "Check Datto EDR/AV Status AOT Ver 12122025-1"
    request = bind_execution(action(name), device_uid="device-1")
    assert request.capability == AUTOMATION_COMPONENT_EXECUTE
    assert request.arguments["device_uid"] == "device-1"
    assert request.arguments["component_uid"] == VERIFIED_COMPONENTS[name].uid
    assert request.arguments["component_name"] == name
    assert request.arguments["idempotency_key"]


def test_all_provider_components_have_exact_uid_and_name():
    assert len(VERIFIED_COMPONENTS) == 6
    for identity in VERIFIED_COMPONENTS.values():
        assert identity.uid
        assert identity.name
        assert "*" not in identity.uid
        assert "*" not in identity.name


def test_unknown_component_fails_closed():
    with pytest.raises(RuntimeBindingError):
        bind_execution(action("Some Other Component"), device_uid="device-1")


def test_predefined_command_never_falls_back_to_shell():
    with pytest.raises(RuntimeBindingError, match="arbitrary shell fallback is prohibited"):
        bind_execution(
            action(
                "agent.exe datto-av --force-update",
                kind=ActionKind.PREDEFINED_COMMAND,
            ),
            device_uid="device-1",
        )


def test_exact_device_uid_is_required():
    name = "Check Datto EDR/AV Status AOT Ver 12122025-1"
    with pytest.raises(RuntimeBindingError):
        bind_execution(action(name), device_uid="")


def test_job_status_read_uses_live_governed_read_capability():
    request = bind_job_read("job-1")
    assert request.capability == AUTOMATION_JOB_READ
    assert request.arguments == {"resource_id": "job-1"}


def test_job_output_read_is_bound_to_job_device_component_and_stream():
    request = bind_job_output_read(
        "job-1",
        device_uid="device-1",
        component_uid="component-1",
        stream="stdout",
    )
    assert request.capability == AUTOMATION_JOB_OUTPUT_READ
    assert request.arguments["resource_id"] == "job-1"
    assert request.arguments["device_uid"] == "device-1"
    assert request.arguments["component_uid"] == "component-1"
    assert request.arguments["stream"] == "stdout"
