from __future__ import annotations

from pathlib import Path

from tools.provider_secret_provision import (
    PROVIDERS,
    provider_policy_text,
)


def test_datto_contract_uses_canonical_connector_path_and_fields() -> None:
    spec = PROVIDERS["datto_rmm"]
    assert spec["logical_name"] == "datto_rmm.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/datto-rmm/production/read-only"
    )
    assert spec["fields"] == ("api_url", "api_key", "api_secret")
    assert spec["policy_name"] == "jason-datto-rmm-read"
    assert spec["role_name"] == "jason-datto-rmm-read"
    assert Path(spec["credential_dir"]) == Path(
        "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle"
    )


def test_it_glue_contract_reuses_existing_production_identity() -> None:
    spec = PROVIDERS["it_glue"]
    assert spec["logical_name"] == "it_glue.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/it-glue/production/read-only"
    )
    assert spec["fields"] == ("api_key",)
    assert spec["policy_name"] == "jason-itglue-read"
    assert spec["role_name"] == "jason-itglue-read"
    assert Path(spec["credential_dir"]) == Path(
        "/opt/jason/bootstrap/secrets/openbao/itglue-read-approle"
    )


def test_provider_policies_are_exactly_read_only() -> None:
    for provider, spec in PROVIDERS.items():
        policy = provider_policy_text(provider)
        assert policy == (
            f'path "{spec["secret_path"]}" {{\n'
            '  capabilities = ["read"]\n'
            '}\n'
        )
        assert '"create"' not in policy
        assert '"update"' not in policy
        assert '"delete"' not in policy
        assert '"sudo"' not in policy


def test_runtime_design_contains_no_persistent_token_path() -> None:
    source = Path("tools/provider_secret_provision.py").read_text(encoding="utf-8")
    assert "openbao-provider.token" not in source
    assert "create-orphan" not in source
    assert '"period": "24h"' not in source
    assert '"token_ttl": "5m"' in source
    assert '"token_num_uses": 2' in source
    assert "auth/approle/role/" in source
    assert "auth/token/revoke-self" in source


def test_live_provisioning_uses_hidden_admin_and_secret_prompts() -> None:
    source = Path("tools/provider_secret_provision.py").read_text(encoding="utf-8")
    assert "getpass.getpass" in source
    assert "OpenBao password for" in source
    assert "api_key" in source
    assert "api_secret" in source
    assert "secret_values_printed" in source
