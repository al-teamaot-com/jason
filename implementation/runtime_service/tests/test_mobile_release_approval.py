"""Owner-only mobile release pilot: policy, immutable intent and signed decision."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService, ApprovalRequestStatus, SQLiteApprovalRequestRepository,
)
from jason_runtime.mobile_release_approval import (
    CAPABILITY, MobileReleaseApprovalFlow, MobileReleaseSignedEvidenceStore, create_mobile_release_request,
    read_eligible_release, read_mobile_release_policy, digest,
)

SHA = "9adde7fd62c0ca6ce0e1c1578b75cb8751841dfa"
ROLLBACK = "71edbeabfdec2fa5dcb43022ac8fdc44a4c77334"
RELEASE = "release-" + SHA[:16]
NOW = datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc)


def policy_file(tmp_path, **updates):
    p = tmp_path / "mobile-owner.json"
    doc = {
        "schema_version": "1.0", "organization_id": "aot",
        "policy_mode": "owner_only_pilot",
        "owner_identity_ids": ["person-al"],
        "allowed_risk_profiles": ["normal"],
        "ttl_seconds": 900,
        "capability": CAPABILITY,
    }
    doc.update(updates)
    p.write_text(json.dumps(doc), encoding="utf-8")
    p.chmod(0o600)
    return p


def release_record(tmp_path, **updates):
    root = tmp_path / "release-state"
    record_dir = root / "records"
    record_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "candidate_sha": SHA, "rollback_sha": ROLLBACK,
        "policy_digest": "sha256:one",
        "desired_state_policy_digest": "sha256:two",
        "risk_profile": "normal", "change_class": "feature",
        "changed_files": ["implementation/runtime_service/mobile.py"],
        "surfaces": ["runtime", "release-manager"],
        "schema_version": "1.0",
    }
    record = {
        "release_id": RELEASE, "state": "production_eligible",
        "rollback_sha": ROLLBACK, "risk_profile": "normal",
        "description": "Fix Teams mobile release approval without allowing extra roles",
        "release_manifest": manifest,
        "release_candidate": {
            "candidate_sha": SHA,
            "artifact_digest": "sha256:a", "mcp_artifact_digest": "sha256:b",
        },
        "preproduction": {
            "acceptance_passed": True, "rollback_readiness_passed": True,
            "provider_mutations_disabled": True, "deployed_sha": SHA,
            "artifact_digest": "sha256:a", "mcp_artifact_digest": "sha256:b",
        },
        "owner_approval": {"approved": False},
    }
    record.update(updates)
    p = record_dir / f"{RELEASE}.json"
    p.write_text(json.dumps(record), encoding="utf-8")
    p.chmod(0o600)
    return root, p


def test_exact_release_request_binds_full_manifest_policy_and_preprod(tmp_path):
    policy = read_mobile_release_policy(policy_file(tmp_path))
    root, _ = release_record(tmp_path)
    evidence = read_eligible_release(root, RELEASE, policy)
    request = create_mobile_release_request(evidence, policy, now=NOW)
    request.validate()
    assert request.organization_id == "aot"
    assert request.authorized_approver_ids == ("person-al",)
    assert request.requested_by != "person-al"
    assert request.capability == CAPABILITY
    assert request.requested_mode == "release:" + SHA
    assert request.metadata["manifest_sha256"] == digest(json.loads((root / "records" / f"{RELEASE}.json").read_text())["release_manifest"])
    assert request.metadata["owner_policy_sha256"] == policy.policy_sha256
    assert request.expires_at == NOW + timedelta(seconds=900)
    assert request.presentation is not None
    assert SHA in repr(request.presentation.facts)
    assert ROLLBACK in repr(request.presentation.facts)
    assert "normal" in repr(request.presentation.facts)
    assert "Fix Teams mobile release approval" in request.presentation.title
    assert request.metadata["purpose_sha256"] == digest(evidence.purpose)


@pytest.mark.parametrize("updates", [
    {"owner_identity_ids": ["person-al", "person-lindsey"]},
    {"owner_identity_ids": ["person-other"]},
    {"allowed_risk_profiles": ["normal", "production_control_core"]},
    {"allowed_risk_profiles": ["production_control_core"]},
    {"allowed_risk_profiles": []},
    {"policy_mode": "unrestricted"},
    {"organization_id": "other"},
    {"capability": "service.ticket.update"},
    {"ttl_seconds": 99999},
    {"ttl_seconds": True},
    {"schema_version": "2.0"},
    {"extra": "unreviewed"},
])
def test_policy_rejects_broader_or_invalid_authority(tmp_path, updates):
    with pytest.raises((PermissionError, ValueError)):
        read_mobile_release_policy(policy_file(tmp_path, **updates))


def test_policy_fails_closed_on_absence_symlink_or_insecure_mode(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_mobile_release_policy(tmp_path / "missing.json")
    p = policy_file(tmp_path)
    p.chmod(0o644)
    with pytest.raises(PermissionError):
        read_mobile_release_policy(p)
    p.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(p)
    with pytest.raises(PermissionError):
        read_mobile_release_policy(link)


@pytest.mark.parametrize("change", [
    {"state": "production"},
    {"state": "preproduction"},
    {"owner_approval": {"approved": True}},
    {"risk_profile": "production_control_core"},
    {"preproduction": {"acceptance_passed": True, "rollback_readiness_passed": False,
                       "provider_mutations_disabled": True, "deployed_sha": SHA,
                       "artifact_digest": "sha256:a", "mcp_artifact_digest": "sha256:b"}},
    {"release_candidate": {"candidate_sha": ROLLBACK}},
])
def test_unsafe_release_cannot_be_offered_to_phone(tmp_path, change):
    policy = read_mobile_release_policy(policy_file(tmp_path))
    root, _ = release_record(tmp_path, **change)
    with pytest.raises(PermissionError):
        read_eligible_release(root, RELEASE, policy)


class FakeVerifier:
    def __init__(self, *, aid, decision, now):
        self.parsed = SimpleNamespace(
            approval_submit=SimpleNamespace(
                approval_id=aid, decision=decision, channel_response_id="teams-response-1",
                selections={},
            ),
            issued_at=now, microsoft_tenant_id="tenant-a", microsoft_object_id="object-al",
            conversation_id="owner-chat", documents=(),
        )

    def parse(self, token):
        assert json.loads(token) == {"signed": True}
        return "svc-openclaw-gateway", self.parsed

    def verify(self, token):
        return SimpleNamespace(tenant_id="tenant-a", object_id="object-al",
                               authentication_evidence_hash="f" * 64)


class SimpleOwnerAuthority:
    def can_approve(self, *, approver_identity_id, organization_id, client_id, capability, requested_mode):
        return (approver_identity_id == "person-al" and organization_id == "aot"
                and client_id is None and capability == CAPABILITY and requested_mode == "release:" + SHA)


def flow_fixture(tmp_path, *, decision="approve"):
    path = policy_file(tmp_path)
    root, record = release_record(tmp_path)
    policy = read_mobile_release_policy(path)
    req = create_mobile_release_request(read_eligible_release(root, RELEASE, policy), policy, now=NOW)
    repo = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    service = ApprovalRequestService(repo, SimpleOwnerAuthority())
    service.create(req, now=NOW)
    bindings = SimpleNamespace(find=lambda **k: SimpleNamespace(status="active", jason_identity_id="person-al"))
    identities = SimpleNamespace(get=lambda k: SimpleNamespace(status="active", identity_id=k, organization_id="aot"))
    flow = MobileReleaseApprovalFlow(service, repo, path, root, bindings, identities,
                                     FakeVerifier(aid=req.approval_id, decision=decision, now=NOW),
                                     MobileReleaseSignedEvidenceStore(tmp_path / "requests.sqlite3"))
    return flow, req, repo, record


def click(flow, request, decision="approve", **updates):
    args = {
        "approval_id": request.approval_id, "decision": decision,
        "microsoft_tenant_id": "tenant-a", "microsoft_object_id": "object-al",
        "conversation_id": "owner-chat", "channel_response_id": "teams-response-1",
        "decided_at": NOW, "signed_envelope": {"signed": True}, "selections": {},
    }
    args.update(updates)
    return flow.handle(**args)


def test_signed_owner_click_consumed_once_without_mutating_release_or_ccc(tmp_path):
    flow, req, repo, record = flow_fixture(tmp_path)
    before = record.read_bytes()
    result = click(flow, req)
    assert result["approval_status"] == "approved"
    assert result["executed"] is False
    assert repo.get(req.approval_id).status == ApprovalRequestStatus.APPROVED
    receipt = repo.accepted_decision(req.approval_id)
    assert receipt.decided_by == "person-al" and receipt.channel == "microsoft_teams"
    assert receipt.authentication_evidence_hash == "f" * 64
    assert record.read_bytes() == before
    assert not (tmp_path / "material-review.json").exists()
    with pytest.raises(PermissionError, match="already terminal"):
        click(flow, req)


def test_deny_is_terminal_without_release_authorization(tmp_path):
    flow, req, repo, record = flow_fixture(tmp_path, decision="deny")
    result = click(flow, req, decision="deny")
    assert result["approval_status"] == "denied"
    assert repo.get(req.approval_id).status == ApprovalRequestStatus.DENIED
    assert not json.loads(record.read_text())["owner_approval"]["approved"]


@pytest.mark.parametrize("mutation", [
    lambda doc: doc["release_manifest"]["changed_files"].append("tools/unreviewed.py"),
    lambda doc: doc["release_manifest"].__setitem__("policy_digest", "sha256:changed"),
    lambda doc: doc["release_manifest"].__setitem__("risk_profile", "production_control_core"),
    lambda doc: doc.__setitem__("owner_approval", {"approved": True}),
    lambda doc: doc.__setitem__("state", "production"),
])
def test_changed_release_or_decision_scope_fails_before_consumption(tmp_path, mutation):
    flow, req, repo, path = flow_fixture(tmp_path)
    doc = json.loads(path.read_text())
    mutation(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError):
        click(flow, req)
    assert repo.get(req.approval_id).status == ApprovalRequestStatus.PENDING
    assert repo.accepted_decision(req.approval_id) is None


def test_wrong_actor_unsigned_wrong_tenant_and_changed_policy_fail_closed(tmp_path):
    flow, req, repo, path = flow_fixture(tmp_path)
    for override in [
        {"signed_envelope": None},
        {"microsoft_tenant_id": "wrong-tenant"},
        {"microsoft_object_id": "wrong-object"},
        {"selections": {"something": "untrusted"}},
        {"channel_response_id": "unbound"},
    ]:
        with pytest.raises(PermissionError):
            click(flow, req, **override)
    assert repo.get(req.approval_id).status == ApprovalRequestStatus.PENDING
    flow.bindings.find = lambda **k: SimpleNamespace(status="active", jason_identity_id="person-other")
    flow.identities.get = lambda k: SimpleNamespace(status="active", identity_id=k, organization_id="aot")
    with pytest.raises(PermissionError, match="authorized owner"):
        click(flow, req)
    assert repo.accepted_decision(req.approval_id) is None


def make_eligible_main_offer(root, policy_file, *, published_at=NOW):
    from jason_runtime.mobile_release_approval import read_eligible_release, read_mobile_release_policy
    policy=read_mobile_release_policy(policy_file)
    evidence=read_eligible_release(root, RELEASE, policy)
    offers=root/"mobile-release-offers"
    offers.mkdir(parents=True, exist_ok=True)
    (offers/(RELEASE+".json")).write_text(json.dumps({
        "schema_version":"1.0", "release_id":RELEASE,
        "candidate_sha":SHA, "manifest_sha256":evidence.manifest_sha256,
        "protected_main_sha":SHA, "live_rollback_sha":ROLLBACK,
        "published_at":published_at.isoformat(),
    }),encoding="utf-8")


def test_owner_only_issuer_sends_exactly_one_actionable_card_no_spam(tmp_path):
    from jason_runtime.mobile_release_approval import (
        MobileReleaseApprovalMaintenance, MobileReleaseOwnerAuthority,
    )
    policy_path = policy_file(tmp_path)
    root, _ = release_record(tmp_path)
    make_eligible_main_offer(root, policy_path)
    repo = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    service = ApprovalRequestService(repo, MobileReleaseOwnerAuthority(policy_path))

    class OneOwnerSender:
        def __init__(self):
            self.sent = []

        def send(self, request):
            self.sent.append(request)
            return ("teams-message-one",)

    sender = OneOwnerSender()
    worker = MobileReleaseApprovalMaintenance(
        enabled=True, policy_path=policy_path, state_root=root,
        requests=repo, approvals=service, sender=sender,
        interval_seconds=60, clock=lambda: NOW,
    )
    assert worker.tick() is True
    assert len(sender.sent) == 1
    request = sender.sent[0]
    assert request.authorized_approver_ids == ("person-al",)
    assert request.capability == "release.production.approve"
    assert "Production + CCC" in request.presentation.title
    assert worker.tick() is False
    worker._next_due = NOW
    assert worker.tick() is False
    assert len(repo.list_all()) == 1
    assert len(sender.sent) == 1
    assert repo.get(request.approval_id).metadata["delivery_message_ids"] == "teams-message-one"


def test_owner_only_issuer_skips_unreviewed_core_release(tmp_path):
    from jason_runtime.mobile_release_approval import (
        MobileReleaseApprovalMaintenance, MobileReleaseOwnerAuthority,
    )
    policy_path = policy_file(tmp_path)
    root, _ = release_record(tmp_path, risk_profile="production_control_core")
    repo = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    service = ApprovalRequestService(repo, MobileReleaseOwnerAuthority(policy_path))
    class Sender:
        def send(self, request):
            raise AssertionError("risky release must not be sent to owner")
    worker = MobileReleaseApprovalMaintenance(
        enabled=True, policy_path=policy_path, state_root=root, requests=repo,
        approvals=service, sender=Sender(), clock=lambda: NOW,
    )
    assert worker.tick() is False
    assert repo.list_all() == ()


def test_real_card_decision_accepts_transport_delivery_evidence_after_issuance(tmp_path):
    """Reproduces the actual owner phone 403: issuer adds delivery receipt to metadata.

    The immutable approval intent remains the original request. Transport
    delivery is a bounded receipt, not a change to authority or plan.
    """
    from dataclasses import replace
    flow, request, repo, release_path = flow_fixture(tmp_path)
    before = release_path.read_bytes()
    repo.put(replace(
        request, metadata={
            **request.metadata, "delivery_message_ids": "accepted:synthetic-receipt-id",
        },
    ))
    result = click(flow, request)
    assert result["approval_status"] == "approved"
    assert result["executed"] is False
    assert repo.get(request.approval_id).status == ApprovalRequestStatus.APPROVED
    receipt = repo.accepted_decision(request.approval_id)
    assert receipt.decided_by == "person-al"
    assert receipt.channel == "microsoft_teams"
    assert release_path.read_bytes() == before


@pytest.mark.parametrize("malicious", [
    {"delivery_message_ids": ""},
    {"delivery_message_ids": []},
    {"delivery_message_ids": "x" * 1500},
    {"delivery_message_ids": "accepted:signed\nHeader: override"},
    {"unexpected_authority_grant": "true"},
    {"delivery_message_ids": "accepted:proof", "owner_policy_sha256": "f" * 64},
])
def test_mobile_request_refuses_malformed_delivery_or_changed_immutable_intent(tmp_path, malicious):
    from dataclasses import replace
    flow, request, repo, _ = flow_fixture(tmp_path)
    try:
        repo.put(replace(request, metadata={**request.metadata, **malicious}))
    except ValueError:
        # Immutable ledger rejects an invalid/altered approval scope before
        # it could ever be presented to the Teams callback.
        assert repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING
        assert repo.accepted_decision(request.approval_id) is None
        return
    with pytest.raises(PermissionError):
        click(flow, request)
    assert repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING
    assert repo.accepted_decision(request.approval_id) is None
