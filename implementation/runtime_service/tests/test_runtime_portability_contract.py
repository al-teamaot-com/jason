from __future__ import annotations

from pathlib import Path

from jason_runtime import procurement_web_read
from jason_runtime import datto_component_scope


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_runtime_compose_has_no_aot_specific_runtime_defaults():
    compose = (_root() / "infrastructure/jason-runtime/compose.yaml").read_text(
        encoding="utf-8"
    )

    assert "@teamaot.com" not in compose
    assert "AOT Ver " not in compose
    assert "aot-procurement-web-v1" not in compose
    assert "/home/al/" not in compose


def test_datto_component_scope_defaults_empty_in_generic_compose():
    compose = (_root() / "infrastructure/jason-runtime/compose.yaml").read_text(
        encoding="utf-8"
    )

    assert "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_UID:-}" in compose
    assert "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME:-}" in compose
    assert "JASON_DATTO_COMPONENT_EXECUTION_COMPONENTS_JSON:-}" in compose


def test_runtime_requires_explicit_msp_sender_and_uses_canonical_kfs_secret_path():
    compose = (_root() / "infrastructure/jason-runtime/compose.yaml").read_text(
        encoding="utf-8"
    )

    assert "JASON_SES_DEFAULT_SENDER must be configured" in compose
    assert "/var/lib/jason/runtime-secrets/kfs-history/password" in compose
    assert "/run/jason-secrets/kfs-history/password:ro" in compose


def test_procurement_web_profile_name_is_provider_neutral():
    assert procurement_web_read.PROFILE == "procurement-web-v1"


def test_generic_runtime_has_no_implicit_datto_component_authority(monkeypatch):
    monkeypatch.setattr(
        datto_component_scope,
        "latest_records_by_identity",
        lambda: {},
    )
    monkeypatch.delenv(
        datto_component_scope.DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        raising=False,
    )
    monkeypatch.delenv(
        datto_component_scope.DATTO_EXECUTION_COMPONENT_UID_ENV,
        raising=False,
    )
    monkeypatch.delenv(
        datto_component_scope.DATTO_EXECUTION_COMPONENT_NAME_ENV,
        raising=False,
    )
    assert datto_component_scope.configured_datto_components() == ()


def test_runtime_source_does_not_default_ses_sender_to_aot_domain():
    source = (
        _root()
        / "implementation/runtime_service/src/jason_runtime/composition.py"
    ).read_text(encoding="utf-8")
    assert '"JASON_SES_DEFAULT_SENDER", ""' in source
    assert '"JASON_SES_DEFAULT_SENDER", "jason@teamaot.com"' not in source
