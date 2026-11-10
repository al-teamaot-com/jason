"""License-free V5 browser assurance is opt-in and fail closed."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json

import pytest

from jason_runtime.mobile_release_approval import read_mobile_release_policy
from jason_runtime.release_v5_ca_attestation import verify_root_ca_enforcement_receipt
from implementation.runtime_service.tests.test_release_v5_aot_policy import (
    base_payload,new_policy,
)
from implementation.runtime_service.tests.test_release_v5_ca_attestation import (
    NOW,receipt,
)


def role_payload():
    raw=base_payload()
    bp=raw["entra_browser_approval"]
    del bp["auth_context_id"]
    bp["mfa_profile"]="existing_admin_role_mfa"
    return raw


def role_receipt():
    old=receipt()
    del old["auth_context_id"]
    old.update({
        "schema_version":"2.0",
        "mfa_profile":"existing_admin_role_mfa",
        "verified_by":"native_entra_policy_and_admin_roles_read",
        "admin_role_ids":["62e90394-69f5-4237-9190-012177145e10"],
    })
    return old


def bundle(tmp_path,receipt_data=None):
    data=role_receipt() if receipt_data is None else receipt_data
    raw=json.dumps(data,sort_keys=True,separators=(",",":")).encode()
    f=tmp_path/"ca-role-mfa.json"
    f.write_bytes(raw); f.chmod(0o600)
    policy_data=role_payload()
    policy_data["entra_browser_approval"]["ca_enforcement_receipt_sha256"]=(
        sha256(raw).hexdigest())
    policy=read_mobile_release_policy(new_policy(tmp_path,policy_data))
    return f,policy


def test_existing_admin_role_mfa_is_explicit_policy_only(tmp_path):
    f,policy=bundle(tmp_path)
    assert policy.browser_policy.mfa_profile=="existing_admin_role_mfa"
    assert policy.browser_policy.auth_context_id is None
    assert verify_root_ca_enforcement_receipt(
        f,browser_policy=policy.browser_policy,now=NOW+timedelta(seconds=5)
    )==policy.browser_policy.ca_enforcement_receipt_sha256


@pytest.mark.parametrize("field,value",[
    ("mfa_profile","unreviewed"),
    ("auth_context_id","c1"),
    ("teams_notice_only",False),
    ("no_admin_teams_license",False),
])
def test_unreviewed_role_policy_is_rejected(tmp_path,field,value):
    data=role_payload()
    data["entra_browser_approval"][field]=value
    with pytest.raises(PermissionError):
        read_mobile_release_policy(new_policy(tmp_path,data))


@pytest.mark.parametrize("field,value",[
    ("admin_oid","00000000-0000-0000-0000-000000000001"),
    ("mfa_profile","auth_context"),
    ("enforcement","report_only"),
    ("verified_by","client_claim"),
    ("provider_read_evidence_sha256","unverified"),
    ("admin_role_ids",[]),
    ("checked_at",(NOW-timedelta(days=2)).isoformat()),
])
def test_role_mfa_receipt_is_exact_root_attested(tmp_path,field,value):
    data=role_receipt(); data[field]=value
    f,policy=bundle(tmp_path,data)
    with pytest.raises(PermissionError,match="ROLE_MFA_ENFORCEMENT"):
        verify_root_ca_enforcement_receipt(
            f,browser_policy=policy.browser_policy,now=NOW)


def test_existing_policy_is_not_relabeled_role_mfa(tmp_path):
    f,policy=bundle(tmp_path)
    f.write_text(f.read_text()+" ")
    with pytest.raises(PermissionError,match="ROLE_MFA_ATTESTATION_NOT_REVIEWED"):
        verify_root_ca_enforcement_receipt(
            f,browser_policy=policy.browser_policy,now=NOW)
