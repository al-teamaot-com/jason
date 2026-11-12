"""Jason canonical System Registry PMv4 protected component admission."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.pmv4_component_scope import (
    PROTECTED, ProtectedCoreScopeDenied, REGISTRY,
    classify_source_paths, assert_component_release_scope,
)


def test_proposed_components_reuse_canonical_registry_not_fake_live_services():
    source = json.loads(REGISTRY.read_text())
    ids = {entry["registry_id"]: entry for entry in source["entities"]}
    assert set(PROTECTED).issubset(ids)
    for rid in PROTECTED:
        entry = ids[rid]
        assert entry["entity_type"] == "component"
        assert entry["lifecycle_status"] == "proposed"
        assert entry["environment"] == "preproduction"
        assert entry["declared_state"]["deployment_status"] == "not_deployed"
        assert entry["declared_state"]["component_lifecycle"] == "independent"
        assert all("pmv3" not in dep.casefold() for dep in entry["dependencies"])


def test_classify_canonical_registry_scopes_with_shared_paths():
    result = classify_source_paths([
        "implementation/runtime_service/src/jason_runtime/ticket_worker_service.py",
        "implementation/autonomous_remediation/playbook_store.py",
        "implementation/runtime_service/src/jason_runtime/composition.py",
        "docs/operations/PMv4-Integrated-Migration-Readiness-20261111.md",
    ])
    assert result["matched"]["component.ticket-processing-core"] == [
        "implementation/runtime_service/src/jason_runtime/ticket_worker_service.py",
    ]
    assert result["matched"]["component.runbook-management"] == [
        "implementation/autonomous_remediation/playbook_store.py",
    ]
    assert result["shared"] == [
        "implementation/runtime_service/src/jason_runtime/composition.py",
    ]


def test_component_specific_scope_accepted_only_for_one_owner():
    ticket = assert_component_release_scope([
        "implementation/runtime_service/src/jason_runtime/ticket_worker_ownership.py",
        "docs/operations/PMv4-Ticket-Core-Independent-Lifecycle-20261111.md",
    ], component="component.ticket-processing-core")
    assert ticket["path_count"] == 2
    runbooks = assert_component_release_scope([
        "implementation/autonomous_remediation/playbook_store.py",
    ], component="component.runbook-management")
    assert set(runbooks["matched"]) == {"component.runbook-management"}
    assert_component_release_scope([
        "tools/pmv4_shadow_release.py",
    ], component="pmv4-shadow")


@pytest.mark.parametrize("component,paths,reason", [
    ("pmv4-shadow", [
        "implementation/runtime_service/src/jason_runtime/ticket_worker_service.py",
    ], "SHADOW_CANNOT_CHANGE_PROTECTED_CORE"),
    ("component.ticket-processing-core", [
        "implementation/autonomous_remediation/playbook_store.py",
    ], "CROSS_COMPONENT_CHANGE_DENIED"),
    ("component.runbook-management", [
        "implementation/runtime_service/src/jason_runtime/ticket_worker_service.py",
    ], "CROSS_COMPONENT_CHANGE_DENIED"),
    ("component.ticket-processing-core", [
        "implementation/runtime_service/src/jason_runtime/ticket_worker_service.py",
        "implementation/autonomous_remediation/playbook_store.py",
    ], "CROSS_COMPONENT_CHANGE_DENIED"),
    ("pmv4-shadow", [
        "implementation/kernel/system_registry/production-registry.json",
    ], "SHARED_CORE_REQUIRES_CROSS_COMPONENT_RELEASE"),
    ("component.runbook-management", [
        "implementation/mcp_service/src/jason_mcp/server.py",
    ], "SHARED_CORE_REQUIRES_CROSS_COMPONENT_RELEASE"),
    ("component.ticket-processing-core", [
        "docs/operations/PMv4-Integrated-Migration-Readiness-20261111.md",
    ], "SCOPE_EMPTY_OR_UNVERIFIED"),
    ("made-up-service", [
        "tools/pmv4_shadow_release.py",
    ], "RELEASE_TARGET_INVALID"),
])
def test_reject_unrelated_or_shared_changes(component, paths, reason):
    with pytest.raises(ProtectedCoreScopeDenied, match=reason):
        assert_component_release_scope(paths, component=component)


@pytest.mark.parametrize("path", [
    "../etc/shadow", "/var/lib/jason/secrets", "foo/../foo",
    "foo\\bar", "./foo",
])
def test_reject_untrusted_repository_paths(path):
    with pytest.raises(ProtectedCoreScopeDenied, match="SOURCE_PATH_INVALID"):
        classify_source_paths([path])


def test_registry_tampering_missing_component_denied(tmp_path):
    document = json.loads(REGISTRY.read_text())
    document["entities"] = [
        entry for entry in document["entities"]
        if entry["registry_id"] != "component.runbook-management"
    ]
    fixture = tmp_path / "tampered.json"
    fixture.write_text(json.dumps(document))
    with pytest.raises(ProtectedCoreScopeDenied, match="PROTECTED_COMPONENT_MISSING"):
        classify_source_paths(["tools/pmv4_shadow_release.py"], registry_path=fixture)


def test_cannot_promote_proposed_component_by_mutating_source_registration(tmp_path):
    document = json.loads(REGISTRY.read_text())
    for entity in document["entities"]:
        if entity["registry_id"] == "component.ticket-processing-core":
            entity["lifecycle_status"] = "active"
    fixture = tmp_path / "active.json"
    fixture.write_text(json.dumps(document))
    with pytest.raises(ProtectedCoreScopeDenied, match="PROTECTED_COMPONENT_NOT_PREPROD"):
        classify_source_paths(["tools/pmv4_shadow_release.py"], registry_path=fixture)


def test_component_must_not_depend_on_pmv3_controller(tmp_path):
    document = json.loads(REGISTRY.read_text())
    for entity in document["entities"]:
        if entity["registry_id"] == "component.runbook-management":
            entity["dependencies"].append("component.pmv3-engineering-controller")
    fixture = tmp_path / "dependent.json"
    fixture.write_text(json.dumps(document))
    with pytest.raises((ProtectedCoreScopeDenied, ValueError), match="pmv3|PMV4|System Registry"):
        classify_source_paths(["tools/pmv4_shadow_release.py"], registry_path=fixture)


def test_transition_release_policy_protects_existing_core_and_management_sources():
    """Old PMv3 releases must not silently treat PMv4 Core changes as routine."""
    import fnmatch
    policy = json.loads((REGISTRY.parents[3] / "config/release-manager-policy.json").read_text())
    globs = policy["protected_core_globs"]
    must_guard = (
        "implementation/runtime_service/src/jason_runtime/ticket_worker_service.py",
        "implementation/runtime_service/src/jason_runtime/ticket_worker_ownership.py",
        "implementation/runtime_service/src/jason_runtime/main.py",
        "implementation/runtime_service/src/jason_runtime/composition.py",
        "implementation/autonomous_remediation/playbook_store.py",
        "implementation/mcp_service/src/jason_mcp/json_playbook_admin.py",
        "tools/pmv4_host_release_guard.py",
        "tools/pmv4_shadow_release.py",
        "tools/pmv4_component_scope.py",
    )
    for source in must_guard:
        assert any(fnmatch.fnmatchcase(source, pattern) for pattern in globs), source


def test_registry_allows_future_lifecycle_without_losing_protection(tmp_path):
    """Activation is a separately governed event; scope protection survives it."""
    doc = json.loads(REGISTRY.read_text())
    for entity in doc["entities"]:
        if entity["registry_id"] == "component.ticket-processing-core":
            entity["lifecycle_status"] = "active"
            entity["declared_state"]["deployment_status"] = "deployed"
    fixture = tmp_path / "verified-future-state.json"
    fixture.write_text(json.dumps(doc))
    allowed = classify_source_paths(
        ["implementation/runtime_service/src/jason_runtime/ticket_worker_service.py"],
        registry_path=fixture,
    )
    assert "component.ticket-processing-core" in allowed["matched"]
