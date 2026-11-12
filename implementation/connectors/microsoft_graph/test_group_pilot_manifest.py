"""Test that the AOT pilot plan cannot be mistaken for a permission grant."""
import json
from pathlib import Path

from connectors.microsoft_graph.governed_operations import operation
from connectors.microsoft_graph.group_reader import canonical_uuid

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / "config" / "microsoft_graph" / "pilots" / "aot-group-admin-20261112.json"


def test_aot_group_pilot_exact_intent_is_source_only():
    pilot = json.loads(PILOT.read_text(encoding="utf-8"))
    assert pilot["status"] == "proposed_not_authorized"
    assert pilot["client_id"] == "client-aot-internal"
    assert canonical_uuid(pilot["tenant_id"]) == pilot["tenant_id"]
    assert pilot["required_group_write"]["application_id"] is None
    assert pilot["required_group_read"]["application_id"] is None
    assert pilot["required_group_write"]["administrator_consent"] == "missing"
    assert pilot["required_group_read"]["administrator_consent"] == "missing"
    group = dict(pilot["create_group"])
    assert group.pop("capability") == "identity.group.create"
    assert operation("identity.group.create").validate_arguments(group) == group
    member = pilot["add_member"]
    assert member["capability"] == "identity.group.member.add"
    assert member["verified_group_id"] is None
    assert member["requires_verified_creation_readback"] is True
    assert member["verified_member_id"] == pilot["owner_user"]["object_id"]
    assert pilot["cleanup"]["no_automatic_group_deletion"] is True
