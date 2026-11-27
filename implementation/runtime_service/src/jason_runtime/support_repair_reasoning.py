from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from connectors.core.contracts import ConnectorTransportError


DEFAULT_SPOOL = Path('/var/lib/jason/openclaw/support-repair')
_ALLOWED_KINDS = {'search_plan', 'edit_plan', 'acceptance_review'}
_BILLING_ERRORS = {
    'credit_balance_exhausted': 'restore_provider_credits',
    'organization_spend_limit_exceeded': 'review_organization_spend_limit',
    'project_spend_limit_exceeded': 'review_project_spend_limit',
    'organization_usage_limit_exceeded': 'review_provider_usage_limit',
    'insufficient_quota': 'review_provider_billing_or_quota',
}
logger = logging.getLogger(__name__)


def _billing_blocker(exc: BaseException) -> str | None:
    if not isinstance(exc, ConnectorTransportError):
        return None
    code = exc.provider_error_code
    if code in _BILLING_ERRORS:
        return code
    return 'insufficient_quota' if exc.provider_error_type == 'insufficient_quota' else None


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
        'required': ['summary', 'edits', 'test_paths', 'blocked_reason', 'evidence_requests'],
        'properties': {
            'evidence_requests': {
                'type': 'array', 'maxItems': 3,
                'items': {
                    'type': 'object', 'additionalProperties': False,
                    'required': ['tool', 'query', 'path'],
                    'properties': {
                        'tool': {'type': 'string', 'enum': ['search_source', 'read_source']},
                        'query': {'anyOf': [{'type': 'string', 'minLength': 3, 'maxLength': 100},
                                           {'type': 'null'}]},
                        'path': {'anyOf': [{'type': 'string', 'minLength': 1, 'maxLength': 240},
                                          {'type': 'null'}]},
                    },
                },
            },
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


def _local_edit_schema() -> dict[str, Any]:
    schema = _edit_schema()
    # Encode the tool/argument relationship in the generation grammar, not
    # merely natural-language instructions. The host still independently
    # validates tracked path, source policy, symbols and remaining budgets.
    def tool_branch(tool, query, path):
        return {
            'type': 'object', 'additionalProperties': False,
            'required': ['tool', 'query', 'path'],
            'properties': {
                'tool': {'type': 'string', 'enum': [tool]},
                'query': query, 'path': path,
            },
        }
    search = tool_branch('search_source',
        {'type': 'string', 'minLength': 3, 'maxLength': 100},
        {'type': 'null'})
    read = tool_branch('read_source',
        {'anyOf': [
            {'type': 'string', 'minLength': 1, 'maxLength': 100,
             'pattern': '^[A-Za-z_][A-Za-z0-9_]*$'},
            {'type': 'null'}]},
        {'type': 'string', 'minLength': 1, 'maxLength': 240})
    schema['properties']['evidence_requests']['items'] = {
        'anyOf': [search, read]}
    return schema


def _validate_local_edit_result(result: Mapping[str, Any]) -> None:
    # Explicitly retain validation even if a backend grammar implementation
    # ignores regex or nested union constraints. Never rewrite model requests
    # to target a file the model did not explicitly supply.
    from jsonschema import Draft202012Validator
    if not Draft202012Validator(_local_edit_schema()).is_valid(result):
        raise ValueError('local engineering tool or patch contract invalid')
    calls = result['evidence_requests']
    if calls and (result['edits'] or result['test_paths'] or result['blocked_reason']):
        raise ValueError('local engineering evidence request mixed with terminal output')
    for call in calls:
        if call['tool'] == 'read_source':
            path = call['path']
            if (re.fullmatch(r'[A-Za-z0-9_./-]+', path) is None
                    or Path(path).is_absolute()
                    or any(part.startswith('.') or part == '..' for part in path.split('/'))
                    or any(not part for part in path.split('/'))):
                raise ValueError('local engineering source path invalid')
        elif (' OR ' in call['query'] or ' AND ' in call['query']
                or '\\n' in call['query']):
            raise ValueError('local engineering search must contain one bounded term')


LOCAL_ENGINEERING_MAX_PROMPT_BYTES = 16000
_LOCAL_SOURCE_PROJECTION_KEY = 'local_source_projection'


def _prompt_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def bounded_local_source_prompt(
    document: Mapping[str, Any], *, max_bytes: int,
) -> tuple[str, dict[str, Any] | None]:
    """Bound model input without rewriting the immutable governed request.

    Preserve every non-excerpt field, including approved scope and evidence
    receipts. Retain exact complete excerpt bytes, never fabricate a truncated
    source anchor. Omitted paths remain discoverable through the existing
    governed source-evidence loop. No model-controlled tool is executed here.
    """
    original = _prompt_json(document)
    size = len(original.encode('utf-8'))
    if size <= max_bytes:
        return original, None
    source = document.get('context')
    if not isinstance(source, Mapping) or _LOCAL_SOURCE_PROJECTION_KEY in source:
        raise ValueError('local reasoning context cannot be safely projected')
    excerpts = source.get('source_excerpts')
    if not isinstance(excerpts, list) or not excerpts:
        raise ValueError('local reasoning input exceeds bounded non-source context')
    paths = []
    for entry in excerpts:
        if (not isinstance(entry, Mapping)
                or not isinstance(entry.get('path'), str)
                or not 1 <= len(entry['path']) <= 240
                or not isinstance(entry.get('content'), str)
                or entry['path'] in paths):
            raise ValueError('local reasoning source inventory is invalid')
        paths.append(entry['path'])
    base = dict(source)
    base['source_excerpts'] = []
    projection = {'omitted_source_paths': list(paths),
                  'all_supplied_excerpts_are_complete': True}
    base[_LOCAL_SOURCE_PROJECTION_KEY] = projection
    projected = dict(document)
    projected['context'] = base
    # Existing source evidence ordering already prioritizes explicit recent
    # read_source receipts. Do not discard the receipt or replace an excerpt.
    current = _prompt_json(projected)
    if len(current.encode('utf-8')) > max_bytes:
        raise ValueError('local reasoning input exceeds bounded non-source context')
    for entry in excerpts:
        base['source_excerpts'].append(dict(entry))
        projection['omitted_source_paths'].remove(entry['path'])
        candidate = _prompt_json(projected)
        if len(candidate.encode('utf-8')) <= max_bytes:
            current = candidate
        else:
            base['source_excerpts'].pop()
            projection['omitted_source_paths'].append(entry['path'])
            current = _prompt_json(projected)
    projected_size = len(current.encode('utf-8'))
    if projected_size > max_bytes:
        raise ValueError('local reasoning source projection exceeded its budget')
    return current, {
        'original_prompt_bytes': size,
        'projected_prompt_bytes': projected_size,
        'omitted_source_count': len(projection['omitted_source_paths']),
        'original_request_unchanged': True,
    }


class SupportRepairReasoningMaintenance:
    """Convert bounded repair evidence into non-executing repository edit proposals.

    The model receives source excerpts and CI evidence only. It has no filesystem,
    GitHub, shell, provider, secret, or deployment handles. A separate host worker
    deterministically validates every proposed path and exact-text replacement.
    """

    def __init__(self, *, structured_client, fallback_structured_client=None, spool: Path = DEFAULT_SPOOL, interval_seconds: int = 5, now=None, local_prompt_max_bytes: int | None = None) -> None:
        if interval_seconds < 1:
            raise ValueError('support repair reasoning interval must be positive')
        if local_prompt_max_bytes is not None:
            if not 12000 <= local_prompt_max_bytes <= 32000:
                raise ValueError('local engineering prompt budget is invalid')
            if fallback_structured_client is not None:
                raise ValueError('local engineering reasoning cannot use fallback')
        self.local_prompt_max_bytes = local_prompt_max_bytes
        self.structured_client = structured_client
        self.fallback_structured_client = fallback_structured_client
        self.spool = Path(spool)
        self.interval_seconds = int(interval_seconds)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.next_due_at: datetime | None = None
        self.attempt_diagnostics: dict[str, Any] = {}

    def local_route_evidence(self) -> dict[str, Any] | None:
        from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
        from orchestrator.model_runtime_adapter import (
            ModelRuntimeAdapter, ollama_extended_generation_schema,
            validate_extended_local_result,
        )
        adapter = self.structured_client
        if (self.local_prompt_max_bytes is None
                or self.fallback_structured_client is not None
                or not isinstance(adapter, ModelRuntimeAdapter)
                or adapter.schema_adapter is not ollama_extended_generation_schema
                or adapter.result_adapter is not validate_extended_local_result
                or not isinstance(adapter.client, OllamaStructuredJsonClient)):
            return None
        client = adapter.client
        if (client.base_url.rstrip('/') != 'http://jason-ollama:11434'
                or client.model not in ('qwen3:1.7b', 'qwen3.5:4b', 'qwen3.5:9b')
                or client.output_token_limit != 4096
                or client.context_tokens != 32768):
            return None
        return {
            'profile': 'bounded_local_engineering_v1',
            'model': client.model,
            'endpoint': 'http://jason-ollama:11434',
            'canonical_schema_validated': True,
            'hosted_fallback': False,
        }

    def _validate_request(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(raw.get('kind') or '').strip()
        support_item = str(raw.get('support_item') or '').strip().upper()
        if kind not in _ALLOWED_KINDS:
            raise ValueError('unsupported support/development reasoning kind')
        is_support = support_item.startswith('SUPPORT-')
        is_development = bool(re.fullmatch(r'DEV-[1-9][0-9]*', support_item))
        if (not is_support and not is_development) or len(support_item) > 80:
            raise ValueError('invalid governed work item')
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
        self.attempt_diagnostics = {}
        kind = str(request['kind'])
        context = request.get('context') or {}
        is_development = str(request['support_item']).startswith('DEV-')
        if kind == 'search_plan':
            if is_development:
                system = (
                    'You are the bounded Project Jason owner-approved development diagnostician. '
                    'The supplied issue text is the maximum approved implementation scope. '
                    'Return search terms that help a deterministic host worker locate the smallest source area needed to implement that scope. '
                    'A new capability or workflow may be proposed only when the approved issue explicitly asks for it. '
                    'Do not propose credentials, secret access, authority beyond the issue, governance bypasses, disruptive provider actions, or production deployment. '
                    'If the issue is ambiguous or requires authority not explicitly approved, set blocked_reason.'
                )
            else:
                system = (
                    'You are the bounded Project Jason support-repair diagnostician. '
                    'Return search terms that help a deterministic host worker locate the smallest source area for this defect. '
                    'Do not propose shell commands, credentials, authority changes, security bypasses, or deployment actions. '
                    'Diagnosing existing software code and proposing bounded regression-tested fixes does not itself require production, root, or provider-write authority. '
                    'A defect mentioning root-governed release, rollback, or privileged verification is not by itself grounds to block source-only diagnosis. '
                    'Do not request new authority, constitutional changes, secrets, service restarts, or production deployment. '
                    'Set blocked_reason only when the proposed SOURCE-ONLY diagnosis inherently cannot proceed without such an action. '
                )
            if context.get('scope_review') == 'source_diagnosis_only' and not is_development:
                system += (
                    ' This is one bounded second assessment after an earlier model-only block. '
                    'Assess whether safe source investigation can begin without executing privileged actions. '
                    'Do not infer that permission to inspect and propose source patches authorizes deployment. '
                    'Return a blocked_reason if even source-only work truly needs unapproved authority, or if scope is genuinely ambiguous. '
                    'Otherwise return specific repository search terms; the host will independently enforce eligibility.'
                )
            schema = _search_schema()
        elif kind == 'edit_plan':
            if is_development:
                system = (
                    'You are the bounded Project Jason owner-approved development patch proposer. '
                    'Use only the supplied repository excerpts and approved issue scope. '
                    'Return exact-text replacements; do not invent unseen surrounding code. '
                    'For test_paths return exact changed repository-relative test file paths, not pytest node IDs or shell commands. '
                    'Implement the smallest complete change plus regression tests. '
                    'Do not add credentials, broaden authority beyond the issue, weaken security/governance, bypass existing controls, or perform deployment. '
                    'If additional repository source is needed, request up to three read-only evidence_requests instead of guessing or blocking: '
                    'search_source with query and null path, or read_source with a tracked path and either a single exact function identifier (e.g. audit_support_admission) or null. Never put descriptions, comma-separated lists, shell syntax, or prose into read_source query. For two functions make two read_source requests. '
                    'In a tool request turn return empty edits/test_paths and null blocked_reason. '
                    'The independent governed host checks every path and tool. Return an empty evidence_requests array for final edits or a real blocker. '
                    'If a safe exact replacement still cannot be formed after tool evidence, set blocked_reason and return no edits.'
                )
            else:
                system = (
                    'You are the bounded Project Jason repair patch proposer. '
                    'Use only the supplied repository excerpts and failure evidence. '
                    'Return exact-text replacements; do not invent unseen surrounding code. '
                    'For test_paths return exact changed repository-relative test file paths, not pytest node IDs or shell commands. '
                    'Prefer the smallest repair plus regression test. Do not modify governance, authority, security, credentials, dependencies, workflows, deployment, or infrastructure. '
                    'If source context is insufficient, return up to three read-only evidence_requests: '
                    'search_source(query with null path), or read_source(tracked path with one exact function identifier or null). Never place prose, multiple names, line numbers or commands into read_source query. Use two separate requests for two symbols. '
                    'Do not request commands or provider operations. For tool requests return empty edits/test_paths and null blocked_reason; '
                    'for final edits or a genuine block return an empty evidence_requests array. '
                    'Do not invent unseen code, and do not weaken governance.'
                )
            if is_development and context.get('final_evidence_turn') is True:
                system += (
                    ' This is the LAST authorized source-evidence turn. '
                    'The independent host has exhausted its bounded read-only evidence budget: '
                    'DO NOT return any evidence_requests. '
                    'Use only the supplied, pinned, policy-eligible source excerpts to '
                    'propose a narrowly scoped exact-text code AND regression-test patch; '
                    'if the source is still insufficient, return no edits and set '
                    'blocked_reason to the precise missing source and why it is needed. '
                    'Do not guess unseen text, fabricate success, or ask for more tools.'
                )
            schema = _edit_schema()
            if self.local_prompt_max_bytes is not None:
                schema = _local_edit_schema()
                system += (
                    ' Tool argument examples (illustrative only; choose actual '
                    'relevant source): {"tool":"search_source","query":"function_name","path":null}; '
                    '{"tool":"read_source","query":"function_name","path":"implementation/example.py"}. '
                    'Never put a file path, colon, parentheses or more than one '
                    'function in read_source query. Use one search term per '
                    'search_source call; do not join queries with OR or AND.'
                )
        else:
            system = (
                'You are the Project Jason governed production-acceptance reviewer. '
                'Decide only whether the explicit acceptance criteria are directly proven by the supplied production evidence. '
                'CI success, merge, deployment, or generic health are not proof of provider-specific behavior unless the acceptance criteria require only those facts. '
                'Never infer missing live evidence. If any criterion lacks direct evidence, verified must be false and missing_evidence must state exactly what remains.'
            )
            schema = _acceptance_schema()

        document = {
            'support_item': request['support_item'],
            'title': request['title'],
            'evidence': request['evidence'],
            'acceptance': request['acceptance'],
            'context': context,
        }
        user = _prompt_json(document)
        if self.local_prompt_max_bytes is not None and kind == 'edit_plan':
            user, projection = bounded_local_source_prompt(
                document, max_bytes=self.local_prompt_max_bytes)
            if projection is not None:
                self.attempt_diagnostics['local_source_projection'] = projection
                system += (
                    ' The model-only context is byte-budgeted. The supplied source '
                    'excerpts are exact complete excerpts, not necessarily whole files. '
                    'The local_source_projection omitted_source_paths list identifies '
                    'excerpts omitted from this prompt, NOT files known to contain '
                    'the defect. Never guess omitted code. Use the existing '
                    'read-only evidence_requests mechanism to request one exact '
                    'function or a targeted source search if necessary, respecting '
                    'the host evidence-turn limit. If a final evidence turn lacks '
                    'the needed exact source, return a specific blocker, not edits.'
                )
        try:
            result = self.structured_client.complete(
                system=system,
                user=user,
                schema=schema,
                max_output_tokens=4096,
            )
            if self.local_prompt_max_bytes is not None and kind == 'edit_plan':
                _validate_local_edit_result(result)
            return result
        except ConnectorTransportError as exc:
            billing = _billing_blocker(exc)
            if billing:
                self.attempt_diagnostics = {
                    'primary_provider_error_code': billing,
                    'primary_http_status': exc.status_code,
                    'required_owner_action': _BILLING_ERRORS[billing],
                }
                logger.error('REASONING_DEPENDENCY_BLOCKED code=%s action=%s',
                             billing, _BILLING_ERRORS[billing])
            transient = exc.status_code is None or exc.status_code in {408, 425, 429, 500, 502, 503, 504}
            # Patch-plan HTTP 400 is a non-retriable hosted request rejection, but
            # the existing isolated local model can independently propose edits.
            # This does not repeat the rejected hosted request or bypass host-side
            # exact-text validation, tests, approval, or release governance.
            local_patch_fallback = kind == 'edit_plan' and exc.status_code == 400
            if self.fallback_structured_client is None or not (transient or local_patch_fallback):
                raise
            try:
                result = self.fallback_structured_client.complete(
                    system=system, user=user, schema=schema, max_output_tokens=1024)
                self.attempt_diagnostics['fallback_status'] = 'succeeded'
                return result
            except Exception as fallback_error:
                self.attempt_diagnostics['fallback_status'] = 'failed'
                self.attempt_diagnostics['fallback_error_type'] = type(fallback_error).__name__
                if billing:
                    # A slow or broken fallback must never overwrite an actionable
                    # primary billing/credit error with generic network failure.
                    raise exc from fallback_error
                raise

    @staticmethod
    def _request_kind_from_file(path: Path) -> str:
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            return str(raw.get('kind') or '') if isinstance(raw, Mapping) else ''
        except (OSError, ValueError, json.JSONDecodeError):
            return ''

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
        def should_process(path: Path) -> bool:
            response_path = response_dir / path.name
            if not response_path.exists():
                return True
            try:
                prior = json.loads(response_path.read_text(encoding='utf-8'))
            except (OSError, ValueError, json.JSONDecodeError):
                return False
            if not isinstance(prior, Mapping) or prior.get('status') != 'failed':
                return False
            if prior.get('retryable') is False or prior.get('primary_provider_error_code') in _BILLING_ERRORS:
                return False
            attempts = int(prior.get('attempts') or 0)
            error = str(prior.get('error') or '')
            transient = (
                prior.get('error_type') == 'ConnectorTransportError'
                and (
                    'status 429' in error
                    or any(f'status {code}' in error for code in (408, 425, 500, 502, 503, 504))
                    or 'status ' not in error
                    or ('status 400' in error and self.fallback_structured_client is not None
                        and self._request_kind_from_file(path) == 'edit_plan')
                )
            )
            fallback_budget_mismatch = (
                prior.get('error_type') == 'ValueError'
                and error == 'Ollama structured reasoning output budget is invalid'
            )
            return (transient or fallback_budget_mismatch) and attempts < 2

        pending = [
            path
            for path in sorted(request_dir.glob('*.json'))
            if should_process(path)
        ]
        for path in pending[:4]:
            response_path = response_dir / path.name
            prior_attempts = 0
            if response_path.exists():
                try:
                    prior_payload = json.loads(response_path.read_text(encoding='utf-8'))
                    if isinstance(prior_payload, Mapping):
                        prior_attempts = int(prior_payload.get('attempts') or 0)
                except (OSError, ValueError, json.JSONDecodeError):
                    prior_attempts = 0
            self.attempt_diagnostics = {}
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
                local_route = self.local_route_evidence()
                if local_route is not None:
                    payload['non_metered_reasoning'] = local_route
            except Exception as exc:
                payload = {
                    'status': 'failed',
                    'request_id': path.stem,
                    'error_type': type(exc).__name__,
                    'transport_failure_code': (
                        exc.provider_error_code
                        if isinstance(exc, ConnectorTransportError) and exc.provider_error_code in {
                            'DNS_RESOLUTION', 'NETWORK_TIMEOUT', 'TLS_FAILURE',
                            'CONNECTION_REFUSED', 'NETWORK_UNREACHABLE',
                            'NETWORK_IO_FAILURE',
                        }
                        else None
                    ),
                    'error': str(exc)[:800],
                    'attempts': prior_attempts + 1,
                    'completed_at': _now(),
                }
            payload.update(self.attempt_diagnostics)
            billing = payload.get('primary_provider_error_code')
            if payload['status'] == 'failed' and billing in _BILLING_ERRORS:
                payload['retryable'] = False
                payload['error'] = 'Hosted reasoning blocked: '+billing+'; Owner action: '+_BILLING_ERRORS[billing]
            _atomic_json(response_path, payload)
            processed = True
        return processed


def build_support_repair_reasoning_maintenance(*, enabled: bool, structured_client, fallback_structured_client=None, spool: Path = DEFAULT_SPOOL, local_prompt_max_bytes: int | None = None):
    if not enabled or structured_client is None:
        return None
    return SupportRepairReasoningMaintenance(
        structured_client=structured_client,
        fallback_structured_client=fallback_structured_client,
        spool=spool,
        interval_seconds=int(os.getenv('JASON_SUPPORT_REPAIR_REASONING_INTERVAL_SECONDS', '5')),
        local_prompt_max_bytes=local_prompt_max_bytes,
    )
