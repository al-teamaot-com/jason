from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from jason_runtime.composition import RuntimeSettings, build_runtime_application
from orchestrator.conversation_action_intent import GovernedActionConversationIntentResolver
from orchestrator.conversation_resource_intent import GovernedResourceConversationIntentResolver
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner


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
                        "key_id": "openclaw-gateway-2",
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


def _settings(tmp_path: Path, *, ollama_model: str = "local-test") -> RuntimeSettings:
    return RuntimeSettings(
        authority_db=tmp_path / "authority.sqlite3",
        bindings_db=tmp_path / "bindings.sqlite3",
        replay_db=tmp_path / "replay.sqlite3",
        security_audit_db=tmp_path / "security.sqlite3",
        orchestration_events_db=tmp_path / "events.sqlite3",
        trusted_keys_registry=_trusted_registry(tmp_path),
        openbao_url="http://openbao:8200",
        openbao_role_id_path=tmp_path / "role_id",
        openbao_secret_id_path=tmp_path / "secret_id",
        ollama_url="http://jason-ollama:11434",
        ollama_model=ollama_model,
        allowed_machine_identities=frozenset({"svc-openclaw-gateway"}),
    )


def test_production_composition_builds_and_serves_internal_health(tmp_path):
    settings = _settings(tmp_path)

    application = build_runtime_application(settings)
    response = application.dispatch(method="GET", path="/healthz", headers={}, body=b"")

    assert response.status_code == 200
    assert response.body["authority"] == "central-orchestrator"
    assert (tmp_path / "authority.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "bindings.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "replay.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "security.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "events.sqlite3").stat().st_mode & 0o777 == 0o600


def test_production_conversation_planning_is_resource_first_and_metadata_driven(tmp_path):
    application = build_runtime_application(_settings(tmp_path))

    governed_ingress = application.ingress.ingress
    resolvers = governed_ingress.flow.intent_resolver.resolvers

    assert len(resolvers) == 2
    assert isinstance(resolvers[0], GovernedResourceConversationIntentResolver)
    assert isinstance(resolvers[0].planner.reasoner, MetadataResourceCapabilityReasoner)
    language_reasoner = resolvers[0].interpreter.reasoner
    assert language_reasoner.resource_types == ("endpoint",)
    assert language_reasoner.selector_keys == (
        "hostname",
        "name",
        "resource_id",
        "serial_number",
        "site",
    )
    assert isinstance(resolvers[1], GovernedActionConversationIntentResolver)


def test_runtime_settings_fail_closed_without_local_reasoning_model(tmp_path):
    settings = RuntimeSettings(
        authority_db=tmp_path / "authority.sqlite3",
        bindings_db=tmp_path / "bindings.sqlite3",
        replay_db=tmp_path / "replay.sqlite3",
        security_audit_db=tmp_path / "security.sqlite3",
        orchestration_events_db=tmp_path / "events.sqlite3",
        trusted_keys_registry=tmp_path / "registry.json",
        openbao_url="http://openbao:8200",
        openbao_role_id_path=tmp_path / "role_id",
        openbao_secret_id_path=tmp_path / "secret_id",
        ollama_url="http://jason-ollama:11434",
        ollama_model="",
        allowed_machine_identities=frozenset({"svc-openclaw-gateway"}),
    )

    try:
        settings.validate()
    except ValueError as error:
        assert "JASON_OLLAMA_MODEL" in str(error)
    else:
        raise AssertionError("runtime must fail closed without an explicit local model")
