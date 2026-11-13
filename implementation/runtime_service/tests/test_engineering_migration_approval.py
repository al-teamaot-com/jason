from types import SimpleNamespace

import pytest

from orchestrator.contracts import OrchestrationMode
from jason_runtime.engineering_migration_approval import (
    EngineeringMigrationApprovalError,
    ExistingTeamsEngineeringMigrationIssuer,
    validate_exact_request,
)

CANDIDATE = "a" * 40
ROLLBACK = "b" * 40
SCOPE = "c" * 64
CONTINUITY = "d" * 64


def request(**changes):
    fields = dict(
        organization_id="aot", client_id=None,
        capability_name="engineering.migration.activate", capability_version="1.0",
        permission_mode="execute", requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        approval_present=False, authority_allowed=False,
        arguments={
            "candidate_sha": CANDIDATE, "rollback_sha": ROLLBACK,
            "reviewed_scope_sha256": SCOPE,
            "continuity_evidence_sha256": CONTINUITY,
            "migration_phase": "independent_engineering_lanes",
        },
    )
    fields.update(changes)
    return SimpleNamespace(**fields)


class FakeIssuer:
    def __init__(self):
        self.calls = []

    def submit_plan(self, **kwargs):
        self.calls.append(("human", kwargs))
        return {"status": "approval_requested_not_approved"}

    def submit_service_plan(self, **kwargs):
        self.calls.append(("service", kwargs))
        return {"status": "approval_requested_not_approved"}


def test_exact_scope_is_validated_but_not_approved():
    output = validate_exact_request(request())
    assert output["candidate_sha"] == CANDIDATE
    assert set(output) == {
        "candidate_sha", "rollback_sha", "reviewed_scope_sha256",
        "continuity_evidence_sha256", "migration_phase",
    }


@pytest.mark.parametrize("changes", [
    {"organization_id": "other"},
    {"client_id": "123"},
    {"capability_name": "release.production.approve"},
    {"capability_version": "2.0"},
    {"permission_mode": "observe"},
    {"approval_present": True},
    {"authority_allowed": True},
    {"arguments": {"candidate_sha": CANDIDATE}},
    {"arguments": dict(request().arguments, candidate_sha=ROLLBACK)},
    {"arguments": dict(request().arguments, reviewed_scope_sha256="not-a-hash")},
    {"arguments": dict(request().arguments, migration_phase="restart_legacy_worker")},
    {"arguments": dict(request().arguments, bypass="true")},
])
def test_unsafe_scope_is_rejected(changes):
    with pytest.raises(EngineeringMigrationApprovalError):
        validate_exact_request(request(**changes))


def test_human_issuer_uses_existing_signed_gateway_and_never_approves():
    issuer = FakeIssuer()
    service = ExistingTeamsEngineeringMigrationIssuer(issuer)
    result = service.submit_for_authenticated_requester(
        request=request(), verified_teams_identity=object(),
    )
    assert result["status"] == "approval_requested_not_approved"
    kind, kwargs = issuer.calls[0]
    assert kind == "human"
    assert kwargs["production"] is True
    assert kwargs["ttl_seconds"] == 900
    assert kwargs["requests"] == (kwargs["requests"][0],)
    assert CANDIDATE in kwargs["summary"]


def test_service_issuer_reuses_existing_signed_workload_route():
    issuer = FakeIssuer()
    service = ExistingTeamsEngineeringMigrationIssuer(issuer)
    service.submit_for_authorized_workload(
        request=request(), verified_workload_principal=object(),
    )
    assert issuer.calls[0][0] == "service"
    assert issuer.calls[0][1]["production"] is True


def test_missing_identity_never_calls_gateway():
    issuer = FakeIssuer()
    service = ExistingTeamsEngineeringMigrationIssuer(issuer)
    with pytest.raises(EngineeringMigrationApprovalError):
        service.submit_for_authenticated_requester(
            request=request(), verified_teams_identity=None,
        )
    with pytest.raises(EngineeringMigrationApprovalError):
        service.submit_for_authorized_workload(
            request=request(), verified_workload_principal=None,
        )
    assert issuer.calls == []
