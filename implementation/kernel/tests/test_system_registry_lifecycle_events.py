from __future__ import annotations

import json
from pathlib import Path

import pytest

from kernel.system_registry.contracts import EntityLifecycle, VerificationOutcome
from kernel.system_registry.manifest import registry_from_manifest


REGISTRY_DIR = Path(__file__).parents[1] / "system_registry"
MANIFEST = REGISTRY_DIR / "production-registry.json"
LIFECYCLE_EVENTS = REGISTRY_DIR / "production-lifecycle-events.json"


CURRENTLY_VERIFIED_PHYSICAL_COMPONENTS = {
    "component.openbao",
    "component.jason-runtime",
    "component.openclaw-gateway",
}

PENDING_REVERIFICATION_COMPONENTS = {
    "component.openclaw-jason-bridge",
}

INITIAL_VERIFICATION_EVENT_IDS = {
    "lifecycle.2026-08-11t154530z.component.openbao.verified",
    "lifecycle.2026-08-11t154530z.component.jason-runtime.verified",
    "lifecycle.2026-08-11t154530z.component.openclaw-gateway.verified",
    "lifecycle.2026-08-11t154530z.component.openclaw-jason-bridge.verified",
}


def test_governed_lifecycle_events_preserve_current_verification_state() -> None:
    registry = registry_from_manifest(
        MANIFEST,
        lifecycle_events_path=LIFECYCLE_EVENTS,
    )

    for registry_id in CURRENTLY_VERIFIED_PHYSICAL_COMPONENTS:
        entity = registry.get(registry_id)
        assert entity.lifecycle_status is EntityLifecycle.VERIFIED
        verification = registry.latest_verification(registry_id)
        assert verification is not None
        assert verification.outcome is VerificationOutcome.VERIFIED
        assert any(
            "system-registry-verification-20260811T154530Z.json" in reference
            for reference in verification.evidence_references
        )

    for registry_id in PENDING_REVERIFICATION_COMPONENTS:
        entity = registry.get(registry_id)
        assert entity.lifecycle_status is EntityLifecycle.CONFIGURED
        # Historical verification evidence is preserved append-only, but it does not
        # make the changed declaration currently verified.
        verification = registry.latest_verification(registry_id)
        assert verification is not None
        assert verification.outcome is VerificationOutcome.VERIFIED
        assert any(
            "system-registry-verification-20260811T154530Z.json" in reference
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
    assert registry.get("deployment.jason-single-host-pilot").lifecycle_status is EntityLifecycle.REGISTERED


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
    assert {
        "lifecycle.2026-08-11t165900z.component.openclaw-jason-bridge.suspended",
        "lifecycle.2026-08-11t165901z.component.openclaw-jason-bridge.configured",
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
    assert ("configured", "verified") in transitions
    assert ("verified", "suspended") in transitions
    assert ("suspended", "configured") in transitions
