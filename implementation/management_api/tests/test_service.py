from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace

import pytest

from management_api.service import (
    ManagementApiService,
    ManagementReadContext,
    ManagementReadDenied,
)


class Value(str, Enum):
    ACTIVE = "active"
    LOW = "low"
    EXTERNAL = "external_connector"
    HEALTHY = "healthy"
    APPROVED = "approved"


class AllowAot:
    def may_read(self, *, context, resource):
        return context.organization_id == "aot" and bool(resource)


class FakeCapabilities:
    def list_all(self):
        return (
            SimpleNamespace(
                capability_name="endpoint.device.search",
                display_name="Endpoint Device Search",
                version="0.1",
                permitted_execution_modes=frozenset({"deterministic"}),
                lifecycle_status=Value.ACTIVE,
                risk_level=Value.LOW,
                approval=SimpleNamespace(required=False),
                owner_service="orchestrator",
                architectural_capability_ids=frozenset({"JAC-001"}),
            ),
        )


class FakeProviders:
    def list_all(self):
        return (
            SimpleNamespace(
                display_name="Datto RMM",
                provider_id="datto-rmm",
                provider_type=Value.EXTERNAL,
                lifecycle_status=Value.ACTIVE,
                health_status=Value.HEALTHY,
                approval_status=Value.APPROVED,
                capabilities=frozenset({"endpoint.device.search"}),
                execution_modes=frozenset({"deterministic"}),
                metadata={"credential_reference": "openbao:datto-rmm"},
            ),
        )


class FakeEvents:
    def list_by_execution(self, execution_id):
        return self.list_recent(limit=100)

    def list_by_correlation(self, correlation_id):
        return self.list_recent(limit=100)

    def list_recent(self, limit=100):
        del limit
        now = datetime.now(timezone.utc)
        return (
            SimpleNamespace(
                event_id="event-aot",
                event_type="resolution.allowed",
                execution_id="exec-1",
                correlation_id="corr-1",
                organization_id="aot",
                principal_id="person-al",
                capability_name="endpoint.device.search",
                stage="resolution",
                payload={"outcome": "allowed"},
                occurred_at=now,
            ),
            SimpleNamespace(
                event_id="event-other",
                event_type="resolution.allowed",
                execution_id="exec-2",
                correlation_id="corr-2",
                organization_id="other-client",
                principal_id="person-other",
                capability_name="endpoint.device.search",
                stage="resolution",
                payload={"outcome": "allowed"},
                occurred_at=now,
            ),
        )


def build_service():
    return ManagementApiService(
        capabilities=FakeCapabilities(),
        providers=FakeProviders(),
        events=FakeEvents(),
        authorizer=AllowAot(),
    )


def test_capability_and_provider_projection_is_read_only_metadata():
    service = build_service()
    context = ManagementReadContext(principal_id="person-al", organization_id="aot")

    capability = service.list_capabilities(context)[0]
    provider = service.list_providers(context)[0]

    assert capability["name"] == "endpoint.device.search"
    assert capability["approval_required"] is False
    assert provider["provider_id"] == "datto-rmm"
    assert provider["credential_reference_present"] is True
    assert "credential_reference" not in provider


def test_audit_projection_enforces_organization_isolation():
    service = build_service()
    context = ManagementReadContext(principal_id="person-al", organization_id="aot")

    events = service.search_audit_events(context)

    assert [event["event_id"] for event in events] == ["event-aot"]


def test_management_read_fails_closed_for_unauthorized_organization():
    service = build_service()
    context = ManagementReadContext(principal_id="person-x", organization_id="not-aot")

    with pytest.raises(ManagementReadDenied):
        service.system_health(context)
