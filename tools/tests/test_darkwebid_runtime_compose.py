from pathlib import Path


def test_darkwebid_runtime_compose_declares_enablement_and_readonly_secret_mounts():
    text = Path("infrastructure/jason-runtime/compose.yaml").read_text(encoding="utf-8")
    assert "JASON_DARKWEBID_ENABLED" in text
    assert "JASON_DARKWEBID_OPENBAO_ROLE_ID_PATH" in text
    assert "JASON_DARKWEBID_OPENBAO_SECRET_ID_PATH" in text
    assert "/var/lib/jason/runtime-secrets/openbao/darkwebid-approle/role-id" in text
    assert "/var/lib/jason/runtime-secrets/openbao/darkwebid-approle/secret-id" in text
    assert "/run/jason-secrets/openbao/darkwebid/role_id:ro" in text
    assert "/run/jason-secrets/openbao/darkwebid/secret_id:ro" in text
