from __future__ import annotations

import pytest

from connectors.datto_rmm.readonly_powershell import (
    DattoRmmReadOnlyPowerShellPolicy,
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
    ("operation", "arguments", "expected"),
    [
        (
            "system.summary",
            {},
            "Get-CimInstance -ClassName Win32_OperatingSystem "
            "-Property Caption,Version,BuildNumber,LastBootUpTime",
        ),
        ("service.list", {}, "Get-Service"),
        ("service.read", {"name": "Dnscache"}, "Get-Service -Name 'Dnscache'"),
        ("process.list", {}, "Get-Process"),
        ("volume.list", {}, "Get-Volume"),
        (
            "network.configuration",
            {},
            "Get-NetIPConfiguration -Detailed",
        ),
        ("hotfix.list", {}, "Get-HotFix"),
        ("scheduled_task.list", {}, "Get-ScheduledTask"),
        (
            "eventlog.read",
            {"log_name": "System", "max_events": 25},
            "Get-WinEvent -LogName 'System' -MaxEvents 25",
        ),
        (
            "cim.read",
            {"class_name": "Win32_LogicalDisk"},
            "Get-CimInstance -ClassName Win32_LogicalDisk",
        ),
        (
            "dns.resolve",
            {"name": "example.com"},
            "Resolve-DnsName -Name 'example.com'",
        ),
        (
            "network.test",
            {"computer_name": "example.com", "port": 443},
            "Test-NetConnection -ComputerName 'example.com' -Port 443",
        ),
    ],
)
def test_safe_operations_render_exact_bounded_commands(
    operation,
    arguments,
    expected,
):
    prepared = policy().prepare(
        device_uid="device-uid-1",
        operation=operation,
        arguments=arguments,
    )

    assert prepared.command == expected
    assert prepared.device_uid == "device-uid-1"
    assert len(prepared.digest()) == 64


def test_registry_reads_are_restricted_to_approved_prefixes():
    prepared = policy().prepare(
        device_uid="device-uid-1",
        operation="registry.read",
        arguments={
            "path": (
                r"HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            ),
            "name": "ProductName",
        },
    )

    assert prepared.command == (
        "Get-ItemProperty -LiteralPath "
        "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' "
        "-Name 'ProductName'"
    )

    with pytest.raises(PermissionError, match="outside approved"):
        policy().prepare(
            device_uid="device-uid-1",
            operation="registry.read",
            arguments={"path": r"HKLM:\SAM"},
        )


def test_cim_class_is_allowlisted_not_arbitrary():
    with pytest.raises(PermissionError, match="CIM class"):
        policy().prepare(
            device_uid="device-uid-1",
            operation="cim.read",
            arguments={"class_name": "Win32_Process"},
        )


def test_unknown_operation_is_rejected_instead_of_becoming_raw_powershell():
    with pytest.raises(PermissionError, match="not allowlisted"):
        policy().prepare(
            device_uid="device-uid-1",
            operation="powershell.raw",
            arguments={"command": "Remove-Item C:\\important.txt"},
        )


def test_unknown_arguments_are_rejected():
    with pytest.raises(PermissionError, match="unsupported diagnostic argument"):
        policy().prepare(
            device_uid="device-uid-1",
            operation="service.list",
            arguments={"command": "Stop-Service Spooler"},
        )


@pytest.mark.parametrize(
    "malicious",
    [
        "Spooler; Stop-Service Spooler",
        "Spooler | Stop-Service",
        "$(Stop-Service Spooler)",
        "Spooler && shutdown.exe /s",
        "Spooler > C:\\temp\\x.txt",
    ],
)
def test_parameter_injection_is_rejected(malicious):
    with pytest.raises(ValueError, match="service name"):
        policy().prepare(
            device_uid="device-uid-1",
            operation="service.read",
            arguments={"name": malicious},
        )


def test_network_active_probes_are_explicitly_marked():
    dns = policy().prepare(
        device_uid="device-uid-1",
        operation="dns.resolve",
        arguments={"name": "example.com"},
    )
    tcp = policy().prepare(
        device_uid="device-uid-1",
        operation="network.test",
        arguments={"computer_name": "example.com", "port": 443},
    )
    services = policy().prepare(
        device_uid="device-uid-1",
        operation="service.list",
    )

    assert dns.active_probe is True
    assert tcp.active_probe is True
    assert services.active_probe is False


def test_timeout_is_bounded():
    with pytest.raises(ValueError, match="between 1 and 120"):
        policy().prepare(
            device_uid="device-uid-1",
            operation="service.list",
            timeout_seconds=121,
        )


def test_no_transport_means_no_execution():
    prepared = policy().prepare(
        device_uid="device-uid-1",
        operation="service.list",
    )

    with pytest.raises(RuntimeError, match="transport is not configured"):
        policy().execute(prepared, transport=None)


def test_transport_boundary_receives_only_rendered_command():
    prepared = policy().prepare(
        device_uid="device-uid-1",
        operation="service.read",
        arguments={"name": "Dnscache"},
        timeout_seconds=45,
    )
    transport = FakeTransport()

    result = policy().execute(prepared, transport=transport)

    assert result.stdout == "ok"
    assert transport.calls == [
        {
            "device_uid": "device-uid-1",
            "command": "Get-Service -Name 'Dnscache'",
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

    prepared = policy().prepare(
        device_uid="device-uid-1",
        operation="process.list",
    )
    result = policy().execute(
        prepared,
        transport=LargeTransport(),
        maximum_output_chars=100,
    )

    assert len(result.stdout) == 100
    assert len(result.stderr) == 100
