from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SHA = re.compile(r'^[0-9a-f]{40}$')
RELEASE_ID = re.compile(r'^release-[0-9a-f]{16}$')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def queue_release_approval_request(
    *,
    state_root: Path,
    release_id: str,
    candidate_sha: str,
    approved_by: str,
    organization_id: str,
    reason: str = '',
) -> dict[str, Any]:
    release_id = str(release_id or '').strip().casefold()
    candidate_sha = str(candidate_sha or '').strip().casefold()
    approved_by = str(approved_by or '').strip()
    organization_id = str(organization_id or '').strip()
    if not RELEASE_ID.fullmatch(release_id):
        raise ValueError('RELEASE_APPROVAL_RELEASE_ID_INVALID')
    if not SHA.fullmatch(candidate_sha):
        raise ValueError('RELEASE_APPROVAL_CANDIDATE_SHA_INVALID')
    if release_id != 'release-' + candidate_sha[:16]:
        raise ValueError('RELEASE_APPROVAL_RELEASE_ID_SHA_MISMATCH')
    if not approved_by:
        raise ValueError('RELEASE_APPROVAL_PRINCIPAL_REQUIRED')
    if not organization_id:
        raise ValueError('RELEASE_APPROVAL_ORGANIZATION_REQUIRED')

    record_path = state_root / 'records' / f'{release_id}.json'
    if not record_path.is_file():
        raise ValueError('RELEASE_APPROVAL_RECORD_NOT_FOUND')
    record = json.loads(record_path.read_text(encoding='utf-8'))
    if str(record.get('state') or '') != 'production_eligible':
        raise ValueError('RELEASE_APPROVAL_NOT_PRODUCTION_ELIGIBLE')
    candidate = record.get('release_candidate')
    if not isinstance(candidate, dict):
        raise ValueError('RELEASE_APPROVAL_CANDIDATE_METADATA_MISSING')
    if str(candidate.get('candidate_sha') or '').strip().casefold() != candidate_sha:
        raise ValueError('RELEASE_APPROVAL_RECORD_SHA_MISMATCH')
    existing = record.get('owner_approval')
    if isinstance(existing, dict) and existing.get('approved') is True:
        if str(existing.get('candidate_sha') or '').strip().casefold() != candidate_sha:
            raise ValueError('RELEASE_APPROVAL_EXISTING_SHA_MISMATCH')
        return {
            'status': 'already_approved',
            'release_id': release_id,
            'candidate_sha': candidate_sha,
            'approved_by': str(existing.get('approved_by') or approved_by),
        }

    request_path = state_root / 'owner-approval-requests' / f'{release_id}.json'
    payload = {
        'schema_version': '1.0',
        'release_id': release_id,
        'candidate_sha': candidate_sha,
        'approved_by': approved_by,
        'organization_id': organization_id,
        'reason': str(reason or '')[:1000],
        'recorded_at': _now(),
        'source': 'authenticated_jason_mcp_owner',
    }
    if request_path.exists():
        current = json.loads(request_path.read_text(encoding='utf-8'))
        immutable = ('release_id', 'candidate_sha', 'approved_by', 'organization_id')
        if any(str(current.get(k) or '') != str(payload.get(k) or '') for k in immutable):
            raise ValueError('RELEASE_APPROVAL_PENDING_REQUEST_CONFLICT')
        return dict(current)
    _atomic_json(request_path, payload)
    return payload
