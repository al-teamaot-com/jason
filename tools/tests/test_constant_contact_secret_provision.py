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
