from __future__ import annotations

import builtins
import importlib.util
import io
from pathlib import Path


def load_exporter():
    path = Path(__file__).resolve().parents[1] / "production_health_exporter.py"
    spec = importlib.util.spec_from_file_location("jason_production_health_exporter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_render_metrics_is_secret_safe_and_reports_current_governed_datto_contract(monkeypatch):
    module = load_exporter()

    runtime = {
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "Config": {},
        "HostConfig": {},
        "Mounts": [],
    }
    mcp = {
        "State": {"Running": True},
        "Config": {
            "Image": module.EXPECTED_MCP_IMAGE,
            "Env": [
                "JASON_SOURCE_REVISION=historical-env-value",
                f"JASON_PROVIDER_READ_ACTIVATION_PROFILE={module.EXPECTED_PROVIDER_PROFILE}",
                "JASON_PROVIDER_READ_ACTIVATION_PROFILE=itglue-autotask-governed-catalog-v3",
                f"JASON_AUTOTASK_REQUESTER_AUTH_MODE={module.EXPECTED_AUTOTASK_MODE}",
                f"JASON_DATTO_COMPONENT_EXECUTION_MCP_PROFILE={module.EXPECTED_DATTO_EXECUTION_PROFILE}",
                f"JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME={module.EXPECTED_DATTO_ALLOWLIST}",
                f"JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_UID={module.EXPECTED_DATTO_COMPONENT_UID}",
                f"JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME={module.EXPECTED_DATTO_COMPONENT_NAME}",
                f"JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID={module.EXPECTED_DATTO_DEVICE_UID}",
                f"JASON_DATTO_COMPONENT_EXECUTION_DEVICE_CLASS={module.EXPECTED_DATTO_DEVICE_CLASS}",
            ],
        },
        "HostConfig": {
            "NetworkMode": module.EXPECTED_MCP_NETWORK,
            "RestartPolicy": {"Name": module.EXPECTED_MCP_RESTART_POLICY},
            "PortBindings": {
                "8000/tcp": [
                    {
                        "HostIp": module.EXPECTED_MCP_HOST_IP,
                        "HostPort": module.EXPECTED_MCP_HOST_PORT,
                    }
                ]
            },
        },
        "Mounts": [
            {"Type": "bind", "RW": False, "Destination": destination}
            for destination in module.REQUIRED_SECRET_MOUNTS
        ],
    }
    openbao_container = {"State": {"Running": True}}

    def inspect(name):
        return {
            "jason-runtime": runtime,
            "jason-mcp-pilot": mcp,
            "openbao": openbao_container,
        }[name]

    monkeypatch.setattr(module, "_docker_inspect", inspect)
    monkeypatch.setattr(module, "_openbao_health", lambda: {"initialized": True, "sealed": False})
    monkeypatch.setattr(module, "_kernel_error_count", lambda: 0)
    monkeypatch.setattr(module, "_failed_systemd_units", lambda: 0)
    monkeypatch.setattr(module, "_root_writable", lambda: 1)
    monkeypatch.setattr(module, "_docker_names", lambda: ("jason-mcp-pilot-rollback-20260916T131914Z",))

    metrics = module.render_metrics()

    assert 'jason_production_component_health{component="jason_runtime"} 1' in metrics
    assert 'jason_production_component_health{component="jason_mcp"} 1' in metrics
    assert 'jason_production_component_health{component="openbao"} 1' in metrics
    assert 'jason_mcp_contract{check="image"} 1' in metrics
    assert 'jason_mcp_contract{check="source_revision"} 1' in metrics
    assert 'jason_mcp_contract{check="provider_profile"} 1' in metrics
    assert 'jason_mcp_contract{check="datto_execution_profile"} 1' in metrics
    assert 'jason_mcp_contract{check="datto_execution_scope"} 1' in metrics
    assert 'jason_mcp_contract{check="environment_unique"} 0' in metrics
    assert 'jason_mcp_env_duplicate_count{key="JASON_PROVIDER_READ_ACTIVATION_PROFILE"} 1' in metrics
    assert "jason_mcp_required_secret_mount_contract 1" in metrics
    assert "jason_datto_governed_execution_contract 1" in metrics
    assert "jason_host_kernel_error_count 0" in metrics
    assert "jason_root_filesystem_writable 1" in metrics
    assert "jason_mcp_rollback_available 1" in metrics
    assert 'jason_production_health_exporter_build_info{version="3"} 1' in metrics

    for forbidden in ("password", "secret_id=", "role_id=", "access_token", "refresh_token"):
        assert forbidden not in metrics.casefold()


def test_datto_contract_fails_closed_when_scope_does_not_match(monkeypatch):
    module = load_exporter()
    mcp = {
        "State": {"Running": True},
        "Config": {
            "Image": module.EXPECTED_MCP_IMAGE,
            "Env": [
                f"JASON_PROVIDER_READ_ACTIVATION_PROFILE={module.EXPECTED_PROVIDER_PROFILE}",
                f"JASON_AUTOTASK_REQUESTER_AUTH_MODE={module.EXPECTED_AUTOTASK_MODE}",
                f"JASON_DATTO_COMPONENT_EXECUTION_MCP_PROFILE={module.EXPECTED_DATTO_EXECUTION_PROFILE}",
                f"JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME={module.EXPECTED_DATTO_ALLOWLIST}",
                f"JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_UID={module.EXPECTED_DATTO_COMPONENT_UID}",
                f"JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME={module.EXPECTED_DATTO_COMPONENT_NAME}",
                "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID=wrong-device",
                f"JASON_DATTO_COMPONENT_EXECUTION_DEVICE_CLASS={module.EXPECTED_DATTO_DEVICE_CLASS}",
            ],
        },
        "HostConfig": {
            "NetworkMode": module.EXPECTED_MCP_NETWORK,
            "RestartPolicy": {"Name": module.EXPECTED_MCP_RESTART_POLICY},
            "PortBindings": {"8000/tcp": [{"HostIp": module.EXPECTED_MCP_HOST_IP, "HostPort": module.EXPECTED_MCP_HOST_PORT}]},
        },
        "Mounts": [
            {"Type": "bind", "RW": False, "Destination": destination}
            for destination in module.REQUIRED_SECRET_MOUNTS
        ],
    }
    runtime = {"State": {"Running": True, "Health": {"Status": "healthy"}}}
    openbao_container = {"State": {"Running": True}}

    monkeypatch.setattr(
        module,
        "_docker_inspect",
        lambda name: {"jason-runtime": runtime, "jason-mcp-pilot": mcp, "openbao": openbao_container}[name],
    )
    monkeypatch.setattr(module, "_openbao_health", lambda: {"initialized": True, "sealed": False})
    monkeypatch.setattr(module, "_kernel_error_count", lambda: 0)
    monkeypatch.setattr(module, "_failed_systemd_units", lambda: 0)
    monkeypatch.setattr(module, "_root_writable", lambda: 1)
    monkeypatch.setattr(module, "_docker_names", lambda: ("jason-mcp-pilot-rollback-test",))

    metrics = module.render_metrics()
    assert 'jason_mcp_contract{check="datto_execution_scope"} 0' in metrics
    assert "jason_datto_governed_execution_contract 0" in metrics


def test_root_writable_prefers_pid1_host_mount_namespace(monkeypatch):
    module = load_exporter()
    seen = []

    def fake_open(path, *args, **kwargs):
        seen.append(path)
        if path == "/proc/1/mounts":
            return io.StringIO("/dev/nvme0n1p2 / ext4 rw,relatime 0 0\n")
        if path == "/proc/mounts":
            return io.StringIO("/dev/nvme0n1p2 / ext4 ro,relatime 0 0\n")
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    assert module._root_writable() == 1
    assert seen == ["/proc/1/mounts"]


def test_root_writable_falls_back_when_pid1_mounts_unavailable(monkeypatch):
    module = load_exporter()

    def fake_open(path, *args, **kwargs):
        if path == "/proc/1/mounts":
            raise PermissionError(path)
        if path == "/proc/mounts":
            return io.StringIO("/dev/nvme0n1p2 / ext4 rw,relatime 0 0\n")
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    assert module._root_writable() == 1


def test_missing_components_fail_closed(monkeypatch):
    module = load_exporter()
    monkeypatch.setattr(module, "_docker_inspect", lambda _name: {})
    monkeypatch.setattr(module, "_openbao_health", lambda: {})
    monkeypatch.setattr(module, "_kernel_error_count", lambda: -1)
    monkeypatch.setattr(module, "_failed_systemd_units", lambda: -1)
    monkeypatch.setattr(module, "_root_writable", lambda: -1)
    monkeypatch.setattr(module, "_docker_names", lambda: ())

    metrics = module.render_metrics()

    assert 'jason_production_component_health{component="jason_runtime"} 0' in metrics
    assert 'jason_production_component_health{component="jason_mcp"} 0' in metrics
    assert 'jason_production_component_health{component="openbao"} 0' in metrics
    assert "jason_mcp_required_secret_mount_contract 0" in metrics
    assert "jason_datto_governed_execution_contract 0" in metrics
    assert "jason_root_filesystem_writable -1" in metrics
    assert "jason_mcp_rollback_available 0" in metrics
