"""Exact source profile and default-disabled production injection contracts."""
import json
from pathlib import Path

from jason_runtime.datto_component_scope import (
    DATTO_AD_HOC_LINUX_SHELL_UID,
    DATTO_AD_HOC_LINUX_SHELL_NAME,
    DATTO_JASON_ROOT_PROBE_DEVICE_UID,
    DATTO_JASON_ROOT_PROBE_ALLOWLIST,
    DATTO_JASON_ROOT_PROBE_COMMAND,
    DATTO_JASON_ROOT_PROBE_ENV,
    jason_root_probe_enabled,
    jason_root_probe_command_allowed,
)


def test_exact_root_probe_manifest_and_release_config(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    policy = json.loads((root / "config/drmm-jason-root-probe-v1.json").read_text())
    assert policy["device_uid"] == DATTO_JASON_ROOT_PROBE_DEVICE_UID
    assert policy["component_uid"] == DATTO_AD_HOC_LINUX_SHELL_UID
    assert policy["component_name"] == DATTO_AD_HOC_LINUX_SHELL_NAME
    assert policy["approved_command"] == DATTO_JASON_ROOT_PROBE_COMMAND
    assert policy["permission"] == "per_run_only"
    assert policy["status"] == "source_prepared_not_activated"
    for part in ("jason-mcp", "jason-runtime"):
        source = (root / "infrastructure" / part / "production-deploy.sh").read_text()
        assert source.count('--set-env "' + DATTO_JASON_ROOT_PROBE_ENV + '=') == 1
        assert ("{" + DATTO_JASON_ROOT_PROBE_ENV + ":-}") in source
    monkeypatch.delenv(DATTO_JASON_ROOT_PROBE_ENV, raising=False)
    assert jason_root_probe_enabled() is False
    monkeypatch.setenv(DATTO_JASON_ROOT_PROBE_ENV, "other")
    assert jason_root_probe_enabled() is False
    monkeypatch.setenv(DATTO_JASON_ROOT_PROBE_ENV, DATTO_JASON_ROOT_PROBE_DEVICE_UID)
    assert jason_root_probe_enabled() is True
    assert jason_root_probe_command_allowed({"usrInput": "id -u"})
    assert not jason_root_probe_command_allowed({"usrInput": "id -u; echo ok"})
    assert DATTO_JASON_ROOT_PROBE_ALLOWLIST == "aot-jason-root-identity-readonly"
