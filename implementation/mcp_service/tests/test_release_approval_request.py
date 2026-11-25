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
