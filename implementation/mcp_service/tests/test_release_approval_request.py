import json
from pathlib import Path

import pytest

from jason_mcp.release_approval_request import queue_release_approval_request

SHA = 'a' * 40
RID = 'release-' + 'a' * 16


def _record(root: Path, *, state: str = 'production_eligible', sha: str = SHA):
    path = root / 'records' / f'{RID}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'state': state,
        'release_candidate': {'candidate_sha': sha},
        'owner_approval': {'approved': False},
    }), encoding='utf-8')


def test_queue_release_approval_request_binds_exact_eligible_release(tmp_path):
    _record(tmp_path)
    result = queue_release_approval_request(
        state_root=tmp_path,
        release_id=RID,
        candidate_sha=SHA,
        approved_by='owner-al',
        organization_id='aot',
        reason='approved in chat',
    )
    assert result['release_id'] == RID
    assert result['candidate_sha'] == SHA
    assert result['approved_by'] == 'owner-al'
    request = tmp_path / 'owner-approval-requests' / f'{RID}.json'
    assert request.is_file()
    assert request.stat().st_mode & 0o777 == 0o600


def test_queue_release_approval_request_is_idempotent(tmp_path):
    _record(tmp_path)
    first = queue_release_approval_request(
        state_root=tmp_path,
        release_id=RID,
        candidate_sha=SHA,
        approved_by='owner-al',
        organization_id='aot',
    )
    second = queue_release_approval_request(
        state_root=tmp_path,
        release_id=RID,
        candidate_sha=SHA,
        approved_by='owner-al',
        organization_id='aot',
    )
    assert second == first


def test_queue_release_approval_request_rejects_noneligible_release(tmp_path):
    _record(tmp_path, state='release_candidate')
    with pytest.raises(ValueError, match='NOT_PRODUCTION_ELIGIBLE'):
        queue_release_approval_request(
            state_root=tmp_path,
            release_id=RID,
            candidate_sha=SHA,
            approved_by='owner-al',
            organization_id='aot',
        )


def test_queue_release_approval_request_rejects_sha_mismatch(tmp_path):
    _record(tmp_path)
    with pytest.raises(ValueError, match='RELEASE_ID_SHA_MISMATCH'):
        queue_release_approval_request(
            state_root=tmp_path,
            release_id=RID,
            candidate_sha='b' * 40,
            approved_by='owner-al',
            organization_id='aot',
        )
