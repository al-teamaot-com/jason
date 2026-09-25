from __future__ import annotations

import pytest

from connectors.datto_rmm.readonly_powershell import (
    DattoRmmReadOnlyPowerShellPolicy,
    ReadOnlyPowerShellClassifier,
    ReadOnlyPowerShellResult,
)


class FakeTransport:
    def __init__(self):
        self.calls = []

    def execute_readonly(self, *, device_uid, command, timeout_seconds):
        self.calls.append(
            {
                "device_uid": device_uid,
                "command": command,
                "timeout_seconds": timeout_seconds,
            }
        )
        return ReadOnlyPowerShellResult(
            stdout="ok",
            stderr="",
            exit_code=0,
            transport_id="fake",
        )


def policy():
    return DattoRmmReadOnlyPowerShellPolicy()


@pytest.mark.parametrize(
    "command",
    [
        "Get-Service",
        "Get-Process | Sort-Object WorkingSet -Descending | "
        "Select-Object -First 20",
        "Get-ChildItem C:\\ -Directory | Sort-Object Name | "
        "Select-Object -First 20",
        "Get-NetIPConfiguration -Detailed",
        "Get-HotFix | Select-Object HotFixID,InstalledOn",
        "Get-ScheduledTask | Where-Object State -ne 'Disabled'",
        "gsv | Where-Object Status -eq 'Running' | Select-Object -First 10",
        (
            "Get-WinEvent -FilterHashtable "
            "@{LogName='System'; StartTime=(Get-Date).AddDays(-3)} | "
            "Where-Object Id -in 41,6008 | "
            "Select-Object TimeCreated,Id,Message"
        ),
    ],
)
def test_general_diagnostic_powershell_is_classified_read_only(command):
    classification = ReadOnlyPowerShellClassifier.classify(command)

    assert classification.classification == "read_only"
    assert classification.allowed_as_read_only is True


def test_general_read_only_pipeline_can_be_prepared():
    command = (
        "Get-Process | Sort-Object WorkingSet -Descending | "
        "Select-Object -First 20"
    )

    prepared = policy().prepare_command(
        device_uid="device-uid-1",
        command=command,
        timeout_seconds=45,
    )

    assert prepared.command == command
    assert prepared.operation == "powershell.readonly"
    assert prepared.classification is not None
    assert prepared.classification.classification == "read_only"
    assert prepared.active_probe is False
    assert len(prepared.digest()) == 64


@pytest.mark.parametrize(
    "command",
    [
        "Get-Process | Stop-Process",
        "Set-Service -Name Spooler -StartupType Disabled",
        "Restart-Service Spooler",
        "Remove-Item C:\\temp\\x.txt",
        "New-Item C:\\temp\\x.txt",
        "Get-Process > C:\\temp\\processes.txt",
        "Get-Process | Out-File C:\\temp\\processes.txt",
        "Get-CimInstance Win32_Process | Invoke-CimMethod -MethodName Terminate",
        "[System.IO.File]::Delete('C:\\temp\\x.txt')",
        "cmd.exe /c del C:\\temp\\x.txt",
        "$x = Get-Process",
    ],
)
def test_mutating_or_stateful_commands_are_rejected(command):
    classification = ReadOnlyPowerShellClassifier.classify(command)

    assert classification.classification == "mutating"

    with pytest.raises(PermissionError, match="mutating"):
        policy().prepare_command(
            device_uid="device-uid-1",
            command=command,
        )


@pytest.mark.parametrize(
    "command",
    [
        "[Environment]::GetEnvironmentVariable('PATH')",
        "Get-Process | ForEach-Object { $_.Handles.ToString() }",
        "Invoke-Command -ComputerName server1 -ScriptBlock { Get-Service }",
    ],
)
def test_ambiguous_constructs_fail_closed(command):
    classification = ReadOnlyPowerShellClassifier.classify(command)

    assert classification.classification == "uncertain"

    with pytest.raises(PermissionError, match="cannot be proven read-only"):
        policy().prepare_command(
            device_uid="device-uid-1",
            command=command,
        )


@pytest.mark.parametrize(
    "command",
    [
        r"Get-Item HKLM:\SAM",
        r"Get-ChildItem C:\Windows\System32\config\SAM",
        "Get-Process lsass",
        r"Get-ChildItem C:\Users\Bob\AppData\Local\Microsoft\Protect",
    ],
)
def test_sensitive_reads_have_separate_authority_boundary(command):
    classification = ReadOnlyPowerShellClassifier.classify(command)

    assert classification.classification == "sensitive"
    assert classification.sensitive is True

    with pytest.raises(PermissionError, match="sensitive information"):
        policy().prepare_command(
            device_uid="device-uid-1",
            command=command,
        )


def test_network_reads_can_be_marked_as_active_probes():
    dns = policy().prepare_command(
        device_uid="device-uid-1",
        command="Resolve-DnsName example.com",
    )
    tcp = policy().prepare_command(
        device_uid="device-uid-1",
        command="Test-NetConnection example.com -Port 443",
    )
    local = policy().prepare_command(
        device_uid="device-uid-1",
        command="Get-NetIPConfiguration",
    )

    assert dns.active_probe is True
    assert tcp.active_probe is True
    assert local.active_probe is False


def test_convenience_operations_use_same_general_classifier():
    prepared = policy().prepare(
        device_uid="device-uid-1",
        operation="eventlog.read",
        arguments={"log_name": "System", "max_events": 25},
    )

    assert prepared.command == "Get-WinEvent -LogName 'System' -MaxEvents 25"
    assert prepared.classification is not None
    assert prepared.classification.classification == "read_only"


def test_convenience_parameter_injection_is_rejected():
    with pytest.raises(ValueError, match="name is invalid"):
        policy().prepare(
            device_uid="device-uid-1",
            operation="service.read",
            arguments={"name": "Spooler; Stop-Service Spooler"},
        )


def test_timeout_is_bounded():
    with pytest.raises(ValueError, match="between 1 and 120"):
        policy().prepare_command(
            device_uid="device-uid-1",
            command="Get-Service",
            timeout_seconds=121,
        )


def test_no_transport_means_no_execution():
    prepared = policy().prepare_command(
        device_uid="device-uid-1",
        command="Get-Service",
    )

    with pytest.raises(RuntimeError, match="transport is not configured"):
        policy().execute(prepared, transport=None)


def test_transport_receives_only_preclassified_read_only_command():
    command = (
        "Get-Process | Sort-Object WorkingSet -Descending | "
        "Select-Object -First 20"
    )
    prepared = policy().prepare_command(
        device_uid="device-uid-1",
        command=command,
        timeout_seconds=45,
    )
    transport = FakeTransport()

    result = policy().execute(prepared, transport=transport)

    assert result.stdout == "ok"
    assert transport.calls == [
        {
            "device_uid": "device-uid-1",
            "command": command,
            "timeout_seconds": 45,
        }
    ]


def test_output_is_bounded_before_return():
    class LargeTransport:
        def execute_readonly(self, *, device_uid, command, timeout_seconds):
            return ReadOnlyPowerShellResult(
                stdout="A" * 1000,
                stderr="B" * 1000,
                transport_id="fake",
            )

    prepared = policy().prepare_command(
        device_uid="device-uid-1",
        command="Get-Process",
    )
    result = policy().execute(
        prepared,
        transport=LargeTransport(),
        maximum_output_chars=100,
    )

    assert len(result.stdout) == 100
    assert len(result.stderr) == 100


def test_unclassified_custom_verb_is_not_assumed_safe():
    command = "Watch-Thing"

    classification = ReadOnlyPowerShellClassifier.classify(command)

    assert classification.classification == "uncertain"


def test_empty_command_is_not_allowed():
    classification = ReadOnlyPowerShellClassifier.classify("")

    assert classification.classification == "uncertain"
