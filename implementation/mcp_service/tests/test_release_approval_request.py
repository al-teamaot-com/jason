import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kernel.signed_owner_release import verify_exact_owner_release

from jason_mcp.release_approval_request import queue_release_approval_request

SHA = 'a' * 40
RID = 'release-' + 'a' * 16
PREV = 'b' * 40
SCOPE = 'c' * 64
CLAIMS = {
    'tid': 'f7054323-d52b-4863-8c2f-1898f0b6077c',
    'oid': 'bee80bdc-ffb0-4c50-b453-c09d4d411f5f',
}
PRINCIPAL = 'person-entra-bee80bdcffb04c50b453c09d4d411f5f'
KEY = Ed25519PrivateKey.generate()


def _record(root: Path, *, state: str = 'production_eligible', sha: str = SHA):
    path = root / 'records' / f'{RID}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'state': state,
        'release_candidate': {'candidate_sha': sha},
        'rollback_sha': PREV,
        'manual_scope_review': {
            'candidate_sha': sha, 'baseline_sha': PREV, 'scope_sha256': SCOPE,
        },
        'release_manifest': {
            'candidate_sha': sha, 'rollback_sha': PREV,
        },
        'owner_approval': {'approved': False},
    }), encoding='utf-8')
    (root / 'production-deployment-freeze').write_text(
        '{"status":"active"}', encoding='utf-8'
    )


def test_queue_release_approval_request_binds_exact_eligible_release(tmp_path):
    _record(tmp_path)
    result = queue_release_approval_request(
        state_root=tmp_path,
        release_id=RID,
        candidate_sha=SHA,
        approved_by=PRINCIPAL,
        organization_id='aot',
        verified_token_claims=CLAIMS,
        service_signer=KEY,
        reason='approved in chat',
    )
    assert result['release_id'] == RID
    assert result['candidate_sha'] == SHA
    assert result['approved_by'] == PRINCIPAL
    request = tmp_path / 'owner-approval-requests' / f'{RID}.json'
    assert request.is_file()
    assert request.stat().st_mode & 0o777 == 0o600


def test_queue_release_approval_request_is_idempotent(tmp_path):
    _record(tmp_path)
    first = queue_release_approval_request(
        state_root=tmp_path,
        release_id=RID,
        candidate_sha=SHA,
        approved_by=PRINCIPAL,
        organization_id='aot',
        verified_token_claims=CLAIMS,
        service_signer=KEY,
    )
    second = queue_release_approval_request(
        state_root=tmp_path,
        release_id=RID,
        candidate_sha=SHA,
        approved_by=PRINCIPAL,
        organization_id='aot',
        verified_token_claims=CLAIMS,
        service_signer=KEY,
    )
    assert second == first


def test_queue_release_approval_request_rejects_noneligible_release(tmp_path):
    _record(tmp_path, state='release_candidate')
    with pytest.raises(ValueError, match='NOT_PRODUCTION_ELIGIBLE'):
        queue_release_approval_request(
            state_root=tmp_path,
            release_id=RID,
            candidate_sha=SHA,
            approved_by=PRINCIPAL,
            organization_id='aot',
            verified_token_claims=CLAIMS,
            service_signer=KEY,
        )


def test_queue_release_approval_request_rejects_sha_mismatch(tmp_path):
    _record(tmp_path)
    with pytest.raises(ValueError, match='RELEASE_ID_SHA_MISMATCH'):
        queue_release_approval_request(
            state_root=tmp_path,
            release_id=RID,
            candidate_sha='b' * 40,
            approved_by=PRINCIPAL,
            organization_id='aot',
            verified_token_claims=CLAIMS,
            service_signer=KEY,
        )



def test_authenticated_mcp_owner_proof_is_crypto_bound_to_freeze_and_scope(tmp_path):
    from hashlib import sha256
    _record(tmp_path)
    receipt = queue_release_approval_request(
        state_root=tmp_path, release_id=RID, candidate_sha=SHA,
        approved_by=PRINCIPAL, organization_id='aot',
        verified_token_claims=CLAIMS, service_signer=KEY,
    )
    assert receipt['source'].startswith('authenticated_jason_mcp_owner:owner-mcp-')
    signed = receipt['signed_owner_proof']
    manifest = json.loads((tmp_path / 'records' / f'{RID}.json').read_text())
    import hashlib
    manifest_digest = hashlib.sha256(json.dumps(
        manifest['release_manifest'], sort_keys=True, separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')).hexdigest()
    freeze_digest = sha256((tmp_path / 'production-deployment-freeze').read_bytes()).hexdigest()
    output = verify_exact_owner_release(
        signed, public_key=KEY.public_key(),
        expected_release_id=RID, expected_candidate_sha=SHA,
        expected_rollback_sha=PREV, expected_scope_sha256=SCOPE,
        expected_manifest_sha256=manifest_digest,
        expected_freeze_sha256=freeze_digest,
        at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
    )
    assert output['owner_principal'] == PRINCIPAL


def test_unsigned_old_mcp_request_is_not_an_approval(tmp_path):
    _record(tmp_path)
    with pytest.raises(ValueError, match='SIGNED_OWNER_EVIDENCE_REQUIRED'):
        queue_release_approval_request(
            state_root=tmp_path, release_id=RID, candidate_sha=SHA,
            approved_by=PRINCIPAL, organization_id='aot',
        )


def test_mismatched_entra_subject_is_not_sufficient(tmp_path):
    _record(tmp_path)
    for principal, claims in (
        ('person-al', CLAIMS),
        (PRINCIPAL, {'tid': CLAIMS['tid'], 'oid':
                    'c848022d-e13b-4457-84b0-e2f5c00dcaf6'}),
        (PRINCIPAL, {'tid': '00000000-0000-0000-0000-000000000000',
                    'oid': CLAIMS['oid']}),
    ):
        with pytest.raises(ValueError, match='SIGNED_OWNER_EVIDENCE_REQUIRED'):
            queue_release_approval_request(
                state_root=tmp_path, release_id=RID, candidate_sha=SHA,
                approved_by=principal, organization_id='aot',
                verified_token_claims=claims, service_signer=KEY,
            )


def test_stale_signed_request_is_not_overwritten_or_reissued(tmp_path):
    _record(tmp_path)
    first = queue_release_approval_request(
        state_root=tmp_path, release_id=RID, candidate_sha=SHA,
        approved_by=PRINCIPAL, organization_id='aot',
        verified_token_claims=CLAIMS, service_signer=KEY,
    )
    second = queue_release_approval_request(
        state_root=tmp_path, release_id=RID, candidate_sha=SHA,
        approved_by=PRINCIPAL, organization_id='aot',
        verified_token_claims=CLAIMS, service_signer=KEY,
    )
    assert second == first


def test_retired_mode_issuer_uses_new_policy_and_rejects_stale_pending(tmp_path, monkeypatch):
    from jason_mcp import release_approval_request as issuer
    from hashlib import sha256
    _record(tmp_path)
    args = dict(state_root=tmp_path, release_id=RID, candidate_sha=SHA,
                approved_by=PRINCIPAL, organization_id="aot",
                verified_token_claims=CLAIMS, service_signer=KEY)
    legacy = queue_release_approval_request(**args)
    old_request = tmp_path / "owner-approval-requests" / (RID+".json")
    (tmp_path/"production-deployment-freeze").unlink()
    monkeypatch.setattr(issuer, "read_retired_release_policy", lambda: "9"*64)
    with pytest.raises(PermissionError, match="MODE_MISMATCH"):
        queue_release_approval_request(**args)
    assert json.loads(old_request.read_text()) == legacy
    old_request.unlink()  # disposable fixture only
    normal = queue_release_approval_request(**args)
    payload = normal["signed_owner_proof"]["payload"]
    assert payload["schema_version"] == "2.0"
    assert payload["release_policy_sha256"] == "9"*64
    assert "freeze_sha256" not in payload
    assert queue_release_approval_request(**args) == normal
    (tmp_path/"production-deployment-freeze").write_text('{"status":"active"}')
    with pytest.raises(PermissionError, match="MODE_CONFLICT"):
        queue_release_approval_request(**args)


def test_missing_freeze_is_not_retirement(tmp_path, monkeypatch):
    from jason_mcp import release_approval_request as issuer
    _record(tmp_path)
    (tmp_path/"production-deployment-freeze").unlink()
    monkeypatch.setattr(issuer, "read_retired_release_policy", lambda: None)
    with pytest.raises(ValueError, match="FROZEN_TRANSACTION_REQUIRED"):
        queue_release_approval_request(
            state_root=tmp_path,release_id=RID,candidate_sha=SHA,
            approved_by=PRINCIPAL,organization_id="aot",
            verified_token_claims=CLAIMS,service_signer=KEY)
    assert not (tmp_path/"owner-approval-requests").exists()


def test_retired_mode_does_not_inherit_historical_approval(tmp_path, monkeypatch):
    from jason_mcp import release_approval_request as issuer
    _record(tmp_path)
    (tmp_path/"production-deployment-freeze").unlink()
    path=tmp_path/"records"/(RID+".json")
    record=json.loads(path.read_text())
    record["owner_approval"]={"approved":True,"candidate_sha":SHA}
    path.write_text(json.dumps(record))
    monkeypatch.setattr(issuer,"read_retired_release_policy",lambda:"9"*64)
    with pytest.raises(ValueError,match="FRESH_RECORD_REQUIRED"):
        queue_release_approval_request(
            state_root=tmp_path,release_id=RID,candidate_sha=SHA,
            approved_by=PRINCIPAL,organization_id="aot",
            verified_token_claims=CLAIMS,service_signer=KEY)


def test_existing_owner_tool_routes_only_exact_normal_coordinated_offer(tmp_path, monkeypatch):
    from jason_mcp import release_approval_request as issuer
    from kernel.signed_owner_release_v2 import verify_exact_owner_release
    from datetime import datetime, timezone
    policy = '9'*64
    view = dict(schema_version='3.0',release_id=RID,candidate_sha=SHA,rollback_sha=PREV,
        manifest_sha256='8'*64,scope_sha256=SCOPE,release_policy_sha256=policy,
        status='native_coordinated_eligible_not_approved',production_mutations=False,
        provider_writes=False,owner_approval_recorded=False,observed_at='2026-11-27T12:00:00Z')
    spool=tmp_path/'proofs';spool.mkdir(mode=0o700)
    monkeypatch.setattr(issuer,'COORDINATED_PROOFS',spool)
    monkeypatch.setattr(issuer,'_coordinated_eligibility',lambda rid:dict(view))
    monkeypatch.setattr(issuer,'read_retired_release_policy',lambda:policy)
    args=dict(state_root=tmp_path,release_id=RID,candidate_sha=SHA,approved_by=PRINCIPAL,
        organization_id='aot',verified_token_claims=CLAIMS,service_signer=KEY)
    with pytest.raises(PermissionError,match='SIGNED_OWNER_EVIDENCE_REQUIRED'):
        queue_release_approval_request(**dict(args,verified_token_claims={}))
    view['release_policy_sha256']='7'*64
    with pytest.raises(PermissionError,match='EXACT_ELIGIBILITY_REQUIRED'):
        queue_release_approval_request(**args)
    view['release_policy_sha256']=policy
    (tmp_path/'production-deployment-freeze').write_text('active')
    with pytest.raises(PermissionError,match='MODE_CONFLICT'):
        queue_release_approval_request(**args)
    (tmp_path/'production-deployment-freeze').unlink()
    assert list(spool.iterdir())==[]
    result=queue_release_approval_request(**args)
    saved=json.loads((spool/(RID+'.json')).read_text())
    assert result['approved_by']==PRINCIPAL
    assert saved['standing_authority'] is False and saved['provider_mutations_approved'] is False
    verify_exact_owner_release(saved['signed_owner_proof'],public_key=KEY.public_key(),
        expected_candidate_sha=SHA,expected_rollback_sha=PREV,expected_release_id=RID,
        expected_scope_sha256=SCOPE,expected_manifest_sha256='8'*64,
        expected_release_policy_sha256=policy,at=datetime.now(timezone.utc))
    with pytest.raises(PermissionError,match='PROOF_ALREADY_RECORDED'):
        queue_release_approval_request(**args)
    _record(tmp_path)
    with pytest.raises(PermissionError,match='AMBIGUOUS_RELEASE_ROUTE'):
        queue_release_approval_request(**args)
