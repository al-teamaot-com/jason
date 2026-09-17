import json

import pytest

from connectors.datto_rmm.component_execution import (
    ComponentAllowlistEntry,
    DattoRmmComponentExecutionPolicy,
    StaticComponentAllowlist,
)
from jason_runtime.datto_component_scope import (
    DATTO_APPROVAL_MODE_PER_RUN,
    DATTO_APPROVAL_MODE_STANDING_SAFE,
    DATTO_DIAGNOSTIC_CLASS_ACTIVE_PROBE,
    DATTO_DIAGNOSTIC_CLASS_APPROVAL_REQUIRED,
    DATTO_DIAGNOSTIC_CLASS_PASSIVE_READ,
    DATTO_EXECUTION_COMPONENTS_JSON_ENV,
    DattoApprovedComponent,
    classify_datto_powershell_diagnostic_command,
    configured_datto_components,
    effective_datto_component_approval_mode,
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


def component():
    return DattoApprovedComponent(
        uid=UID,
        name=NAME,
        approval_mode=DATTO_APPROVAL_MODE_PER_RUN,
    )


def effective_mode(command):
    return effective_datto_component_approval_mode(
        component(),
        {"usrInput": command},
    )[0]


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


def test_powershell_component_cannot_be_configured_standing_safe(
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


@pytest.mark.parametrize(
    "command",
    [
        "Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object Caption,Version,LastBootUpTime",
        "Get-WinEvent -LogName System -MaxEvents 20 | Select-Object Id,TimeCreated,ProviderName",
        r"reg.exe query 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion' /v ProductName",
        "netsh wlan show interfaces",
        "ipconfig /all",
        "sc.exe query HUNTAgent",
        "pnputil.exe /enum-drivers",
    ],
)
def test_previously_unseen_passive_diagnostics_can_run_standing_safe(command):
    assert (
        classify_datto_powershell_diagnostic_command(command)
        == DATTO_DIAGNOSTIC_CLASS_PASSIVE_READ
    )
    assert effective_mode(command) == DATTO_APPROVAL_MODE_STANDING_SAFE


@pytest.mark.parametrize(
    "command",
    [
        "Test-NetConnection 1.1.1.1 -Port 443",
        "Resolve-DnsName example.com",
        "ping.exe 1.1.1.1 -n 2 -w 1000",
        "tracert.exe example.com -h 10 -w 1000",
        "nslookup.exe example.com",
    ],
)
def test_bounded_active_diagnostic_probes_can_run_standing_safe(command):
    assert (
        classify_datto_powershell_diagnostic_command(command)
        == DATTO_DIAGNOSTIC_CLASS_ACTIVE_PROBE
    )
    assert effective_mode(command) == DATTO_APPROVAL_MODE_STANDING_SAFE


@pytest.mark.parametrize(
    "command",
    [
        "Restart-Service HUNTAgent",
        "Set-ItemProperty HKLM:\\Software\\AOT -Name Test -Value 1",
        "netsh wlan delete profile name=AlphaGuest",
        r"reg.exe add HKLM\Software\AOT /v Test /d 1",
        "ipconfig /flushdns",
        "sc.exe stop HUNTAgent",
        "shutdown.exe /r /t 0",
        "Get-SomethingNew -Name Example",
        "ping.exe 1.1.1.1 -t",
    ],
)
def test_mutating_unknown_or_unbounded_commands_still_require_approval(command):
    assert (
        classify_datto_powershell_diagnostic_command(command)
        == DATTO_DIAGNOSTIC_CLASS_APPROVAL_REQUIRED
    )
    assert effective_mode(command) == DATTO_APPROVAL_MODE_PER_RUN


@pytest.mark.parametrize(
    "command",
    [
        r"Get-ItemProperty 'HKLM:\SAM\Domains\Account'",
        r"reg.exe query HKLM\SECURITY\Policy\Secrets",
        "netsh wlan show profile name=AlphaPsych key=clear",
        "Get-CimInstance Win32_Process | Select-Object Name,CommandLine",
    ],
)
def test_secret_or_credential_oriented_reads_do_not_auto_pass(command):
    assert (
        classify_datto_powershell_diagnostic_command(command)
        == DATTO_DIAGNOSTIC_CLASS_APPROVAL_REQUIRED
    )
    assert effective_mode(command) == DATTO_APPROVAL_MODE_PER_RUN


def test_command_chaining_and_remote_management_scope_fail_closed():
    commands = (
        "Get-Service; Restart-Service HUNTAgent",
        "Get-Service -ComputerName server01",
        "Get-CimInstance Win32_OperatingSystem -ComputerName server01",
        "Get-Service | ForEach-Object Stop-Service",
    )

    for command in commands:
        assert (
            classify_datto_powershell_diagnostic_command(command)
            == DATTO_DIAGNOSTIC_CLASS_APPROVAL_REQUIRED
        )
        assert effective_mode(command) == DATTO_APPROVAL_MODE_PER_RUN
