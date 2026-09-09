from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import jason_runtime.composition as composition
from jason_runtime.composition import RuntimeSettings, build_runtime_application
from orchestrator.dynamic_teams_flow_bridge import DynamicTeamsFlowBridge
from orchestrator.teams_conversation_flow import TeamsConversationFlow


def _trusted_registry(root: Path) -> Path:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    pem = public.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    der = public.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    public_path = root / "openclaw.pub.pem"
    public_path.write_bytes(pem)
    registry = root / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "key_id": "openclaw-gateway-dynamic",
                        "machine_identity": "svc-openclaw-gateway",
                        "public_key_path": str(public_path),
                        "sha256_fingerprint": hashlib.sha256(der).hexdigest(),
                        "status": "active",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return registry


def _settings(tmp_path: Path, *, dynamic: bool) -> RuntimeSettings:
    return RuntimeSettings(
        authority_db=tmp_path / "authority.sqlite3",
        bindings_db=tmp_path / "bindings.sqlite3",
        continuation_db=tmp_path / "continuation.sqlite3",
        replay_db=tmp_path / "replay.sqlite3",
        security_audit_db=tmp_path / "security.sqlite3",
        orchestration_events_db=tmp_path / "events.sqlite3",
        trusted_keys_registry=_trusted_registry(tmp_path),
        openbao_url="http://openbao:8200",
        openbao_role_id_path=tmp_path / "role_id",
        openbao_secret_id_path=tmp_path / "secret_id",
        ollama_url="http://jason-ollama:11434",
        ollama_model="local-test",
        allowed_machine_identities=frozenset({"svc-openclaw-gateway"}),
        dynamic_conversation_enabled=dynamic,
        dynamic_conversation_context_db=tmp_path / "dynamic-context.sqlite3",
        dynamic_conversation_context_ttl_seconds=1800,
    )


def test_dynamic_runtime_flag_defaults_off_and_preserves_exact_legacy_flow(tmp_path):
    settings = _settings(tmp_path, dynamic=False)
    application = build_runtime_application(settings)

    flow = application.ingress.ingress.flow
    assert isinstance(flow, TeamsConversationFlow)
    assert not isinstance(flow, DynamicTeamsFlowBridge)
    assert not (tmp_path / "dynamic-context.sqlite3").exists()


def test_dynamic_runtime_flag_selects_provider_independent_bridge(tmp_path):
    settings = _settings(tmp_path, dynamic=True)
    application = build_runtime_application(settings)

    flow = application.ingress.ingress.flow
    assert isinstance(flow, DynamicTeamsFlowBridge)
    assert flow.coordinator.capability_catalog.registry is flow.request_factory.capabilities
    assert flow.orchestrator is application.ingress.ingress.flow.orchestrator
    context_db = tmp_path / "dynamic-context.sqlite3"
    assert context_db.exists()
    assert context_db.stat().st_mode & 0o777 == 0o600


def test_dynamic_runtime_does_not_load_legacy_static_semantic_mapping_registry(
    tmp_path,
    monkeypatch,
):
    class ForbiddenLegacyMappingLoader:
        def __init__(self, *args, **kwargs):
            raise AssertionError(
                "dynamic conversation mode must not construct the legacy semantic mapping registry"
            )

    monkeypatch.setattr(
        composition,
        "JsonSemanticMappingRegistryLoader",
        ForbiddenLegacyMappingLoader,
    )

    application = build_runtime_application(_settings(tmp_path, dynamic=True))
    assert isinstance(application.ingress.ingress.flow, DynamicTeamsFlowBridge)


def test_legacy_runtime_still_loads_rollback_semantic_path(tmp_path, monkeypatch):
    observed = {"called": False}
    real_loader = composition.JsonSemanticMappingRegistryLoader

    class ObservedLoader:
        def __init__(self, *args, **kwargs):
            observed["called"] = True
            self._delegate = real_loader(*args, **kwargs)

        def load(self):
            return self._delegate.load()

    monkeypatch.setattr(composition, "JsonSemanticMappingRegistryLoader", ObservedLoader)
    application = build_runtime_application(_settings(tmp_path, dynamic=False))

    assert isinstance(application.ingress.ingress.flow, TeamsConversationFlow)
    assert observed["called"] is True


def test_dynamic_context_ttl_fails_closed_outside_bound(tmp_path):
    settings = _settings(tmp_path, dynamic=True)
    with pytest.raises(ValueError, match="ttl must be between 60 and 86400"):
        RuntimeSettings(
            authority_db=settings.authority_db,
            bindings_db=settings.bindings_db,
            continuation_db=settings.continuation_db,
            replay_db=settings.replay_db,
            security_audit_db=settings.security_audit_db,
            orchestration_events_db=settings.orchestration_events_db,
            trusted_keys_registry=settings.trusted_keys_registry,
            openbao_url=settings.openbao_url,
            openbao_role_id_path=settings.openbao_role_id_path,
            openbao_secret_id_path=settings.openbao_secret_id_path,
            ollama_url=settings.ollama_url,
            ollama_model=settings.ollama_model,
            allowed_machine_identities=settings.allowed_machine_identities,
            dynamic_conversation_enabled=True,
            dynamic_conversation_context_db=settings.dynamic_conversation_context_db,
            dynamic_conversation_context_ttl_seconds=30,
        ).validate()


def test_dynamic_runtime_settings_parse_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("JASON_OLLAMA_MODEL", "local-test")
    monkeypatch.setenv("JASON_DYNAMIC_CONVERSATION_ENABLED", "true")
    monkeypatch.setenv(
        "JASON_DYNAMIC_CONVERSATION_CONTEXT_DB",
        str(tmp_path / "context.sqlite3"),
    )
    monkeypatch.setenv("JASON_DYNAMIC_CONVERSATION_CONTEXT_TTL_SECONDS", "7200")

    settings = RuntimeSettings.from_env()

    assert settings.dynamic_conversation_enabled is True
    assert settings.dynamic_conversation_context_db == tmp_path / "context.sqlite3"
    assert settings.dynamic_conversation_context_ttl_seconds == 7200
