"""Native host recognizes V5 only under strict fixed-identity root policy."""
from __future__ import annotations
from copy import deepcopy
import json
import pytest

from tools import release_manager_host_runner as host
from implementation.runtime_service.tests.test_release_v5_aot_policy import base_payload
from implementation.runtime_service.tests.v5_synthetic_identity import AOT_REQUESTER_OID,AOT_ADMIN_OID


def _file(tmp_path,payload):
    original={
        "organization_id":"aot",
        "owner_identity_ids":["person-al"],
        "capability":"release.production.approve",
        **payload,
    }
    path=tmp_path/"mobile-release-policy.json"
    path.write_text(json.dumps(original,sort_keys=True))
    path.chmod(0o600)
    return path


def test_host_accepts_exact_reviewed_v5_policy(tmp_path):
    value=host._validated_mobile_release_policy(
        _file(tmp_path,base_payload()),source_v2_required=True,
    )
    assert value["schema_version"]=="5.0"
    assert value["mode"]=="admin_browser_stepup_regular_teams_notice"
    assert value["ttl_seconds"]==600


@pytest.mark.parametrize("part,field,value",[
    ("admin_approver_binding","microsoft_object_id",AOT_REQUESTER_OID),
    ("regular_requester_binding","microsoft_object_id",AOT_ADMIN_OID),
    ("entra_browser_approval","teams_notice_only",False),
    ("entra_browser_approval","no_admin_teams_license",False),
    ("entra_browser_approval","callback_uri","https://evil.example/admin/release-approval/callback"),
    ("entra_browser_approval","ca_enforcement_receipt_sha256","0"*64),
    ("high_impact_review","signed_teams_identity_required",True),
])
def test_host_rejects_v5_unreviewed_identity_or_scope(tmp_path,part,field,value):
    payload=base_payload()
    payload[part][field]=value
    with pytest.raises(host.ReleaseManagerError):
        host._validated_mobile_release_policy(
            _file(tmp_path,payload),source_v2_required=True,
        )
