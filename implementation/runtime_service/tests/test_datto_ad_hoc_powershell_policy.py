import json

import pytest

from connectors.datto_rmm.component_execution import (
    ComponentAllowlistEntry,
    DattoRmmComponentExecutionPolicy,
    StaticComponentAllowlist,
)
from jason_runtime.datto_component_scope import (
    DATTO_EXECUTION_COMPONENTS_JSON_ENV,
    configured_datto_components,
)


UID = "8a1c153c-feee-41c5-9c9b-58a48e0214fe"
NAME = "Run Ad Hoc Command (PowerShell 2-5) [WIN]"


def policy_for(
    *,
    uid=UID,
    name=NAME,
):
    entry = ComponentAllowlistEntry(
        allowlist_name="pilot-diagnostic",
        canonical_component_id=(
            f"datto:pilot-diagnostic:{uid}"
        ),
        display_name=name,
        provider_component_uid=uid,
        allowed_target_classes=frozenset(
            {"workstation"}
        ),
        variable_policies=(),
        requires_per_run_approval=True,
        status="active",
    )

    return DattoRmmComponentExecutionPolicy(
        allowlist=StaticComponentAllowlist(
            entries=(entry,)
        )
    )


def test_exact_powershell_component_accepts_usrinput():
    command = (
        "Get-Service -Name "
        "'EndpointProtectionService' | "
        "Select-Object Name,Status"
    )

    prepared = policy_for().prepare(
        allowlist_name="pilot-diagnostic",
        device_uid="device-1",
        device_class="workstation",
        component_uid=UID,
        variables={
            "usrInput": command,
        },
        observed_component_name=NAME,
    )

    assert prepared.normalized_variables == {
        "usrInput": command,
    }

    assert prepared.provider_request.body == {
        "jobName": f"Jason - {NAME}",
        "jobComponent": {
            "componentUid": UID,
            "variables": [
                {
                    "name": "usrInput",
                    "value": command,
                }
            ],
        },
    }


def test_unknown_powershell_variable_fails_closed():
    with pytest.raises(PermissionError):
        policy_for().prepare(
            allowlist_name="pilot-diagnostic",
            device_uid="device-1",
            device_class="workstation",
            component_uid=UID,
            variables={
                "otherInput": "Get-Date",
            },
            observed_component_name=NAME,
        )


def test_same_name_with_unreviewed_uid_cannot_use_usrinput():
    other_uid = "unreviewed-component"

    with pytest.raises(PermissionError):
        policy_for(
            uid=other_uid,
        ).prepare(
            allowlist_name="pilot-diagnostic",
            device_uid="device-1",
            device_class="workstation",
            component_uid=other_uid,
            variables={
                "usrInput": "Get-Date",
            },
            observed_component_name=NAME,
        )


def test_powershell_component_cannot_be_standing_safe(
    monkeypatch,
):
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        json.dumps(
            [
                {
                    "uid": UID,
                    "name": NAME,
                    "approval_mode": (
                        "standing_safe"
                    ),
                }
            ]
        ),
    )

    components = configured_datto_components()

    assert len(components) == 1
    assert components[0].approval_mode == "per_run"
    assert (
        components[0].requires_explicit_approval
        is True
    )


# Linux shell worker contract: exact live UID/name, per-run approval and
# a source-controlled usrInput schema; no shell command is standing-safe.
LINUX_SHELL_UID = "bc7c4531-6869-4658-b1d6-7639a477045e"
LINUX_SHELL_NAME = "Run Ad Hoc Command (Shell) [MAC] [LIN]"


def test_exact_linux_shell_component_accepts_usrinput():
    cmd = "uname -srm"
    prepared = policy_for(uid=LINUX_SHELL_UID, name=LINUX_SHELL_NAME).prepare(
        allowlist_name="pilot-diagnostic",
        device_uid="worker-1",
        device_class="workstation",
        component_uid=LINUX_SHELL_UID,
        variables={"usrInput": cmd},
        observed_component_name=LINUX_SHELL_NAME,
    )
    assert prepared.normalized_variables == {"usrInput": cmd}
    assert prepared.provider_request.body["jobComponent"]["variables"] == [
        {"name": "usrInput", "value": cmd}
    ]


def test_linux_shell_rejects_unknown_variable():
    with pytest.raises(PermissionError):
        policy_for(uid=LINUX_SHELL_UID, name=LINUX_SHELL_NAME).prepare(
            allowlist_name="pilot-diagnostic",
            device_uid="worker-1",
            device_class="workstation",
            component_uid=LINUX_SHELL_UID,
            variables={"unexpected": "uname -srm"},
            observed_component_name=LINUX_SHELL_NAME,
        )


def test_linux_shell_rejects_same_name_wrong_uid():
    with pytest.raises(PermissionError):
        policy_for(uid="unreviewed-uid", name=LINUX_SHELL_NAME).prepare(
            allowlist_name="pilot-diagnostic",
            device_uid="worker-1",
            device_class="workstation",
            component_uid="unreviewed-uid",
            variables={"usrInput": "uname -srm"},
            observed_component_name=LINUX_SHELL_NAME,
        )


def test_linux_shell_rejects_missing_input():
    with pytest.raises((PermissionError, ValueError)):
        policy_for(uid=LINUX_SHELL_UID, name=LINUX_SHELL_NAME).prepare(
            allowlist_name="pilot-diagnostic",
            device_uid="worker-1",
            device_class="workstation",
            component_uid=LINUX_SHELL_UID,
            variables={},
            observed_component_name=LINUX_SHELL_NAME,
        )


def test_linux_shell_cannot_be_configured_standing_safe(monkeypatch):
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        json.dumps([{"uid": LINUX_SHELL_UID, "name": LINUX_SHELL_NAME, "approval_mode": "standing_safe"}]),
    )
    components = configured_datto_components()
    assert len(components) == 1
    assert components[0].approval_mode == "per_run"
    assert components[0].requires_explicit_approval is True
