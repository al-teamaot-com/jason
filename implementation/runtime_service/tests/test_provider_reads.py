from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from orchestrator.integration_broker import IntegrationBroker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_TICKET_SEARCH,
)
from jason_runtime.composition import RuntimeSettings, build_runtime_application
from jason_runtime.provider_reads import (
    build_provider_read_invoker,
    register_provider_read_invokers,
    register_provider_read_runtime_foundation,
    scope_runtime_provider_secret_resolvers,
)


class _Secrets:
    def resolve(self, logical_name, context):
        raise AssertionError("source composition tests must not resolve provider secrets")


class _Transport:
    def request(self, **kwargs):
        raise AssertionError("source composition tests must not call provider APIs")


class _Audit:
    def record(self, event_type, context, details):
        return None


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
                        "key_id": "provider-read-test",
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


def _runtime_settings(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(
        authority_db=tmp_path / "authority.sqlite3",
        bindings_db=tmp_path / "bindings.sqlite3",
        continuation_db=tmp_path / "continuation.sqlite3",
        replay_db=tmp_path / "replay.sqlite3",
        security_audit_db=tmp_path / "security.sqlite3",
        orchestration_events_db=tmp_path / "events.sqlite3",
        trusted_keys_registry=_trusted_registry(tmp_path),
        openbao_url="http://openbao.invalid:8200",
        openbao_role_id_path=tmp_path / "role_id",
        openbao_secret_id_path=tmp_path / "secret_id",
        ollama_url="http://ollama.invalid:11434",
        ollama_model="local-test",
        allowed_machine_identities=frozenset({"svc-openclaw-gateway"}),
    )


def test_provider_read_runtime_registers_broker_manifests_without_becoming_operational() -> None:
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    broker = IntegrationBroker(capabilities=capabilities, providers=providers)

    register_provider_read_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        integration_broker=broker,
        now=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    assert providers.get(IT_GLUE_PROVIDER).provider_id == IT_GLUE_PROVIDER
    assert providers.get(AUTOTASK_PROVIDER).provider_id == AUTOTASK_PROVIDER
    assert not broker.get(IT_GLUE_PROVIDER).operational
    assert not broker.get(AUTOTASK_PROVIDER).operational


def test_provider_read_runtime_registers_canonical_invokers_without_io() -> None:
    provider_invoker = build_provider_read_invoker(
        secrets=_Secrets(),
        transport=_Transport(),
        audit=_Audit(),
    )
    invokers = CapabilityInvokerRegistry()

    register_provider_read_invokers(invokers=invokers, invoker=provider_invoker)

    registered = set(invokers.registered_capabilities())
    assert DOCUMENTATION_ORGANIZATION_SEARCH in registered
    assert SERVICE_TICKET_SEARCH in registered


def test_runtime_openbao_identity_is_split_by_provider_without_reading_credentials() -> None:
    resolver = OpenBaoSecretResolver(
        base_url="http://openbao.invalid:8200",
        role_id_path=Path("/run/jason-secrets/openbao/role_id"),
        secret_id_path=Path("/run/jason-secrets/openbao/secret_id"),
    )

    it_glue, autotask = scope_runtime_provider_secret_resolvers(resolver)

    assert isinstance(it_glue, OpenBaoSecretResolver)
    assert isinstance(autotask, OpenBaoSecretResolver)
    assert it_glue is not resolver
    assert autotask is not resolver
    assert it_glue.role_id_path == Path(
        "/run/jason-secrets/openbao/it-glue/role_id"
    )
    assert it_glue.secret_id_path == Path(
        "/run/jason-secrets/openbao/it-glue/secret_id"
    )
    assert autotask.role_id_path == Path(
        "/run/jason-secrets/openbao/autotask/role_id"
    )
    assert autotask.secret_id_path == Path(
        "/run/jason-secrets/openbao/autotask/secret_id"
    )
    assert resolver.role_id_path == Path("/run/jason-secrets/openbao/role_id")


def test_acceptance_openbao_identity_is_not_rewritten() -> None:
    resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/autotask-read-approle/role-id"
        ),
        secret_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/autotask-read-approle/secret-id"
        ),
    )

    it_glue, autotask = scope_runtime_provider_secret_resolvers(resolver)

    assert it_glue is resolver
    assert autotask is resolver


def test_explicit_provider_resolvers_do_not_require_shared_secret_identity() -> None:
    build_provider_read_invoker(
        it_glue_secrets=_Secrets(),
        autotask_secrets=_Secrets(),
        transport=_Transport(),
        audit=_Audit(),
    )


def test_provider_read_invoker_requires_both_provider_identities_without_compatibility() -> None:
    with pytest.raises(ValueError, match="IT Glue and Autotask secret resolvers"):
        build_provider_read_invoker(
            it_glue_secrets=_Secrets(),
            transport=_Transport(),
            audit=_Audit(),
        )


def test_full_runtime_composes_provider_reads_but_keeps_them_out_of_active_surface(
    tmp_path: Path,
) -> None:
    application = build_runtime_application(_runtime_settings(tmp_path))

    documentation = application.capabilities.get_current(
        capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
        allow_pilot=True,
    )
    service = application.capabilities.get_current(
        capability_name=SERVICE_TICKET_SEARCH,
        allow_pilot=True,
    )

    assert documentation.lifecycle_status is CapabilityLifecycle.PILOT
    assert service.lifecycle_status is CapabilityLifecycle.PILOT

    with pytest.raises(LookupError):
        application.capabilities.get_current(
            capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
        )

    registered = set(
        application.governed_orchestrator._invoker.registered_capabilities()
    )
    assert DOCUMENTATION_ORGANIZATION_SEARCH in registered
    assert SERVICE_TICKET_SEARCH in registered


def test_runtime_composition_wires_provider_reads_without_a_second_ai_brain() -> None:
    root = Path("implementation/runtime_service/src/jason_runtime")
    composition = (root / "composition.py").read_text(encoding="utf-8")
    provider_reads = (root / "provider_reads.py").read_text(encoding="utf-8")

    assert "register_provider_read_runtime_foundation(" in composition
    assert "build_provider_read_invoker(" in composition
    assert "register_provider_read_invokers(" in composition

    assert "OpenAI" not in provider_reads
    assert "Ollama" not in provider_reads
    assert "model" not in provider_reads.casefold()
    assert "it_glue.readonly" not in composition
    assert "autotask.readonly" not in composition
