"""The privileged consumer owns the displayed scope and delivery witness."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
import pytest

from test_pmv4_teams_objective_admission import case,NOW
from test_pmv4_teams_objective_store import store_case
from tools.owner_objective_teams_delivery import review
from tools.pmv4_teams_objective_admission import TeamsObjectiveDenied


def test_root_review_contains_immutable_artifacts_and_only_fixed_owner_actions(case):
    enrolled,_,_,_=case
    body=review(enrolled)
    assert body["aadObjectId"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
    assert body["tenantId"]=="f7054323-d52b-4863-8c2f-1898f0b6077c"
    card=body["card"]
    assert [a["data"]["decision"] for a in card["actions"]]==["approve","deny"]
    assert all(a["data"]["approval_id"]==enrolled["approval_id"] and
        a["data"]["card_challenge"]==enrolled["card_instance_challenge"] for a in card["actions"])
    facts=str(card["body"])
    args=enrolled["material"]["requests"][0]["arguments"]
    assert all(args[k] in facts for k in ("candidate_sha","rollback_sha","scope_sha256","manifest_sha256"))
    assert "runtime" in facts.lower() and "freeze" in facts.lower()


def fresh(store_case):
    store,staged,_,ports=store_case
    (store.root/staged["approval_id"]/"delivery.json").unlink()
    return store,staged,ports


def test_root_durable_delivery_does_not_resend_on_retry(store_case):
    store,staged,ports=fresh(store_case)
    send=Mock(return_value="real-provider-id")
    kwargs=dict(approval_id=staged["approval_id"],at=NOW,policy_digest=ports["policy_digest"],
        allowed_components=ports["allowed_components"],native_delivery=send)
    assert store.deliver(**kwargs)=="real-provider-id"
    assert store.deliver(**kwargs)=="real-provider-id"
    assert send.call_count==1


def test_unknown_send_is_not_a_new_delivery_attempt(store_case):
    store,staged,ports=fresh(store_case)
    send=Mock(side_effect=TimeoutError("lost result"))
    kwargs=dict(approval_id=staged["approval_id"],at=NOW,policy_digest=ports["policy_digest"],
        allowed_components=ports["allowed_components"],native_delivery=send)
    with pytest.raises(TimeoutError):store.deliver(**kwargs)
    with pytest.raises(TeamsObjectiveDenied,match="UNKNOWN_NO_RESEND"):store.deliver(**kwargs)
    assert send.call_count==1
    assert not (store.root/staged["approval_id"]/"delivery.json").exists()


def test_synthetic_provider_id_is_never_a_root_delivery_witness(store_case):
    store,staged,ports=fresh(store_case)
    with pytest.raises(TeamsObjectiveDenied,match="UNVERIFIED_PROVIDER"):
        store.deliver(approval_id=staged["approval_id"],at=NOW,policy_digest=ports["policy_digest"],
            allowed_components=ports["allowed_components"],native_delivery=lambda _:"accepted:fake")
    assert not (store.root/staged["approval_id"]/"delivery.json").exists()
