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
