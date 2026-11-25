from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release,
    verify_exact_owner_release,
)
from pathlib import Path

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
    verified_token_claims: Mapping[str, Any] | None = None,
    service_signer: Ed25519PrivateKey | None = None,
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

    # The ordinary MCP request is not independent human authorization until
    # backed by an Entra-OAuth verified, service-signed exact-action receipt.
    # Never silently fall back to a bare Owner email, chat text or JSON flag.
    if (not isinstance(verified_token_claims, Mapping)
            or not isinstance(service_signer, Ed25519PrivateKey)
            or verified_token_claims.get('tid') !=
                'f7054323-d52b-4863-8c2f-1898f0b6077c'
            or verified_token_claims.get('oid') not in EXACT_OWNER_OAUTH_SUBJECTS
            or approved_by != EXACT_OWNER_OAUTH_SUBJECTS.get(
                verified_token_claims.get('oid'))
            or organization_id != 'aot'):
        raise ValueError('RELEASE_APPROVAL_SIGNED_OWNER_EVIDENCE_REQUIRED')
    reviewed = record.get('manual_scope_review') or {}
    manifest = record.get('release_manifest') or {}
    rollback = str(record.get('rollback_sha') or '')
    scope_sha = str(reviewed.get('scope_sha256') or '')
    if (reviewed.get('candidate_sha') != candidate_sha
            or reviewed.get('baseline_sha') != rollback
            or manifest.get('candidate_sha') != candidate_sha
            or manifest.get('rollback_sha') != rollback
            or len(scope_sha) != 64):
        raise ValueError('RELEASE_APPROVAL_EXACT_REVIEWED_SCOPE_REQUIRED')
    freeze = state_root / 'production-deployment-freeze'
    if not freeze.is_file() or freeze.is_symlink():
        raise ValueError('RELEASE_APPROVAL_FROZEN_TRANSACTION_REQUIRED')
    freeze_hash = hashlib.sha256(freeze.read_bytes()).hexdigest()
    manifest_hash = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')).hexdigest()
    signed = issue_exact_owner_release(
        approval_id='owner-mcp-' + uuid4().hex,
        release_id=release_id,
        candidate_sha=candidate_sha,
        rollback_sha=rollback,
        scope_sha256=scope_sha,
        manifest_sha256=manifest_hash,
        freeze_sha256=freeze_hash,
        verified_tenant_id=str(verified_token_claims['tid']),
        verified_owner_oid=str(verified_token_claims['oid']),
        verified_principal=approved_by,
        verified_organization_id=organization_id,
        confirmed_decision='approve',
        at=datetime.now(timezone.utc),
        private_key=service_signer,
    )
    # Self-verification is a consistency check. Root independently uses a
    # separately pinned public key and fresh live source/readback.
    verify_exact_owner_release(
        signed, public_key=service_signer.public_key(),
        expected_candidate_sha=candidate_sha,
        expected_rollback_sha=rollback,
        expected_release_id=release_id,
        expected_scope_sha256=scope_sha,
        expected_manifest_sha256=manifest_hash,
        expected_freeze_sha256=freeze_hash,
        at=datetime.now(timezone.utc),
    )
    request_path = state_root / 'owner-approval-requests' / f'{release_id}.json'
    payload = {
        'schema_version': '1.0',
        'release_id': release_id,
        'candidate_sha': candidate_sha,
        'approved_by': approved_by,
        'organization_id': organization_id,
        'reason': str(reason or '')[:1000],
        'recorded_at': _now(),
        'source': 'authenticated_jason_mcp_owner:' + signed['payload']['approval_id'],
        'signed_owner_proof': signed,
    }
    if request_path.exists():
        current = json.loads(request_path.read_text(encoding='utf-8'))
        immutable = ('release_id', 'candidate_sha', 'approved_by', 'organization_id')
        if any(str(current.get(k) or '') != str(payload.get(k) or '') for k in immutable):
            raise ValueError('RELEASE_APPROVAL_PENDING_REQUEST_CONFLICT')
        # Do not replace an existing signed one-use decision or silently
        # upgrade a legacy unsigned request. Its original proof must still
        # be independently checked by the host consumer.
        if not isinstance(current.get('signed_owner_proof'), dict):
            raise ValueError('RELEASE_APPROVAL_EXISTING_REQUEST_UNSIGNED')
        return dict(current)
    _atomic_json(request_path, payload)
    return payload
