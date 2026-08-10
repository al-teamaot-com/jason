from __future__ import annotations

from pathlib import Path

from tools.provider_secret_provision import (
    PROVIDERS,
    provider_policy_text,
)


def test_aws_ses_contract_uses_canonical_sendmail_path_and_fields() -> None:
    spec = PROVIDERS["aws_ses"]
    assert spec["logical_name"] == "aws_ses.sendmail"
    assert spec["secret_path"] == (
        "secret/data/connectors/aws-ses/production/sendmail"
    )
    assert spec["fields"] == (
        "access_key_id",
        "secret_access_key",
        "session_token",
    )
    assert spec["required_fields"] == (
        "access_key_id",
        "secret_access_key",
    )
    assert spec["policy_name"] == "jason-aws-ses-sendmail-read"
    assert spec["role_name"] == "jason-aws-ses-sendmail-read"
    assert Path(spec["credential_dir"]) == Path(
        "/opt/jason/bootstrap/secrets/openbao/aws-ses-sendmail-approle"
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


def test_provider_policies_are_read_only_except_self_revoke() -> None:
    for provider, spec in PROVIDERS.items():
        policy = provider_policy_text(provider)
        assert policy == (
            f'path "{spec["secret_path"]}" {{\n'
            '  capabilities = ["read"]\n'
            '}\n\n'
            'path "auth/token/revoke-self" {\n'
            '  capabilities = ["update"]\n'
            '}\n'
        )
        assert '"create"' not in policy
        assert '"delete"' not in policy
        assert '"sudo"' not in policy
        assert policy.count('"update"') == 1


def test_runtime_design_contains_no_persistent_token_path() -> None:
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "tools/provider_secret.py",
            "tools/provider_secret_lifecycle.py",
            "tools/provider_secret_provision.py",
            "tools/provider_secret_kv_write.py",
        )
    )
    assert "openbao-provider.token" not in sources
    assert "create-orphan" not in sources
    assert '"period": "24h"' not in sources
    assert '"token_ttl": "5m"' in sources
    assert '"token_max_ttl": "5m"' in sources
    assert '"token_explicit_max_ttl": "5m"' in sources
    assert '"token_num_uses": 2' in sources
    assert "auth/approle/role/" in sources
    assert "auth/token/revoke-self" in sources


def test_live_provisioning_uses_hidden_admin_and_secret_prompts() -> None:
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "tools/provider_secret_lifecycle.py",
            "tools/provider_secret_provision.py",
        )
    )
    assert "getpass.getpass" in sources
    assert "OpenBao password for" in sources
    assert "api_key" in sources
    assert "api_secret" in sources
    assert "access_key_id" in sources
    assert "secret_access_key" in sources
    assert "secret_values_printed" in sources


def test_operations_document_is_authoritative_and_rejects_old_pattern() -> None:
    text = Path("07-Operations/Provider-Secret-Provisioning.md").read_text(
        encoding="utf-8"
    )
    assert "canonical production lifecycle" in text
    assert "python3 tools/provider_secret.py <action> <provider>" in text
    assert "provider-specific OpenBao AppRoles" in text
    assert "shared persistent provider runtime token is prohibited" in text
    assert "KV v2 create/update operations use compare-and-set" in text
    assert "auth/token/revoke-self" in text
    assert "Deactivation is intentionally reversible" in text
    assert "Do not create `/etc/jason/openbao-provider.token`" in text
    assert "create the provider runtime orphan token" not in text
    assert "--admin-token-file" not in text


def test_jkd003_contains_production_identity_and_lifecycle_invariant() -> None:
    text = Path("03-Components/Kernel/JKD-003-Secrets-Broker.md").read_text(
        encoding="utf-8"
    )
    assert "**Version:** 0.4" in text
    assert "## Production OpenBao identity invariant" in text
    assert "provider-specific least-privilege AppRoles" in text
    assert "shared persistent provider runtime token" in text
    assert "five-minute maximum lifetime and two-use limit" in text
    assert "CI must enforce the production identity and lifecycle invariant" in text
    assert "Production KV v2 create/update operations must use compare-and-set" in text
    assert "Routine deactivation revokes runtime identity while preserving" in text
    assert "Provider identity rotation must install replacement runtime identity" in text
    assert "A second production secret-authentication pattern requires" in text


def test_canonical_resolver_self_revokes_runtime_token() -> None:
    source = Path(
        "implementation/connectors/core/openbao_secrets.py"
    ).read_text(encoding="utf-8")
    assert "auth/approle/login" in source
    assert "auth/token/revoke-self" in source
    assert "finally:" in source
    assert '"datto_rmm.readonly"' in source
    assert '"it_glue.readonly"' in source
    assert '"aws_ses.sendmail"' in source
