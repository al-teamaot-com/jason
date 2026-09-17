import pytest

from jason_runtime.datto_component_scope import (
    DATTO_AD_HOC_POWERSHELL_NAME,
    DATTO_AD_HOC_POWERSHELL_UID,
    DATTO_APPROVAL_MODE_PER_RUN,
    DATTO_APPROVAL_MODE_STANDING_SAFE,
    DattoApprovedComponent,
    effective_datto_component_approval_mode,
)


def component():
    return DattoApprovedComponent(
        uid=DATTO_AD_HOC_POWERSHELL_UID,
        name=DATTO_AD_HOC_POWERSHELL_NAME,
        approval_mode=DATTO_APPROVAL_MODE_PER_RUN,
    )


@pytest.mark.parametrize(
    "command",
    [
        "Get-Date",
        "Get-Service -Name 'EndpointProtectionService'",
        (
            "Get-Service -Name 'EndpointProtectionService' "
            "| Select-Object Name,Status"
        ),
        (
            "Get-Service "
            "| Where-Object Status -eq 'Running' "
            "| Select-Object Name,Status"
        ),
        (
            "Test-NetConnection -ComputerName 8.8.8.8 "
            "-Port 53"
        ),
        "Get-NetIPConfiguration",
        "Get-NetTCPConnection | Select-Object LocalAddress,LocalPort,State",
        "Get-MpComputerStatus | Format-List",
    ],
)
def test_known_read_only_commands_use_standing_policy(
    command,
):
    mode, reason = (
        effective_datto_component_approval_mode(
            component(),
            {
                "usrInput": command,
            },
        )
    )

    assert mode == DATTO_APPROVAL_MODE_STANDING_SAFE
    assert reason == "DATTO_POWERSHELL_READ_ONLY_COMMAND"


@pytest.mark.parametrize(
    "command",
    [
        "Start-Service -Name 'EndpointProtectionService'",
        "Stop-Service -Name 'EndpointProtectionService'",
        "Restart-Service -Name 'EndpointProtectionService'",
        "Set-Service -Name 'EndpointProtectionService' -StartupType Automatic",
        "Get-Service; Start-Service Spooler",
        "Get-Service | ForEach-Object { Stop-Service $_.Name }",
        "Get-Content C:\\Windows\\win.ini",
        "Get-ItemProperty HKLM:\\Software",
        "Get-CimInstance -ClassName Win32_OperatingSystem",
        "Get-WmiObject Win32_OperatingSystem",
        "Invoke-Expression 'Get-Date'",
        "Get-Service -ComputerName OTHERPC",
        "Get-Service $(Start-Service Spooler)",
        "Get-Date > C:\\Temp\\date.txt",
        "powershell.exe -EncodedCommand AAAA",
    ],
)
def test_mutating_sensitive_or_ambiguous_commands_require_approval(
    command,
):
    mode, reason = (
        effective_datto_component_approval_mode(
            component(),
            {
                "usrInput": command,
            },
        )
    )

    assert mode == DATTO_APPROVAL_MODE_PER_RUN
    assert reason == "DATTO_POWERSHELL_COMMAND_APPROVAL_REQUIRED"


def test_extra_variables_cannot_receive_standing_policy():
    mode, reason = (
        effective_datto_component_approval_mode(
            component(),
            {
                "usrInput": "Get-Date",
                "other": "value",
            },
        )
    )

    assert mode == DATTO_APPROVAL_MODE_PER_RUN
    assert reason == "DATTO_POWERSHELL_COMMAND_APPROVAL_REQUIRED"


def test_other_component_keeps_its_server_classification():
    other = DattoApprovedComponent(
        uid="component-1",
        name="Known Diagnostic",
        approval_mode=DATTO_APPROVAL_MODE_STANDING_SAFE,
    )

    mode, reason = (
        effective_datto_component_approval_mode(
            other,
            {},
        )
    )

    assert mode == DATTO_APPROVAL_MODE_STANDING_SAFE
    assert reason is None
