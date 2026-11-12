from pathlib import Path

from connectors.core.openbao_secrets import DEFAULT_FIELDS, DEFAULT_MAPPINGS
from tools.provider_secret_provision import PROVIDERS


def test_constant_contact_secret_mapping_is_isolated_and_least_privileged():
    spec = PROVIDERS["constant_contact"]
    assert spec["logical_name"] == "constant_contact.oauth_client"
    assert spec["secret_path"] == DEFAULT_MAPPINGS["constant_contact.oauth_client"]
    assert spec["fields"] == ("client_id", "client_secret", "token_key_b64")
    assert DEFAULT_FIELDS["constant_contact.oauth_client"] == frozenset(spec["fields"])
    assert spec["credential_dir"] == Path(
        "/var/lib/jason/runtime-secrets/openbao/constant-contact-oauth-client-approle"
    )
    assert spec["environment"] == "production"
    assert spec["credential_file_mode"] == 0o640


import base64

import pytest

from tools import constant_contact_oauth as oauth_cli
from tools import provider_secret_provision as provision


def _synthetic_fields() -> dict[str, str]:
    return {
        "client_id": "synthetic-client-id",
        "client_secret": "synthetic-client-secret",
        "token_key_b64": base64.b64encode(b"k" * 32).decode("ascii"),
    }


def test_constant_contact_create_only_cas_zero_and_no_extra_paths(monkeypatch):
    calls = []
    def no_network(_address, path, **kwargs):
        calls.append((path, kwargs))
        return {}
    monkeypatch.setattr(provision, "api_request", no_network)
    provision.write_provider_secret(
        address="http://localhost",
        admin_token="synthetic-not-a-real-token",
        provider="constant_contact",
        values=_synthetic_fields(),
    )
    assert len(calls) == 1
    path, kwargs = calls[0]
    assert path == "secret/data/connectors/constant-contact/production/oauth-client"
    assert kwargs["method"] == "POST"
    assert kwargs["allow_empty"] is True
    assert kwargs["payload"]["options"] == {"cas": 0}
    assert kwargs["payload"]["data"] == _synthetic_fields()


@pytest.mark.parametrize("bad_value", ["not-base64!", base64.b64encode(b"short").decode()])
def test_constant_contact_key_invalid_fails_before_write(monkeypatch, bad_value):
    monkeypatch.setattr(
        provision, "api_request",
        lambda *a, **kw: pytest.fail("must never contact OpenBao with bad key"),
    )
    fields = _synthetic_fields()
    fields["token_key_b64"] = bad_value
    with pytest.raises(provision.ProvisionError, match="token key"):
        provision.write_provider_secret(
            address="http://localhost",
            admin_token="synthetic",
            provider="constant_contact",
            values=fields,
        )


def test_constant_contact_cas_conflict_fails_closed(monkeypatch):
    def reject_write(_address, path, **kwargs):
        assert path.endswith("/constant-contact/production/oauth-client")
        assert kwargs["payload"]["options"] == {"cas": 0}
        raise provision.ProvisionError("OpenBao provisioning request failed with HTTP 400.")
    monkeypatch.setattr(provision, "api_request", reject_write)
    with pytest.raises(provision.ProvisionError, match="HTTP 400"):
        provision.write_provider_secret(
            address="http://localhost", admin_token="synthetic",
            provider="constant_contact", values=_synthetic_fields(),
        )


def test_non_constant_contact_write_contract_unchanged(monkeypatch):
    received = []
    monkeypatch.setattr(
        provision, "api_request",
        lambda addr, path, **kwargs: received.append(kwargs["payload"]) or {},
    )
    provision.write_provider_secret(
        address="http://localhost",
        admin_token="synthetic",
        provider="quickbooks_production",
        values=_synthetic_fields(),
    )
    assert len(received) == 1
    assert "options" not in received[0]


def test_constant_contact_blank_encryption_key_generated_without_exposure(
    monkeypatch, capsys
):
    replies = iter(["synthetic-client", "synthetic-secret", ""])
    monkeypatch.setattr(provision.getpass, "getpass", lambda _: next(replies))
    monkeypatch.setattr(provision.os, "urandom", lambda n: b"u" * n)
    fields = provision.collect_values("constant_contact")
    assert fields["client_id"] == "synthetic-client"
    assert fields["client_secret"] == "synthetic-secret"
    assert base64.b64decode(fields["token_key_b64"], validate=True) == b"u" * 32
    assert fields["token_key_b64"] not in capsys.readouterr().out


def test_constant_contact_cli_uses_existing_root_provisioned_hyphenated_paths(
    monkeypatch, tmp_path, capsys
):
    captured = {}
    class FakeResolver:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        def resolve(self, *_):
            return _synthetic_fields()
    class FakeStore:
        def __init__(self, path, key):
            assert key == b"k" * 32
        def load_tokens(self):
            return None
    monkeypatch.setattr(oauth_cli, "OpenBaoSecretResolver", FakeResolver)
    monkeypatch.setattr(oauth_cli, "EncryptedOAuthStore", FakeStore)
    assert oauth_cli.main([
        "status", "--db", str(tmp_path / "oauth.sqlite3"),
        "--approle-dir", str(tmp_path),
    ]) == 0
    assert captured["role_id_path"] == tmp_path / "role-id"
    assert captured["secret_id_path"] == tmp_path / "secret-id"
    assert "CONSTANT_CONTACT_CONNECTED=FALSE" in capsys.readouterr().out
