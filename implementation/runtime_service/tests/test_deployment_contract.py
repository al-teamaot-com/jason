from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_runtime_compose_has_no_host_published_port_and_preserves_network_separation():
    compose = (_repo_root() / "infrastructure/jason-runtime/compose.yaml").read_text(encoding="utf-8")

    assert "ports:" not in compose
    assert 'user: "1000:1000"' in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "name: openclaw_default" in compose
    assert "name: jason-core" in compose
    assert "name: jason-observability" in compose
    assert "/var/lib/jason/openclaw/trusted-keys:/var/lib/jason/openclaw/trusted-keys:ro" in compose


def test_runtime_compose_mounts_dedicated_read_only_ses_approle_and_non_secret_config():
    compose = (_repo_root() / "infrastructure/jason-runtime/compose.yaml").read_text(encoding="utf-8")

    assert "JASON_SES_REGION: us-east-1" in compose
    assert "JASON_SES_DEFAULT_SENDER: jason@teamaot.com" in compose
    assert "JASON_SES_OPENBAO_ROLE_ID_HOST_PATH" in compose
    assert "JASON_SES_OPENBAO_SECRET_ID_HOST_PATH" in compose
    assert "/run/jason-secrets/openbao/aws-ses/role_id:ro" in compose
    assert "/run/jason-secrets/openbao/aws-ses/secret_id:ro" in compose
    assert "AKIA" not in compose
    assert "secret_access_key" not in compose


def test_runtime_image_drops_to_host_state_owner_uid_and_uses_internal_entrypoint():
    dockerfile = (_repo_root() / "infrastructure/jason-runtime/Dockerfile").read_text(encoding="utf-8")

    assert "USER 1000:1000" in dockerfile
    assert "/app/implementation/cap-007/src" in dockerfile
    assert 'CMD ["python", "-m", "jason_runtime.main"]' in dockerfile
