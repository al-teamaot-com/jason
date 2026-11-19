"""Partial offline-ticket JSON read-only classifier, same legacy pure logic.

No internal note, no source ticket status, and no provider mutation is
executed. This is NOT full legacy-workflow parity.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from autonomous_remediation.json_shadow_integration import (
    GovernedJsonShadowIntegration, JsonShadowBoundaryError, SQLiteJsonShadowState,
)
from autonomous_remediation.playbook_document import validate_playbook_document
from autonomous_remediation.offline_ticket_augmentation import (
    SiteContextEvidence, SiteWitness, classify_site_context,
    render_site_context_note,
)
from jason_runtime.json_offline_context_facts import reduce_offline_context_shadow

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/offline_ticket_context_augmentation.v1.json"
SCHEMA = ROOT / "docs/playbooks/json/playbook-v1.schema.json"
NOW = datetime(2026, 11, 19, 16, tzinfo=timezone.utc)
SITE = "site-uid-101"


def peer(uid, name, system, online, *, site=SITE):
    return {
        "resource_id": uid, "hostname": name, "siteUid": site,
        "operatingSystem": system, "online": online,
    }


class Provider:
    bound_client_id = "777"
    def __init__(self, peers=(), *, title="Device offline", deb=(),
                 ticket_company="777", target_company="777"):
        self.peers = list(peers)
        self.title = title
        self.deb = list(deb)
        self.ticket_company = ticket_company
        self.target_company = target_company
        self.calls = []
        self.mutations = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "service.ticket.read":
            assert arguments == {"ticket_id": "123"}
            return {"status": "succeeded", "evidence": {"data": {"item": {
                "id": 123, "companyID": self.ticket_company,
                "title": self.title, "description": "Device reported offline",
                "status": "In Progress",
                "configurationItemID": 44, "ticketNumber": "T-TEST-123",
            }}}}
        if capability == "service.configuration.read":
            assert arguments == {"resource_id": 44}
            return {"status": "succeeded", "evidence": {"data": {"item": {
                "id": 44, "companyID": self.target_company,
                "isActive": True, "referenceNumber": "dev-1",
                "referenceTitle": "WORKSTATION-A",
            }}}}
        if capability == "endpoint.device.read":
            assert arguments == {"resource_id": "dev-1"}
            return {"status": "succeeded", "evidence": {"record": {
                "resource_id": "dev-1", "hostname": "WORKSTATION-A",
                "online": False, "site": "Site A", "siteUid": SITE,
            }}}
        if capability == "backup.endpoint.asset.search":
            assert arguments == {
                "company_id": "777", "name": "WORKSTATION-A", "page_size": 100}
            return {"status": "succeeded", "evidence": {"data": {
                "items": self.deb,
            }}}
        if capability == "endpoint.device.search":
            assert arguments == {"site": "Site A"}
            return {"status": "succeeded", "evidence": {"data": {
                "resource_matches": self.peers,
            }}}
        raise AssertionError("Unexpected capability " + capability)


def build(tmp_path, provider):
    payload = json.loads(CANDIDATE.read_text())
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(payload)
    document = validate_playbook_document(payload)
    state = SQLiteJsonShadowState(tmp_path / "isolated-offline.sqlite3")
    runner = GovernedJsonShadowIntegration(
        document=document, state=state, read_port=provider,
        read_capabilities=frozenset(document.capabilities),
        normalize=lambda cap, res, facts: reduce_offline_context_shadow(
            cap, res, facts, at=NOW),
        clock=lambda: NOW,
    )
    return runner, state


def execute(runner):
    return runner.run(
        run_id="offline-123", client_id="777", target_id="123",
        trusted_seed={"client_id": "777", "target_id": "123"},
    )


@pytest.mark.parametrize("peers,expected", [
    ([], "site_status_unknown"),
    ([peer("fixed-1", "DESKTOP-1", "Windows Desktop", True),
      peer("fixed-2", "DESKTOP-2", "Windows Desktop", True)], "site_likely_up"),
    ([peer("fixed-1", "DESKTOP-1", "Windows Desktop", False),
      peer("fixed-2", "DESKTOP-2", "Windows Desktop", False)], "site_likely_down"),
    ([peer("mobile-1", "LAPTOP-1", "Windows Laptop", True),
      peer("mobile-2", "LAPTOP-2", "Windows Laptop", True)], "site_status_unknown"),
    ([peer("fixed-1", "DESKTOP-1", "Windows Desktop", False),
      peer("mobile-1", "LAPTOP-1", "Windows Laptop", True)], "site_status_unknown"),
])
def test_exact_same_source_pure_classifier_fingerprint_and_read_only_evidence(
    tmp_path, peers, expected,
):
    provider = Provider(peers)
    runner, state = build(tmp_path, provider)
    try:
        result = execute(runner)
        assert result.status == "completed_readonly"
        assert result.step_id == "classified"
        assert result.facts["classification"] == expected
        assert len(provider.calls) == 5
        assert provider.mutations == []
        assert result.facts["active_server_witness_attempted"] is False
        witnesses = tuple(
            SiteWitness(
                device_uid=p["resource_id"],
                hostname=p["hostname"],
                role="laptop" if "Laptop" in p["operatingSystem"] else "desktop",
                online=p["online"], fixed="Desktop" in p["operatingSystem"],
                mobile="Laptop" in p["operatingSystem"],
                site_presence_confirmed="Desktop" in p["operatingSystem"],
                live_read_succeeded=False,
            ) for p in peers
        )
        same_evidence = SiteContextEvidence(
            target_hostname="WORKSTATION-A", target_drmm_online=False,
            target_deb_online=None, site_name="Site A",
            witnesses=witnesses,
        )
        legacy = classify_site_context(same_evidence)
        assert legacy.state.value == expected
        assert result.facts["assessment_fingerprint"] == legacy.fingerprint()
        assert result.facts["legacy_readonly_note_preview"] == render_site_context_note(
            legacy, target_drmm_online=False, target_deb_online=None,
            site_name="Site A",
        )
        assert execute(runner) == result
        assert len(provider.calls) == 5
    finally:
        state.close()


@pytest.mark.parametrize("condition", ["ticket_client", "ci_client", "peer_site"])
def test_exact_company_and_peer_scope_fail_closed(tmp_path, condition):
    provider = Provider(
        peers=[peer("fixed-1", "DESKTOP-1", "Windows Desktop", True,
                    site="foreign-site" if condition == "peer_site" else SITE)],
        ticket_company="foreign" if condition == "ticket_client" else "777",
        target_company="foreign" if condition == "ci_client" else "777",
    )
    runner, state = build(tmp_path, provider)
    try:
        result = execute(runner)
        assert result.status == "failed_closed"
        assert provider.mutations == []
    finally:
        state.close()


def test_missing_or_unrelated_trigger_is_no_action(tmp_path):
    provider = Provider(title="Printer supplies")
    # Description still says device offline: this is indeed a trigger.
    # To prove no trigger, replace the two evidence fields.
    original_execute = provider.execute
    def unrelated(capability, arguments):
        value = original_execute(capability, arguments)
        if capability == "service.ticket.read":
            value["evidence"]["data"]["item"]["description"] = "Supply order only"
        return value
    provider.execute = unrelated
    runner, state = build(tmp_path, provider)
    try:
        result = execute(runner)
        assert result.status == "completed_readonly"
        assert result.step_id == "unrelated_ticket"
        assert len(provider.calls) == 1
        assert provider.mutations == []
    finally:
        state.close()


def test_peer_page_over_20_refuses_partial_evidence(tmp_path):
    provider = Provider([
        peer(f"host-{i}", f"DESKTOP-{i}", "Windows Desktop", True)
        for i in range(21)
    ])
    runner, state = build(tmp_path, provider)
    try:
        assert execute(runner).status == "failed_closed"
        assert provider.mutations == []
    finally:
        state.close()


def test_source_cannot_invent_approval_or_health_fact(tmp_path):
    runner, state = build(tmp_path, Provider())
    with pytest.raises(JsonShadowBoundaryError, match="SEED_FACTS_NOT_TRUSTED"):
        runner.run(
            run_id="offline-123", client_id="777", target_id="123",
            trusted_seed={
                "client_id": "777", "target_id": "123",
                "exact_active_same_company_ci": True,
            },
        )
    state.close()
