"""Mutation boundary source tests: actual governed reads, existing Owner gateway.

No production composition, service launch, provider write or approval change.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from autonomous_remediation.playbook_autonomy_approval import (
    PlaybookAutonomyApproval, SQLitePlaybookAutonomyApprovalStore,
)
from autonomous_remediation.playbook_document import validate_playbook_document
from autonomous_remediation.playbook_ticket_evidence import MANAGED_NOTE_TITLE
from jason_runtime.autonomy_worker_runtime import GovernedAutonomyActionPort
from jason_runtime.json_governed_mutation_bridge import (
    JsonGovernedMutationBoundaryError, SQLiteJsonMutationCheckpoint,
    build_json_mutation_plan, dispatch_json_mutation_once,
    reconcile_indeterminate_json_mutation,
)

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs/playbooks/json/migration/candidates/unsupported_triage_human_review.v1.json"
NOW = datetime.now(timezone.utc)
CLIENT = "company-777"
TARGET = "143305"
NOTE = "Verified Jason investigation note, synthetic fixture."


class CurrentGovernedReadPort:
    client_id = CLIENT

    def __init__(self):
        self.calls = []
        self.updated = False
        self.mismatch = False
        self.missing_note = False

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "service.ticket.search":
            assert arguments == {"resource_id": 143305, "page_size": 2}
            return {"status": "succeeded", "evidence": {"data": {
                "items": [snapshot()]}}}
        if capability == "service.ticket.notes.search":
            assert arguments == {"ticket_id": 143305}
            return {"status": "succeeded", "evidence": {"data": {
                "items": [] if self.missing_note else [{
                    "title": MANAGED_NOTE_TITLE, "description": NOTE,
                }]}}}
        if capability == "service.ticket.read":
            assert arguments == {"ticket_id": 143305}
            return {"status": "succeeded", "evidence": {"data": {
                "items": [{
                    "id": 143305, "companyID": "other-client" if self.mismatch else CLIENT,
                    "queueID": 29682833 if self.updated else 101,
                    "status": 37 if self.updated else "In Progress",
                }]}}}
        raise AssertionError("unexpected read capability")


def snapshot():
    return {"id": 143305, "companyID": CLIENT, "queueID": 101,
            "status": "In Progress", "assignedResourceID": 9001}


class SyntheticActionRequestFactory:
    def __init__(self):
        self.calls = []

    def build(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            approval_id="synthetic-exact", correlation_id="synthetic",
            capability_name=kwargs["capability_name"],
            arguments=kwargs["arguments"],
            standing_policy=kwargs["standing_policy"],
        )


class SyntheticAutotask:
    def __init__(self, reads, *, success=True, verification=True, commit=True):
        self.reads = reads
        self.calls = []
        self.success = success
        self.verification = verification
        self.commit = commit

    def execute(self, request):
        self.calls.append(request)
        assert request.capability_name == "service.ticket.update"
        assert request.arguments == {
            "payload": {"id": 143305, "queueID": "Help Desk I",
                        "status": "Human Review"}
        }
        assert request.standing_policy.playbook_version == "1.0.0-migration.1"
        if self.commit:
            self.reads.updated = True
        return SimpleNamespace(
            status=SimpleNamespace(value="succeeded" if self.success else "denied"),
            error_code=None if self.success else "SYNTHETIC_PROVIDER_FAILURE",
            reason_codes=(),
            output={"data": {"jasonVerification": {
                "readbackVerified": self.verification,
                "verifiedFields": ["queueID", "status"] if self.verification else [],
            }}},
        )


def build(tmp_path, *, approved=True, version="1.0.0-migration.1",
          success=True, verification=True, commit=True):
    document = validate_playbook_document(json.loads(DOC.read_text()))
    facts = {
        "client_id": CLIENT, "target_id": TARGET,
        "ticket_id": 143305, "unique_current_ticket": True,
        "company_identity_exact": True, "owned_by_jason": True,
        "current_queue": "Jason", "current_status": "In Progress",
        "source_snapshot_unchanged": True, "review_reason": "needs_human_review",
        "internal_note_readback_verified": True,
        "exact_handoff_promotion_verified": True,
    }
    plan = build_json_mutation_plan(
        document=document, run_id="synthetic-run", client_id=CLIENT,
        target_id=TARGET, step_id="handoff_update", trusted_facts=facts,
        expected_verified_fields=frozenset({"queueID", "status"}),
    )
    promotions = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    if approved:
        promotions.put(PlaybookAutonomyApproval(
            approval_id="synthetic-owner-never-production",
            playbook_id=document.playbook_id, playbook_version=version,
            policy_id=f"playbook-autonomy:{document.playbook_id}",
            allowed_capabilities=(plan.capability,),
            approved_by="synthetic-only",
            approved_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=20),
        ))
    reads = CurrentGovernedReadPort()
    orchestrator = SyntheticAutotask(
        reads, success=success, verification=verification, commit=commit)
    factory = SyntheticActionRequestFactory()
    gateway = GovernedAutonomyActionPort(
        request_factory=factory, orchestrator=orchestrator,
        promotion_store=promotions)
    checkpoint = SQLiteJsonMutationCheckpoint(tmp_path / "claim.sqlite3")
    return document, plan, promotions, reads, orchestrator, factory, gateway, checkpoint


def execute(parts, **overrides):
    document, plan, _, reads, _, _, gateway, checkpoint = parts
    params = dict(
        plan=plan, document=document, checkpoint=checkpoint,
        actions=gateway, read_port=reads, source_snapshot=snapshot(),
        expected_note_body=NOTE, source_status_label="In Progress",
        review_reason="needs_human_review", owned_by_jason=True,
    )
    params.update(overrides)
    return dispatch_json_mutation_once(**params)


def close(parts):
    parts[-1].close()
    parts[2].close()


def test_verified_action_requires_both_existing_gateway_and_fresh_provider_readback(tmp_path):
    p = build(tmp_path)
    try:
        result = execute(p)
        assert result["state"] == "verified"
        assert result["provider_call_attempted"]
        assert [name for name, _ in p[3].calls] == [
            "service.ticket.search", "service.ticket.notes.search", "service.ticket.read"]
        assert len(p[4].calls) == len(p[5].calls) == 1
        assert len(p[-1].read(p[1])["evidence_sha256"]) == 64
        second = execute(p)
        assert second["provider_call_attempted"] is False
        assert len(p[4].calls) == 1
    finally:
        close(p)


@pytest.mark.parametrize("approved,version", [
    (False, "1.0.0-migration.1"), (True, "1.0.0")
])
def test_missing_or_wrong_owner_promotion_never_calls_provider(tmp_path, approved, version):
    p = build(tmp_path, approved=approved, version=version)
    try:
        first = execute(p)
        assert first["state"] == "indeterminate"
        assert len(p[4].calls) == 0
        assert execute(p)["provider_call_attempted"] is False
    finally:
        close(p)


@pytest.mark.parametrize("success,verification,commit", [
    (False, True, True), (True, False, True), (True, True, False)
])
def test_failure_missing_receipt_or_missing_fresh_readback_is_never_retried(
    tmp_path, success, verification, commit,
):
    p = build(tmp_path, success=success, verification=verification, commit=commit)
    try:
        first = execute(p)
        assert first["state"] == "indeterminate"
        assert len(p[4].calls) == 1
        assert execute(p)["provider_call_attempted"] is False
        assert len(p[4].calls) == 1
    finally:
        close(p)


@pytest.mark.parametrize("variation", [
    "client", "target", "snapshot", "note", "owner", "status",
])
def test_current_read_preflight_rejects_mismatch_before_claim_or_action(tmp_path, variation):
    p = build(tmp_path)
    try:
        params = {}
        if variation == "client":
            p[3].client_id = "unbound-client"
        elif variation == "target":
            params["plan"] = replace(p[1], target_id="143306")
        elif variation == "snapshot":
            params["source_snapshot"] = {**snapshot(), "companyID": "other"}
        elif variation == "note":
            p[3].missing_note = True
        elif variation == "owner":
            params["owned_by_jason"] = False
        elif variation == "status":
            params["source_status_label"] = "Complete"
        with pytest.raises(JsonGovernedMutationBoundaryError):
            execute(p, **params)
        assert p[-1].read(p[1]) is None
        assert not p[4].calls
    finally:
        close(p)


def test_durable_preclaimed_indeterminate_write_cannot_replay_after_restart(tmp_path):
    p = build(tmp_path)
    try:
        assert p[-1].claim(p[1])[1] is True
        p[-1].close()
        reopened = SQLiteJsonMutationCheckpoint(tmp_path / "claim.sqlite3")
        try:
            result = execute(p, checkpoint=reopened)
            assert result["state"] == "indeterminate"
            assert not result["provider_call_attempted"]
            assert p[4].calls == []
        finally:
            reopened.close()
    finally:
        p[2].close()


def test_reconciliation_performs_new_authoritative_read_no_passed_boolean(tmp_path):
    p = build(tmp_path)
    try:
        p[-1].claim(p[1])
        assert reconcile_indeterminate_json_mutation(
            plan=p[1], document=p[0], checkpoint=p[-1],
            read_port=p[3]) is False
        p[3].updated = True
        assert reconcile_indeterminate_json_mutation(
            plan=p[1], document=p[0], checkpoint=p[-1],
            read_port=p[3]) is True
        assert p[-1].read(p[1])["state"] == "verified"
        assert not p[4].calls
    finally:
        close(p)


def test_wrong_tenant_provider_readback_does_not_reconcile(tmp_path):
    p = build(tmp_path)
    try:
        p[-1].claim(p[1])
        p[3].updated = True
        p[3].mismatch = True
        assert reconcile_indeterminate_json_mutation(
            plan=p[1], document=p[0], checkpoint=p[-1],
            read_port=p[3]) is False
        assert p[-1].read(p[1])["state"] == "indeterminate"
    finally:
        close(p)


def test_changed_intent_under_same_run_is_denied(tmp_path):
    p = build(tmp_path)
    try:
        p[-1].claim(p[1])
        changed = replace(p[1], intent_fingerprint="0" * 64)
        with pytest.raises(JsonGovernedMutationBoundaryError, match="INTENT_SCOPE_CHANGED"):
            p[-1].claim(changed)
    finally:
        close(p)


@pytest.mark.parametrize("tamper", [
    {"arguments": {"payload": {"id": 143306, "queueID": "Help Desk I", "status": "Human Review"}}},
    {"arguments": {"payload": {"id": 143305, "queueID": "Help Desk I", "status": "Complete"}}},
    {"client_id": "other-company"},
    {"intent_fingerprint": "0" * 64},
])
def test_mutated_plan_cannot_dispatch_or_reconcile(tmp_path, tamper):
    p = build(tmp_path)
    try:
        changed = replace(p[1], **tamper)
        with pytest.raises(JsonGovernedMutationBoundaryError):
            execute(p, plan=changed)
        assert not p[4].calls and p[-1].read(p[1]) is None
        with pytest.raises(JsonGovernedMutationBoundaryError):
            reconcile_indeterminate_json_mutation(
                plan=changed, document=p[0], checkpoint=p[-1], read_port=p[3])
    finally:
        close(p)
