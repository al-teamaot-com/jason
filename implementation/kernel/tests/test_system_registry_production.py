from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kernel.system_registry import VerificationOutcome
from kernel.system_registry.manifest import registry_from_manifest
from kernel.system_registry.probes import (
    HostObservationRunner,
    ProbeExecutionError,
    VerificationCheck,
    load_verification_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = REPO_ROOT / "implementation/kernel/system_registry/production-registry.json"
LIFECYCLE_EVENTS = REPO_ROOT / "implementation/kernel/system_registry/production-lifecycle-events.json"
PLAN = REPO_ROOT / "implementation/kernel/system_registry/production-verification-plan.json"
NOW = datetime(2026, 8, 11, 15, 30, tzinfo=timezone.utc)
HOST_VERIFICATION_METHODS = {
    "docker-container-inspect-v1",
    "docker-file-sha256-v1",
}


def test_production_manifest_loads_with_resolved_dependencies() -> None:
    registry = registry_from_manifest(MANIFEST)
    ids = {entity.registry_id for entity in registry.list_all()}

    assert "component.jason-runtime" in ids
    assert "component.jason-teams-gateway" in ids
    assert "component.openclaw-jason-bridge" in ids
    assert "component.openbao" in ids
    assert "component.central-orchestrator" in ids
    assert "credential.microsoft-teams-gateway-client" in ids
    assert "capability.endpoint-device-search" in ids
    assert "capability.endpoint-device-read" in ids
    assert "capability.communication-email-send" in ids
    assert "capability.system-registry-search" in ids
    assert "capability.system-registry-read" in ids
    assert "capability.system-registry-trace" in ids
    assert "provider.datto-rmm" in ids
    assert "provider.microsoft-graph" in ids
    assert "provider.aws-ses" in ids
    assert "provider.system-registry" in ids
    assert "identity-binding.aot-microsoft-al" in ids
    assert "deployment.jason-single-host-pilot" in ids


def test_physical_configured_entities_have_bounded_host_checks_or_governed_verification() -> None:
    baseline = registry_from_manifest(MANIFEST)
    effective = registry_from_manifest(
        MANIFEST,
        lifecycle_events_path=LIFECYCLE_EVENTS,
    )
    plan = load_verification_plan(PLAN, registry=baseline)
    planned_ids = {check.registry_id for check in plan.checks}

    configured_physical = {
        entity.registry_id
        for entity in baseline.list_all()
        if entity.lifecycle_status.value == "configured"
        and HOST_VERIFICATION_METHODS.intersection(entity.verification_methods)
    }

    # The recurring observer plan remains deliberately bounded. A configured
    # physical entity may be outside that recurring plan only when a separately
    # governed production proof has already promoted the effective lifecycle to
    # VERIFIED with retained verification evidence. This preserves the invariant
    # that no unplanned configured physical component is silently assumed healthy.
    assert planned_ids.issubset(configured_physical)
    for registry_id in configured_physical - planned_ids:
        entity = effective.get(registry_id)
        assert entity.lifecycle_status.value == "verified"
        verification = effective.latest_verification(registry_id)
        assert verification is not None
        assert verification.outcome is VerificationOutcome.VERIFIED


def test_non_host_configured_entities_require_separate_governed_verification() -> None:
    registry = registry_from_manifest(MANIFEST)
    configured_non_host = {
        entity.registry_id
        for entity in registry.list_all()
        if entity.lifecycle_status.value == "configured"
        and not HOST_VERIFICATION_METHODS.intersection(entity.verification_methods)
    }

    assert configured_non_host == {
        "provider.system-registry",
        "capability.system-registry-search",
        "capability.system-registry-read",
        "capability.system-registry-trace",
    }


def test_docker_container_probe_can_verify_runtime_security_state() -> None:
    registry = registry_from_manifest(MANIFEST)
    plan = load_verification_plan(PLAN, registry=registry)
    check = next(item for item in plan.checks if item.registry_id == "component.jason-runtime")

    def command(arguments) -> str:
        assert tuple(arguments) == ("docker", "inspect", "jason-runtime")
        return json.dumps(
            [
                {
                    "Name": "/jason-runtime",
                    "State": {"Status": "running", "Health": {"Status": "healthy"}},
                    "Config": {"Image": "jason-runtime:local", "User": "1000:1000"},
                    "HostConfig": {
                        "ReadonlyRootfs": True,
                        "SecurityOpt": ["no-new-privileges:true"],
                        "CapDrop": ["ALL"],
                    },
                    "NetworkSettings": {
                        "Networks": {
                            "openclaw_default": {},
                            "jason-core": {},
                            "jason-observability": {},
                        }
                    },
                }
            ]
        )

    observation = HostObservationRunner(command).observe(
        check=check,
        source=plan.source,
        observed_at=NOW,
    )
    registry.record_observation(observation)
    result = registry.verify_from_latest_observation(
        registry_id=check.registry_id,
        method=check.method,
        verified_at=NOW,
    )

    assert result.outcome is VerificationOutcome.VERIFIED


def test_bridge_probe_verifies_deployed_digest_without_arbitrary_shell() -> None:
    registry = registry_from_manifest(MANIFEST)
    plan = load_verification_plan(PLAN, registry=registry)
    check = next(
        item for item in plan.checks if item.registry_id == "component.openclaw-jason-bridge"
    )
    expected = registry.get(check.registry_id).declared_state["sha256"]

    def command(arguments) -> str:
        assert tuple(arguments) == (
            "docker",
            "exec",
            "openclaw-openclaw-gateway-1",
            "sha256sum",
            "/home/node/.openclaw/extensions/jason-bridge/index.mjs",
        )
        return expected + "  /home/node/.openclaw/extensions/jason-bridge/index.mjs"

    observation = HostObservationRunner(command).observe(
        check=check,
        source=plan.source,
        observed_at=NOW,
    )
    registry.record_observation(observation)
    result = registry.verify_from_latest_observation(
        registry_id=check.registry_id,
        method=check.method,
        verified_at=NOW,
    )

    assert result.outcome is VerificationOutcome.VERIFIED


def test_probe_runner_rejects_unregistered_arbitrary_probe_type() -> None:
    check = VerificationCheck(
        registry_id="component.jason-runtime",
        method="docker-container-inspect-v1",
        probe={"type": "shell", "command": "whoami"},
    )

    with pytest.raises(ProbeExecutionError, match="Unsupported probe type"):
        HostObservationRunner(lambda _: "").observe(
            check=check,
            source="test",
            observed_at=NOW,
        )
