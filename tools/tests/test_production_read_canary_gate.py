"""Accept only end-to-end OAuth-bound owner read receipts, not HTTP-green."""
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "implementation" / "mcp_service" / "src"))
sys.path.insert(0, str(REPO / "tools"))

import pytest

from production_read_canary_gate import (
    PROFILE_V11,
    PROFILE_V13,
    LiveReadAcceptanceError,
    begin_authenticated_read_canary,
    require_authenticated_read_canary,
    verify_authenticated_read_canary,
)
from jason_mcp.production_read_acceptance import record_authenticated_owner_read

SHA = "a" * 40
CONNECTED_AOT_PRINCIPAL = "person-entra-" + "a" * 32
ARGS = {
    "created_after": "2026-10-26T00:00:00-04:00",
    "created_before": "2026-10-27T00:00:00-04:00",
}


def _send(root: Path, session: dict, capability: str, arguments: dict, data: dict,
          *, principal=CONNECTED_AOT_PRINCIPAL, org="aot", client=None, profile=PROFILE_V11):
    return record_authenticated_owner_read(
        capability=capability, arguments=arguments,
        result={"status": "succeeded", "evidence": {"data": data}},
        principal_id=principal, organization_id=org, client_id=client,
        live_profile=profile, root=root / "functional-canary",
        now=session["issued_at"] + 1,
    )


def _start(tmp_path):
    return begin_authenticated_read_canary(
        tmp_path, candidate_sha=SHA, profile=PROFILE_V11,
        now=time.time(), ttl_seconds=360,
    )


def _full(tmp_path, session, *, include_read=True, include_project=True, include_page2=True):
    assert _send(tmp_path, session, "service.ticket.count", ARGS, {"queryCount": 72})
    ids = [{"id": x, "title": "NEVER STORE THIS CUSTOMER TITLE"} for x in range(101, 151)]
    assert _send(tmp_path, session, "service.ticket.search",
                 {**ARGS, "page_size": 50}, {"items": ids})
    if include_page2:
        assert _send(tmp_path, session, "service.ticket.search",
                     {**ARGS, "page_size": 50, "after_resource_id": 150},
                     {"items": [{"id": i} for i in range(151, 173)]})
    if include_read:
        assert _send(tmp_path, session, "service.ticket.read",
                     {"resource_id": 101},
                     {"items": [{"id": 101, "title": "NEVER STORE TICKET CONTENT"}]})
    if include_project:
        assert _send(tmp_path, session, "service.entity.search",
                     {"entity": "Projects", "page_size": 1},
                     {"items": [{"id": 222, "customerSecret": "NEVER STORE THIS"}]})


def test_full_live_owner_read_attestation_passes_with_exact_pagination(tmp_path):
    session = _start(tmp_path)
    _full(tmp_path, session)
    verdict = verify_authenticated_read_canary(tmp_path, session)
    assert {
        key: value for key, value in verdict.items()
        if key not in ("ticket_window_digest", "authenticated_principal_digest")
    } == {
        "status": "PASS", "source_revision": SHA,
        "identity": "authenticated-aot-human-jason-managed", "ticket_count": 72,
        "ticket_pages": 2, "ticket_page_sum": 72,
        "exact_id_readback": True, "generic_project_read": True,
        "customer_data_in_receipt": False,
    }
    assert len(verdict["ticket_window_digest"]) == 64
    assert len(verdict["authenticated_principal_digest"]) == 64
    assert require_authenticated_read_canary(tmp_path, session, max_wait_seconds=0) == verdict
    content = "".join(p.read_text() for p in (tmp_path / "functional-canary" / "events").glob("*.json"))
    assert "NEVER STORE" not in content
    assert "customerSecret" not in content


@pytest.mark.parametrize("excluded", [
    "include_read", "include_project", "include_page2",
])
def test_missing_one_real_read_never_finishes_owner_acceptance(tmp_path, excluded):
    session = _start(tmp_path)
    _full(tmp_path, session, **{excluded: False})
    assert verify_authenticated_read_canary(tmp_path, session) is None
    with pytest.raises(LiveReadAcceptanceError, match="not verified"):
        require_authenticated_read_canary(tmp_path, session, max_wait_seconds=0)


@pytest.mark.parametrize("actor,org,client,profile", [
    ("svc-jason", "aot", None, PROFILE_V11),
    (CONNECTED_AOT_PRINCIPAL, "wrong-org", None, PROFILE_V11),
    (CONNECTED_AOT_PRINCIPAL, "aot", "customer-14", PROFILE_V11),
    (CONNECTED_AOT_PRINCIPAL, "aot", None, "itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10"),
])
def test_service_customer_wrong_tenant_or_inactive_profile_cannot_attest(
    tmp_path, actor, org, client, profile,
):
    session = _start(tmp_path)
    assert not _send(tmp_path, session, "service.ticket.count", ARGS,
                     {"queryCount": 72}, principal=actor,
                     org=org, client=client, profile=profile)
    assert verify_authenticated_read_canary(tmp_path, session) is None


def test_denied_mcp_read_cannot_write_a_success_receipt(tmp_path):
    session = _start(tmp_path)
    recorded = record_authenticated_owner_read(
        capability="service.ticket.count", arguments=ARGS,
        result={"status": "denied", "reason_codes": ["SOURCE_REQUESTER_AUTHORIZATION_UNVERIFIED"],
                "evidence": {"data": {"queryCount": 72}}},
        principal_id=CONNECTED_AOT_PRINCIPAL, organization_id="aot", client_id=None,
        live_profile=PROFILE_V11, root=tmp_path / "functional-canary",
        now=session["issued_at"] + 1,
    )
    assert recorded is False
    assert not list((tmp_path / "functional-canary" / "events").glob("*.json"))


def test_wrong_id_readback_rejected_even_if_provider_claims_success(tmp_path):
    session = _start(tmp_path)
    _full(tmp_path, session, include_read=False)
    assert not _send(tmp_path, session, "service.ticket.read",
                     {"resource_id": 101}, {"items": [{"id": 999}]})
    assert verify_authenticated_read_canary(tmp_path, session) is None


def test_replayed_receipt_from_another_nonce_cannot_pass(tmp_path):
    first = _start(tmp_path)
    _full(tmp_path, first)
    intent = tmp_path / "functional-canary" / "intent.json"
    old = json.loads(intent.read_text())
    old["expires_at"] = old["issued_at"] - 1
    intent.write_text(json.dumps(old))
    second = _start(tmp_path)
    assert second["nonce"] != first["nonce"]
    assert verify_authenticated_read_canary(tmp_path, second) is None


def test_an_active_session_is_not_replaced_by_later_candidate(tmp_path):
    _start(tmp_path)
    with pytest.raises(LiveReadAcceptanceError, match="active"):
        _start(tmp_path)


def test_wrong_scope_cannot_be_used_to_satisfy_count(tmp_path):
    session = _start(tmp_path)
    _full(tmp_path, session)
    event_files = list((tmp_path / "functional-canary" / "events").glob("*.json"))
    for path in event_files:
        event = json.loads(path.read_text())
        if event["proof"]["kind"] == "ticket_count":
            event["proof"]["scope"]["created_before"] = "2026-10-25T00:00:00-04:00"
            path.write_text(json.dumps(event))
    assert verify_authenticated_read_canary(tmp_path, session) is None


def test_malformed_or_expired_intent_rejected(tmp_path):
    session = _start(tmp_path)
    intent = tmp_path / "functional-canary" / "intent.json"
    data = json.loads(intent.read_text())
    data["expires_at"] = data["issued_at"] + 0.1
    intent.write_text(json.dumps(data))
    assert not _send(tmp_path, session, "service.ticket.count", ARGS, {"queryCount": 72})


def test_recording_requires_existing_private_intent(tmp_path):
    assert not record_authenticated_owner_read(
        capability="service.ticket.count", arguments=ARGS,
        result={"status": "succeeded", "evidence": {"data": {"queryCount": 72}}},
        principal_id=CONNECTED_AOT_PRINCIPAL, organization_id="aot", client_id=None,
        live_profile=PROFILE_V11, root=tmp_path / "functional-canary",
    )


def test_read_expansion_is_gated_in_actual_pm_before_post_certification():
    script = (Path(__file__).resolve().parents[1] / "release_manager_host_runner.py").read_text()
    start = script.index("smoke = run_functional_smoke_tests(candidate_sha)")
    wait = script.index("require_authenticated_read_canary(", start)
    ccc = script.index("run_release_ccc_gate(", wait)
    close = script.index("gate_transition(repo, state_root, record, \"closed\")", ccc)
    assert start < wait < ccc < close
    # A release that does not touch Autotask must still prove Autotask works.
    assert "candidate_autotask_profile != prior_autotask_profile" not in script
    assert "profile=prior_autotask_profile, phase=\"before\"" in script
    assert "profile=target_autotask_profile, phase=\"after\"" in script
    assert script.index("verified_owner_read_canary_preflight =") < script.index(
        'gate_transition(repo, state_root, record, "production")'
    )


def test_exact_read_duplicate_items_rejected_even_when_id_matches(tmp_path):
    session = _start(tmp_path)
    assert not _send(tmp_path, session, "service.ticket.read",
                     {"resource_id": 101},
                     {"items": [{"id": 101}, {"id": 101}]})


def test_exact_read_real_mcp_one_item_shape_is_accepted(tmp_path):
    session = _start(tmp_path)
    assert _send(tmp_path, session, "service.ticket.read",
                 {"resource_id": 143192},
                 {"items": [{"id": 143192}], "pageDetails": {"count": 1}})


def test_live_jit_enrolled_owner_identity_is_accepted_not_only_legacy_alias(tmp_path):
    session = _start(tmp_path)
    assert _send(tmp_path, session, "service.ticket.count", ARGS,
                 {"queryCount": 72}, principal=CONNECTED_AOT_PRINCIPAL)
    assert not _send(tmp_path, session, "service.ticket.count", ARGS,
                     {"queryCount": 72}, principal="person-not-bound-to-aot")


def test_do_not_stitch_one_aot_operators_count_to_anothers_tickets(tmp_path):
    session = _start(tmp_path)
    _full(tmp_path, session)
    event_dir = tmp_path / "functional-canary" / "events"
    other = "person-entra-" + "b" * 32
    for path in event_dir.glob("*.json"):
        payload = json.loads(path.read_text())
        if payload["proof"]["kind"] == "ticket_count":
            payload["principal_id"] = other
            path.write_text(json.dumps(payload))
    assert verify_authenticated_read_canary(tmp_path, session) is None

def _full_v13_receipts(root: Path, session, *, include_dynamic=True, dynamic_actor=CONNECTED_AOT_PRINCIPAL):
    """All five read classes must derive from the same bound human."""
    def send(capability, arguments, data, actor=CONNECTED_AOT_PRINCIPAL):
        return _send(root, session, capability, arguments, data,
                     principal=actor, profile=PROFILE_V13)
    assert send("service.ticket.count", ARGS, {"queryCount":72})
    assert send("service.ticket.search",{**ARGS,"page_size":50},
                {"items":[{"id":x} for x in range(101,151)]})
    assert send("service.ticket.search",{**ARGS,"page_size":50,"after_resource_id":150},
                {"items":[{"id":x} for x in range(151,173)]})
    assert send("service.ticket.read",{"resource_id":101},{"items":[{"id":101}]})
    assert send("service.entity.search",{"entity":"Projects","page_size":1},
                {"items":[{"id":222}]})
    if include_dynamic:
        assert send("service.entity.search",
                    {"entity":"ActionTypes","page_size":1,"select":["id","name"]},
                    {"items":[{"id":17,"name":"CUSTOMER_DATA_MUST_NOT_APPEAR"}]},
                    actor=dynamic_actor)


def test_v13_requires_real_dynamic_schema_query_as_well_as_ticket_and_projects(tmp_path):
    session=begin_authenticated_read_canary(
        tmp_path,candidate_sha=SHA,profile=PROFILE_V13,now=time.time(),
    )
    _full_v13_receipts(tmp_path,session)
    verdict=verify_authenticated_read_canary(tmp_path,session)
    assert verdict is not None and verdict["status"]=="PASS"
    assert verdict["dynamic_schema_search"] is True
    assert verdict["ticket_page_sum"]==72
    assert verdict["generic_project_read"] is True
    assert verdict["customer_data_in_receipt"] is False
    all_receipts="".join(
        f.read_text() for f in (tmp_path/"functional-canary"/"events").glob("*.json")
    )
    assert "CUSTOMER_DATA_MUST_NOT_APPEAR" not in all_receipts


def test_v13_missing_dynamic_read_can_never_pass_release(tmp_path):
    session=begin_authenticated_read_canary(
        tmp_path,candidate_sha=SHA,profile=PROFILE_V13,now=time.time(),
    )
    _full_v13_receipts(tmp_path,session,include_dynamic=False)
    assert verify_authenticated_read_canary(tmp_path,session) is None
    with pytest.raises(LiveReadAcceptanceError,match="not verified"):
        require_authenticated_read_canary(tmp_path,session,max_wait_seconds=0)


def test_v13_dynamic_read_by_another_user_cannot_be_stitched_into_release(tmp_path):
    session=begin_authenticated_read_canary(
        tmp_path,candidate_sha=SHA,profile=PROFILE_V13,now=time.time(),
    )
    _full_v13_receipts(tmp_path,session,dynamic_actor="person-entra-"+"b"*32)
    assert verify_authenticated_read_canary(tmp_path,session) is None


def test_v13_rejects_invented_successful_unvalidated_raw_dynamic_proof(tmp_path):
    session=begin_authenticated_read_canary(
        tmp_path,candidate_sha=SHA,profile=PROFILE_V13,now=time.time(),
    )
    _full_v13_receipts(tmp_path,session,include_dynamic=False)
    assert not _send(
        tmp_path,session,"service.entity.search",
        {"entity":"OtherEntity","page_size":1,"select":["id","name"]},
        {"items":[{"id":101}]},profile=PROFILE_V13
    )
    assert verify_authenticated_read_canary(tmp_path,session) is None


def test_foundational_pre_and_post_require_independent_verified_nonces(tmp_path):
    pre = begin_authenticated_read_canary(
        tmp_path, candidate_sha=SHA, profile=PROFILE_V13, phase="before",
        now=time.time(),
    )
    assert pre["phase"] == "before"
    with pytest.raises(LiveReadAcceptanceError, match="active"):
        begin_authenticated_read_canary(
            tmp_path, candidate_sha=SHA, profile=PROFILE_V13, phase="after",
            replacing_verified_session=pre,
        )
    _full_v13_receipts(tmp_path, pre)
    before = require_authenticated_read_canary(tmp_path, pre, max_wait_seconds=0)
    assert before["phase"] == "before"
    post = begin_authenticated_read_canary(
        tmp_path, candidate_sha=SHA, profile=PROFILE_V13, phase="after",
        replacing_verified_session=pre,
    )
    assert post["nonce"] != pre["nonce"]
    assert verify_authenticated_read_canary(tmp_path, post) is None
    with pytest.raises(LiveReadAcceptanceError, match="not verified"):
        require_authenticated_read_canary(tmp_path, post, max_wait_seconds=0)
    _full_v13_receipts(tmp_path, post)
    after = require_authenticated_read_canary(tmp_path, post, max_wait_seconds=0)
    assert after["phase"] == "after"
    assert before["ticket_window_digest"] == after["ticket_window_digest"]
    assert before["authenticated_principal_digest"] == after["authenticated_principal_digest"]
    assert before["ticket_count"] == after["ticket_count"]


def test_pre_post_replacement_rejects_wrong_candidate_and_session(tmp_path):
    pre = begin_authenticated_read_canary(
        tmp_path, candidate_sha=SHA, profile=PROFILE_V11, phase="before",
        now=time.time(),
    )
    _full(tmp_path, pre)
    with pytest.raises(LiveReadAcceptanceError, match="active"):
        begin_authenticated_read_canary(
            tmp_path, candidate_sha="b" * 40, profile=PROFILE_V11,
            phase="after", replacing_verified_session=pre,
        )
    with pytest.raises(LiveReadAcceptanceError, match="active"):
        begin_authenticated_read_canary(
            tmp_path, candidate_sha=SHA, profile=PROFILE_V11,
            phase="after", replacing_verified_session={**pre, "nonce": "0" * 32},
        )
    with pytest.raises(LiveReadAcceptanceError, match="only after"):
        begin_authenticated_read_canary(
            tmp_path, candidate_sha=SHA, profile=PROFILE_V11,
            phase="before", replacing_verified_session=pre,
        )


def test_phase_digest_detects_changing_autotask_scope_or_authenticated_human(tmp_path):
    pre = begin_authenticated_read_canary(
        tmp_path, candidate_sha=SHA, profile=PROFILE_V11,
        phase="before", now=time.time(),
    )
    _full(tmp_path, pre)
    before = require_authenticated_read_canary(tmp_path, pre, max_wait_seconds=0)
    post = begin_authenticated_read_canary(
        tmp_path, candidate_sha=SHA, profile=PROFILE_V11,
        phase="after", replacing_verified_session=pre,
    )
    changed_window = {
        "created_after": "2026-10-25T00:00:00-04:00",
        "created_before": "2026-10-27T00:00:00-04:00",
    }
    actor = "person-entra-" + "b" * 32
    def send(capability, arguments, data):
        assert _send(tmp_path, post, capability, arguments, data,
                     principal=actor)
    send("service.ticket.count", changed_window, {"queryCount": 1})
    send("service.ticket.search", {**changed_window, "page_size": 50},
         {"items": [{"id": 123}]})
    send("service.ticket.read", {"resource_id": 123},
         {"items": [{"id": 123}]})
    send("service.entity.search", {"entity": "Projects", "page_size": 1},
         {"items": [{"id": 42}]})
    after = require_authenticated_read_canary(tmp_path, post, max_wait_seconds=0)
    assert after["ticket_window_digest"] != before["ticket_window_digest"]
    assert after["authenticated_principal_digest"] != before["authenticated_principal_digest"]
