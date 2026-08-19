from __future__ import annotations

import json
from pathlib import Path

import pytest

from kernel.system_registry.contracts import EntityLifecycle, VerificationOutcome
from kernel.system_registry.manifest import registry_from_manifest


REGISTRY_DIR = Path(__file__).parents[1] / "system_registry"
MANIFEST = REGISTRY_DIR / "production-registry.json"
LIFECYCLE_EVENTS = REGISTRY_DIR / "production-lifecycle-events.json"


CURRENT_VERIFICATION_EVIDENCE = {
    "component.openbao": "system-registry-verification-20260811T154530Z.json",
    "component.jason-runtime": "system-registry-verification-20260811T154530Z.json",
    "component.openclaw-gateway": "system-registry-verification-20260811T154530Z.json",
    "component.openclaw-jason-bridge": "post-openclaw-bridge-20260811T171348Z.json",
    "credential.microsoft-teams-gateway-client": "Direct-Teams-Gateway-Production-Proof-2026-08-15.md",
    "component.jason-teams-gateway": "Direct-Teams-Gateway-Production-Proof-2026-08-15.md",
    "deployment.jason-single-host-pilot": "Direct-Teams-Gateway-Production-Proof-2026-08-15.md",
}

INITIAL_VERIFICATION_EVENT_IDS = {
    "lifecycle.2026-08-11t154530z.component.openbao.verified",
    "lifecycle.2026-08-11t154530z.component.jason-runtime.verified",
    "lifecycle.2026-08-11t154530z.component.openclaw-gateway.verified",
    "lifecycle.2026-08-11t154530z.component.openclaw-jason-bridge.verified",
}

DIRECT_TEAMS_EVENT_IDS = {
    "lifecycle.2026-08-15t173800z.credential.microsoft-teams-gateway-client.configured",
    "lifecycle.2026-08-15t173900z.credential.microsoft-teams-gateway-client.verified",
    "lifecycle.2026-08-15t174000z.component.jason-teams-gateway.verified",
    "lifecycle.2026-08-15t174100z.deployment.jason-single-host-pilot.configured",
    "lifecycle.2026-08-15t174200z.deployment.jason-single-host-pilot.verified",
}


def test_governed_lifecycle_events_preserve_current_verification_state() -> None:
    registry = registry_from_manifest(
        MANIFEST,
        lifecycle_events_path=LIFECYCLE_EVENTS,
    )

    for registry_id, evidence_fragment in CURRENT_VERIFICATION_EVIDENCE.items():
        entity = registry.get(registry_id)
        assert entity.lifecycle_status is EntityLifecycle.VERIFIED
        verification = registry.latest_verification(registry_id)
        assert verification is not None
        assert verification.outcome is VerificationOutcome.VERIFIED
        assert any(
            evidence_fragment in reference
            for reference in verification.evidence_references
        )

    assert registry.get("component.central-orchestrator").lifecycle_status is EntityLifecycle.REGISTERED
    assert registry.get("provider.datto-rmm").lifecycle_status is EntityLifecycle.REGISTERED
    assert registry.get("provider.microsoft-graph").lifecycle_status is EntityLifecycle.REGISTERED
    assert registry.get("provider.aws-ses").lifecycle_status is EntityLifecycle.REGISTERED
    assert registry.get("identity-binding.aot-microsoft-al").lifecycle_status is EntityLifecycle.REGISTERED
    assert registry.get("capability.endpoint-device-search").lifecycle_status is EntityLifecycle.REGISTERED
    assert registry.get("capability.endpoint-device-read").lifecycle_status is EntityLifecycle.REGISTERED
    assert registry.get("capability.communication-email-send").lifecycle_status is EntityLifecycle.REGISTERED


def test_lifecycle_event_history_fails_closed_when_expected_prior_state_is_wrong(
    tmp_path: Path,
) -> None:
    document = json.loads(LIFECYCLE_EVENTS.read_text(encoding="utf-8"))
    document["events"][0]["from_lifecycle"] = "registered"
    path = tmp_path / "events.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="expected component.openbao to be registered"):
        registry_from_manifest(MANIFEST, lifecycle_events_path=path)


def test_lifecycle_event_history_is_append_only_in_effect() -> None:
    document = json.loads(LIFECYCLE_EVENTS.read_text(encoding="utf-8"))
    events = document["events"]
    event_ids = [event["event_id"] for event in events]

    assert len(event_ids) == len(set(event_ids))
    assert INITIAL_VERIFICATION_EVENT_IDS.issubset(set(event_ids))
    assert DIRECT_TEAMS_EVENT_IDS.issubset(set(event_ids))
    assert {
        "lifecycle.2026-08-11t165900z.component.openclaw-jason-bridge.suspended",
        "lifecycle.2026-08-11t165901z.component.openclaw-jason-bridge.configured",
        "lifecycle.2026-08-11t171400z.component.openclaw-jason-bridge.verified",
    }.issubset(set(event_ids))
    assert all(event["principal_id"] == "person-al" for event in events)

    for event in events:
        if event["to_lifecycle"] in {"verified", "active"}:
            assert event["verification_outcome"] == "verified"
            assert event["verification_method"]

    bridge_events = [
        event
        for event in events
        if event["registry_id"] == "component.openclaw-jason-bridge"
    ]
    transitions = [
        (event["from_lifecycle"], event["to_lifecycle"])
        for event in bridge_events
    ]
    assert transitions.count(("configured", "verified")) >= 2
    assert ("verified", "suspended") in transitions
    assert ("suspended", "configured") in transitions

    latest_bridge_event = max(
        bridge_events,
        key=lambda event: (event["effective_at"], event["event_id"]),
    )
    assert latest_bridge_event["to_lifecycle"] == "verified"
    assert any(
        "post-openclaw-bridge-20260811T171348Z.json" in reference
        for reference in latest_bridge_event["evidence_references"]
    )
