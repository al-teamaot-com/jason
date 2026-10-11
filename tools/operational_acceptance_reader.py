"""Read owner-issued, signed, scope-bound operational acceptance receipts.

The trust store and receipts are protected inputs provisioned out of band.
This reader never creates a key, approval, or acceptance receipt.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ID = re.compile(r"^acceptance-[a-z0-9][a-z0-9-]{2,63}$")
KEY = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def verify_acceptance(receipt: Mapping[str, Any], trust: Mapping[str, Any], *,
                      identity: str, issue_number: int, now: datetime | None = None) -> dict[str, Any] | None:
    """Check protected issuer allowlist, signed payload, scope, expiry and revocation."""
    if not ID.fullmatch(identity) or issue_number <= 0:
        return None
    if not isinstance(receipt, Mapping) or not isinstance(trust, Mapping):
        return None
    issuer = receipt.get('issuer')
    trusted = trust.get('issuers')
    if not isinstance(issuer, str) or not KEY.fullmatch(issuer) or not isinstance(trusted, Mapping):
        return None
    pub = trusted.get(issuer)
    revoked = trust.get('revoked_receipts', [])
    if not isinstance(pub, str) or not isinstance(revoked, list):
        return None
    body = receipt.get('payload')
    if not isinstance(body, Mapping) or body.get('identity') != identity or body.get('state') != 'operationally_accepted':
        return None
    if body.get('issue_number') != issue_number or not isinstance(body.get('evidence_ref'), str) or not body['evidence_ref'].strip():
        return None
    receipt_id = body.get('receipt_id')
    if not isinstance(receipt_id, str) or not KEY.fullmatch(receipt_id) or receipt_id in revoked:
        return None
    issued = _parse_time(body.get('issued_at'))
    expires = _parse_time(body.get('expires_at'))
    current = now or datetime.now(timezone.utc)
    if not issued or not expires or issued > current or expires <= current or expires <= issued:
        return None
    if (expires - issued).total_seconds() > 31 * 86400:
        return None
    try:
        # Payload is canonical JSON with stable key sorting: issuer and payload are signed together.
        message = json.dumps({'issuer': issuer, 'payload': body}, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub, validate=True)).verify(
            base64.b64decode(receipt.get('signature', ''), validate=True), message)
    except (ValueError, TypeError, KeyError):
        return None
    except Exception:
        return None
    return {'identity': identity, 'state': 'operationally_accepted',
            'authority_verified': True, 'evidence_ref': body['evidence_ref']}


def accepted_operational_dependencies(root: Path, identities: list[str], issue_number: int) -> dict[str, Any]:
    """Protected receipt directory: no traversal, unknown issuers fail closed."""
    try:
        trust = json.loads((root / 'trust.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    accepted = {}
    for identity in sorted(set(identities))[:12]:
        if not isinstance(identity, str) or not ID.fullmatch(identity):
            continue
        try:
            receipt = json.loads((root / 'receipts' / (identity + '.json')).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        verified = verify_acceptance(receipt, trust, identity=identity, issue_number=issue_number)
        if verified:
            accepted[identity] = verified
    return accepted
