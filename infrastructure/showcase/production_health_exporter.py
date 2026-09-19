#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = os.environ.get("JASON_PRODUCTION_HEALTH_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_PRODUCTION_HEALTH_PORT", "9467"))

EXPECTED_MCP_IMAGE = os.environ.get(
    "JASON_EXPECTED_MCP_IMAGE",
    "jason-mcp:generic-governed-26704f0600bb",
)
EXPECTED_SOURCE_REVISION = os.environ.get(
    "JASON_EXPECTED_MCP_SOURCE_REVISION",
    "26704f0600bbc6c48c790c9b9ff501a3b5ec3aad",
)
EXPECTED_PROVIDER_PROFILE = os.environ.get(
    "JASON_EXPECTED_PROVIDER_PROFILE",
    "itglue-autotask-entra-governed-catalog-v4",
)
EXPECTED_AUTOTASK_MODE = os.environ.get(
    "JASON_EXPECTED_AUTOTASK_REQUESTER_MODE",
    "impersonated",
)
EXPECTED_DATTO_EXECUTION_PROFILE = os.environ.get(
    "JASON_EXPECTED_DATTO_EXECUTION_PROFILE",
    "owner-diagnostic-v1",
)
EXPECTED_DATTO_ALLOWLIST = os.environ.get(
    "JASON_EXPECTED_DATTO_EXECUTION_ALLOWLIST",
    "AOT governed diagnostic pilot",
)
EXPECTED_DATTO_COMPONENTS_JSON = os.environ.get(
    "JASON_EXPECTED_DATTO_COMPONENTS_JSON",
    (
        '[{"uid":"afb858ae-e0d5-4c7b-b0da-8617a22b60d4",'
        '"name":"Get-DNS Settings AOT Ver 06042025-1",'
        '"approval_mode":"standing_safe"},'
        '{"uid":"8cb0f063-5875-452e-88ad-2e1748ed0fd0",'
        '"name":"Check Datto EDR/AV Status AOT Ver 12122025-1",'
        '"approval_mode":"standing_safe"}]'
    ),
)
EXPECTED_DATTO_DEVICE_UID = os.environ.get(
    "JASON_EXPECTED_DATTO_DEVICE_UID",
    "69571572-83f7-1e33-9cdf-01717d4e74a4",
)
EXPECTED_DATTO_DEVICE_CLASS = os.environ.get(
    "JASON_EXPECTED_DATTO_DEVICE_CLASS",
    "Desktop",
)

EXPECTED_MCP_NETWORK = "jason-core"
EXPECTED_MCP_HOST_IP = "10.87.246.157"
EXPECTED_MCP_HOST_PORT = "8765"
EXPECTED_MCP_RESTART_POLICY = "no"

WATCHED_ENV_KEYS = (
    "JASON_SOURCE_REVISION",
    "JASON_PROVIDER_READ_ACTIVATION_PROFILE",
    "JASON_AUTOTASK_REQUESTER_AUTH_MODE",
    "JASON_DATTO_COMPONENT_EXECUTION_MCP_PROFILE",
    "JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME",
    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENTS_JSON",
    "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID",
    "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_CLASS",
)

REQUIRED_SECRET_MOUNTS = frozenset(
    {
        "/run/jason-secrets/openbao/role_id",
        "/run/jason-secrets/openbao/secret_id",
        "/run/jason-secrets/openbao/autotask/role_id",
        "/run/jason-secrets/openbao/autotask/secret_id",
        "/run/jason-secrets/openbao/autotask-write/role_id",
        "/run/jason-secrets/openbao/autotask-write/secret_id",
        "/run/jason-secrets/openbao/it-glue/role_id",
        "/run/jason-secrets/openbao/it-glue/secret_id",
        "/run/jason-secrets/openbao/datto-edr/role_id",
        "/run/jason-secrets/openbao/datto-edr/secret_id",
        "/run/jason-secrets/openbao/microsoft-graph/role_id",
        "/run/jason-secrets/openbao/microsoft-graph/secret_id",
        "/run/jason-secrets/openbao/openai/role_id",
        "/run/jason-secrets/openbao/openai/secret_id",
        "/run/jason-secrets/openbao/aws-ses/role_id",
        "/run/jason-secrets/openbao/aws-ses/secret_id",
        "/run/jason-secrets/openbao/datto-rmm-execution/role_id",
        "/run/jason-secrets/openbao/datto-rmm-execution/secret_id",
    }
)

_CACHE: dict[str, tuple[float, int]] = {}


def _metric_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _run(args: list[str], timeout: float = 3.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None



def _systemctl_show(unit: str, properties: tuple[str, ...]) -> dict[str, str]:
    args = ["systemctl", "show", unit]
    for prop in properties:
        args.extend(["-p", prop])
    completed = _run(args, timeout=5)
    if completed is None or completed.returncode != 0:
        return {}
    result: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def _systemd_jason_timers() -> list[dict[str, str | int | float]]:
    completed = _run(["systemctl", "list-unit-files", "jason-*.timer", "--no-legend", "--plain"], timeout=5)
    if completed is None or completed.returncode != 0:
        return []
    timers: list[dict[str, str | int | float]] = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if not fields or not fields[0].endswith(".timer"):
            continue
        unit = fields[0]
        timer = _systemctl_show(unit, ("Description", "ActiveState", "UnitFileState", "NextElapseUSecRealtime", "NextElapseUSecMonotonic", "LastTriggerUSec", "Triggers"))
        service_unit = str(timer.get("Triggers") or "").split()[0] if timer.get("Triggers") else unit[:-6] + ".service"
        service = _systemctl_show(service_unit, ("Result", "ExecMainStatus"))
        next_epoch = _systemd_timestamp_epoch(str(timer.get("NextElapseUSecRealtime") or ""))
        if next_epoch == 0.0:
            next_epoch = _systemd_monotonic_to_epoch(str(timer.get("NextElapseUSecMonotonic") or ""))
        last_epoch = _systemd_timestamp_epoch(str(timer.get("LastTriggerUSec") or ""))
        timers.append({
            "unit": unit,
            "description": str(timer.get("Description") or unit),
            "service": service_unit,
            "active": 1 if timer.get("ActiveState") == "active" else 0,
            "enabled": 1 if timer.get("UnitFileState") in {"enabled", "static"} else 0,
            "next_epoch": next_epoch,
            "last_epoch": last_epoch,
            "last_success": 1 if service.get("Result") == "success" and str(service.get("ExecMainStatus") or "0") == "0" else 0,
            "result": str(service.get("Result") or "unknown"),
        })
    return timers

def _systemd_monotonic_to_epoch(value: str) -> float:
    if not value:
        return 0.0
    completed = _run(["systemd-analyze", "timespan", value], timeout=2)
    if completed is None or completed.returncode != 0:
        return 0.0
    microseconds = None
    for line in completed.stdout.splitlines():
        if line.strip().startswith("μs:"):
            try:
                microseconds = float(line.split(":", 1)[1].strip())
            except ValueError:
                return 0.0
    if microseconds is None:
        return 0.0
    try:
        with open("/proc/uptime", encoding="utf-8") as handle:
            uptime = float(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0
    return time.time() + (microseconds / 1_000_000.0) - uptime

def _systemd_timestamp_epoch(value: str) -> float:
    if not value or value in {"n/a", "-"}:
        return 0.0
    completed = _run(["date", "-d", value, "+%s"], timeout=2)
    if completed is None or completed.returncode != 0:
        return 0.0
    try:
        return float(completed.stdout.strip())
    except ValueError:
        return 0.0

def _docker_inspect(container: str) -> dict:
    completed = _run(["docker", "inspect", container])
    if completed is None or completed.returncode != 0:
        return {}
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        return {}
    return payload[0]


def _docker_names() -> tuple[str, ...]:
    completed = _run(["docker", "ps", "-a", "--format", "{{.Names}}"])
    if completed is None or completed.returncode != 0:
        return ()
    return tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())


def _env_values(inspect: dict, key: str) -> list[str]:
    config = inspect.get("Config") if isinstance(inspect.get("Config"), dict) else {}
    raw = config.get("Env") if isinstance(config.get("Env"), list) else []
    prefix = key + "="
    return [
        str(item)[len(prefix):]
        for item in raw
        if isinstance(item, str) and item.startswith(prefix)
    ]


def _container_running(inspect: dict) -> bool:
    state = inspect.get("State") if isinstance(inspect.get("State"), dict) else {}
    return state.get("Running") is True


def _container_healthy(inspect: dict) -> bool:
    state = inspect.get("State") if isinstance(inspect.get("State"), dict) else {}
    health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
    return str(health.get("Status") or "").casefold() == "healthy"


def _openbao_health() -> dict:
    request = urllib.request.Request("http://127.0.0.1:8200/v1/sys/health")
    try:
        response = urllib.request.urlopen(request, timeout=2)
        body = response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except OSError:
            return {}
    except (OSError, urllib.error.URLError):
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _root_writable_from_mounts(path: str) -> int | None:
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "/":
            options = set(parts[3].split(","))
            return 1 if "rw" in options and "ro" not in options else 0
    return None


def _root_writable() -> int:
    for path in ("/proc/1/mounts", "/proc/mounts"):
        value = _root_writable_from_mounts(path)
        if value is not None:
            return value
    return -1


def _cached_count(name: str, ttl: float, loader) -> int:
    now = time.monotonic()
    cached = _CACHE.get(name)
    if cached is not None and now - cached[0] < ttl:
        return cached[1]
    value = int(loader())
    _CACHE[name] = (now, value)
    return value


def _kernel_error_count_uncached() -> int:
    completed = _run(["journalctl", "-k", "-b", "--no-pager", "-o", "cat"], timeout=5)
    if completed is None or completed.returncode != 0:
        return -1
    patterns = (
        "ext4-fs error",
        "general protection fault",
        "list_del corruption",
        "i/o error",
        "media error",
        "kernel bug",
        "oops:",
    )
    return sum(
        1
        for line in completed.stdout.splitlines()
        if any(pattern in line.casefold() for pattern in patterns)
    )


def _kernel_error_count() -> int:
    return _cached_count("kernel-errors", 60.0, _kernel_error_count_uncached)


def _failed_systemd_units_uncached() -> int:
    completed = _run(["systemctl", "--failed", "--no-legend", "--plain"], timeout=5)
    if completed is None or completed.returncode != 0:
        return -1
    return sum(1 for line in completed.stdout.splitlines() if line.strip())


def _failed_systemd_units() -> int:
    return _cached_count("failed-units", 60.0, _failed_systemd_units_uncached)


def _mcp_contract(mcp: dict) -> tuple[dict[str, int], dict[str, int], int, int]:
    config = mcp.get("Config") if isinstance(mcp.get("Config"), dict) else {}
    host_config = mcp.get("HostConfig") if isinstance(mcp.get("HostConfig"), dict) else {}

    env = {key: _env_values(mcp, key) for key in WATCHED_ENV_KEYS}
    duplicates = {key: max(0, len(values) - 1) for key, values in env.items()}

    image_ref = str(config.get("Image") or "")
    source_ok = (
        EXPECTED_SOURCE_REVISION in env["JASON_SOURCE_REVISION"]
        or EXPECTED_SOURCE_REVISION[:12] in image_ref
    )

    ports = host_config.get("PortBindings") if isinstance(host_config.get("PortBindings"), dict) else {}
    binding_rows = ports.get("8000/tcp") if isinstance(ports.get("8000/tcp"), list) else []
    port_ok = any(
        isinstance(row, dict)
        and str(row.get("HostIp") or "") == EXPECTED_MCP_HOST_IP
        and str(row.get("HostPort") or "") == EXPECTED_MCP_HOST_PORT
        for row in binding_rows
    )

    restart = host_config.get("RestartPolicy") if isinstance(host_config.get("RestartPolicy"), dict) else {}
    network_ok = str(host_config.get("NetworkMode") or "") == EXPECTED_MCP_NETWORK
    restart_ok = str(restart.get("Name") or "") == EXPECTED_MCP_RESTART_POLICY

    datto_profile_ok = (
        EXPECTED_DATTO_EXECUTION_PROFILE
        in env["JASON_DATTO_COMPONENT_EXECUTION_MCP_PROFILE"]
    )
    datto_scope_ok = all(
        expected in env[key]
        for key, expected in (
            ("JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME", EXPECTED_DATTO_ALLOWLIST),
            ("JASON_DATTO_COMPONENT_EXECUTION_COMPONENTS_JSON", EXPECTED_DATTO_COMPONENTS_JSON),
            ("JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID", EXPECTED_DATTO_DEVICE_UID),
            ("JASON_DATTO_COMPONENT_EXECUTION_DEVICE_CLASS", EXPECTED_DATTO_DEVICE_CLASS),
        )
    )

    checks = {
        "running": 1 if _container_running(mcp) else 0,
        "image": 1 if image_ref == EXPECTED_MCP_IMAGE else 0,
        "source_revision": 1 if source_ok else 0,
        "provider_profile": 1 if EXPECTED_PROVIDER_PROFILE in env["JASON_PROVIDER_READ_ACTIVATION_PROFILE"] else 0,
        "autotask_requester_mode": 1 if EXPECTED_AUTOTASK_MODE in env["JASON_AUTOTASK_REQUESTER_AUTH_MODE"] else 0,
        "datto_execution_profile": 1 if datto_profile_ok else 0,
        "datto_execution_scope": 1 if datto_scope_ok else 0,
        "network": 1 if network_ok else 0,
        "port_binding": 1 if port_ok else 0,
        "restart_policy": 1 if restart_ok else 0,
        "environment_unique": 1 if not any(duplicates.values()) else 0,
    }

    mounts = mcp.get("Mounts") if isinstance(mcp.get("Mounts"), list) else []
    destinations = {
        str(item.get("Destination") or "")
        for item in mounts
        if isinstance(item, dict)
        and item.get("Type") == "bind"
        and item.get("RW") is False
    }
    mounted = len(REQUIRED_SECRET_MOUNTS & destinations)
    mount_contract = 1 if REQUIRED_SECRET_MOUNTS.issubset(destinations) else 0
    return checks, duplicates, mounted, mount_contract


def render_metrics() -> str:
    runtime = _docker_inspect("jason-runtime")
    mcp = _docker_inspect("jason-mcp-pilot")
    openbao_container = _docker_inspect("openbao")
    openbao = _openbao_health()

    checks, duplicates, mounted, mount_contract = _mcp_contract(mcp)
    kernel_errors = _kernel_error_count()
    failed_units = _failed_systemd_units()
    root_writable = _root_writable()
    rollback_available = 1 if any(
        name.startswith("jason-mcp-pilot-rollback-")
        or name.startswith("jason-mcp-pilot-pre-v4-")
        for name in _docker_names()
    ) else 0
    datto_contract = 1 if (
        checks.get("running") == 1
        and checks.get("image") == 1
        and checks.get("datto_execution_profile") == 1
        and checks.get("datto_execution_scope") == 1
        and mount_contract == 1
    ) else 0

    lines = [
        "# HELP jason_production_component_health Secret-safe production component health.",
        "# TYPE jason_production_component_health gauge",
        f'jason_production_component_health{{component="jason_runtime"}} {1 if _container_running(runtime) and _container_healthy(runtime) else 0}',
        f'jason_production_component_health{{component="jason_mcp"}} {1 if _container_running(mcp) else 0}',
        f'jason_production_component_health{{component="openbao"}} {1 if _container_running(openbao_container) and openbao.get("initialized") is True and openbao.get("sealed") is False else 0}',
        "# HELP jason_openbao_initialized OpenBao initialization state from the unauthenticated health endpoint.",
        "# TYPE jason_openbao_initialized gauge",
        f'jason_openbao_initialized {1 if openbao.get("initialized") is True else 0}',
        "# HELP jason_openbao_unsealed OpenBao unsealed state from the unauthenticated health endpoint.",
        "# TYPE jason_openbao_unsealed gauge",
        f'jason_openbao_unsealed {1 if openbao.get("initialized") is True and openbao.get("sealed") is False else 0}',
        "# HELP jason_mcp_contract Production MCP deployment and bounded governed-action contract checks.",
        "# TYPE jason_mcp_contract gauge",
    ]

    for check, value in sorted(checks.items()):
        lines.append(f'jason_mcp_contract{{check="{_metric_escape(check)}"}} {value}')

    lines.extend([
        "# HELP jason_mcp_env_duplicate_count Extra Docker environment entries for watched production MCP keys.",
        "# TYPE jason_mcp_env_duplicate_count gauge",
    ])
    for key, value in sorted(duplicates.items()):
        lines.append(f'jason_mcp_env_duplicate_count{{key="{_metric_escape(key)}"}} {value}')

    lines.extend([
        "# HELP jason_mcp_required_secret_mounts_present Number of required read-only OpenBao credential bind destinations present on the MCP.",
        "# TYPE jason_mcp_required_secret_mounts_present gauge",
        f"jason_mcp_required_secret_mounts_present {mounted}",
        "# HELP jason_mcp_required_secret_mount_contract Whether all required read-only credential mount destinations are present.",
        "# TYPE jason_mcp_required_secret_mount_contract gauge",
        f"jason_mcp_required_secret_mount_contract {mount_contract}",
        "# HELP jason_datto_governed_execution_contract Secret-safe readiness of the exact bounded Datto governed-execution pilot configuration. This is not provider execution authority or a provider canary.",
        "# TYPE jason_datto_governed_execution_contract gauge",
        f"jason_datto_governed_execution_contract {datto_contract}",
        "# HELP jason_host_kernel_error_count Current-boot kernel corruption/storage error signature count; -1 means unavailable.",
        "# TYPE jason_host_kernel_error_count gauge",
        f"jason_host_kernel_error_count {kernel_errors}",
        "# HELP jason_host_failed_systemd_units Failed systemd unit count; -1 means unavailable.",
        "# TYPE jason_host_failed_systemd_units gauge",
        f"jason_host_failed_systemd_units {failed_units}",
        "# HELP jason_root_filesystem_writable Whether the host root filesystem is mounted read/write; -1 means unavailable.",
        "# TYPE jason_root_filesystem_writable gauge",
        f"jason_root_filesystem_writable {root_writable}",
        "# HELP jason_mcp_rollback_available Whether a preserved MCP rollback container is present.",
        "# TYPE jason_mcp_rollback_available gauge",
        f"jason_mcp_rollback_available {rollback_available}",
        "# HELP jason_production_expected_info Expected production MCP release metadata. No credentials or provider records are exposed.",
        "# TYPE jason_production_expected_info gauge",
        (
            'jason_production_expected_info{image="'
            + _metric_escape(EXPECTED_MCP_IMAGE)
            + '",source_revision="'
            + _metric_escape(EXPECTED_SOURCE_REVISION)
            + '",provider_profile="'
            + _metric_escape(EXPECTED_PROVIDER_PROFILE)
            + '"} 1'
        ),
        "# HELP jason_production_health_exporter_build_info Production health exporter metadata.",
        "# TYPE jason_production_health_exporter_build_info gauge",
        'jason_production_health_exporter_build_info{version="5"} 1',
    ])

    timers = _systemd_jason_timers()
    lines.extend([
        "# HELP jason_scheduled_task_info Secret-safe Jason systemd scheduled-task metadata.",
        "# TYPE jason_scheduled_task_info gauge",
    ])
    for timer in timers:
        labels = ",".join(
            f'{key}="{_metric_escape(str(value))}"'
            for key, value in (("unit", timer["unit"]), ("description", timer["description"]), ("service", timer["service"]), ("last_result", timer["result"]))
        )
        lines.append(f"jason_scheduled_task_info{{{labels}}} 1")
        for metric, key in (("enabled", "enabled"), ("active", "active"), ("last_success", "last_success"), ("next_run_timestamp_seconds", "next_epoch"), ("last_run_timestamp_seconds", "last_epoch")):
            lines.append(f'jason_scheduled_task_{metric}{{unit="{_metric_escape(str(timer["unit"]))}"}} {timer[key]}')

    lines.extend([
        "# HELP jason_system_configuration_info Curated secret-safe operator configuration metadata.",
        "# TYPE jason_system_configuration_info gauge",
        'jason_system_configuration_info{setting="direct_provider_access",value="false"} 1',
        f'jason_system_configuration_info{{setting="provider_profile",value="{_metric_escape(EXPECTED_PROVIDER_PROFILE)}"}} 1',
        f'jason_system_configuration_info{{setting="autotask_requester_mode",value="{_metric_escape(EXPECTED_AUTOTASK_MODE)}"}} 1',
        f'jason_system_configuration_info{{setting="datto_execution_profile",value="{_metric_escape(EXPECTED_DATTO_EXECUTION_PROFILE)}"}} 1',
        f'jason_system_configuration_info{{setting="source_revision",value="{_metric_escape(EXPECTED_SOURCE_REVISION)}"}} 1',
    ])

    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/metrics"):
            self.send_response(404)
            self.end_headers()
            return
        payload = render_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Jason production health exporter listening on {HOST}:{PORT}", flush=True)
    while True:
        server.handle_request()
        time.sleep(0)
