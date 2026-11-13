from dataclasses import dataclass, field

import pytest

from orchestrator.organization_match_service import (
    GovernedOrganizationMatchService, OrganizationMatchRequest,
)
from orchestrator.organization_matching import OrganizationRecord, VerifiedOrganizationLink


@dataclass
class Auth:
    allowed: bool = True
    calls: list = field(default_factory=list)

    def approved(self, **kwargs):
        self.calls.append(kwargs)
        return self.allowed


@dataclass
class Registry:
    links: tuple = ()
    calls: list = field(default_factory=list)

    def verified_links(self, **kwargs):
        self.calls.append(kwargs)
        return self.links


@dataclass
class Audit:
    events: list = field(default_factory=list)

    def record(self, name, details):
        self.events.append((name, details))


def req(process="reconciliation", scope="client-a", principal="owner-a"):
    return OrganizationMatchRequest(
        principal_id=principal, process_id=process, scope_id=scope,
        left_source="autotask", right_source="quickbooks",
        left_evidence_id="at-read-1", right_evidence_id="qbo-read-1",
    )


def records(scope="client-a"):
    return (
        [OrganizationRecord("autotask", "101", scope, "ABC Office", phone="7575550123")],
        [OrganizationRecord("quickbooks", "17", scope, "ABC Office", phone="7575550123")],
    )


def test_two_independently_approved_processes_reuse_same_engine():
    gate, registry, audit = Auth(), Registry(), Audit()
    service = GovernedOrganizationMatchService(gate, registry, audit)
    left, right = records()
    for process in ("billing-reconciliation", "procurement-correlation"):
        output = service.match(req(process=process), left, right)
        assert output[0].status == "probable"
    assert len(gate.calls) == 2
    assert [c["process_id"] for c in gate.calls] == [
        "billing-reconciliation", "procurement-correlation",
    ]


def test_unapproved_process_denied_before_registry_audit_or_matching():
    gate, registry, audit = Auth(False), Registry(), Audit()
    service = GovernedOrganizationMatchService(gate, registry, audit)
    with pytest.raises(PermissionError):
        service.match(req(process="unapproved"), *records())
    assert not registry.calls
    assert not audit.events


def test_approved_service_cannot_cross_client_scope():
    gate, registry, audit = Auth(), Registry(), Audit()
    service = GovernedOrganizationMatchService(gate, registry, audit)
    with pytest.raises(PermissionError):
        service.match(req(scope="client-b"), *records())
    assert len(registry.calls) == 1


def test_only_registry_supplied_approved_mapping_can_be_verified():
    gate, registry, audit = Auth(), Registry((
        VerifiedOrganizationLink("101", "17", "approved-map-1"),
    )), Audit()
    service = GovernedOrganizationMatchService(gate, registry, audit)
    result = service.match(req(), *records())[0]
    assert result.status == "verified"
    assert audit.events[-1][1]["verified"] == 1
    assert "phone" not in str(audit.events)


def test_audit_contains_no_names_or_raw_accounting_fields():
    gate, registry, audit = Auth(), Registry(), Audit()
    service = GovernedOrganizationMatchService(gate, registry, audit)
    service.match(req(), *records())
    assert all("ABC Office" not in str(event) for event in audit.events)
    assert audit.events[-1][1]["probable"] == 1


def test_missing_evidence_ids_cannot_be_used():
    with pytest.raises(ValueError):
        OrganizationMatchRequest(
            principal_id="owner", process_id="billing", scope_id="client",
            left_source="autotask", right_source="quickbooks",
            left_evidence_id="", right_evidence_id="qbo-read-1",
        )
