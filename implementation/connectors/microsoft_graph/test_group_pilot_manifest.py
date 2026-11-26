"""Test that the AOT pilot plan cannot be mistaken for a permission grant."""
import json
from pathlib import Path

from connectors.microsoft_graph.governed_operations import operation
from connectors.microsoft_graph.group_reader import canonical_uuid

ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / "config" / "microsoft_graph" / "pilots" / "aot-group-admin-20261112.json"


def test_aot_group_pilot_exact_intent_is_source_only():
    pilot = json.loads(PILOT.read_text(encoding="utf-8"))
    assert pilot["status"] == "aot_lab_live_readonly_preflight_verified_release_pending"
    assert pilot["client_id"] == "client-aot-internal"
    assert canonical_uuid(pilot["tenant_id"]) == pilot["tenant_id"]
    assert pilot["required_group_write"]["application_id"] == "6583ee4b-5aa7-4c82-a46e-472f03a4c467"
    assert pilot["required_group_read"]["application_id"] == "bb8f8e09-f851-4e0d-9c4a-95ff36d34b9a"
    assert pilot["required_group_write"]["administrator_consent"].startswith("granted_and_read_back")
    assert pilot["required_group_read"]["administrator_consent"].startswith("granted_and_read_back")
    assert pilot["required_group_read"]["certificate_uploaded"] is True
    assert pilot["required_group_write"]["certificate_uploaded"] is True
    assert pilot["required_group_read"]["lab_token_acquired"] is True
    assert pilot["required_group_write"]["lab_token_acquired"] is True
    assert pilot["required_group_read"]["production_openbao_provisioned"] is False
    assert pilot["required_group_write"]["production_openbao_provisioned"] is False
    assert pilot["read_only_smoke_verification"]["write_app_mutation_exercised"] is False
    assert pilot["read_only_smoke_verification"]["proposed_group_mail_nickname_available"] is True
    group = dict(pilot["create_group"])
    assert group.pop("capability") == "identity.group.create"
    assert operation("identity.group.create").validate_arguments(group) == group
    member = pilot["add_member"]
    assert member["capability"] == "identity.group.member.add"
    assert member["verified_group_id"] is None
    assert member["requires_verified_creation_readback"] is True
    assert member["verified_member_id"] == pilot["owner_user"]["object_id"]
    assert pilot["cleanup"]["no_automatic_group_deletion"] is True
