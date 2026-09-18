import json

from jason_runtime.datto_component_approval_registry import (
    approve_component,
    component_metadata_fingerprint,
    latest_records_by_identity,
    list_records,
    revoke_component,
)


def test_approval_registry_round_trip(tmp_path):
    path = tmp_path / "approvals.json"
    metadata = {
        "resource_id": "component-1",
        "name": "Diagnostic One",
        "description": "Read-only diagnostic",
        "category": "scripts",
        "credentials_required": False,
        "variables": [],
    }
    fingerprint = component_metadata_fingerprint(metadata)

    approved = approve_component(
        uid="component-1",
        name="Diagnostic One",
        approved_by="person-al",
        metadata_fingerprint=fingerprint,
        reason="Approved for autonomous diagnostics",
        path=path,
    )

    assert approved.status == "approved"
    assert approved.metadata_fingerprint == fingerprint
    assert len(list_records(path)) == 1
    latest = latest_records_by_identity(path)
    assert latest[("component-1", "diagnostic one")].status == "approved"

    revoked = revoke_component(
        uid="component-1",
        name="Diagnostic One",
        revoked_by="person-al",
        reason="No longer approved",
        path=path,
    )

    assert revoked.status == "revoked"
    assert len(list_records(path)) == 2
    latest = latest_records_by_identity(path)
    assert latest[("component-1", "diagnostic one")].status == "revoked"


def test_metadata_fingerprint_is_stable_and_change_sensitive():
    base = {
        "resource_id": "component-1",
        "name": "Diagnostic One",
        "description": "Read-only diagnostic",
        "category": "scripts",
        "credentials_required": False,
        "variables": [{"name": "mode", "type": "string"}],
    }
    reordered = {
        "variables": [{"type": "string", "name": "mode"}],
        "category": "scripts",
        "description": "Read-only diagnostic",
        "credentials_required": False,
        "name": "Diagnostic One",
        "resource_id": "component-1",
    }
    changed = dict(base)
    changed["description"] = "Now also changes configuration"

    assert component_metadata_fingerprint(base) == component_metadata_fingerprint(reordered)
    assert component_metadata_fingerprint(base) != component_metadata_fingerprint(changed)


def test_registry_file_is_versioned_and_auditable(tmp_path):
    path = tmp_path / "approvals.json"
    fp = "a" * 64
    approve_component(
        uid="component-1",
        name="Diagnostic One",
        approved_by="person-al",
        metadata_fingerprint=fp,
        reason="Owner review",
        path=path,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["records"][0]["approved_by"] == "person-al"
    assert payload["records"][0]["reason"] == "Owner review"
