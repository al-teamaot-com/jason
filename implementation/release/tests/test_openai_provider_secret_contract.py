from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import provider_secret_lifecycle as lifecycle
from tools import provider_secret_provision as provision


def test_openai_semantic_intent_uses_canonical_provider_secret_lifecycle():
    spec = provision.PROVIDERS["openai"]

    assert spec["logical_name"] == "openai.semantic_intent"
    assert spec["secret_path"] == (
        "secret/data/providers/openai/production/semantic-intent"
    )
    assert spec["fields"] == ("api_key",)
    assert spec["required_fields"] == ("api_key",)
    assert spec["policy_name"] == (
        "jason-openai-semantic-intent-read"
    )
    assert spec["role_name"] == (
        "jason-openai-semantic-intent-read"
    )
    assert spec["connector_identity"] == (
        "openai-semantic-intent"
    )

    check = lifecycle._check_only("create", "openai")

    assert check["provider"] == "openai"
    assert check["logical_name"] == "openai.semantic_intent"
    assert check["runtime_authentication"] == "approle"
    assert check["kv_write_semantics"] == (
        "kv_v2_compare_and_set"
    )
    assert check["runtime_token_persisted"] is False
    assert check["network_contacted"] is False
    assert check["secret_entered"] is False


def test_openai_policy_grants_only_secret_read_and_self_revoke():
    policy = provision.provider_policy_text("openai")

    assert (
        'path "secret/data/providers/openai/production/'
        'semantic-intent"'
    ) in policy
    assert 'capabilities = ["read"]' in policy
    assert 'path "auth/token/revoke-self"' in policy

    assert "write" not in policy
    assert "delete" not in policy
    assert "sudo" not in policy
