"""V5 CA/MFA enforcement requires root-reviewed native Entra evidence."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,os
from pathlib import Path
import pytest

from jason_runtime.release_v5_ca_attestation import (
    verify_root_ca_enforcement_receipt,
)
from implementation.runtime_service.tests.v5_synthetic_identity import (
    AOT_TENANT,AOT_ADMIN_OID,AOT_REQUESTER_OID,CALLBACK_URL,NOTICE_URL,
)
from jason_runtime.release_v5_aot_policy import AotV5BrowserPolicy

NOW=datetime.now(timezone.utc).replace(microsecond=0)


def receipt():
    return {
        "schema_version":"1.0",
        "tenant_id":AOT_TENANT,
        "admin_oid":AOT_ADMIN_OID,
        "browser_client_id":"267b5641-cea0-4251-95c5-685178e0e087",
        "auth_context_id":"c1",
        "enforcement":"mfa_required",
        "verified_by":"native_entra_policy_read",
        "provider_policy_id":"33333333-3333-3333-3333-333333333333",
        "provider_read_evidence_sha256":"f"*64,
        "checked_at":NOW.isoformat(),
    }


def fixture(tmp_path,values=None):
    obj=values if values is not None else receipt()
    raw=json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
    f=tmp_path/"ca-enforcement.json";f.write_bytes(raw);f.chmod(0o600)
    policy=AotV5BrowserPolicy(
        browser_client_id="267b5641-cea0-4251-95c5-685178e0e087",
        auth_context_id="c1",
        ca_enforcement_receipt_sha256=sha256(raw).hexdigest(),
        signer_public_key_sha256="a"*64,
        callback_uri=CALLBACK_URL,notice_uri=NOTICE_URL,
        tenant_id=AOT_TENANT,admin_approver_oid=AOT_ADMIN_OID,
        requester_oid=AOT_REQUESTER_OID,owner_identity_id="person-al",
        organization_id="aot",
    )
    return f,policy


def verify(path,policy):
    return verify_root_ca_enforcement_receipt(
        path,browser_policy=policy,now=NOW+timedelta(minutes=1),
    )


def test_exact_root_owned_provider_read_enforcement_required(tmp_path):
    f,p=fixture(tmp_path)
    assert verify(f,p)==p.ca_enforcement_receipt_sha256


@pytest.mark.parametrize("changes",[
    {"tenant_id":"00000000-0000-0000-0000-000000000001"},
    {"admin_oid":"00000000-0000-0000-0000-000000000001"},
    {"browser_client_id":"00000000-0000-0000-0000-000000000001"},
    {"auth_context_id":"c2"},
    {"enforcement":"report_only"},
    {"verified_by":"browser_claim_only"},
    {"provider_read_evidence_sha256":"unknown"},
    {"checked_at":(NOW-timedelta(days=8)).isoformat()},
])
def test_missing_mfa_enforcement_or_wrong_tenant_rejected(tmp_path,changes):
    item={**receipt(),**changes}
    f,p=fixture(tmp_path,item)
    with pytest.raises(PermissionError,match="MFA_ENFORCEMENT_NOT_INDEPENDENTLY"):
        verify(f,p)


def test_unreviewed_tampered_or_public_receipt_fails(tmp_path):
    f,p=fixture(tmp_path)
    f.write_text(f.read_text()+" ")
    with pytest.raises(PermissionError,match="ATTESTATION_NOT_REVIEWED"):
        verify(f,p)
    f,p=fixture(tmp_path)
    f.chmod(0o644)
    with pytest.raises(PermissionError,match="ATTESTATION_NOT_REVIEWED"):
        verify(f,p)
    f,p=fixture(tmp_path)
    symlink=tmp_path/"alias.json";symlink.symlink_to(f)
    with pytest.raises(PermissionError,match="ATTESTATION_NOT_REVIEWED"):
        verify(symlink,p)


def test_missing_independently_reviewed_mfa_evidence_is_not_a_browser_approval(tmp_path):
    f,p=fixture(tmp_path)
    f.unlink()
    with pytest.raises(PermissionError,match="ATTESTATION_MISSING"):
        verify(f,p)
