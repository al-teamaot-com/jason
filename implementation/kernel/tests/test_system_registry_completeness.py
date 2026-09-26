from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "system_registry_completeness.py"
SPEC = importlib.util.spec_from_file_location("system_registry_completeness", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def manifest(*entities):
    return {"schema_version": "1.0", "entities": list(entities)}


def capability_entity(name: str):
    return {
        "registry_id": "capability." + name.replace(".", "-"),
        "entity_type": "capability",
        "lifecycle_status": "registered",
        "declared_state": {"capability_name": name},
    }


def component_entity(name: str, *, lifecycle: str = "configured"):
    return {
        "registry_id": "component." + name,
        "entity_type": "component",
        "lifecycle_status": lifecycle,
        "declared_state": {"container_name": name},
    }


def capability_payload(*names):
    return {
        "capabilities": [
            {"capability": name, "lifecycle": "active"}
            for name in names
        ]
    }


def test_complete_inventory_passes():
    result = MODULE.audit(
        manifest=manifest(
            capability_entity("service.ticket.read"),
            component_entity("jason-runtime"),
        ),
        capability_payload=capability_payload("service.ticket.read"),
        container_payload=[{"name": "jason-runtime"}],
    )
    assert result.passed
    assert result.to_dict()["status"] == "pass"


def test_missing_active_capability_fails_closed():
    result = MODULE.audit(
        manifest=manifest(),
        capability_payload=capability_payload("service.ticket.read"),
        container_payload=[],
    )
    assert not result.passed
    assert result.missing_capabilities == ("service.ticket.read",)


def test_missing_live_component_fails_closed():
    result = MODULE.audit(
        manifest=manifest(),
        capability_payload=capability_payload(),
        container_payload=[{"name": "jason-runtime"}],
    )
    assert not result.passed
    assert result.missing_components == ("jason-runtime",)


def test_stale_operational_component_fails_closed():
    result = MODULE.audit(
        manifest=manifest(component_entity("retired-but-still-configured")),
        capability_payload=capability_payload(),
        container_payload=[],
    )
    assert not result.passed
    assert result.stale_components == ("retired-but-still-configured",)


def test_nonoperational_component_does_not_require_live_observation():
    result = MODULE.audit(
        manifest=manifest(component_entity("future", lifecycle="registered")),
        capability_payload=capability_payload(),
        container_payload=[],
    )
    assert result.passed


def test_explicit_ephemeral_container_ignore_is_bounded():
    result = MODULE.audit(
        manifest=manifest(),
        capability_payload=capability_payload(),
        container_payload=["buildx-builder"],
        ignored_live_containers=("buildx-builder",),
    )
    assert result.passed
