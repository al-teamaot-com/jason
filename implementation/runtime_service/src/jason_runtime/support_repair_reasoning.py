from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SPOOL = Path('/var/lib/jason/openclaw/support-repair')
_ALLOWED_KINDS = {'search_plan', 'edit_plan', 'acceptance_review'}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('x', encoding='utf-8') as handle:
        os.chmod(temp, 0o600)
        handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _request_id(payload: Mapping[str, Any]) -> str:
    material = {
        key: payload.get(key)
        for key in ('kind', 'support_item', 'title', 'evidence', 'acceptance', 'context')
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    ).hexdigest()


def _search_schema() -> dict[str, Any]:
    return {
        'type': 'object',
        'additionalProperties': False,
        'required': ['diagnosis', 'search_terms', 'blocked_reason'],
        'properties': {
            'diagnosis': {'type': 'string', 'maxLength': 1200},
            'search_terms': {
                'type': 'array',
                'minItems': 1,
                'maxItems': 8,
                'items': {'type': 'string', 'minLength': 2, 'maxLength': 80},
            },
            'blocked_reason': {'anyOf': [{'type': 'string', 'maxLength': 1000}, {'type': 'null'}]},
        },
    }


def _acceptance_schema() -> dict[str, Any]:
    return {
        'type': 'object',
        'additionalProperties': False,
        'required': ['verified', 'reason', 'missing_evidence', 'evidence_used'],
        'properties': {
            'verified': {'type': 'boolean'},
            'reason': {'type': 'string', 'maxLength': 1600},
            'missing_evidence': {
                'type': 'array',
                'maxItems': 12,
                'items': {'type': 'string', 'maxLength': 300},
            },
            'evidence_used': {
                'type': 'array',
                'maxItems': 12,
                'items': {'type': 'string', 'maxLength': 300},
            },
        },
    }


def _edit_schema() -> dict[str, Any]:
    return {
        'type': 'object',
        'additionalProperties': False,
        'required': ['summary', 'edits', 'test_paths', 'blocked_reason'],
        'properties': {
            'summary': {'type': 'string', 'maxLength': 1600},
            'edits': {
                'type': 'array',
                'maxItems': 12,
                'items': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['path', 'old_text', 'new_text'],
                    'properties': {
                        'path': {'type': 'string', 'minLength': 1, 'maxLength': 240},
                        'old_text': {'type': 'string', 'minLength': 1, 'maxLength': 12000},
                        'new_text': {'type': 'string', 'maxLength': 16000},
                    },
                },
            },
            'test_paths': {
                'type': 'array',
                'maxItems': 12,
                'items': {'type': 'string', 'minLength': 1, 'maxLength': 240},
            },
            'blocked_reason': {'anyOf': [{'type': 'string', 'maxLength': 1200}, {'type': 'null'}]},
        },
    }


class SupportRepairReasoningMaintenance:
    """Convert bounded repair evidence into non-executing repository edit proposals.

    The model receives source excerpts and CI evidence only. It has no filesystem,
    GitHub, shell, provider, secret, or deployment handles. A separate host worker
    deterministically validates every proposed path and exact-text replacement.
    """

    def __init__(self, *, structured_client, spool: Path = DEFAULT_SPOOL, interval_seconds: int = 5, now=None) -> None:
        if interval_seconds < 1:
            raise ValueError('support repair reasoning interval must be positive')
        self.structured_client = structured_client
        self.spool = Path(spool)
        self.interval_seconds = int(interval_seconds)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.next_due_at: datetime | None = None

    def _validate_request(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(raw.get('kind') or '').strip()
        support_item = str(raw.get('support_item') or '').strip().upper()
        if kind not in _ALLOWED_KINDS:
            raise ValueError('unsupported support repair reasoning kind')
        if not support_item.startswith('SUPPORT-') or len(support_item) > 80:
            raise ValueError('invalid support item')
        payload = {
            'kind': kind,
            'support_item': support_item,
            'title': str(raw.get('title') or '')[:500],
            'evidence': str(raw.get('evidence') or '')[:5000],
            'acceptance': str(raw.get('acceptance') or '')[:5000],
            'context': raw.get('context') if isinstance(raw.get('context'), Mapping) else {},
        }
        expected = _request_id(payload)
        if str(raw.get('request_id') or '') != expected:
            raise ValueError('support repair reasoning request fingerprint mismatch')
        return payload | {'request_id': expected}

    def _complete(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        kind = str(request['kind'])
        context = request.get('context') or {}
        if kind == 'search_plan':
            system = (
                'You are the bounded Project Jason support-repair diagnostician. '
                'Return search terms that help a deterministic host worker locate the smallest source area for this defect. '
                'Do not propose shell commands, credentials, authority changes, security bypasses, or deployment actions. '
                'If the defect inherently requires new authority, constitutional change, secret access, or disruptive behavior, set blocked_reason.'
            )
            schema = _search_schema()
        elif kind == 'edit_plan':
            system = (
                'You are the bounded Project Jason repair patch proposer. '
                'Use only the supplied repository excerpts and failure evidence. '
                'Return exact-text replacements; do not invent unseen surrounding code. '
                'Prefer the smallest repair plus regression test. Do not modify governance, authority, security, credentials, dependencies, workflows, deployment, or infrastructure. '
                'If a safe exact replacement cannot be formed from supplied excerpts, set blocked_reason and return no edits.'
            )
            schema = _edit_schema()
        else:
            system = (
                'You are the Project Jason support production-acceptance reviewer. '
                'Decide only whether the explicit acceptance criteria are directly proven by the supplied production evidence. '
                'CI success, merge, deployment, or generic health are not proof of provider-specific behavior unless the acceptance criteria require only those facts. '
                'Never infer missing live evidence. If any criterion lacks direct evidence, verified must be false and missing_evidence must state exactly what remains.'
            )
            schema = _acceptance_schema()

        user = json.dumps(
            {
                'support_item': request['support_item'],
                'title': request['title'],
                'evidence': request['evidence'],
                'acceptance': request['acceptance'],
                'context': context,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return self.structured_client.complete(
            system=system,
            user=user,
            schema=schema,
            max_output_tokens=4096,
        )

    def tick(self) -> bool:
        current = self.now()
        if self.next_due_at is not None and current < self.next_due_at:
            return False
        self.next_due_at = current + timedelta(seconds=self.interval_seconds)

        request_dir = self.spool / 'reasoning' / 'requests'
        response_dir = self.spool / 'reasoning' / 'responses'
        request_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        response_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        processed = False
        pending = [
            path
            for path in sorted(request_dir.glob('*.json'))
            if not (response_dir / path.name).exists()
        ]
        for path in pending[:4]:
            response_path = response_dir / path.name
            try:
                raw = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(raw, Mapping):
                    raise ValueError('request must be a mapping')
                request = self._validate_request(raw)
                result = dict(self._complete(request))
                payload = {
                    'status': 'succeeded',
                    'request_id': request['request_id'],
                    'kind': request['kind'],
                    'support_item': request['support_item'],
                    'result': result,
                    'completed_at': _now(),
                }
            except Exception as exc:
                payload = {
                    'status': 'failed',
                    'request_id': path.stem,
                    'error_type': type(exc).__name__,
                    'error': str(exc)[:800],
                    'completed_at': _now(),
                }
            _atomic_json(response_path, payload)
            processed = True
        return processed


def build_support_repair_reasoning_maintenance(*, enabled: bool, structured_client, spool: Path = DEFAULT_SPOOL):
    if not enabled or structured_client is None:
        return None
    return SupportRepairReasoningMaintenance(
        structured_client=structured_client,
        spool=spool,
        interval_seconds=int(os.getenv('JASON_SUPPORT_REPAIR_REASONING_INTERVAL_SECONDS', '5')),
    )
