from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


_SAFE_HOST = re.compile(r"^[A-Za-z0-9.-]+$")
_SAFE_SERVICE = re.compile(r"^[A-Za-z0-9_. -]+$")
_SAFE_EVENT_LOG = {
    "Application",
    "System",
    "Setup",
    "Microsoft-Windows-WindowsUpdateClient/Operational",
}
_SAFE_CIM_CLASSES = {
    "Win32_ComputerSystem",
    "Win32_OperatingSystem",
    "Win32_LogicalDisk",
    "Win32_NetworkAdapterConfiguration",
}
_SAFE_REGISTRY_PREFIXES = (
    "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",
    "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall",
    "HKLM:\\SOFTWARE\\Policies",
    "HKLM:\\SYSTEM\\CurrentControlSet\\Services",
)


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _bounded_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


@dataclass(frozen=True, slots=True)
class PreparedReadOnlyPowerShell:
    device_uid: str
    operation: str
    command: str
    normalized_arguments: Mapping[str, Any]
    timeout_seconds: int
    active_probe: bool = False

    def digest(self) -> str:
        payload = {
            "device_uid": self.device_uid,
            "operation": self.operation,
            "command": self.command,
            "normalized_arguments": self.normalized_arguments,
            "timeout_seconds": self.timeout_seconds,
            "active_probe": self.active_probe,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class ReadOnlyPowerShellResult:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    transport_id: str = "unknown"

    def bounded(self, maximum_chars: int = 50_000) -> "ReadOnlyPowerShellResult":
        if maximum_chars < 1:
            raise ValueError("maximum_chars must be positive")
        return ReadOnlyPowerShellResult(
            stdout=self.stdout[:maximum_chars],
            stderr=self.stderr[:maximum_chars],
            exit_code=self.exit_code,
            transport_id=self.transport_id,
        )


class ReadOnlyPowerShellTransport(Protocol):
    """Provider transport boundary for a future supported real-time shell.

    The transport is intentionally not implemented here. A Datto Web Remote,
    API, or other provider transport must be separately reviewed and bound to
    this contract before production activation.
    """

    def execute_readonly(
        self,
        *,
        device_uid: str,
        command: str,
        timeout_seconds: int,
    ) -> ReadOnlyPowerShellResult: ...


class DattoRmmReadOnlyPowerShellPolicy:
    """Render a small, fail-closed diagnostic PowerShell grammar.

    The caller does not submit arbitrary PowerShell. It selects one reviewed
    diagnostic operation and supplies bounded parameters. The policy renders
    exactly one command and rejects script blocks, pipelines, redirection,
    arbitrary native programs, file-content access, mutation cmdlets, and
    unrestricted WMI/CIM execution.

    This source module is intentionally transport-neutral and dormant until a
    separately reviewed Datto real-time transport is supplied.
    """

    capability_name = "endpoint.powershell.read"

    supported_operations = frozenset(
        {
            "system.summary",
            "service.list",
            "service.read",
            "process.list",
            "volume.list",
            "network.configuration",
            "network.connections",
            "hotfix.list",
            "scheduled_task.list",
            "eventlog.read",
            "cim.read",
            "registry.read",
            "dns.resolve",
            "network.test",
        }
    )

    def prepare(
        self,
        *,
        device_uid: str,
        operation: str,
        arguments: Mapping[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> PreparedReadOnlyPowerShell:
        target = str(device_uid or "").strip()
        if not target:
            raise ValueError("device_uid is required")

        op = str(operation or "").strip().casefold()
        if op not in self.supported_operations:
            raise PermissionError("diagnostic operation is not allowlisted")

        args = dict(arguments or {})
        timeout = _bounded_int(
            timeout_seconds,
            name="timeout_seconds",
            minimum=1,
            maximum=120,
        )

        renderer = getattr(self, f"_render_{op.replace('.', '_')}")
        command, normalized, active_probe = renderer(args)

        forbidden = ("|", ";", "&&", "||", ">", "<", "\x60", "$(", "@(", "{", "}")
        if any(token in command for token in forbidden):
            raise AssertionError("rendered read-only command violated grammar boundary")

        return PreparedReadOnlyPowerShell(
            device_uid=target,
            operation=op,
            command=command,
            normalized_arguments=normalized,
            timeout_seconds=timeout,
            active_probe=active_probe,
        )

    def execute(
        self,
        prepared: PreparedReadOnlyPowerShell,
        *,
        transport: ReadOnlyPowerShellTransport | None,
        maximum_output_chars: int = 50_000,
    ) -> ReadOnlyPowerShellResult:
        if transport is None:
            raise RuntimeError("read-only PowerShell transport is not configured")
        result = transport.execute_readonly(
            device_uid=prepared.device_uid,
            command=prepared.command,
            timeout_seconds=prepared.timeout_seconds,
        )
        return result.bounded(maximum_output_chars)

    @staticmethod
    def _reject_unknown(args: Mapping[str, Any], allowed: set[str]) -> None:
        unknown = sorted(set(args) - allowed)
        if unknown:
            raise PermissionError(
                "unsupported diagnostic argument(s): " + ", ".join(unknown)
            )

    def _render_system_summary(self, args: Mapping[str, Any]):
        self._reject_unknown(args, set())
        command = (
            "Get-CimInstance -ClassName Win32_OperatingSystem "
            "-Property Caption,Version,BuildNumber,LastBootUpTime"
        )
        return command, {}, False

    def _render_service_list(self, args: Mapping[str, Any]):
        self._reject_unknown(args, set())
        return "Get-Service", {}, False

    def _render_service_read(self, args: Mapping[str, Any]):
        self._reject_unknown(args, {"name"})
        name = str(args.get("name") or "").strip()
        if not name or len(name) > 256 or not _SAFE_SERVICE.fullmatch(name):
            raise ValueError("service name is invalid")
        return f"Get-Service -Name {_quote(name)}", {"name": name}, False

    def _render_process_list(self, args: Mapping[str, Any]):
        self._reject_unknown(args, set())
        return "Get-Process", {}, False

    def _render_volume_list(self, args: Mapping[str, Any]):
        self._reject_unknown(args, set())
        return "Get-Volume", {}, False

    def _render_network_configuration(self, args: Mapping[str, Any]):
        self._reject_unknown(args, set())
        return "Get-NetIPConfiguration -Detailed", {}, False

    def _render_network_connections(self, args: Mapping[str, Any]):
        self._reject_unknown(args, {"state"})
        state = str(args.get("state") or "").strip()
        if state:
            allowed = {"Listen", "Established", "TimeWait", "CloseWait", "SynSent"}
            if state not in allowed:
                raise PermissionError("network connection state is not allowlisted")
            return f"Get-NetTCPConnection -State {state}", {"state": state}, False
        return "Get-NetTCPConnection", {}, False

    def _render_hotfix_list(self, args: Mapping[str, Any]):
        self._reject_unknown(args, set())
        return "Get-HotFix", {}, False

    def _render_scheduled_task_list(self, args: Mapping[str, Any]):
        self._reject_unknown(args, set())
        return "Get-ScheduledTask", {}, False

    def _render_eventlog_read(self, args: Mapping[str, Any]):
        self._reject_unknown(args, {"log_name", "max_events"})
        log_name = str(args.get("log_name") or "System").strip()
        if log_name not in _SAFE_EVENT_LOG:
            raise PermissionError("event log is not allowlisted")
        max_events = _bounded_int(
            args.get("max_events", 100),
            name="max_events",
            minimum=1,
            maximum=500,
        )
        return (
            f"Get-WinEvent -LogName {_quote(log_name)} -MaxEvents {max_events}",
            {"log_name": log_name, "max_events": max_events},
            False,
        )

    def _render_cim_read(self, args: Mapping[str, Any]):
        self._reject_unknown(args, {"class_name"})
        class_name = str(args.get("class_name") or "").strip()
        if class_name not in _SAFE_CIM_CLASSES:
            raise PermissionError("CIM class is not allowlisted")
        return f"Get-CimInstance -ClassName {class_name}", {"class_name": class_name}, False

    def _render_registry_read(self, args: Mapping[str, Any]):
        self._reject_unknown(args, {"path", "name"})
        path = str(args.get("path") or "").strip()
        if not path or len(path) > 1024:
            raise ValueError("registry path is required")
        folded_path = path.casefold()
        if not any(
            folded_path == prefix.casefold()
            or folded_path.startswith(prefix.casefold() + "\\")
            for prefix in _SAFE_REGISTRY_PREFIXES
        ):
            raise PermissionError("registry path is outside approved read prefixes")

        name = str(args.get("name") or "").strip()
        normalized = {"path": path}
        command = f"Get-ItemProperty -LiteralPath {_quote(path)}"
        if name:
            if len(name) > 256 or not _SAFE_SERVICE.fullmatch(name):
                raise ValueError("registry value name is invalid")
            command += f" -Name {_quote(name)}"
            normalized["name"] = name
        return command, normalized, False

    def _render_dns_resolve(self, args: Mapping[str, Any]):
        self._reject_unknown(args, {"name"})
        name = str(args.get("name") or "").strip()
        if not name or len(name) > 253 or not _SAFE_HOST.fullmatch(name):
            raise ValueError("DNS name is invalid")
        return f"Resolve-DnsName -Name {_quote(name)}", {"name": name}, True

    def _render_network_test(self, args: Mapping[str, Any]):
        self._reject_unknown(args, {"computer_name", "port"})
        host = str(args.get("computer_name") or "").strip()
        if not host or len(host) > 253 or not _SAFE_HOST.fullmatch(host):
            raise ValueError("computer_name is invalid")
        port = _bounded_int(
            args.get("port", 443),
            name="port",
            minimum=1,
            maximum=65535,
        )
        return (
            f"Test-NetConnection -ComputerName {_quote(host)} -Port {port}",
            {"computer_name": host, "port": port},
            True,
        )
