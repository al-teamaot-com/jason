from __future__ import annotations

import json
from pathlib import Path

from tools.provider_secret_provision import (
    PROVIDERS,
    RUNTIME_POLICY_NAME,
    runtime_policy_text,
    update_mappings,
)


def test_runtime_policy_is_read_only_for_known_provider_paths() -> None:
    policy = runtime_policy_text()
    assert 'capabilities = ["read"]' in policy
    assert '"create"' not in policy
    assert '"update"' not in policy
    for spec in PROVIDERS.values():
        assert str(spec["secret_path"]) in policy


def test_datto_mapping_exposes_existing_value_only_wrapper_fields(tmp_path: Path) -> None:
    mapping = tmp_path / "secret-mappings.json"
    update_mappings(mapping, "datto_rmm")
    data = json.loads(mapping.read_text(encoding="utf-8"))
    assert data["datto_rmm.readonly.api_url"]["field"] == "api_url"
    assert data["datto_rmm.readonly.api_key"]["field"] == "api_key"
    assert data["datto_rmm.readonly.api_secret"]["field"] == "api_secret"
    paths = {entry["path"] for entry in data.values()}
    assert paths == {"secret/data/jason/providers/datto_rmm/readonly"}


def test_it_glue_mapping_is_provider_scoped(tmp_path: Path) -> None:
    mapping = tmp_path / "secret-mappings.json"
    update_mappings(mapping, "it_glue")
    data = json.loads(mapping.read_text(encoding="utf-8"))
    assert data == {
        "it_glue.readonly.api_key": {
            "field": "api_key",
            "path": "secret/data/jason/providers/it_glue/readonly",
        }
    }


def test_runtime_policy_name_is_specific() -> None:
    assert RUNTIME_POLICY_NAME == "jason-provider-readonly"
