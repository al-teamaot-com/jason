"""Full preproduction acceptance through real V2 modules with mocked transports.

No production credential, endpoint change, Autotask mutation, Teams send, or
implicit deployment is part of this test.
"""
from datetime import datetime, timezone

import pytest

from jason_runtime.autonomy_worker_runtime import SQLiteOperationalWorkStore
from jason_runtime.vulscan_microsoft_public_source import (
    OfficialMicrosoftFetchedDocument, WINDOWS_RELEASE_SOURCES,
)
from jason_runtime.vulscan_microsoft_release_evidence import MicrosoftPatchEvidenceUnavailable
from jason_runtime.vulscan_owner_disposition_evidence import VerifiedPatchReviewDisposition
from jason_runtime.vulscan_policy_kb_attribution import VerifiedPolicyKBAttribution
from jason_runtime.vulscan_v2_preproduction_factory import build_vulscan_v2_shadow_workflow
from jason_runtime.vulscan_v2_site_inventory import (
    ApprovedDattoSiteScope, ApprovedDattoSiteInventory,
)

NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)
SITE = "site-verified-12"
DEVICE = "datto-device-123"
KB = "KB5127648"
LINK = "https://support.microsoft.com/help/5127648"
HISTORY = """<table><tr><th>Servicing option</th><th>Update type</th>
<th>Availability date</th><th>Build</th><th>KB article</th></tr>
<tr><td>General Availability Channel</td><td>2026-10 B</td>
<td>2026-10-13</td><td>26300.9711</td>
<td><a href="https://support.microsoft.com/help/5127648">KB5127648</a></td></tr>
</table>"""
ARTICLE = """<title>October 13, 2026 - KB5127648 Windows update</title>
<meta name="description" content="Microsoft documents security improvements.">"""


class MicrosoftTransportFixture:
    def __init__(self):
        self.calls = []

    def fetch(self, url, *, kb=None):
        self.calls.append((url, kb))
        if url == WINDOWS_RELEASE_SOURCES[0]:
            return OfficialMicrosoftFetchedDocument(HISTORY, url, url, True)
        if url == LINK and kb == KB:
            return OfficialMicrosoftFetchedDocument(ARTICLE, url, url, True)
        raise MicrosoftPatchEvidenceUnavailable("not the selected OS update")


def scoped_sites():
    return ApprovedDattoSiteInventory(
        sites=(ApprovedDattoSiteScope(SITE, "company-12", True),),
        full_scope_verified=True, source_reference="preproduction-verified-client-site-map",
    )


def build(tmp_path, *, patch_state=None, gate=None, ms_grant=None,
          review_state=None, review_source_available=True,
          policy_attribution_available=True, policy_state=None):
    patch_state = patch_state or {"installStatus": "NOT_APPROVED"}
    review_state = review_state if review_state is not None else {"disposition": "review_pending"}
    reads = []
    def governed_read(capability, args):
        reads.append((capability, args))
        if capability == "management.site.patch.search":
            return {"status": "succeeded", "evidence": {
                "collection_key": "patches",
                "items": [{"kbArticleId": "5127648", "deviceUid": DEVICE,
                           "installStatus": patch_state["installStatus"]}],
                "pageDetails": {"totalCount": 1, "nextPageUrl": None},
                "bounded": False,
            }}
        if capability == "endpoint.device.read":
            return {"status": "succeeded", "evidence": {
                "record": {"resource_id": DEVICE, "site_id": SITE,
                           "hostname": "PC-123"}}}
        if capability == "endpoint.patch.policy.search":
            return {"status": "succeeded", "evidence": {
                "items": [{"policyUid": "weekly"}],
                "pageDetails": {"totalCount": 1, "nextPageUrl": None},
                "bounded": False,
            }}
        if capability == "endpoint.patch.search":
            return {"status": "succeeded", "evidence": {
                "items": [{"kbArticleId": "5127648",
                           "installStatus": patch_state["installStatus"]}],
                "pageDetails": {"count": 12, "totalCount": 12,
                                "nextPageUrl": None},
                "exact_selector_match": True, "ambiguous": False,
                "bounded": False,
            }}
        assert False, f"unexpected read capability: {capability}"

    def policy_attribution_read(site_uid, client_id, device_uid, kb):
        return VerifiedPolicyKBAttribution(
            kb=kb, client_id=client_id, site_uid=site_uid, device_uid=device_uid,
            policy_states=(("weekly", policy_state or "NOT_APPROVED"),),
            full_scope_verified=True, observed_at=NOW,
            source_reference="verified-governed-actual-KB-policy-status",
        )

    def review_read(item):
        return VerifiedPatchReviewDisposition(
            kb=item.kb, client_id=item.client_id, policy_id=item.policy_id,
            device_uid=item.device_uid, disposition=review_state["disposition"],
            checked_at=NOW, source_reference="approved-complete-technician-decision-store",
            full_scope_verified=True,
        )
    transport = MicrosoftTransportFixture()
    store = SQLiteOperationalWorkStore(tmp_path / "v2-shadow.db")
    flow = build_vulscan_v2_shadow_workflow(
        store=store, authorized_site_inventory_read=scoped_sites,
        governed_read=governed_read,
        can_read_microsoft_public_docs=ms_grant or (lambda: True),
        governed_review_disposition_read=review_read if review_source_available else None,
        governed_policy_attribution_read=(
            policy_attribution_read if policy_attribution_available else None),
        authority_gate=gate,
        microsoft_transport=transport,
        microsoft_source_clock=lambda: NOW,
    )
    return flow, store, reads, transport


def test_real_modules_shadow_produce_day16_review_without_any_send(tmp_path):
    flow, store, reads, docs = build(tmp_path)
    result = flow.evaluate_once(now=NOW)
    assert result.mode == "shadow"
    assert result.candidate_count == 1 and result.enqueued_count == 0
    assert store.due_patch_approval_notifications(now=NOW) == ()
    assert len([x for x, _ in reads if x == "endpoint.patch.search"]) == 1
    assert (LINK, KB) in docs.calls


def test_enqueue_fails_closed_before_provider_reads_when_unpromoted(tmp_path):
    flow, store, reads, docs = build(tmp_path)
    with pytest.raises(PermissionError):
        flow.evaluate_once(now=NOW, enqueue=True)
    assert reads == [] and docs.calls == []
    assert store.due_patch_approval_notifications(now=NOW) == ()


def test_promoted_fixture_only_queues_shared_outbox_not_teams(tmp_path):
    flow, store, reads, docs = build(tmp_path, gate=lambda: True)
    result = flow.evaluate_once(now=NOW, enqueue=True)
    assert result.mode == "queued"
    assert result.enqueued_count == 1
    entries = store.due_patch_approval_notifications(now=NOW)
    assert len(entries) == 1
    assert LINK in entries[0]["arguments_json"]
    assert store.due_teams_notifications(now=NOW) == ()


def test_patch_policy_change_ends_eligibility_and_blocks_send(tmp_path):
    mutable = {"installStatus": "NOT_APPROVED"}
    flow, store, _, _ = build(tmp_path, patch_state=mutable, gate=lambda: True)
    flow.evaluate_once(now=NOW, enqueue=True)
    mutable["installStatus"] = "APPROVED_PENDING"
    assert flow.evaluate_once(now=NOW).candidate_count == 0


def test_public_microsoft_read_revocation_fails_closed(tmp_path):
    flow, store, _, _ = build(tmp_path, ms_grant=lambda: False)
    with pytest.raises(PermissionError):
        flow.evaluate_once(now=NOW)
    assert store.due_patch_approval_notifications(now=NOW) == ()


def test_no_governed_owner_decision_read_cannot_be_treated_as_no_deferral(tmp_path):
    flow, store, reads, docs = build(tmp_path, review_source_available=False)
    with pytest.raises(ValueError, match="owner disposition"):
        flow.evaluate_once(now=NOW)
    assert reads == []
    assert docs.calls == []
    assert store.due_patch_approval_notifications(now=NOW) == ()


@pytest.mark.parametrize("state", ["deferred", "declined", "superseded"])
def test_signed_owner_exception_suppresses_full_kb_notification(tmp_path, state):
    review_state = {"disposition": state}
    flow, store, reads, docs = build(tmp_path, review_state=review_state)
    result = flow.evaluate_once(now=NOW)
    assert result.mode == "shadow"
    assert result.candidate_count == 0
    assert store.due_patch_approval_notifications(now=NOW) == ()


def test_missing_kb_specific_policy_attribution_is_never_inferred_from_assigned_policy(tmp_path):
    flow, store, reads, docs = build(tmp_path, policy_attribution_available=False)
    with pytest.raises(ValueError, match="attribution source"):
        flow.evaluate_once(now=NOW)
    assert reads == [] and docs.calls == []
    assert store.due_patch_approval_notifications(now=NOW) == ()


def test_effective_not_approved_is_insufficient_if_policy_is_not_unapproved(tmp_path):
    flow, store, reads, docs = build(tmp_path, policy_state="APPROVED_PENDING")
    with pytest.raises(ValueError, match="attribution"):
        flow.evaluate_once(now=NOW)
    assert store.due_patch_approval_notifications(now=NOW) == ()
