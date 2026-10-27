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
    assert verdict == {
        "status": "PASS", "source_revision": SHA,
        "identity": "authenticated-aot-human-jason-managed", "ticket_count": 72,
        "ticket_pages": 2, "ticket_page_sum": 72,
        "exact_id_readback": True, "generic_project_read": True,
        "customer_data_in_receipt": False,
    }
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
    assert "candidate_autotask_profile != prior_autotask_profile" in script


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
