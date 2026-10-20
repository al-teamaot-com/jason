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
# Use a rolling test clock: the original fixed October 17 time expires
# every synthetic approval once wall clock advances past the fixture.
NOW = datetime.now(timezone.utc).replace(microsecond=0)


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


HIGH_IMPACT_REVIEW = {
    "owner_exact_sha_required": True,
    "signed_teams_identity_required": True,
    "independent_ccc_required": True,
    "protected_release_gates_unchanged": True,
}


def reviewed_policy_file(tmp_path, **updates):
    reviewed = {
        "schema_version": "2.0",
        "policy_mode": "owner_reviewed",
        "allowed_risk_profiles": ["normal", "production_control_core"],
        "ttl_seconds": 600,
        "high_impact_review": HIGH_IMPACT_REVIEW,
    }
    reviewed.update(updates)
    return policy_file(tmp_path, **reviewed)


def mark_release_high_impact(root, risk="production_control_core"):
    p = root / "records" / f"{RELEASE}.json"
    record = json.loads(p.read_text(encoding="utf-8"))
    record["risk_profile"] = risk
    record["release_manifest"]["risk_profile"] = risk
    record["release_manifest"]["changed_files"] = ["tools/release_manager_host_runner.py"]
    p.write_text(json.dumps(record), encoding="utf-8")
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


@pytest.mark.parametrize("overrides", [
    {"schema_version": "1.0"},
    {"policy_mode": "owner_only_pilot"},
    {"owner_identity_ids": ["person-other"]},
    {"allowed_risk_profiles": ["production_control_core"]},
    {"allowed_risk_profiles": ["normal", "unknown"]},
    {"allowed_risk_profiles": ["normal", "normal"]},
    {"ttl_seconds": 1800},
    {"ttl_seconds": True},
    {"high_impact_review": {"owner_exact_sha_required": True}},
    {"high_impact_review": {**HIGH_IMPACT_REVIEW, "independent_ccc_required": False}},
    {"high_impact_review": {**HIGH_IMPACT_REVIEW, "new_authority": True}},
])
def test_explicit_high_risk_policy_requires_reviewed_v2_scope(tmp_path, overrides):
    with pytest.raises((PermissionError, ValueError)):
        read_mobile_release_policy(reviewed_policy_file(tmp_path, **overrides))


def test_explicit_v2_protected_release_is_exact_signed_owner_only_request(tmp_path):
    policy_path = reviewed_policy_file(tmp_path)
    policy = read_mobile_release_policy(policy_path)
    assert policy.schema_version == "2.0"
    assert policy.allowed_risk_profiles == frozenset({"normal", "production_control_core"})
    root, _ = release_record(tmp_path)
    mark_release_high_impact(root)
    verified = read_eligible_release(root, RELEASE, policy)
    assert verified.risk_profile == "production_control_core"
    request = create_mobile_release_request(verified, policy, now=NOW)
    request.validate()
    assert request.authorized_approver_ids == ("person-al",)
    assert request.requested_by == "svc-jason-release-manager"
    assert request.requested_mode == "release:" + SHA
    assert request.metadata["owner_policy_sha256"] == policy.policy_sha256
    assert "production_control_core" in repr(request.presentation.facts)
    assert SHA in repr(request.presentation.facts)
    assert ROLLBACK in repr(request.presentation.facts)
    assert request.expires_at == NOW + timedelta(seconds=600)
    assert read_mobile_release_policy(policy_path).policy_sha256 == policy.policy_sha256


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
    def __init__(self, *, aid, decision, now, selections=None):
        self.parsed = SimpleNamespace(
            approval_submit=SimpleNamespace(
                approval_id=aid, decision=decision, channel_response_id="teams-response-1",
                selections=selections or {},
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


def flow_fixture(tmp_path, *, decision="approve", reviewed=False):
    path = reviewed_policy_file(tmp_path) if reviewed else policy_file(tmp_path)
    root, record = release_record(tmp_path)
    if reviewed:
        mark_release_high_impact(root)
    policy = read_mobile_release_policy(path)
    req = create_mobile_release_request(read_eligible_release(root, RELEASE, policy), policy, now=NOW)
    repo = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    service = ApprovalRequestService(repo, SimpleOwnerAuthority())
    service.create(req, now=NOW)
    bindings = SimpleNamespace(find=lambda **k: SimpleNamespace(status="active", jason_identity_id="person-al"))
    identities = SimpleNamespace(get=lambda k: SimpleNamespace(status="active", identity_id=k, organization_id="aot"))
    flow = MobileReleaseApprovalFlow(service, repo, path, root, bindings, identities,
                                     FakeVerifier(
                                         aid=req.approval_id, decision=decision, now=NOW,
                                         selections=({"card_challenge": req.metadata["card_instance_challenge"]}
                                                     if reviewed else {}),
                                     ),
                                     MobileReleaseSignedEvidenceStore(tmp_path / "requests.sqlite3"),
                                     required_policy_version="2.0" if reviewed else "1.0")
    return flow, req, repo, record


def click(flow, request, decision="approve", **updates):
    args = {
        "approval_id": request.approval_id, "decision": decision,
        "microsoft_tenant_id": "tenant-a", "microsoft_object_id": "object-al",
        "conversation_id": "owner-chat", "channel_response_id": "teams-response-1",
        "decided_at": NOW, "signed_envelope": {"signed": True},
        "selections": dict(flow.signed_verifier.parsed.approval_submit.selections),
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


def test_reviewed_v2_card_challenges_unique_for_each_issued_request(tmp_path):
    policy_path = reviewed_policy_file(tmp_path)
    policy = read_mobile_release_policy(policy_path)
    root, _ = release_record(tmp_path)
    mark_release_high_impact(root)
    evidence = read_eligible_release(root, RELEASE, policy)
    a = create_mobile_release_request(evidence, policy, now=NOW)
    b = create_mobile_release_request(evidence, policy, now=NOW)
    assert a.approval_id != b.approval_id
    assert a.metadata["card_instance_challenge"] != b.metadata["card_instance_challenge"]
    from hashlib import sha256
    for request in (a, b):
        proof = request.metadata["card_instance_challenge"]
        assert request.metadata["card_instance_challenge_sha256"] == sha256(
            proof.encode("ascii")
        ).hexdigest()
        roundtrip = create_mobile_release_request(
            evidence, policy, now=NOW, card_challenge=proof,
        )
        assert roundtrip.metadata == request.metadata
    with pytest.raises(PermissionError):
        create_mobile_release_request(evidence, policy, now=NOW, card_challenge="bad")


def test_reviewed_v2_owner_click_records_one_receipt_without_execution(tmp_path):
    flow, req, repo, record = flow_fixture(tmp_path, reviewed=True)
    before = record.read_bytes()
    result = click(flow, req)
    assert result["approval_status"] == "approved"
    assert result["executed"] is False
    assert repo.accepted_decision(req.approval_id).decided_by == "person-al"
    assert repo.accepted_decision(req.approval_id).channel == "microsoft_teams"
    assert record.read_bytes() == before
    with pytest.raises(PermissionError):
        click(flow, req)


def test_reviewed_v2_changed_policy_cannot_consume_pending_click(tmp_path):
    flow, req, repo, record = flow_fixture(tmp_path, reviewed=True)
    flow.policy_path.write_text(flow.policy_path.read_text().replace(
        '"ttl_seconds": 600', '"ttl_seconds": 900'
    ), encoding="utf-8")
    with pytest.raises(PermissionError, match="policy"):
        click(flow, req)
    assert repo.accepted_decision(req.approval_id) is None


def test_reviewed_v2_mismatch_with_active_pilot_mode_denies_signed_vote(tmp_path):
    flow, req, repo, record = flow_fixture(tmp_path, reviewed=True)
    flow.required_policy_version = "1.0"
    with pytest.raises(PermissionError, match="reviewed runtime mode"):
        click(flow, req)
    assert repo.get(req.approval_id).status == ApprovalRequestStatus.PENDING


def test_reviewed_v2_wrong_actor_denied_even_when_risk_allowed(tmp_path):
    flow, req, repo, record = flow_fixture(tmp_path, reviewed=True)
    flow.bindings.find = lambda **kw: SimpleNamespace(status="active", jason_identity_id="person-other")
    with pytest.raises(PermissionError, match="authorized owner"):
        click(flow, req)
    assert repo.accepted_decision(req.approval_id) is None


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


def test_reviewed_v2_issuer_requires_matching_runtime_activation(tmp_path):
    from jason_runtime.mobile_release_approval import (
        MobileReleaseApprovalMaintenance, MobileReleaseOwnerAuthority,
    )
    policy_path = reviewed_policy_file(tmp_path)
    root, _ = release_record(tmp_path)
    mark_release_high_impact(root)
    make_eligible_main_offer(root, policy_path)
    repo = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    approvals = ApprovalRequestService(repo, MobileReleaseOwnerAuthority(policy_path))

    class Sender:
        sent = []
        def send(self, request):
            self.sent.append(request)
            return ("accepted:verified-transport-only",)

    sender = Sender()
    legacy = MobileReleaseApprovalMaintenance(
        enabled=True, policy_path=policy_path, state_root=root, requests=repo,
        approvals=approvals, sender=sender, clock=lambda: NOW,
    )
    with pytest.raises(PermissionError, match="reviewed runtime activation"):
        legacy.tick()
    assert repo.list_all() == () and sender.sent == []

    activated = MobileReleaseApprovalMaintenance(
        enabled=True, policy_path=policy_path, state_root=root, requests=repo,
        approvals=approvals, sender=sender, clock=lambda: NOW,
        required_policy_version="2.0",
    )
    assert activated.tick() is True
    assert len(sender.sent) == 1
    sent = sender.sent[0]
    assert "production_control_core" in repr(sent.presentation.facts)
    assert repo.get(sent.approval_id).status == ApprovalRequestStatus.PENDING
    assert activated.tick() is False


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


def _write_owner_release_hold(root, *, state="held", released_at=None):
    from jason_runtime.owner_release_approval_containment import HOLD_FILENAME
    started_at = NOW - timedelta(minutes=5)
    item = {
        "schema_version": "1.0",
        "capability": "release.production.approve",
        "state": state,
        "hold_id": "P0-1553",
        "hold_started_at": started_at.isoformat(),
    }
    if released_at is not None:
        item["released_at"] = released_at.isoformat()
    hold_path = root / HOLD_FILENAME
    hold_path.write_text(json.dumps(item), encoding="utf-8")
    hold_path.chmod(0o600)
    return hold_path


@pytest.mark.parametrize("decision", ["approve", "deny"])
def test_p0_active_owner_containment_blocks_both_signed_decisions(tmp_path, decision):
    flow, req, repo, record = flow_fixture(tmp_path, decision=decision)
    _write_owner_release_hold(flow.state_root)
    before = record.read_bytes()
    with pytest.raises(PermissionError, match="owner_release_approval_hold_active"):
        click(flow, req, decision=decision)
    assert repo.get(req.approval_id).status == ApprovalRequestStatus.PENDING
    assert repo.accepted_decision(req.approval_id) is None
    assert record.read_bytes() == before


def test_p0_released_hold_refuses_signed_callback_from_old_request(tmp_path):
    flow, req, repo, record = flow_fixture(tmp_path)
    _write_owner_release_hold(
        flow.state_root,
        state="released",
        released_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(PermissionError, match="pre_hold_request_revoked"):
        click(flow, req)
    assert repo.get(req.approval_id).status == ApprovalRequestStatus.PENDING


def test_p0_invalid_hold_policy_fails_closed_before_signed_evidence(tmp_path):
    from jason_runtime.owner_release_approval_containment import HOLD_FILENAME
    flow, req, repo, record = flow_fixture(tmp_path)
    p = flow.state_root / HOLD_FILENAME
    p.write_text('{"unexpected":"bypass"}')
    p.chmod(0o600)
    with pytest.raises(PermissionError, match="policy_invalid"):
        click(flow, req)
    assert repo.accepted_decision(req.approval_id) is None


def test_p0_issuer_never_sends_or_creates_approval_while_hold_is_active(tmp_path):
    from jason_runtime.mobile_release_approval import (
        MobileReleaseApprovalMaintenance, MobileReleaseOwnerAuthority,
    )
    policy_path = policy_file(tmp_path)
    root, _ = release_record(tmp_path)
    make_eligible_main_offer(root, policy_path)
    _write_owner_release_hold(root)
    repo = SQLiteApprovalRequestRepository(tmp_path / "held-approvals.sqlite3")
    approval_service = ApprovalRequestService(
        repo, MobileReleaseOwnerAuthority(policy_path)
    )
    class Sender:
        def send(self, request):
            pytest.fail("owner mobile Teams approval card cannot be issued during hold")
    worker = MobileReleaseApprovalMaintenance(
        enabled=True, policy_path=policy_path,
        state_root=root, requests=repo, approvals=approval_service,
        sender=Sender(), interval_seconds=60, clock=lambda: NOW,
    )
    assert worker.tick() is False
    assert repo.list_all() == ()


def test_reviewed_v2_can_request_ccc_only_after_exact_owner_release_grant(tmp_path):
    policy = read_mobile_release_policy(reviewed_policy_file(tmp_path))
    root, p = release_record(tmp_path)
    mark_release_high_impact(root)
    record = json.loads(p.read_text())
    record["owner_approval"] = {
        "approved": True, "candidate_sha": SHA,
        "source": "explicit_owner_instruction",
    }
    p.write_text(json.dumps(record))
    with pytest.raises(PermissionError, match="exact CCC-only card"):
        read_eligible_release(root, RELEASE, policy)
    review = read_eligible_release(
        root, RELEASE, policy, allow_existing_owner_approval=True,
    )
    assert review.review_only is True
    request = create_mobile_release_request(review, policy, now=NOW)
    request.validate()
    assert request.metadata["review_only"] is True
    assert "CCC Material Review" in request.presentation.title
    assert SHA in repr(request.presentation.facts)
    assert ROLLBACK in repr(request.presentation.facts)
    assert request.metadata["card_instance_challenge"]


def test_v1_can_never_issue_owner_reviewed_ccc_only_card(tmp_path):
    policy = read_mobile_release_policy(policy_file(tmp_path))
    root, p = release_record(tmp_path)
    record = json.loads(p.read_text())
    record["owner_approval"] = {"approved": True, "candidate_sha": SHA}
    p.write_text(json.dumps(record))
    with pytest.raises(PermissionError, match="exact CCC-only card"):
        read_eligible_release(root, RELEASE, policy, allow_existing_owner_approval=True)
