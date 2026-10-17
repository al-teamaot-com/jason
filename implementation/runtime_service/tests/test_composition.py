from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from jason_runtime.composition import RuntimeSettings, build_runtime_application
from jason_runtime.procurement_web_read import (
    CAPABILITY as PROCUREMENT_WEB_PRODUCT_READ,
    PROFILE as PROCUREMENT_WEB_READ_PROFILE,
    PROFILE_ENV as PROCUREMENT_WEB_READ_PROFILE_ENV,
)
from jason_runtime.dnsfilter_mcp_mutation import (
    DNSFILTER_MCP_MUTATION_ENABLED_ENV,
    DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_CAPABILITY,
    DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_PROFILE,
    DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_CAPABILITY,
    DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_PROFILE,
    DNSFILTER_MCP_MUTATION_PROFILE_ENV,
    DNSFILTER_MCP_MUTATION_PROVIDER,
)
from orchestrator.backup_capability_catalog import (
    BACKUP_BACKUPIQ_ALERT_SEARCH,
    BACKUP_ENDPOINT_ASSET_READ,
    BACKUP_ENDPOINT_ASSET_SEARCH,
    BACKUP_ENDPOINT_BACKUP_SEARCH,
)
from orchestrator.dnsfilter_mcp_mutation_capability_catalog import (
    DNSFILTER_MCP_MUTATION_TOOLS,
)
from orchestrator.dns_protection_capability_catalog import (
    DNS_INVESTIGATION_ANOMALY_SEARCH,
    DNS_INVESTIGATION_BLOCKED_TRAFFIC_SEARCH,
    DNS_INVESTIGATION_QUERY_EXPLAIN,
    DNS_INVESTIGATION_QUERY_SEARCH,
    DNS_PROTECTION_AGENT_COUNTS_READ,
    DNS_PROTECTION_AGENT_DUPLICATE_SEARCH,
    DNS_PROTECTION_AGENT_SEARCH,
    DNS_PROTECTION_AGENT_STALE_SEARCH,
    DNS_PROTECTION_AGENT_VERSION_REPORT,
    DNS_PROTECTION_ORGANIZATION_READ,
    DNS_PROTECTION_POLICY_CATEGORY_SEARCH,
    DNS_PROTECTION_POLICY_SEARCH,
    DNS_PROTECTION_SITE_DRIFT_SEARCH,
    DNS_PROTECTION_SITE_SEARCH,
    DNS_PROTECTION_UNBLOCK_REQUEST_COUNT_READ,
    DNS_PROTECTION_UNBLOCK_REQUEST_SEARCH,
)
from orchestrator.conversation_action_intent import GovernedActionConversationIntentResolver
from orchestrator.conversation_resource_intent import (
    GovernedResourceConversationIntentResolver,
    MetadataFirstResourceInquiryInterpreter,
)
from orchestrator.governed_semantic_coverage import GovernedSemanticCoverageIntentResolver
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
from orchestrator.system_registry_resource import (
    SYSTEM_REGISTRY_READ,
    SYSTEM_REGISTRY_SEARCH,
    SYSTEM_REGISTRY_TRACE,
)


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
        playbook_owner_approval_policy=tmp_path / "playbook-owner-pilot.json",
        bindings_db=tmp_path / "bindings.sqlite3",
        continuation_db=tmp_path / "continuation.sqlite3",
        replay_db=tmp_path / "replay.sqlite3",
        governed_execution_db=tmp_path / "governed-execution.sqlite3",
        security_audit_db=tmp_path / "security.sqlite3",
        orchestration_events_db=tmp_path / "events.sqlite3",
        model_usage_db=tmp_path / "model-usage.sqlite3",
        resolution_memory_db=tmp_path / "resolution-memory.sqlite3",
        dynamic_conversation_context_db=tmp_path / "dynamic-conversation-context.sqlite3",
        dnsfilter_mcp_oauth_db=tmp_path / "dnsfilter-mcp-oauth.sqlite3",
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
    assert (tmp_path / "continuation.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "replay.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "security.sqlite3").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "events.sqlite3").stat().st_mode & 0o777 == 0o600



def test_playbook_approve_callback_remains_live_when_maintenance_is_split(tmp_path, monkeypatch):
    """The HTTP process must consume genuine owner clicks, not spawn card producers."""
    from datetime import datetime, timedelta, timezone

    from autonomous_remediation.playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore
    from autonomous_remediation.playbook_autonomy_review import PlaybookAutonomyReviewService
    from connectors.src.jason_connectors.approval_requests import (
        ApprovalRequestService,
        SQLiteApprovalRequestRepository,
    )
    from jason_runtime.maintenance_process import http_runtime_settings
    from jason_runtime.playbook_autonomy_review import (
        OwnerOnlyPlaybookAutonomyAuthority,
        PlaybookAutonomyApprovalInteractionFlow,
        PlaybookAutonomyReviewMaintenance,
    )
    from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
    from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore

    monkeypatch.setattr(
        "jason_runtime.composition.approval_owner_identities",
        lambda: frozenset(),  # Reproduce production's empty shared owner list.
    )
    pilot = tmp_path / "playbook-owner-pilot.json"
    pilot.write_text(json.dumps({
        "schema_version": "1.0",
        "organization_id": "aot",
        "capability": "playbook.autonomy.promote",
        "policy_mode": "owner_only_test",
        "owner_identity_ids": ["person-owner"],
        "allowed_requested_modes": ["promote:demo@1.0.0"],
    }), encoding="utf-8")
    pilot.chmod(0o600)
    registry = tmp_path / "demo-registry.json"
    registry.write_text(json.dumps({
        "schema_version": 2,
        "playbooks": [{
            "id": "demo", "name": "Demonstration", "version": "1.0.0",
            "lifecycle": "production", "enabled": True,
            "source": "tests/no-provider.md", "review_status": "test_only",
            "autonomy": {
                "activation": "autonomous",
                "required_gates": ["identity"],
                "allowed_capabilities": ["service.ticket.note.create"],
                "policy_id": "playbook-autonomy:demo",
            },
        }],
    }), encoding="utf-8")
    settings = replace(
        _settings(tmp_path),
        autonomy_review_enabled=True,
        autonomy_playbook_registry=registry,
        autonomy_review_db=tmp_path / "review.sqlite3",
        autonomy_promotion_db=tmp_path / "promotions.sqlite3",
        autonomy_review_audit_path=tmp_path / "review-audit.jsonl",
    )
    SQLiteMicrosoftIdentityBindingStore(settings.bindings_db).put(
        MicrosoftIdentityBinding(
            microsoft_tenant_id="tenant-a",
            microsoft_object_id="object-owner",
            jason_identity_id="person-owner",
        )
    )
    serving = http_runtime_settings(settings)
    assert serving.autonomy_review_enabled is False
    assert serving.playbook_approval_ingress_enabled is True

    application = build_runtime_application(serving)
    dispatcher = application.ingress.ingress.approval_flow
    assert isinstance(dispatcher.fallback, PlaybookAutonomyApprovalInteractionFlow)
    assert dispatcher.fallback.approval_service.authority.owner_identity_ids == frozenset({"person-owner"})
    assert dispatcher.fallback.approval_service.authority.allowed_requested_modes == frozenset({"promote:demo@1.0.0"})
    assert not dispatcher.fallback.approval_service.authority.can_approve(
        approver_identity_id="person-owner",
        organization_id="aot", client_id=None,
        capability="playbook.autonomy.promote",
        requested_mode="promote:unrelated@1.0.0",
    )
    assert not any(
        isinstance(item, PlaybookAutonomyReviewMaintenance)
        for item in application.maintenance.services
    ), "HTTP must never duplicate the scheduled approval request generator"

    requests = SQLiteApprovalRequestRepository(settings.autonomy_review_db)
    promotions = SQLitePlaybookAutonomyApprovalStore(settings.autonomy_promotion_db)
    # Seed an independently preapproved scope; the pilot is explicitly
    # forbidden to create new operational promotion authority.
    from autonomous_remediation.playbook_autonomy_scope import registered_autonomy_scope
    exact = registered_autonomy_scope(registry_path=registry, playbook_id="demo")
    existing = promotions.new(
        playbook_id=exact.playbook_id,
        playbook_version=exact.playbook_version,
        policy_id=exact.policy_id,
        allowed_capabilities=exact.allowed_capabilities,
        approved_by="person-owner",
    )
    promotions.put(existing)
    review = PlaybookAutonomyReviewService(
        registry_path=registry,
        promotion_store=promotions,
        owner_identity_ids=frozenset({"person-owner"}),
        audit_path=settings.autonomy_review_audit_path,
    )
    service = ApprovalRequestService(
        repository=requests,
        authority=OwnerOnlyPlaybookAutonomyAuthority({"person-owner"}),
    )
    now = datetime.now(timezone.utc)
    request = review.build_request(
        playbook_id="demo", requested_by="svc-test-runner",
        now=now, ttl=timedelta(minutes=5),
    )
    service.create(request, now=now)

    # The exact HTTP composition, using its independent SQLite connection,
    # rejects an unbound Microsoft actor while leaving the request pending.
    import pytest
    with pytest.raises(PermissionError, match="not bound"):
        dispatcher.handle(
            approval_id=request.approval_id,
            decision="approve",
            microsoft_tenant_id="tenant-a",
            microsoft_object_id="object-unbound",
            conversation_id="test-conversation",
            channel_response_id="unbound-message",
            decided_at=now + timedelta(seconds=20),
        )
    assert requests.get(request.approval_id).status.value == "pending"

    accepted = dispatcher.handle(
        approval_id=request.approval_id,
        decision="approve",
        microsoft_tenant_id="tenant-a",
        microsoft_object_id="object-owner",
        conversation_id="test-conversation",
        channel_response_id="owner-message",
        decided_at=now + timedelta(seconds=30),
    )
    assert accepted["status"] == "completed"
    receipt = requests.accepted_decision(request.approval_id)
    assert receipt is not None
    assert receipt.status == "approved"
    assert receipt.decided_by == "person-owner"
    assert receipt.channel_response_id == "owner-message"
    # The only resulting promotion is in the isolated test database. No
    # provider action, production authority or real Teams message was touched.
    assert len(promotions.list_all()) == 1
    assert promotions.list_all()[0].approval_id == existing.approval_id

    # A second button delivery cannot reuse the already-consumed approval.
    with pytest.raises(ValueError, match="no longer pending"):
        dispatcher.handle(
            approval_id=request.approval_id,
            decision="approve",
            microsoft_tenant_id="tenant-a",
            microsoft_object_id="object-owner",
            conversation_id="test-conversation",
            channel_response_id="replayed-owner-message",
            decided_at=now + timedelta(seconds=40),
        )
    assert len(promotions.list_all()) == 1
    assert requests.accepted_decision(request.approval_id).channel_response_id == "owner-message"


def test_procurement_web_profile_seeds_exact_aot_observe_authority(tmp_path, monkeypatch):
    monkeypatch.setenv(PROCUREMENT_WEB_READ_PROFILE_ENV, PROCUREMENT_WEB_READ_PROFILE)
    application = build_runtime_application(_settings(tmp_path))

    grants = application.identity_authority.grants.list_for_subject("organization:aot")
    matching = [grant for grant in grants if grant.capability == PROCUREMENT_WEB_PRODUCT_READ]

    assert len(matching) == 1
    assert matching[0].organization_id == "aot"
    assert matching[0].client_id is None
    assert matching[0].permission.value == "observe"
    assert matching[0].approval_required is False
    assert matching[0].status == "active"


def test_backup_capabilities_are_composed_but_provider_stays_gated_by_default(tmp_path):
    application = build_runtime_application(_settings(tmp_path))
    for capability_name in (
        BACKUP_ENDPOINT_ASSET_SEARCH,
        BACKUP_ENDPOINT_ASSET_READ,
        BACKUP_ENDPOINT_BACKUP_SEARCH,
        BACKUP_BACKUPIQ_ALERT_SEARCH,
    ):
        capability = application.capabilities.get_current(
            capability_name=capability_name,
        )
        assert capability is not None
        assert capability.metadata["read_only"] == "true"
        assert capability.metadata["client_partition_enforced_by"] == (
            "validated_backup_net_customer_boundary"
        )


def test_dnsfilter_capabilities_are_composed_active_but_providers_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("jason_runtime.datto_component_execution.configured_pilot", lambda: None)
    application = build_runtime_application(_settings(tmp_path))
    expected = {
        DNS_PROTECTION_ORGANIZATION_READ,
        DNS_PROTECTION_SITE_SEARCH,
        DNS_PROTECTION_POLICY_SEARCH,
        DNS_PROTECTION_AGENT_SEARCH,
        DNS_PROTECTION_AGENT_COUNTS_READ,
        DNS_INVESTIGATION_QUERY_SEARCH,
        DNS_INVESTIGATION_QUERY_EXPLAIN,
        DNS_INVESTIGATION_BLOCKED_TRAFFIC_SEARCH,
        DNS_INVESTIGATION_ANOMALY_SEARCH,
        DNS_PROTECTION_AGENT_STALE_SEARCH,
        DNS_PROTECTION_AGENT_VERSION_REPORT,
        DNS_PROTECTION_AGENT_DUPLICATE_SEARCH,
        DNS_PROTECTION_SITE_DRIFT_SEARCH,
        DNS_PROTECTION_POLICY_CATEGORY_SEARCH,
        DNS_PROTECTION_UNBLOCK_REQUEST_SEARCH,
        DNS_PROTECTION_UNBLOCK_REQUEST_COUNT_READ,
    }
    for capability_name in expected:
        capability = application.capabilities.get_current(
            capability_name=capability_name,
            allow_pilot=True,
        )
        assert capability is not None
        assert capability.lifecycle_status.value == "active"
        assert capability.metadata["read_only"] == "true"
        assert capability.metadata["client_partition_enforced_by"] == (
            "validated_dnsfilter_organization_boundary"
        )


def test_dnsfilter_runtime_enablement_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr("jason_runtime.datto_component_execution.configured_pilot", lambda: None)
    settings = replace(
        _settings(tmp_path),
        dnsfilter_enabled=True,
        dnsfilter_openbao_role_id_path=tmp_path / "dnsfilter-role",
        dnsfilter_openbao_secret_id_path=tmp_path / "dnsfilter-secret",
        dnsfilter_mcp_enabled=True,
        dnsfilter_mcp_oauth_db=tmp_path / "dnsfilter-mcp-oauth.sqlite3",
    )
    settings.validate()
    application = build_runtime_application(settings)
    assert application.capabilities.get_current(
        capability_name=DNS_PROTECTION_AGENT_SEARCH,
        allow_pilot=True,
    ) is not None
    assert application.capabilities.get_current(
        capability_name=DNS_INVESTIGATION_QUERY_SEARCH,
        allow_pilot=True,
    ) is not None


def test_production_conversation_planning_is_resource_first_and_metadata_driven(tmp_path):
    application = build_runtime_application(_settings(tmp_path))

    governed_ingress = application.ingress.ingress
    resolvers = governed_ingress.flow.intent_resolver.resolvers

    assert len(resolvers) == 2
    assert isinstance(resolvers[0], GovernedSemanticCoverageIntentResolver)
    resource_resolver = resolvers[0].delegate
    assert isinstance(resource_resolver, GovernedResourceConversationIntentResolver)
    assert isinstance(resource_resolver.planner.reasoner, MetadataResourceCapabilityReasoner)
    deterministic_interpreter = resource_resolver.interpreter
    assert isinstance(deterministic_interpreter, MetadataFirstResourceInquiryInterpreter)
    language_reasoner = deterministic_interpreter.fallback.reasoner
    assert set(language_reasoner.resource_types) >= {
        "endpoint",
        "endpoint_alert",
        "endpoint_audit",
        "endpoint_software",
        "alert",
        "management_site",
        "system_registry",
    }
    assert set(language_reasoner.selector_keys) >= {
        "entity_type",
        "environment",
        "from",
        "hostname",
        "lifecycle",
        "name",
        "priority",
        "query",
        "registry_id",
        "resource_id",
        "serial_number",
        "severity",
        "site",
        "site_id",
        "software",
        "status",
        "to",
    }
    assert language_reasoner.fact_hints
    assert "last logged in user" in language_reasoner.fact_hints
    assert "operating system" in language_reasoner.fact_hints
    assert "bitlocker status" in language_reasoner.fact_hints
    invokers = governed_ingress.flow.orchestrator._invoker.registered_capabilities()
    assert SYSTEM_REGISTRY_SEARCH in invokers
    assert SYSTEM_REGISTRY_READ in invokers
    assert SYSTEM_REGISTRY_TRACE in invokers
    assert isinstance(resolvers[1], GovernedActionConversationIntentResolver)


def test_runtime_settings_fail_closed_without_local_reasoning_model(tmp_path):
    settings = RuntimeSettings(
        authority_db=tmp_path / "authority.sqlite3",
        bindings_db=tmp_path / "bindings.sqlite3",
        continuation_db=tmp_path / "continuation.sqlite3",
        replay_db=tmp_path / "replay.sqlite3",
        governed_execution_db=tmp_path / "governed-execution.sqlite3",
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


def test_production_authority_uses_governed_provider_read_matcher(tmp_path):
    from orchestrator.provider_read_authority import GovernedProviderReadAuthorityMatcher

    application = build_runtime_application(_settings(tmp_path))

    authority = application.ingress.ingress.flow.request_factory.authority

    assert isinstance(authority.capability_matcher, GovernedProviderReadAuthorityMatcher)


def test_production_composition_selects_conversation_experience_when_enabled(tmp_path):
    settings = _settings(tmp_path)
    settings = RuntimeSettings(
        **{
            field.name: getattr(settings, field.name)
            for field in __import__("dataclasses").fields(settings)
            if field.name not in {
                "dynamic_conversation_enabled",
                "conversation_experience_enabled",
            }
        },
        dynamic_conversation_enabled=True,
        conversation_experience_enabled=True,
    )

    application = build_runtime_application(settings)

    flow = application.ingress.ingress.flow

    assert type(flow).__name__ == "TeamsConversationExperienceFlow"


def test_runtime_composition_declares_integration_broker_foundation():
    from pathlib import Path

    source = Path(
        "implementation/runtime_service/src/jason_runtime/composition.py"
    ).read_text()

    assert "IntegrationBroker(" in source
    assert "build_datto_rmm_manifest()" in source
    assert "integration_broker.register(" in source


def test_runtime_composition_registers_endpoint_security_reads_only(tmp_path):
    from orchestrator.resource_capability_catalog import (
        ENDPOINT_SECURITY_DETECTION_READ,
        ENDPOINT_SECURITY_DETECTION_SEARCH,
        ENDPOINT_SECURITY_POLICY_READ,
        ENDPOINT_SECURITY_QUARANTINE_SEARCH,
        ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
        ENDPOINT_SECURITY_STATUS_READ,
    )

    application = build_runtime_application(_settings(tmp_path))
    invokers = (
        application.ingress.ingress.flow.orchestrator._invoker.registered_capabilities()
    )
    expected = {
        ENDPOINT_SECURITY_STATUS_READ,
        ENDPOINT_SECURITY_DETECTION_SEARCH,
        ENDPOINT_SECURITY_DETECTION_READ,
        ENDPOINT_SECURITY_POLICY_READ,
        ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
        ENDPOINT_SECURITY_QUARANTINE_SEARCH,
    }

    assert expected <= set(invokers)
    assert "endpoint.security.scan.execute" not in invokers
    assert "endpoint.security.isolate" not in invokers
    assert "endpoint.security.quarantine.execute" not in invokers

def test_backup_net_full_access_profile_is_an_explicit_runtime_setting(tmp_path):
    settings = replace(
        _settings(tmp_path),
        backup_net_enabled=True,
        backup_net_access_profile="full_access",
        backup_net_full_access_openbao_role_id_path=tmp_path / "backup-full-role",
        backup_net_full_access_openbao_secret_id_path=tmp_path / "backup-full-secret",
    )
    settings.validate()
    application = build_runtime_application(settings)
    assert application.capabilities.get_current(
        capability_name=BACKUP_ENDPOINT_ASSET_SEARCH
    ) is not None


def test_backup_net_unknown_access_profile_fails_closed(tmp_path):
    settings = replace(_settings(tmp_path), backup_net_access_profile="unmanaged")
    try:
        settings.validate()
    except ValueError as error:
        assert "JASON_BACKUP_NET_ACCESS_PROFILE" in str(error)
    else:
        raise AssertionError("unknown Backup.net access profile must fail closed")

def test_dnsfilter_mutation_surface_is_dormant_in_default_composition(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(DNSFILTER_MCP_MUTATION_PROFILE_ENV, raising=False)
    monkeypatch.delenv(DNSFILTER_MCP_MUTATION_ENABLED_ENV, raising=False)
    monkeypatch.setattr(
        "jason_runtime.datto_component_execution.configured_pilot",
        lambda: None,
    )
    application = build_runtime_application(_settings(tmp_path))

    for capability_name in DNSFILTER_MCP_MUTATION_TOOLS:
        definition = application.capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        assert definition.lifecycle_status.value == "building"

    provider = (
        application.governed_orchestrator
        ._resolution
        ._providers
        .get(DNSFILTER_MCP_MUTATION_PROVIDER)
    )
    assert provider.lifecycle_status.value == "planned"
    assert provider.health_status.value == "unknown"
    assert provider.approval_status.value == "blocked"

    registered = set(
        application.governed_orchestrator
        ._invoker
        .registered_capabilities()
    )
    assert set(DNSFILTER_MCP_MUTATION_TOOLS).isdisjoint(registered)


def test_dnsfilter_policy_create_acceptance_profile_registers_only_create(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        DNSFILTER_MCP_MUTATION_PROFILE_ENV,
        DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_PROFILE,
    )
    monkeypatch.setenv(DNSFILTER_MCP_MUTATION_ENABLED_ENV, "true")
    monkeypatch.setattr(
        "jason_runtime.datto_component_execution.configured_pilot",
        lambda: None,
    )
    application = build_runtime_application(_settings(tmp_path))

    for capability_name in DNSFILTER_MCP_MUTATION_TOOLS:
        definition = application.capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        expected = (
            "active"
            if capability_name
            == DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_CAPABILITY
            else "building"
        )
        assert definition.lifecycle_status.value == expected

    provider = (
        application.governed_orchestrator
        ._resolution
        ._providers
        .get(DNSFILTER_MCP_MUTATION_PROVIDER)
    )
    assert provider.lifecycle_status.value == "available"
    assert provider.health_status.value == "healthy"
    assert provider.approval_status.value == "approved"

    registered = set(
        application.governed_orchestrator
        ._invoker
        .registered_capabilities()
    )
    active_mutations = set(DNSFILTER_MCP_MUTATION_TOOLS).intersection(
        registered
    )
    assert active_mutations == {
        DNSFILTER_MCP_MUTATION_POLICY_CREATE_ACCEPTANCE_CAPABILITY
    }


def test_dnsfilter_policy_delete_acceptance_profile_registers_only_delete(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        DNSFILTER_MCP_MUTATION_PROFILE_ENV,
        DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_PROFILE,
    )
    monkeypatch.setenv(DNSFILTER_MCP_MUTATION_ENABLED_ENV, "true")
    monkeypatch.setattr(
        "jason_runtime.datto_component_execution.configured_pilot",
        lambda: None,
    )
    application = build_runtime_application(_settings(tmp_path))

    for capability_name in DNSFILTER_MCP_MUTATION_TOOLS:
        definition = application.capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        expected = (
            "active"
            if capability_name
            == DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_CAPABILITY
            else "building"
        )
        assert definition.lifecycle_status.value == expected

    provider = (
        application.governed_orchestrator
        ._resolution
        ._providers
        .get(DNSFILTER_MCP_MUTATION_PROVIDER)
    )
    assert provider.lifecycle_status.value == "available"
    assert provider.health_status.value == "healthy"
    assert provider.approval_status.value == "approved"

    registered = set(
        application.governed_orchestrator
        ._invoker
        .registered_capabilities()
    )
    active_mutations = set(DNSFILTER_MCP_MUTATION_TOOLS).intersection(
        registered
    )
    assert active_mutations == {
        DNSFILTER_MCP_MUTATION_POLICY_DELETE_ACCEPTANCE_CAPABILITY
    }
