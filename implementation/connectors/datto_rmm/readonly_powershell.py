from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


MUTATING_VERBS = frozenset({
    "add", "block", "clear", "close", "connect", "copy", "disable",
    "disconnect", "dismount", "enable", "enter", "exit", "export",
    "import", "install", "invoke", "mount", "move", "new", "out",
    "publish", "register", "remove", "rename", "repair", "reset",
    "restart", "restore", "resume", "save", "set", "start", "stop",
    "submit", "suspend", "unblock", "uninstall", "unregister",
    "update", "write",
})

READ_ONLY_VERBS = frozenset({
    "compare", "convertfrom", "convertto", "find", "format", "get",
    "group", "measure", "resolve", "search", "select", "sort", "test",
    "where",
})

SAFE_BARE_COMMANDS = frozenset({
    "foreach-object", "where-object", "select-object", "sort-object",
    "group-object", "measure-object", "compare-object", "format-list",
    "format-table", "format-wide", "format-custom",
})

READ_ONLY_ALIASES = {
    "dir": "Get-ChildItem", "gci": "Get-ChildItem", "ls": "Get-ChildItem",
    "gps": "Get-Process", "ps": "Get-Process", "gsv": "Get-Service",
    "gal": "Get-Alias", "gi": "Get-Item", "gp": "Get-ItemProperty",
    "gc": "Get-Content", "cat": "Get-Content", "type": "Get-Content",
    "sls": "Select-String", "select": "Select-Object",
    "sort": "Sort-Object", "where": "Where-Object", "?": "Where-Object",
    "measure": "Measure-Object",
}

ACTIVE_PROBE_COMMANDS = frozenset({
    "resolve-dnsname", "test-connection", "test-netconnection",
})

SENSITIVE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\\sam(?:\\|['\"\s]|$)",
        r"\\security(?:\\|['\"\s]|$)",
        r"\\system32\\config\\(?:sam|security|system)",
        r"\\windows\\system32\\config\\regback",
        r"lsass(?:\.exe|\.dmp|\b)",
        r"credential\s*manager",
        r"vaultcmd",
        r"dpapi",
        r"browser.*(?:cookies|login data|password)",
        r"(?:chrome|edge|firefox).*(?:cookies|login data)",
        r"private\s*key",
        r"\\microsoft\\protect\\",
        r"ntds\.dit",
    )
)

FORBIDDEN_SYNTAX = tuple(
    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    for pattern in (
        r"(^|[^|])>(?!>)",
        r">>",
        r"\b(?:cmd|powershell|pwsh|wscript|cscript|mshta|rundll32|regsvr32)\.exe\b",
        r"\b(?:shutdown|sc|net|netsh|reg|diskpart|bcdedit|schtasks)\.exe\b",
        r"\bstart-process\b",
        r"\binvoke-expression\b",
        r"\biex\b",
        r"\badd-type\b",
        r"\bset-content\b",
        r"\badd-content\b",
        r"\bclear-content\b",
        r"\bout-file\b",
        r"\bexport-clixml\b",
        r"\bexport-csv\b",
        r"\btee-object\b",
        r"\bset-itemproperty\b",
        r"\bnew-itemproperty\b",
        r"\bremove-itemproperty\b",
        r"\binvoke-cimmethod\b",
        r"\binvoke-wmimethod\b",
        r"\bset-ciminstance\b",
        r"\bremove-ciminstance\b",
        r"\bnew-ciminstance\b",
        r"\bset-wmiinstance\b",
        r"\[\s*(?:system\.)?io\.",
        r"\[\s*microsoft\.win32\.",
        r"\&\s*['\"]",
        r"^\s*\.\s+",
        r"\$[A-Za-z_][A-Za-z0-9_:]*\s*=(?!=)",
        r"\+\+|--",
    )
)

ALLOWED_METHODS = frozenset({
    "adddays", "addhours", "addminutes", "addseconds", "tostring",
    "tolower", "tolowerinvariant", "toupper", "toupperinvariant", "trim",
    "contains", "startswith", "endswith",
})

COMMAND_TOKEN = re.compile(
    r"(?<![\w.-])([A-Za-z?][A-Za-z0-9?]*-[A-Za-z][A-Za-z0-9]*|"
    r"foreach-object|where-object|select-object|sort-object|group-object|"
    r"measure-object|compare-object|format-(?:list|table|wide|custom)|"
    r"dir|gci|ls|gps|ps|gsv|gal|gi|gp|gc|cat|type|sls|select|sort|where|"
    r"measure|\?)\b",
    re.IGNORECASE,
)

METHOD_CALL = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")


@dataclass(frozen=True, slots=True)
class PowerShellClassification:
    classification: str
    reasons: tuple[str, ...] = ()
    active_probe: bool = False
    sensitive: bool = False

    @property
    def allowed_as_read_only(self) -> bool:
        return self.classification == "read_only" and not self.sensitive


@dataclass(frozen=True, slots=True)
class PreparedReadOnlyPowerShell:
    device_uid: str
    operation: str
    command: str
    normalized_arguments: Mapping[str, Any]
    timeout_seconds: int
    active_probe: bool = False
    classification: PowerShellClassification | None = None

    def digest(self) -> str:
        payload = {
            "device_uid": self.device_uid,
            "operation": self.operation,
            "command": self.command,
            "normalized_arguments": self.normalized_arguments,
            "timeout_seconds": self.timeout_seconds,
            "active_probe": self.active_probe,
            "classification": (
                self.classification.classification if self.classification else None
            ),
            "sensitive": (
                self.classification.sensitive if self.classification else False
            ),
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
    def execute_readonly(
        self,
        *,
        device_uid: str,
        command: str,
        timeout_seconds: int,
    ) -> ReadOnlyPowerShellResult: ...


class ReadOnlyPowerShellClassifier:
    """Conservatively classify Jason-generated diagnostic PowerShell.

    Text alone cannot prove every arbitrary PowerShell program is read-only.
    Clearly observational commands are accepted; known mutations are rejected;
    sensitive reads are routed to a separate authority boundary; and ambiguous
    constructs fail closed for reformulation.
    """

    maximum_command_chars = 20_000

    @classmethod
    def classify(cls, command: str) -> PowerShellClassification:
        text = str(command or "").strip()
        if not text:
            return PowerShellClassification("uncertain", ("command is empty",))
        if len(text) > cls.maximum_command_chars:
            return PowerShellClassification(
                "uncertain",
                ("command exceeds read-only classifier size bound",),
            )

        sensitive_reasons = tuple(
            f"sensitive pattern: {pattern.pattern}"
            for pattern in SENSITIVE_PATTERNS
            if pattern.search(text)
        )

        mutation_reasons = tuple(
            f"forbidden syntax: {pattern.pattern}"
            for pattern in FORBIDDEN_SYNTAX
            if pattern.search(text)
        )
        if mutation_reasons:
            return PowerShellClassification(
                "mutating",
                mutation_reasons,
                sensitive=bool(sensitive_reasons),
            )

        raw_tokens = [match.group(1) for match in COMMAND_TOKEN.finditer(text)]
        if not raw_tokens:
            return PowerShellClassification(
                "uncertain",
                ("no classifiable PowerShell command was found",),
                sensitive=bool(sensitive_reasons),
            )

        normalized_tokens = [
            READ_ONLY_ALIASES.get(token.casefold(), token)
            for token in raw_tokens
        ]

        reasons: list[str] = []
        active_probe = False
        saw_observational = False

        for token in normalized_tokens:
            folded = token.casefold()
            if folded in ACTIVE_PROBE_COMMANDS:
                active_probe = True

            if folded in SAFE_BARE_COMMANDS:
                saw_observational = True
                continue

            if "-" not in folded:
                reasons.append(f"unclassified command token: {token}")
                continue

            verb, _noun = folded.split("-", 1)
            if verb in MUTATING_VERBS:
                return PowerShellClassification(
                    "mutating",
                    (f"mutating PowerShell verb: {verb}",),
                    active_probe=active_probe,
                    sensitive=bool(sensitive_reasons),
                )
            if verb in READ_ONLY_VERBS:
                saw_observational = True
                continue
            reasons.append(f"unclassified PowerShell verb: {verb}")

        method_calls = {
            match.group(1).casefold()
            for match in METHOD_CALL.finditer(text)
        }
        unsafe_methods = sorted(method_calls - ALLOWED_METHODS)
        if unsafe_methods:
            reasons.extend(
                f"unclassified method call: {name}" for name in unsafe_methods
            )

        if reasons or not saw_observational:
            return PowerShellClassification(
                "uncertain",
                tuple(reasons) or ("command is not demonstrably observational",),
                active_probe=active_probe,
                sensitive=bool(sensitive_reasons),
            )

        if sensitive_reasons:
            return PowerShellClassification(
                "sensitive",
                sensitive_reasons,
                active_probe=active_probe,
                sensitive=True,
            )

        return PowerShellClassification(
            "read_only",
            ("all detected operations are observational",),
            active_probe=active_probe,
            sensitive=False,
        )


class DattoRmmReadOnlyPowerShellPolicy:
    """Prepare broad diagnostic PowerShell while failing closed on writes."""

    capability_name = "endpoint.powershell.read"

    def __init__(
        self,
        *,
        classifier: type[ReadOnlyPowerShellClassifier] = ReadOnlyPowerShellClassifier,
    ) -> None:
        self._classifier = classifier

    def prepare_command(
        self,
        *,
        device_uid: str,
        command: str,
        timeout_seconds: int = 30,
    ) -> PreparedReadOnlyPowerShell:
        target = str(device_uid or "").strip()
        if not target:
            raise ValueError("device_uid is required")
        timeout = self._bounded_timeout(timeout_seconds)

        classification = self._classifier.classify(command)
        if classification.classification == "mutating":
            raise PermissionError(
                "PowerShell command is mutating and requires governed execution: "
                + "; ".join(classification.reasons)
            )
        if classification.classification == "sensitive":
            raise PermissionError(
                "PowerShell command requests sensitive information and requires "
                "separate information-access authority: "
                + "; ".join(classification.reasons)
            )
        if classification.classification != "read_only":
            raise PermissionError(
                "PowerShell command cannot be proven read-only; reformulate or "
                "use governed execution: "
                + "; ".join(classification.reasons)
            )

        normalized = str(command).strip()
        return PreparedReadOnlyPowerShell(
            device_uid=target,
            operation="powershell.readonly",
            command=normalized,
            normalized_arguments={},
            timeout_seconds=timeout,
            active_probe=classification.active_probe,
            classification=classification,
        )

    def prepare(
        self,
        *,
        device_uid: str,
        operation: str,
        arguments: Mapping[str, Any] | None = None,
        timeout_seconds: int = 30,
    ) -> PreparedReadOnlyPowerShell:
        """Compatibility convenience operations rendered into general commands."""

        args = dict(arguments or {})
        op = str(operation or "").strip().casefold()
        renderers = {
            "system.summary": lambda: (
                "Get-CimInstance -ClassName Win32_OperatingSystem "
                "-Property Caption,Version,BuildNumber,LastBootUpTime"
            ),
            "service.list": lambda: "Get-Service",
            "process.list": lambda: "Get-Process",
            "volume.list": lambda: "Get-Volume",
            "network.configuration": lambda: "Get-NetIPConfiguration -Detailed",
            "network.connections": lambda: "Get-NetTCPConnection",
            "hotfix.list": lambda: "Get-HotFix",
            "scheduled_task.list": lambda: "Get-ScheduledTask",
        }

        if op == "service.read":
            name = self._simple_value(args, "name", 256)
            command = f"Get-Service -Name {self._quote(name)}"
        elif op == "eventlog.read":
            log_name = self._simple_value(
                args, "log_name", 256, default="System",
                allowed_extra={"max_events"},
            )
            max_events = int(args.get("max_events", 100))
            if not 1 <= max_events <= 500:
                raise ValueError("max_events must be between 1 and 500")
            command = (
                f"Get-WinEvent -LogName {self._quote(log_name)} "
                f"-MaxEvents {max_events}"
            )
        elif op == "dns.resolve":
            name = self._simple_value(args, "name", 253)
            command = f"Resolve-DnsName -Name {self._quote(name)}"
        elif op == "network.test":
            host = self._simple_value(
                args, "computer_name", 253, allowed_extra={"port"},
            )
            port = int(args.get("port", 443))
            if not 1 <= port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            command = (
                f"Test-NetConnection -ComputerName {self._quote(host)} "
                f"-Port {port}"
            )
        elif op in renderers:
            if args:
                raise PermissionError("unsupported diagnostic arguments")
            command = renderers[op]()
        else:
            raise PermissionError("diagnostic operation is not supported")

        return self.prepare_command(
            device_uid=device_uid,
            command=command,
            timeout_seconds=timeout_seconds,
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
        if (
            prepared.classification is None
            or not prepared.classification.allowed_as_read_only
        ):
            raise PermissionError(
                "prepared PowerShell is not classified for read-only execution"
            )
        result = transport.execute_readonly(
            device_uid=prepared.device_uid,
            command=prepared.command,
            timeout_seconds=prepared.timeout_seconds,
        )
        return result.bounded(maximum_output_chars)

    @staticmethod
    def _bounded_timeout(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout_seconds must be an integer") from exc
        if not 1 <= parsed <= 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        return parsed

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    @staticmethod
    def _simple_value(
        args: Mapping[str, Any],
        name: str,
        maximum_length: int,
        *,
        default: str | None = None,
        allowed_extra: set[str] | None = None,
    ) -> str:
        allowed = {name} | (allowed_extra or set())
        unknown = sorted(set(args) - allowed)
        if unknown:
            raise PermissionError(
                "unsupported diagnostic argument(s): " + ", ".join(unknown)
            )
        value = str(args.get(name) or default or "").strip()
        if not value or len(value) > maximum_length:
            raise ValueError(f"{name} is invalid")
        if any(
            token in value
            for token in (";", "|", "\n", "\r", "$(", chr(96))
        ):
            raise ValueError(f"{name} is invalid")
        return value
