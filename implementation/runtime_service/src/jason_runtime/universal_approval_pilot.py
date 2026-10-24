"""Source-reviewed, expiring internal-note acceptance on the existing approval core.

No HTTP endpoint, separate worker, identity, grant, direct provider access or
fabricated decision. An authorized operator issues each exact test once; the
normal live Teams callback and canonical continuation perform the work.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Mapping

CONFIG = Path(__file__).resolve().parents[4] / 'config'
MANIFEST = 'universal-approval-pilot-v1.json'
POLICY = 'universal-approval-internal-pilot-v1.json'
DEFAULT_POLICY = '/var/lib/jason/authority/universal-approval-policy.json'


def load_campaign(config: Path = CONFIG, *, now: datetime | None = None) -> dict | None:
    path = config / MANIFEST
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('invalid bounded pilot manifest')
    doc = json.loads(path.read_text())
    if doc.get('schema_version') != '1.0' or type(doc.get('enabled')) is not bool:
        raise ValueError('invalid pilot activation schema')
    if not doc['enabled']:
        return None
    stamp = datetime.fromisoformat(doc['expires_at'].replace('Z', '+00:00'))
    now = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or now.tzinfo is None:
        raise ValueError('pilot expiration must be timezone-aware')
    if now >= stamp:
        return None
    policy = config / POLICY
    if (doc.get('policy_file') != POLICY or policy.is_symlink()
            or policy.stat().st_size > 65536
            or hashlib.sha256(policy.read_bytes()).hexdigest() != doc.get('policy_sha256')):
        raise ValueError('source-pinned pilot policy digest mismatch')
    if set(doc.get('cases', {})) != {'deny', 'approve'}:
        raise ValueError('pilot must contain exactly the two reviewed cases')
    return doc


def settings_defaults(environ: Mapping[str, str], config: Path = CONFIG, *, now=None) -> tuple[str, str]:
    # Explicit OFF in isolated preproduction always wins. This never modifies
    # deployment environment or widens an existing operator-selected policy.
    if 'JASON_UNIVERSAL_APPROVAL_MODE' in environ:
        return (environ['JASON_UNIVERSAL_APPROVAL_MODE'].strip().lower(),
                environ.get('JASON_UNIVERSAL_APPROVAL_POLICY', DEFAULT_POLICY))
    if re.fullmatch(r'[0-9a-f]{40}', environ.get('JASON_SOURCE_REVISION', '')) is None:
        return 'off', DEFAULT_POLICY
    campaign = load_campaign(config, now=now)
    if campaign is None:
        return 'off', DEFAULT_POLICY
    return 'enforced', str(config / POLICY)


def issue_case(app, campaign: dict, case: str) -> dict:
    from autonomous_remediation.autonomous_principal import AutonomousPrincipal
    from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
    from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
    if case not in {'deny', 'approve'}:
        raise ValueError('unknown pilot case')
    handler = app.universal_approval_handler
    if handler is None or handler.issuer is None:
        raise PermissionError('reviewed approval pilot is not active')
    item = campaign['cases'][case]
    approval_id = item['approval_id']
    existing = handler.requests.progress(approval_id)
    if existing is not None:
        return {'approval_id': approval_id, 'status': existing['state'], 'reissued': False}
    pending = handler.service.teams_flow.approval_service.repository.get(approval_id)
    if pending is not None:
        return {'approval_id': approval_id, 'status': pending.status.value, 'reissued': False}
    if case == 'approve':
        denied = handler.service.teams_flow.approval_service.repository.get(
            campaign['cases']['deny']['approval_id'])
        if denied is None or denied.status.value != 'denied':
            raise PermissionError('the real Deny/no-action case must finish first')
    request = OrchestrationRequest(
        execution_id=item['execution_id'], correlation_id=item['execution_id'],
        principal_id=campaign['requester_id'], organization_id=campaign['organization_id'],
        capability_name=item['capability'], capability_version=None,
        requested_mode='deterministic', orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=False, approval_present=False, risk='low',
        data_handling=DataHandlingPolicy('internal', False, retention_allowed=True),
        budget=ExecutionBudget(Decimal('0.01'), maximum_attempts=1),
        arguments=item['arguments'], client_id=item.get('client_id'), permission_mode='execute',
        requester_kind='service', principal_attributes={'workload': campaign['requester_id']},
    )
    issuer = replace(handler.issuer, approval_id_factory=lambda: approval_id)
    return issuer.submit_service_plan(
        requests=(request,), principal=AutonomousPrincipal(
            campaign['requester_id'], campaign['organization_id']),
        title=item['title'], summary=item['summary'], production=True, ttl_seconds=1800)


def main() -> int:
    parser = argparse.ArgumentParser(description='Issue or inspect the exact internal Teams pilot')
    parser.add_argument('action', choices=('deny', 'approve', 'status'))
    args = parser.parse_args()
    campaign = load_campaign()
    if campaign is None:
        raise PermissionError('source-reviewed pilot is disabled or expired')
    from .composition import RuntimeSettings, build_runtime_application
    settings = RuntimeSettings.from_env()
    if settings.universal_approval_mode != 'enforced' or settings.universal_approval_policy != CONFIG / POLICY:
        raise PermissionError('active runtime is not using the exact source-reviewed pilot policy')
    app = build_runtime_application(settings)
    if args.action == 'status':
        handler = app.universal_approval_handler
        result = {case: handler.requests.progress(item['approval_id'])
                  for case, item in campaign['cases'].items()}
    else:
        result = issue_case(app, campaign, args.action)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
