"""Offline Ticket Core Docker acceptance attestor fail-closed regressions."""
from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from tools import pmv4_ticket_core_container_acceptance as lab


RUNNING = {
    "HostConfig": {
        "NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False,
        "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
        "PortBindings": {}, "Tmpfs": {"/tmp": "rw,nosuid,noexec,size=8m"},
    },
    "Config": {"User": "1000:1000", "Env": [
        "HOME=/home/node", "PYTHONPATH=/src",
    ]},
    "Mounts": [
        {"Destination": "/lab", "Type": "bind", "RW": True},
        {"Destination": "/src", "Type": "bind", "RW": False},
        {"Destination": "/opt/lab-worker.py", "Type": "bind", "RW": False},
    ],
}


def _test(monkeypatch, inspect_data):
    calls = []
    def fake_docker(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=json.dumps([inspect_data]), returncode=0)
    monkeypatch.setattr(lab, "_docker", fake_docker)
    lab._check_container("pmv4-test")
    assert calls == [("inspect", "pmv4-test")]


def test_readback_accepts_expected_isolated_container(monkeypatch):
    _test(monkeypatch, deepcopy(RUNNING))


@pytest.mark.parametrize("field", [
    "network", "rootfs", "privilege", "caps", "security", "ports", "user",
    "tmpfs", "mounted_production", "mounted_provider_secret",
    "source_writable", "script_writable", "lab_read_only", "named_volume",
])
def test_readback_rejects_unsafe_runtime_changes(monkeypatch, field):
    data = deepcopy(RUNNING)
    if field == "network":
        data["HostConfig"]["NetworkMode"] = "host"
    elif field == "rootfs":
        data["HostConfig"]["ReadonlyRootfs"] = False
    elif field == "privilege":
        data["HostConfig"]["Privileged"] = True
    elif field == "caps":
        data["HostConfig"]["CapDrop"] = []
    elif field == "security":
        data["HostConfig"]["SecurityOpt"] = []
    elif field == "ports":
        data["HostConfig"]["PortBindings"] = {"8080/tcp": []}
    elif field == "user":
        data["Config"]["User"] = "0:0"
    elif field == "tmpfs":
        data["HostConfig"]["Tmpfs"] = {}
    elif field == "mounted_production":
        data["Mounts"].append({"Destination": "/var/lib/jason/openclaw", "Type": "bind", "RW": True})
    elif field == "mounted_provider_secret":
        data["Mounts"].append({"Destination": "/run/jason-secrets", "Type": "bind", "RW": False})
    elif field == "source_writable":
        data["Mounts"][1]["RW"] = True
    elif field == "script_writable":
        data["Mounts"][2]["RW"] = True
    elif field == "lab_read_only":
        data["Mounts"][0]["RW"] = False
    elif field == "named_volume":
        data["Mounts"][0]["Type"] = "volume"
    with pytest.raises(RuntimeError, match="ISOLATION_READBACK_FAILED"):
        _test(monkeypatch, data)


@pytest.mark.parametrize("key", [
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY",
    "DATTO_API_KEY", "AUTOTASK_API_KEY", "AWS_SECRET_ACCESS_KEY",
])
def test_readback_rejects_provider_or_metered_ai_credentials(monkeypatch, key):
    data = deepcopy(RUNNING)
    data["Config"]["Env"].append(key + "=not-a-real-key")
    with pytest.raises(RuntimeError, match="UNEXPECTED_PROVIDER_KEY"):
        _test(monkeypatch, data)
