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


def test_autotask_write_contract_is_separate_from_readonly_credentials() -> None:
    spec = PROVIDERS["autotask_write"]
    assert spec["logical_name"] == "autotask.write"
    assert spec["secret_path"] == (
        "secret/data/connectors/autotask/production/write"
    )
    assert spec["fields"] == ("username", "secret", "integration_code")
    assert spec["required_fields"] == (
        "username",
        "secret",
        "integration_code",
    )
    assert spec["policy_name"] == "jason-autotask-write-secret-read"
    assert spec["role_name"] == "jason-autotask-write-secret-read"
    assert spec["connector_identity"] == "autotask-write"
    assert Path(spec["credential_dir"]) == Path(
        "/opt/jason/bootstrap/secrets/openbao/autotask-write-approle"
    )
    assert "read-only" not in str(spec["secret_path"])


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


def test_microsoft_mail_contract_is_separate_from_directory_read() -> None:
    directory = PROVIDERS["microsoft_graph"]
    mail = PROVIDERS["microsoft_graph_mail"]
    assert mail["logical_name"] == "microsoft_graph.mail_read"
    assert mail["secret_path"] == (
        "secret/data/connectors/microsoft-graph/production/mail-read"
    )
    assert mail["fields"] == directory["fields"]
    assert mail["policy_name"] == "jason-microsoft-graph-mail-read"
    assert mail["role_name"] == "jason-microsoft-graph-mail-read"
    assert mail["connector_identity"] == "microsoft-graph-mail-read"
    assert Path(mail["credential_dir"]) == Path(
        "/opt/jason/bootstrap/secrets/openbao/microsoft-graph-mail-read-approle"
    )
    assert mail["secret_path"] != directory["secret_path"]
    assert mail["role_name"] != directory["role_name"]


def test_kyocera_kfs_contract_uses_canonical_connector_path_and_fields() -> None:
    spec = PROVIDERS["kyocera_kfs"]
    assert spec["logical_name"] == "kyocera_kfs.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/kyocera-kfs/production/read-only"
    )
    assert spec["fields"] == (
        "api_url",
        "request_from",
        "request_to",
        "authorization",
        "kfs_username",
        "kfs_password",
    )
    assert spec["policy_name"] == "jason-kyocera-kfs-read"
    assert spec["role_name"] == "jason-kyocera-kfs-read"
    assert Path(spec["credential_dir"]) == Path(
        "/opt/jason/bootstrap/secrets/openbao/kyocera-kfs-read-approle"
    )


def test_backup_net_contract_uses_canonical_connector_path_and_fields() -> None:
    spec = PROVIDERS["backup_net"]
    assert spec["logical_name"] == "backup_net.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/backup-net/production/read-only"
    )
    assert spec["fields"] == ("client_id", "client_secret")
    assert spec["policy_name"] == "jason-backup-net-read"
    assert spec["role_name"] == "jason-backup-net-read"
    assert Path(spec["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/backup-net-read-approle"
    )
    assert spec["credential_uid"] == 0
    assert spec["credential_gid"] == 1000
    assert spec["credential_dir_mode"] == 0o750
    assert spec["credential_file_mode"] == 0o640


def test_backup_net_full_access_contract_is_isolated_from_readonly_identity() -> None:
    spec = PROVIDERS["backup_net_full_access"]
    assert spec["logical_name"] == "backup_net.fullaccess"
    assert spec["secret_path"] == (
        "secret/data/connectors/backup-net/production/full-access"
    )
    assert spec["fields"] == ("client_id", "client_secret")
    assert spec["policy_name"] == "jason-backup-net-full-access"
    assert spec["role_name"] == "jason-backup-net-full-access"
    assert Path(spec["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/backup-net-full-access-approle"
    )
    assert spec["credential_uid"] == 0
    assert spec["credential_gid"] == 1000
    assert spec["credential_dir_mode"] == 0o750
    assert spec["credential_file_mode"] == 0o640


def test_dnsfilter_contract_uses_canonical_readonly_path_and_fields() -> None:
    spec = PROVIDERS["dnsfilter"]
    assert spec["logical_name"] == "dnsfilter.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/dnsfilter/production/read-only"
    )
    assert spec["fields"] == ("api_key",)
    assert spec["policy_name"] == "jason-dnsfilter-read"
    assert spec["role_name"] == "jason-dnsfilter-read"
    assert Path(spec["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/dnsfilter-read-approle"
    )
    assert spec["credential_uid"] == 0
    assert spec["credential_gid"] == 1000
    assert spec["credential_dir_mode"] == 0o750
    assert spec["credential_file_mode"] == 0o640


def test_darkwebid_contract_uses_canonical_runtime_path_and_fields() -> None:
    spec = PROVIDERS["darkwebid"]
    assert spec["logical_name"] == "darkwebid.runtime"
    assert spec["secret_path"] == (
        "secret/data/connectors/darkwebid/production/runtime"
    )
    assert spec["fields"] == ("username", "password")
    assert spec["required_fields"] == ("username", "password")
    assert spec["policy_name"] == "jason-darkwebid-secret-read"
    assert spec["role_name"] == "jason-darkwebid-secret-read"
    assert spec["connector_identity"] == "darkwebid"
    assert Path(spec["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/darkwebid-approle"
    )
    assert spec["credential_uid"] == 0
    assert spec["credential_gid"] == 1000
    assert spec["credential_dir_mode"] == 0o750
    assert spec["credential_file_mode"] == 0o640


def test_saas_alerts_contract_uses_canonical_readonly_path_and_fields() -> None:
    spec = PROVIDERS["saas_alerts"]
    assert spec["logical_name"] == "saas_alerts.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/saas-alerts/production/read-only"
    )
    assert spec["fields"] == ("api_key", "partner_id")
    assert spec["required_fields"] == ("api_key", "partner_id")
    assert spec["policy_name"] == "jason-saas-alerts-read"
    assert spec["role_name"] == "jason-saas-alerts-read"
    assert Path(spec["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/saas-alerts-read-approle"
    )
    assert spec["credential_uid"] == 0
    assert spec["credential_gid"] == 1000
    assert spec["credential_dir_mode"] == 0o750
    assert spec["credential_file_mode"] == 0o640


def test_vulscan_contract_uses_canonical_readonly_path_and_fields() -> None:
    spec = PROVIDERS["vulscan"]
    assert spec["logical_name"] == "vulscan.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/vulscan/production/read-only"
    )
    assert spec["fields"] == ("api_key",)
    assert spec["required_fields"] == ("api_key",)
    assert spec["policy_name"] == "jason-vulscan-read"
    assert spec["role_name"] == "jason-vulscan-read"
    assert Path(spec["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/vulscan-read-approle"
    )
    assert spec["credential_uid"] == 0
    assert spec["credential_gid"] == 1000
    assert spec["credential_dir_mode"] == 0o750
    assert spec["credential_file_mode"] == 0o640



def test_quickbooks_development_contract_is_isolated_from_production() -> None:
    spec = PROVIDERS["quickbooks_development"]
    assert spec["logical_name"] == "quickbooks.oauth_client"
    assert spec["secret_path"] == (
        "secret/data/connectors/quickbooks/development/oauth-client"
    )
    assert spec["fields"] == ("client_id", "client_secret")
    assert spec["required_fields"] == ("client_id", "client_secret")
    assert spec["policy_name"] == "jason-quickbooks-development-oauth-client-read"
    assert spec["role_name"] == "jason-quickbooks-development-oauth-client-read"
    assert spec["connector_identity"] == "quickbooks-development-oauth-client"
    assert spec["environment"] == "development"
    assert "production" not in str(spec["secret_path"])
    assert Path(spec["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/"
        "quickbooks-development-oauth-client-approle"
    )


def test_quickbooks_production_contract_is_isolated_from_development() -> None:
    dev = PROVIDERS["quickbooks_development"]
    prod = PROVIDERS["quickbooks_production"]
    assert prod["logical_name"] == "quickbooks.production.oauth_client"
    assert prod["secret_path"] == (
        "secret/data/connectors/quickbooks/production/oauth-client"
    )
    assert prod["fields"] == ("client_id", "client_secret", "token_key_b64")
    assert prod["required_fields"] == ("client_id", "client_secret", "token_key_b64")
    assert prod["policy_name"] == "jason-quickbooks-production-oauth-client-read"
    assert prod["role_name"] == "jason-quickbooks-production-oauth-client-read"
    assert prod["connector_identity"] == "quickbooks-production-oauth-client"
    assert prod["environment"] == "production"
    assert Path(prod["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/"
        "quickbooks-production-oauth-client-approle"
    )
    assert prod["secret_path"] != dev["secret_path"]
    assert prod["role_name"] != dev["role_name"]
    assert prod["credential_dir"] != dev["credential_dir"]


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
    assert "api_token" in sources
    assert "access_key_id" in sources
    assert "secret_access_key" in sources
    assert "secret_values_printed" in sources


def test_operations_document_is_authoritative_and_rejects_old_pattern() -> None:
    text = Path("docs/operations/Provider-Secret-Provisioning.md").read_text(
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
    assert "autotask_write" in text
    assert "autotask.write" in text
    assert "create the provider runtime orphan token" not in text
    assert "--admin-token-file" not in text


def test_jkd003_contains_production_identity_and_lifecycle_invariant() -> None:
    text = Path("docs/components/kernel/JKD-003-Secrets-Broker.md").read_text(
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
    assert '"autotask.write"' in source
    assert '"datto_rmm.readonly"' in source
    assert '"datto_edr.readonly"' in source
    assert '"it_glue.readonly"' in source
    assert '"kyocera_kfs.readonly"' in source
    assert '"backup_net.readonly"' in source
    assert '"backup_net.fullaccess"' in source
    assert '"darkwebid.runtime"' in source
    assert '"aws_ses.sendmail"' in source


def test_datto_edr_contract_uses_dedicated_readonly_identity() -> None:
    spec = PROVIDERS["datto_edr"]
    assert spec["logical_name"] == "datto_edr.readonly"
    assert spec["secret_path"] == (
        "secret/data/connectors/datto-edr/production/read-only"
    )
    assert spec["fields"] == ("api_url", "api_token")
    assert spec["required_fields"] == ("api_url", "api_token")
    assert spec["policy_name"] == "jason-datto-edr-read"
    assert spec["role_name"] == "jason-datto-edr-read"
    assert spec["connector_identity"] == "datto-edr-read"
    assert Path(spec["credential_dir"]) == Path(
        "/opt/jason/bootstrap/secrets/openbao/datto-edr-read-approle"
    )



def test_microsoft_group_admin_policies_use_two_distinct_secrets_and_approles() -> None:
    read = PROVIDERS["microsoft_graph_group_read"]
    write = PROVIDERS["microsoft_graph_group_write"]
    existing = PROVIDERS["microsoft_graph"]
    fields = ("private_key_pem", "certificate_pem", "certificate_thumbprint", "generation")
    for profile in (read, write):
        assert profile["fields"] == fields
        assert set(profile["fields"]) == set(existing["fields"])
        assert profile["logical_name"].startswith("microsoft_graph.group_")
        assert profile["secret_path"] not in {existing["secret_path"]}
        assert profile["role_name"] != existing["role_name"]
        assert provider_policy_text("microsoft_graph_group_read").count('capabilities = ["read"]') == 1
    assert read["logical_name"] != write["logical_name"]
    assert read["secret_path"] != write["secret_path"]
    assert read["role_name"] != write["role_name"]
    assert read["credential_dir"] != write["credential_dir"]



def test_group_admin_secrets_use_create_only_cas_and_no_overwrite(monkeypatch):
    import tools.provider_secret_provision as module

    calls = []

    def fake_api_request(address, api_path, *, method, payload=None, token=None, allow_empty=False):
        calls.append((api_path, method, payload, allow_empty))
        return {}

    monkeypatch.setattr(module, "api_request", fake_api_request)
    values = {
        "private_key_pem": "fake-private-test-only",
        "certificate_pem": "fake-public-test-only",
        "certificate_thumbprint": "A" * 40,
        "generation": "test-only",
    }
    for provider in ("microsoft_graph_group_read", "microsoft_graph_group_write"):
        calls.clear()
        module.write_provider_secret(
            address="http://unused.invalid", admin_token="test",
            provider=provider, values=values,
        )
        assert len(calls) == 1
        assert calls[0][0] == PROVIDERS[provider]["secret_path"]
        assert calls[0][1] == "POST"
        assert calls[0][2] == {"data": values, "options": {"cas": 0}}
        assert calls[0][3] is True


def test_group_admin_read_write_provisioning_no_cross_provider_paths():
    read = PROVIDERS["microsoft_graph_group_read"]
    write = PROVIDERS["microsoft_graph_group_write"]
    for spec in (read, write):
        assert spec["create_only_secret"] is True
        assert spec["secret_path"].startswith("secret/data/connectors/microsoft-graph/production/group-")
    assert read["secret_path"] != write["secret_path"]


def test_sharepoint_writer_uses_certificate_files_and_create_only_secret(monkeypatch):
    import tools.provider_secret_provision as module

    expected = {
        "private_key_pem": "private-test-only",
        "certificate_pem": "certificate-test-only",
        "certificate_thumbprint": "A" * 40,
        "generation": "test-only",
    }
    monkeypatch.setattr(module, "_collect_microsoft_graph_values", lambda: expected)
    assert module.collect_values("microsoft_graph_sharepoint_write") == expected

    calls = []
    monkeypatch.setattr(module, "api_request", lambda *a, **kw: calls.append((a, kw)) or {})
    module.write_provider_secret(
        address="http://unused.invalid", admin_token="test",
        provider="microsoft_graph_sharepoint_write", values=expected,
    )
    assert calls[0][1]["payload"] == {"data": expected, "options": {"cas": 0}}


def test_microsoft_sharepoint_write_contract_is_isolated_and_site_scoped_by_design() -> None:
    directory = PROVIDERS["microsoft_graph"]
    sharepoint = PROVIDERS["microsoft_graph_sharepoint_write"]
    assert sharepoint["logical_name"] == "microsoft_graph.sharepoint_write"
    assert sharepoint["create_only_secret"] is True
    assert sharepoint["secret_path"] == (
        "secret/data/connectors/microsoft-graph/production/sharepoint-write"
    )
    assert sharepoint["fields"] == directory["fields"]
    assert sharepoint["required_fields"] == directory["fields"]
    assert sharepoint["policy_name"] == "jason-microsoft-graph-sharepoint-write"
    assert sharepoint["role_name"] == "jason-microsoft-graph-sharepoint-write"
    assert sharepoint["connector_identity"] == "microsoft-graph-sharepoint-write"
    assert Path(sharepoint["credential_dir"]) == Path(
        "/var/lib/jason/runtime-secrets/openbao/microsoft-sharepoint-write-approle"
    )
    assert sharepoint["secret_path"] != directory["secret_path"]
    assert sharepoint["role_name"] != directory["role_name"]

def test_it_glue_shared_key_requires_distinct_role_and_denies_value_mutation(monkeypatch):
    import pytest
    from tools import provider_secret_provision as module
    from tools import provider_secret_kv_write as kv
    from tools import provider_secret_lifecycle as lifecycle
    spec=module.PROVIDERS["it_glue_write"]
    read=module.PROVIDERS["it_glue"]
    assert spec["shared_secret_provider"] == "it_glue"
    assert spec["secret_path"] == read["secret_path"]
    for name in ("logical_name","policy_name","role_name","credential_dir","connector_identity"):
        assert spec[name]!=read[name]
    assert module.provider_policy_text("it_glue_write")==module.provider_policy_text("it_glue")
    def unexpected(*a,**kw): raise AssertionError("no prompt, network, or role mutation")
    monkeypatch.setattr(module,"api_request",unexpected)
    monkeypatch.setattr(module.getpass,"getpass",unexpected)
    monkeypatch.setattr(kv,"current_version",unexpected)
    monkeypatch.setattr(module,"configure_read_approle",unexpected)
    monkeypatch.setattr(module.os,"geteuid",lambda:0)
    with pytest.raises(module.ProvisionError,match="SHARED_PROVIDER_SECRET_VALUE_MUTATION_DENIED"):
        module.collect_values("it_glue_write")
    with pytest.raises(module.ProvisionError,match="SHARED_PROVIDER_SECRET_VALUE_MUTATION_DENIED"):
        module.write_provider_secret(address="http://unused.invalid",admin_token="test-only",
            provider="it_glue_write",values={"api_key":"synthetic"})
    with pytest.raises(module.ProvisionError,match="SHARED_PROVIDER_SECRET_VALUE_MUTATION_DENIED"):
        kv.write_provider_secret_cas(address="http://unused.invalid",admin_token="test-only",
            provider="it_glue_write",values={"api_key":"synthetic"})
    with pytest.raises(SystemExit,match="SHARED_PROVIDER_SECRET_VALUE_MUTATION_DENIED"):
        module.main(["it_glue_write"])
    for action in ("create","update"):
        with pytest.raises(lifecycle.LifecycleError,match="SHARED_PROVIDER_SECRET_VALUE_MUTATION_DENIED"):
            lifecycle.create_or_update(address="http://unused.invalid",admin_token="test-only",
                provider="it_glue_write",action=action)
        with pytest.raises(SystemExit,match="SHARED_PROVIDER_SECRET_VALUE_MUTATION_DENIED"):
            lifecycle.main([action,"it_glue_write"])


def test_it_glue_alias_reactivate_only_binds_existing_key(monkeypatch,tmp_path):
    from tools import provider_secret_lifecycle as lifecycle
    from tools import provider_secret_provision as base
    import pytest
    spec=dict(base.PROVIDERS["it_glue_write"],credential_dir=tmp_path/"write")
    monkeypatch.setitem(base.PROVIDERS,"it_glue_write",spec)
    calls=[]
    def version(address,path,token):
        assert path==base.PROVIDERS["it_glue"]["secret_path"]
        return 4
    monkeypatch.setattr(lifecycle.kv,"current_version",version)
    monkeypatch.setattr(base,"configure_read_approle",
        lambda **kw: calls.append(kw["provider"]) or {"credential_dir":str(spec["credential_dir"])})
    def forbidden(*a,**kw): raise AssertionError("shared key must remain unchanged")
    monkeypatch.setattr(base,"collect_values",forbidden)
    monkeypatch.setattr(lifecycle.kv,"write_provider_secret_cas",forbidden)
    verified=[]
    monkeypatch.setattr(lifecycle,"verify",
        lambda provider: verified.append(provider) or {"status":"pass"})
    result=lifecycle.reactivate(address=base.DEFAULT_ADDRESS,admin_token="test",
        provider="it_glue_write")
    assert result["kv_version"]==4 and result["provider_secret_reentered"] is False
    assert result["shared_kv_version_unchanged"] and result["canonical_identity_verified"] and result["alias_identity_verified"]
    assert verified==["it_glue","it_glue_write","it_glue"]
    assert calls==["it_glue_write"]
    monkeypatch.setattr(lifecycle.kv,"current_version",lambda *a:0)
    with pytest.raises(lifecycle.LifecycleError,match="alias cannot create"):
        lifecycle.reactivate(address=base.DEFAULT_ADDRESS,admin_token="test",provider="it_glue_write")
    assert calls==["it_glue_write"]
    monkeypatch.setattr(lifecycle.kv,"current_version",version)
    monkeypatch.setattr(lifecycle,"verify",lambda provider:{"status":"failed"})
    with pytest.raises(lifecycle.LifecycleError,match="Canonical shared provider secret verification failed"):
        lifecycle.reactivate(address=base.DEFAULT_ADDRESS,admin_token="test",provider="it_glue_write")
    assert calls==["it_glue_write"]

def test_it_glue_write_identity_verify_maps_only_the_alias(monkeypatch,tmp_path):
    from tools import provider_secret_lifecycle as lifecycle
    from tools import provider_secret_provision as base
    from connectors.core.openbao_secrets import OpenBaoSecretResolver
    spec=dict(base.PROVIDERS["it_glue_write"],credential_dir=tmp_path/"write")
    monkeypatch.setitem(base.PROVIDERS,"it_glue_write",spec)
    d=spec["credential_dir"];d.mkdir()
    for name in ("role-id","secret-id","credential-metadata.json"):
        (d/name).write_text("synthetic-test-only")
    def resolve(self,logical,context):
        assert self.role_id_path==d/"role-id" and self.secret_id_path==d/"secret-id"
        assert logical=="it_glue.readwrite"
        assert self._mappings=={logical:base.PROVIDERS["it_glue"]["secret_path"]}
        assert self._allowed_fields=={logical:frozenset({"api_key"})}
        return {"api_key":"synthetic-test-only"}
    monkeypatch.setattr(OpenBaoSecretResolver,"resolve",resolve)
    assert lifecycle.verify("it_glue_write")["status"]=="pass"


def test_it_glue_write_deactivation_never_removes_canonical_key_or_read_identity(monkeypatch,tmp_path):
    from tools import provider_secret_lifecycle as lifecycle
    from tools import provider_secret_provision as base
    for profile in ("it_glue","it_glue_write"):
        spec=dict(base.PROVIDERS[profile],credential_dir=tmp_path/profile)
        monkeypatch.setitem(base.PROVIDERS,profile,spec)
        d=spec["credential_dir"];d.mkdir()
        for name,value in (("role-id","fake-role"),("secret-id","fake-secret"),
                           ("credential-metadata.json",'{"secret_id_accessor":"synthetic-accessor"}')):
            (d/name).write_text(value)
    calls=[]
    monkeypatch.setattr(base,"api_request",lambda address,path,**kw:calls.append((path,kw["method"])) or {})
    monkeypatch.setattr(lifecycle,"_revoke_secret_id_accessor",lambda **kw:None)
    result=lifecycle.deactivate(address=base.DEFAULT_ADDRESS,admin_token="test",provider="it_glue_write")
    assert result["provider_secret_destroyed"] is False and result["kv_history_preserved"]
    assert calls==[("auth/approle/role/"+base.PROVIDERS["it_glue_write"]["role_name"],"DELETE")]
    assert (tmp_path/"it_glue"/"role-id").is_file()
    assert (tmp_path/"it_glue"/"secret-id").is_file()
    assert not (tmp_path/"it_glue_write").exists()
