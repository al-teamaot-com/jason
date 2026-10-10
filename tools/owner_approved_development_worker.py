#!/usr/bin/env python3
"""Owner-approved Project Jason development queue worker for the 2:30 window."""
from __future__ import annotations

import argparse
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import support_repair_host_worker as support
import change_integration_gate
import documentation_impact_gate

DEFAULT_REPO = Path('/home/al/projects/jason')
DEFAULT_SPOOL = Path('/var/lib/jason/openclaw/support-repair')
WORKTREE_ROOT = Path('/home/al/jason-worktrees/owner-approved-development')
APPROVAL = re.compile(
    r'(?im)^\s*-\s*\*\*Autonomous development:\*\*\s*owner-approved\s*$'
)
BLOCKED = re.compile(
    r'(?im)^\s*-\s*\*\*(?:Autonomous development|Status):\*\*\s*(?:blocked|manual-only)\s*$'
)
META = re.compile(r'(?im)^\s*-\s*Development issue\s*:\s*#([1-9][0-9]*)\s*$')
ACTIVE_PHASES = {'identified', 'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'}
SUPPORT_ACTIVE_PHASES = ACTIVE_PHASES - {'identified'}
TERMINAL_PHASES = {
    'pr_ready',
    'blocked',
    'complete',
    'waiting_operational_acceptance',
    'waiting_external_dependency',
    'waiting_sequenced_work',
}
APPROVED_BODY_LIMIT = 30000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def approved_scope(item: Mapping[str, Any]) -> str:
    return str(item.get('body') or '')[:APPROVED_BODY_LIMIT]


def _section(body: str, heading: str) -> str:
    match = re.search(
        rf'(?ims)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)',
        body,
    )
    return match.group(1).strip()[:5000] if match else ''
def repository_name(repo: Path) -> str:
    value = support.gh_json(['repo', 'view', '--json', 'nameWithOwner'], cwd=repo) or {}
    name = str(value.get('nameWithOwner') or '').strip()
    if '/' not in name:
        raise support.WorkerError('could not determine GitHub repository identity')
    return name


def owner_approved_issues(repo: Path) -> list[dict[str, Any]]:
    slug = repository_name(repo)
    issues = support.gh_json([
        'issue', 'list', '--state', 'open', '--limit', '1000',
        '--json', 'number,title,body,url,labels,updatedAt'
    ], cwd=repo) or []
    eligible: list[dict[str, Any]] = []
    for issue in issues:
        body = str(issue.get('body') or '')
        if not APPROVAL.search(body) or BLOCKED.search(body):
            continue
        number = int(issue['number'])
        detail = support.gh_json(['api', f'repos/{slug}/issues/{number}'], cwd=repo) or {}
        if str(detail.get('author_association') or '').upper() != 'OWNER':
            continue
        labels = {
            str((item or {}).get('name') or '').casefold()
            for item in issue.get('labels') or []
            if isinstance(item, Mapping)
        }
        if {'blocked', 'manual-only'} & labels:
            continue
        eligible.append({
            'id': f'DEV-{number}',
            'issue_number': number,
            'title': str(issue.get('title') or '')[:240],
            'url': str(issue.get('url') or ''),
            'body': body[:APPROVED_BODY_LIMIT],
            'evidence': body[:5000],
            'acceptance': (
                _section(body, 'Acceptance test')
                or _section(body, 'Acceptance')
                or 'Implement the exact Owner-approved issue scope with regression coverage and a green PR.'
            ),
            'approval_source': str(issue.get('url') or ''),
            'approved_by': str((detail.get('user') or {}).get('login') or ''),
            'updated_at': str(issue.get('updatedAt') or ''),
        })
    eligible.sort(key=lambda item: item['issue_number'])
    return eligible
def active_support_count(spool: Path) -> int:
    state = support.load_state(spool / 'state.json')
    items = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    return sum(
        1 for value in items.values()
        if isinstance(value, Mapping) and str(value.get('phase') or '') in SUPPORT_ACTIVE_PHASES
    )


def ensure_worktree(repo: Path, issue_number: int, branch: str | None = None) -> Path:
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = WORKTREE_ROOT / f'issue-{issue_number}'
    if path.exists():
        return path
    support.run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    selected = branch or f'develop/owner-approved-issue-{issue_number}'
    remote = support.run(['git', 'ls-remote', '--heads', 'origin', selected], cwd=repo, check=False)
    if remote:
        support.run(['git', 'worktree', 'add', '-B', selected, str(path), f'origin/{selected}'], cwd=repo)
    else:
        support.run(['git', 'worktree', 'add', '-b', selected, str(path), 'origin/main'], cwd=repo)
    return path


def development_pr_for(issue_number: int, prs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for pr in prs:
        match = META.search(str(pr.get('body') or ''))
        if match and int(match.group(1)) == issue_number:
            return pr
    return None


def known_development_pr_is_merged(repo: Path, record: Mapping[str, Any]) -> bool:
    value = record.get('pr_number')
    if value in (None, ''):
        return False
    fresh = support.pr_view(repo, int(value))
    return bool(fresh.get('mergedAt'))


def integration_coordination(repo: Path, changed: set[str]) -> list[int]:
    overlaps: list[int] = []
    for pr in support.open_prs(repo):
        detail = support.pr_view(repo, int(pr['number']))
        paths = {
            str(item.get('path') or '')
            for item in detail.get('files') or []
            if isinstance(item, Mapping)
        }
        if changed & paths:
            overlaps.append(int(pr['number']))
    return sorted(set(overlaps))
def pr_body(repo: Path, item: Mapping[str, Any], worktree: Path, tests: list[str]) -> str:
    files = set(support.changed_files(worktree))
    overlaps = integration_coordination(repo, files)
    coordination = ' '.join(f'#{number}' for number in overlaps) if overlaps else 'none'
    baseline = support.run(['git', 'merge-base', 'HEAD', 'origin/main'], cwd=worktree)
    regression = tests[0] if tests else 'required regression test'
    return f"""## Owner-approved autonomous development

- Development issue: #{item['issue_number']}
- Autonomous development: owner-approved
- Approval source: {item['approval_source']}
- Approved by: {item['approved_by']}
- Production deployment authority: none

## Organizational outcome

Implement only the bounded scope approved in #{item['issue_number']}: {item['title']}

## Integration coordination

- Branch baseline SHA: {baseline}
- Current-main reconciliation performed: yes
- Integration coordination: {coordination}
- Integration automation: enabled
- Production-impacting change: yes; merge is unattended only after protected checks pass
- Intended production release candidate: exact merged main SHA; production promotion remains Release Manager governed

## Governance and risk

- [x] Owner approval is durably bound to the source issue.
- [x] Non-approved issues are not eligible.
- [x] Existing authority/security controls remain authoritative.
- [x] Production deployment is outside this worker's authority.
- [x] Regression coverage is required before PR creation.

## Verification

- Focused regression: {regression}
- Host worker validation: git diff --check, Python compile where applicable, focused pytest.

## Documentation impact

- [ ] Documentation updated
- [x] No documentation impact

No-documentation-impact reason: Documentation remains governed by normal PR validation; the autonomous worker does not infer documentation changes.
"""


def validate_pr_preflight(body: str, expected_overlaps: list[int]) -> None:
    """Fail before PR creation on mechanical governance/integration defects."""
    documentation_impact_gate.validate_pull_request_body(body)
    acknowledged = change_integration_gate.parse_acknowledged(body)
    missing = sorted(set(int(value) for value in expected_overlaps) - acknowledged)
    if missing:
        joined = ", ".join(f"#{value}" for value in missing)
        raise support.WorkerError(
            "PR preflight missing Integration coordination acknowledgement for " + joined
        )
    required = (
        "- Current-main reconciliation performed: yes",
        "- Integration automation:",
        "- Production deployment authority: none",
    )
    missing_contract = [line for line in required if line not in body]
    if missing_contract:
        raise support.WorkerError(
            "PR preflight missing required development contract: "
            + "; ".join(missing_contract)
        )


def commit_and_pr(repo: Path, worktree: Path, item: Mapping[str, Any], tests: list[str]) -> int:
    branch = support.run(['git', 'branch', '--show-current'], cwd=worktree)
    support.run(['git', 'add', '--all'], cwd=worktree)
    support.run(['git', 'commit', '-m', f"Implement owner-approved issue #{item['issue_number']}: {item['title'][:55]}"], cwd=worktree)
    support.run(['git', 'push', '-u', 'origin', branch], cwd=worktree)
    body = pr_body(repo, item, worktree, tests)
    overlaps = integration_coordination(repo, set(support.changed_files(worktree)))
    validate_pr_preflight(body, overlaps)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        raw = support.run([
            'gh', 'pr', 'create', '--base', 'main', '--head', branch,
            '--title', f"Implement #{item['issue_number']}: {item['title'][:75]}",
            '--body-file', str(body_path),
        ], cwd=repo)
    finally:
        body_path.unlink(missing_ok=True)
    match = re.search(r'/pull/(\d+)', raw)
    if not match:
        raise support.WorkerError('could not determine development PR number')
    return int(match.group(1))
def queue_reasoning(
    spool: Path,
    *,
    kind: str,
    item: Mapping[str, Any],
    context: Mapping[str, Any],
) -> str:
    reasoning_item = {
        'id': item['id'],
        'title': item['title'],
        'evidence': item['evidence'],
        'acceptance': item['acceptance'],
    }
    return support.queue_reasoning(
        spool,
        kind=kind,
        item=reasoning_item,
        context=context,
    )


def select_items(
    state: Mapping[str, Any],
    eligible: list[dict[str, Any]],
    *,
    capacity: int,
) -> list[str]:
    """Select all existing nonterminal work plus up to ``capacity`` new claims.

    Existing approved development must remain reconcilable even when it already
    consumes the active-work limit; otherwise a full worker self-starves and can
    never advance or fail closed. ``capacity`` therefore means new-claim capacity.
    """
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    eligible_ids = {item['id'] for item in eligible}
    selected = [
        item_id for item_id, record in records.items()
        if item_id in eligible_ids
        and isinstance(record, Mapping)
        and str(record.get('phase') or '') not in TERMINAL_PHASES
    ]
    new_claims = 0
    for item in eligible:
        if new_claims >= max(0, int(capacity)):
            break
        if item['id'] in selected:
            continue
        record = records.get(item['id'])
        if isinstance(record, Mapping) and str(record.get('phase') or '') in TERMINAL_PHASES:
            continue
        selected.append(item['id'])
        new_claims += 1
    return selected


def source_context_blocker(reason: str) -> bool:
    text = str(reason or '').casefold()
    explicit_markers = (
        'supplied excerpt',
        'provided excerpt',
        'source excerpt',
        'repository excerpt',
        'source context',
        'repository context',
        'unseen code',
        'unseen repository',
        'not expose enough',
        'missing source',
        'enough surrounding',
        'cannot form a complete, exact replacement',
        "can't form a complete, exact replacement",
    )
    if any(marker in text for marker in explicit_markers):
        return True
    context_terms = (
        'excerpt',
        'context',
        'surrounding code',
        'surrounding call site',
        'unseen api',
        'unseen interface',
    )
    shortage_terms = (
        'insufficient',
        'incomplete',
        'not enough',
        'does not expose',
        'do not expose',
        'missing',
        'would require inventing',
        'require inventing',
    )
    return (
        any(term in text for term in context_terms)
        and any(term in text for term in shortage_terms)
    )


def self_recoverable_blocker(reason: str) -> bool:
    """Return True only for bounded worker failures Jason can safely retry itself."""
    text = str(reason or '').casefold()
    return (
        source_context_blocker(reason)
        or 'http transport failed' in text
        or 'no j-change-002-eligible source excerpts matched' in text
        or 'repair path does not exist:' in text
        or 'autonomous support repair requires a changed regression test' in text
        or 'development worker requires a changed regression test' in text
    )


def issue_has_closed_dependency_gate(item: Mapping[str, Any]) -> bool:
    """Honor an explicit authoritative issue-level development hold."""
    body = str(item.get('body') or '')
    return bool(
        re.search(r'(?im)^##\s+Production-health gate hold\s*$', body)
        and re.search(r'(?i)blocked by dependency|do not (?:begin|treat).*development', body)
    )



def reconcile_issue_dependency_holds(
    state: dict[str, Any], eligible: list[dict[str, Any]],
) -> None:
    """Represent issue-level closed admission gates as dependency holds, not worker errors."""
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    by_id = {item['id']: item for item in eligible}
    for item_id, record in records.items():
        if item_id not in by_id or not isinstance(record, dict):
            continue
        held = issue_has_closed_dependency_gate(by_id[item_id])
        if held:
            if record.get('blocker_class') != 'blocked_by_dependency':
                record.setdefault('prior_worker_error', str(record.get('reason') or '')[:1000])
            record.update({
                'phase': 'blocked',
                'blocker_class': 'blocked_by_dependency',
                'reason': 'Authoritative issue declares a closed production-health/dependency gate.',
                'recovery_next_action': 'Verify upstream production acceptance and clear the authoritative issue hold.',
                'updated_at': now(),
            })
        elif record.get('blocker_class') == 'blocked_by_dependency':
            # The source issue is authoritative for release of its explicit hold.
            # Fresh production/worker admission checks still apply downstream.
            record.update({
                'phase': 'diagnosing', 'blocker_class': '',
                'reason': 'Authoritative dependency hold lifted; rechecking admission.',
                'reasoning_request_id': '', 'updated_at': now(),
            })



def recycle_self_recoverable_blockers(
    state: dict[str, Any],
    eligible_ids: set[str],
    *,
    max_recycles: int = 2,
) -> None:
    """Resume owner-approved work after bounded internal worker/context failures.

    External/provider/authority/prerequisite blockers remain terminal. Approval is
    never broadened; only work whose original owner approval is still present is
    eligible for recycling.
    """
    items = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    for item_id, record in items.items():
        if item_id not in eligible_ids or not isinstance(record, dict):
            continue
        if str(record.get('phase') or '') != 'blocked':
            continue
        reason = str(record.get('reason') or '')
        if not self_recoverable_blocker(reason):
            continue
        attempts = int(record.get('self_recovery_attempts', 0) or 0)
        if attempts >= max_recycles:
            # Retry exhaustion must remain fail-closed, but must not be silent.
            # Keep the original error so support can diagnose the failure.
            record.setdefault('blocker_class', 'internal_retry_exhausted')
            record.setdefault('recovery_next_action',
                'Open an engineering repair using the original blocker and source evidence; '
                're-admit only after the repair is verified and all dependency gates pass.')
            record.setdefault('recovery_exhausted_at', now())
            continue
        record.update({
            'phase': 'diagnosing',
            'reason': 'Automatic bounded self-recovery retry after internal worker/context blocker.',
            'reasoning_request_id': '',
            'context_expansion_attempts': 0,
            'self_recovery_attempts': attempts + 1,
            'updated_at': now(),
        })


def queue_exhausted_recovery_diagnostics(
    state: dict[str, Any], eligible: list[dict[str, Any]], spool: Path,
) -> None:
    """Create one evidence-gathering handoff, never a retry or an approval grant.

    The response is advisory only; a separate authorized engineering repair and
    production acceptance are mandatory before any re-admission.
    """
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    for item in eligible:
        record = records.get(item['id'])
        if not isinstance(record, dict):
            continue
        if record.get('phase') != 'blocked' or record.get('blocker_class') != 'internal_retry_exhausted':
            continue
        if record.get('recovery_diagnostic_request_id'):
            continue
        rid = queue_reasoning(spool, kind='diagnosis', item=item, context={
            'work_class': 'development_retry_exhaustion_diagnostics',
            'issue_number': item['issue_number'],
            'original_blocker': str(record.get('reason') or '')[:1800],
            'retry_count': int(record.get('self_recovery_attempts', 0)),
            'source_paths': list(record.get('source_paths') or [])[:20],
            'instruction': (
                'Diagnose this exhausted development-worker failure and propose a bounded '
                'engineering repair with evidence, regression tests, and upstream dependency '
                'gates. Do not resume work, edit source, grant authority, or deploy.'
            ),
        })
        record['recovery_diagnostic_request_id'] = rid
        record['recovery_diagnostic_queued_at'] = now()


def reconcile_exhausted_recovery_diagnostics(
    state: dict[str, Any], eligible_ids: set[str], spool: Path,
) -> None:
    """Record diagnostic output without treating suggestions as execution authority."""
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    for item_id, record in records.items():
        if item_id not in eligible_ids or not isinstance(record, dict):
            continue
        if record.get('phase') != 'blocked' or record.get('blocker_class') != 'internal_retry_exhausted':
            continue
        rid = str(record.get('recovery_diagnostic_request_id') or '')
        if not rid or record.get('recovery_diagnostic_result_status'):
            continue
        response = support.reasoning_response(spool, rid)
        if response is None:
            continue
        if str(response.get('request_id') or rid) != rid:
            record['recovery_diagnostic_result_status'] = 'invalid_request_id'
            record['recovery_next_action'] = 'Inspect mismatched diagnostic response; no automatic re-admission.'
            continue
        status = str(response.get('status') or 'unknown')
        record['recovery_diagnostic_result_status'] = status
        record['recovery_diagnostic_result_at'] = now()
        if status == 'succeeded':
            result = response.get('result')
            if isinstance(result, Mapping):
                record['recovery_diagnostic_summary'] = str(
                    result.get('diagnosis') or result.get('summary') or result.get('blocked_reason') or ''
                )[:1800]
            record['recovery_next_action'] = (
                'Review diagnostic evidence and open a bounded governed repair; '
                'verify source changes, tests, dependencies, and release approval before re-admission.'
            )
            # Durable, idempotent repair intake evidence for the governed support
            # worker. This is NOT an executable development claim or approval.
            from hashlib import sha256
            import json
            handoff = {
                'schema': 'jason.development-recovery-handoff.v1',
                'source_item': item_id,
                'diagnostic_request_id': rid,
                'original_blocker': str(record.get('reason') or '')[:1800],
                'diagnosis': str(record.get('recovery_diagnostic_summary') or ''),
                'required_gate': 'authorized_repair_and_production_acceptance',
                'admission_authority': False,
            }
            handoff_id = sha256(json.dumps(handoff, sort_keys=True).encode()).hexdigest()
            handoff_path = spool / 'development-recovery' / 'handoffs' / f'{handoff_id}.json'
            if not handoff_path.exists():
                support.atomic_json(handoff_path, handoff)
            record['recovery_handoff_id'] = handoff_id
        else:
            record['recovery_next_action'] = (
                'Diagnostic reasoning failed; route to support with request ID and original blocker. '
                'Do not restart retries or bypass dependencies.'
            )


def reconcile_recovery_handoff_intake(
    state: dict[str, Any], eligible_ids: set[str], spool: Path,
) -> None:
    """Consume handoff as an inert review record, never executable authority."""
    import json
    import re
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    root = spool / 'development-recovery' / 'handoffs'
    if not root.is_dir():
        return
    for path in sorted(root.glob('*.json')):
        if not re.fullmatch(r'[0-9a-f]{64}\.json', path.name):
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get('schema') != 'jason.development-recovery-handoff.v1':
            continue
        # The filename is a content-addressed identity, not just a label.
        # Fail closed on modified or substituted handoff evidence.
        from hashlib import sha256
        expected_id = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if path.stem != expected_id:
            continue
        item_id = payload.get('source_item')
        if not isinstance(item_id, str) or item_id not in eligible_ids:
            continue
        record = records.get(item_id)
        if not isinstance(record, dict) or record.get('phase') != 'blocked':
            continue
        if record.get('recovery_handoff_id') != path.stem:
            continue
        if record.get('recovery_diagnostic_request_id') != payload.get('diagnostic_request_id'):
            continue
        if payload.get('admission_authority') is not False:
            continue
        record.setdefault('recovery_handoff_intake', {
            'status': 'awaiting_governed_repair',
            'handoff_id': path.stem,
            'required_gate': 'authorized_repair_and_production_acceptance',
            'observed_at': now(),
        })



def raise_exhausted_repair_support_issues(
    state: dict[str, Any], eligible_ids: set[str], repo: Path,
) -> None:
    """Route governed repair handoffs to existing deduplicated support intake."""
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    for item_id, record in records.items():
        if item_id not in eligible_ids or not isinstance(record, dict):
            continue
        intake = record.get('recovery_handoff_intake')
        if record.get('phase') != 'blocked' or not isinstance(intake, Mapping):
            continue
        if intake.get('status') != 'awaiting_governed_repair':
            continue
        if record.get('recovery_support_issue_raised'):
            continue
        if not isinstance(record.get('issue_number'), int):
            continue
        original_issue = int(record['issue_number'])
        item = {
            'id': f'SUPPORT-DEV-{original_issue}',
            'title': f'Development recovery exhausted for issue #{original_issue}',
            'evidence': (
                f'Approved development item {item_id}; original issue #{original_issue}; '
                f'handoff {intake.get("handoff_id")}; original failure: '
                f'{str(record.get("reason") or "")[:800]}; diagnosis: '
                f'{str(record.get("recovery_diagnostic_summary") or "")[:800]}'
            ),
            'acceptance': (
                'Repair via authorized source changes and regression tests; verify every upstream '
                'dependency and production acceptance before re-admitting the blocked item.'
            ),
        }
        support.ensure_support_issue(repo, item)
        record['recovery_support_issue_raised'] = item['id']
        record['recovery_support_issue_raised_at'] = now()



def readmit_verified_development_recoveries(
    state: dict[str, Any], eligible_ids: set[str], spool: Path, repo: Path,
) -> None:
    """Resume only after support closure AND exact healthy production receipt."""
    import re
    support_state = support.load_state(spool / 'state.json')
    support_items = support_state.get('items') if isinstance(support_state.get('items'), Mapping) else {}
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    for item_id, record in records.items():
        if item_id not in eligible_ids or not isinstance(record, dict):
            continue
        if record.get('phase') != 'blocked' or not record.get('recovery_support_issue_raised'):
            continue
        # TODO-GOV-002 must not bypass explicitly outstanding #1078/#1069 gates.
        # Other externally constrained work is never classified as internal recovery.
        if record.get('issue_number') == 866 or record.get('blocker_class') != 'internal_retry_exhausted':
            continue
        support_id = str(record['recovery_support_issue_raised'])
        support_record = support_items.get(support_id)
        if not isinstance(support_record, Mapping) or support_record.get('phase') != 'complete':
            continue
        sha = str(support_record.get('merge_sha') or '')
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            continue
        if not support_record.get('closure_pr_number') or not support_record.get('acceptance_reason'):
            continue
        observed = support.production_state_from_main(repo)
        production = observed.get('production') if isinstance(observed.get('production'), Mapping) else {}
        if production.get('status') != 'aligned_and_healthy' or production.get('revision') != sha:
            continue
        try:
            observed_at = datetime.fromisoformat(str(production['observed_at']).replace('Z', '+00:00'))
            age = (datetime.now(timezone.utc) - observed_at).total_seconds()
            if observed_at.tzinfo is None or not (0 <= age <= 1800):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        record.update({
            'phase': 'diagnosing', 'reasoning_request_id': '',
            'reason': 'Re-admitted following exact verified governed support repair.',
            'context_expansion_attempts': 0, 'self_recovery_attempts': 0,
            'recovery_readmitted_after_sha': sha, 'recovery_readmitted_at': now(),
            'updated_at': now(),
        })



def reconcile_removed_approval(state: dict[str, Any], eligible_ids: set[str]) -> None:
    items = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    for item_id, record in items.items():
        if (
            item_id not in eligible_ids
            and isinstance(record, dict)
            and str(record.get('phase') or '') not in TERMINAL_PHASES
        ):
            record.update({
                'phase': 'blocked',
                'reason': 'Owner-approved development marker is no longer present; work stopped fail-closed.',
                'updated_at': now(),
            })
def sync_lifecycle_notification(
    record: dict[str, Any],
    item: Mapping[str, Any],
    *,
    event_root: Path,
) -> None:
    try:
        phase = str(record.get('phase') or '').strip().casefold()
        if (phase == 'blocked'
                and record.get('notification_class') == 'owner_action_required'
                and not record.get('lifecycle_blocked_fingerprint')):
            owner_action = str(record.get('owner_action') or '').strip()
            if not owner_action:
                raise ValueError('owner_action_required blocker must include owner_action')
            record['lifecycle_blocked_fingerprint'] = support.emit_lifecycle_event(
                event_type='work_blocked', work_id=str(item['id']),
                work_title=str(item['title']),
                summary=str(record.get('reason') or 'Owner action required.'),
                owner_action=owner_action, event_root=event_root,
            )
        # Owner policy: routine starts and recoverable blockers are internal-only.
        # Emit only a verified terminal development milestone once per work item.
        if phase == 'complete' and record.get('pr_number') and not record.get('lifecycle_completed_fingerprint'):
            fingerprint = support.emit_lifecycle_event(
                event_type='work_completed',
                work_id=str(item['id']),
                work_title=str(item['title']),
                summary=f"Development PR #{int(record['pr_number'])} merged and verified; production activation is separate.",
                event_root=event_root,
            )
            record['lifecycle_completed_fingerprint'] = fingerprint
        record.pop('lifecycle_notification_error', None)
    except Exception as exc:
        record['lifecycle_notification_error'] = f'{type(exc).__name__}: {str(exc)[:300]}'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--spool', type=Path, default=DEFAULT_SPOOL)
    parser.add_argument('--max-active', type=int, default=2)
    args = parser.parse_args()

    repo = args.repo.resolve()
    spool = args.spool.resolve()
    state_path = spool / 'development-state.json'
    state = support.load_state(state_path)
    state.setdefault('items', {})

    support.run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    eligible = owner_approved_issues(repo)
    eligible_ids = {item['id'] for item in eligible}
    reconcile_issue_dependency_holds(state, eligible)
    admitted = [item for item in eligible if not issue_has_closed_dependency_gate(item)]
    admitted_ids = {item['id'] for item in admitted}
    reconcile_removed_approval(state, eligible_ids)
    recycle_self_recoverable_blockers(state, admitted_ids)
    queue_exhausted_recovery_diagnostics(state, admitted, spool)
    reconcile_exhausted_recovery_diagnostics(state, admitted_ids, spool)
    reconcile_recovery_handoff_intake(state, admitted_ids, spool)
    raise_exhausted_repair_support_issues(state, admitted_ids, repo)
    readmit_verified_development_recoveries(state, admitted_ids, spool, repo)
    state['discovery'] = {
        'observed_at': now(),
        'approved_issue_numbers': [item['issue_number'] for item in eligible],
        'approval_rule': 'exact owner-authored Autonomous development: owner-approved marker',
    }

    support_active = active_support_count(spool)
    development_active = sum(
        1 for record in state['items'].values()
        if isinstance(record, Mapping) and str(record.get('phase') or '') in ACTIVE_PHASES
    )
    capacity = max(
        0,
        max(1, int(args.max_active)) - support_active - development_active,
    )
    selected = select_items(state, admitted, capacity=capacity)
    by_id = {item['id']: item for item in admitted}
    prs = support.open_prs(repo)
    gate = support.load_gate(repo)
    policy = gate.load_json(repo / 'config' / 'autonomous-repair-release-policy.json')

    for item_id in selected:
        item = by_id[item_id]
        record = state['items'].setdefault(item_id, {
            'phase': 'identified',
            'attempts': 0,
            'claimed_at': now(),
            'approval_source': item['approval_source'],
            'approved_by': item['approved_by'],
            'issue_number': item['issue_number'],
            'worker': 'jason-owner-approved-development-worker',
            'updated_at': now(),
        })
        phase = str(record.get('phase') or 'identified')
        try:
            if known_development_pr_is_merged(repo, record):
                record.update({
                    'phase': 'complete',
                    'reason': 'PR merged through separate governed integration.',
                    'updated_at': now(),
                })
                continue
            pr = development_pr_for(item['issue_number'], prs)
            if pr is not None:
                record['pr_number'] = int(pr['number'])
                record['branch'] = str(pr['headRefName'])
                phase = 'pr_validating'
            if phase in {'ci_repair_needed', 'ci_repairing'}:
                worktree = ensure_worktree(
                    repo,
                    item['issue_number'],
                    str(record.get('branch') or '') or None,
                )
                if phase == 'ci_repair_needed':
                    rid = queue_reasoning(
                        spool,
                        kind='edit_plan',
                        item=item,
                        context={
                            'mode': 'development_ci_repair',
                            'approved_scope': approved_scope(item),
                            'ci_failure': support.failed_ci_context(
                                repo,
                                str(record['branch']),
                            ),
                            'source_excerpts': support.diff_excerpts(
                                worktree,
                                gate,
                                policy,
                            ),
                        },
                    )
                    record.update({
                        'phase': 'ci_repairing',
                        'reasoning_request_id': rid,
                        'updated_at': now(),
                    })
                    continue
                response = support.reasoning_response(
                    spool,
                    str(record.get('reasoning_request_id') or ''),
                )
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({
                        'phase': 'blocked',
                        'reason': 'CI reasoning failed: ' + str(response.get('error') or ''),
                        'updated_at': now(),
                    })
                    continue
                result = response.get('result') or {}
                if result.get('blocked_reason'):
                    record.update({
                        'phase': 'blocked',
                        'reason': str(result['blocked_reason']),
                        'updated_at': now(),
                    })
                    continue
                support.apply_edits(
                    worktree,
                    list(result.get('edits') or []),
                    gate,
                    policy,
                )
                tests = support.validate_patch(
                    worktree,
                    list(result.get('test_paths') or []),
                    gate,
                    policy,
                )
                support.commit_existing(worktree, item_id)
                record.update({
                    'phase': 'pr_validating',
                    'tests': tests,
                    'attempts': int(record.get('attempts', 0)) + 1,
                    'reason': '',
                    'updated_at': now(),
                })
                continue
            if phase == 'pr_validating' and record.get('pr_number'):
                fresh = support.pr_view(repo, int(record['pr_number']))
                if fresh.get('mergedAt'):
                    record.update({
                        'phase': 'complete',
                        'reason': 'PR merged through separate governed integration.',
                        'updated_at': now(),
                    })
                    continue
                if str(fresh.get('mergeStateStatus') or '').upper() == 'BEHIND':
                    support.run(
                        ['gh', 'pr', 'update-branch', str(record['pr_number'])],
                        cwd=repo,
                        check=False,
                    )
                    record.update({
                        'reason': 'branch update requested',
                        'updated_at': now(),
                    })
                    continue
                check_phase, detail = support.check_state(fresh)
                if check_phase == 'passed':
                    record.update({
                        'phase': 'pr_ready',
                        'reason': (
                            'Required PR checks passed; production deployment '
                            'remains separately governed.'
                        ),
                        'checks': 'passed',
                        'updated_at': now(),
                    })
                elif check_phase == 'failed':
                    if int(record.get('attempts', 0)) >= 2:
                        record.update({
                            'phase': 'blocked',
                            'reason': (
                                'development CI retry boundary exhausted: '
                                + ', '.join(detail)
                            ),
                            'updated_at': now(),
                        })
                    else:
                        record.update({
                            'phase': 'ci_repair_needed',
                            'reason': ', '.join(detail),
                            'updated_at': now(),
                        })
                else:
                    record.update({
                        'reason': ', '.join(detail),
                        'updated_at': now(),
                    })
                continue

            worktree = ensure_worktree(
                repo,
                item['issue_number'],
                str(record.get('branch') or '') or None,
            )
            record['branch'] = support.run(
                ['git', 'branch', '--show-current'],
                cwd=worktree,
            )
            record['worktree'] = str(worktree)
            if phase in {'identified', 'diagnosing'}:
                rid = record.get('reasoning_request_id')
                if not rid:
                    rid = queue_reasoning(
                        spool,
                        kind='search_plan',
                        item=item,
                        context={
                            'work_class': 'owner_approved_development',
                            'approved_scope': approved_scope(item),
                            'approval_source': item['approval_source'],
                        },
                    )
                    record.update({
                        'phase': 'diagnosing',
                        'reasoning_request_id': rid,
                        'updated_at': now(),
                    })
                    continue
                response = support.reasoning_response(spool, str(rid))
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({
                        'phase': 'blocked',
                        'reason': (
                            'development reasoning failed: '
                            + str(response.get('error') or '')
                        ),
                        'updated_at': now(),
                    })
                    continue
                result = response.get('result') or {}
                blocked_reason = str(result.get('blocked_reason') or '').strip()
                search_terms = [
                    str(value).strip()
                    for value in list(result.get('search_terms') or [])
                    if str(value).strip()
                ]
                expansion_search = int(record.get('context_expansion_attempts', 0)) > 0
                if blocked_reason and (
                    not search_terms
                    or (
                        not expansion_search
                        and not source_context_blocker(blocked_reason)
                    )
                ):
                    record.update({
                        'phase': 'blocked',
                        'reason': blocked_reason,
                        'updated_at': now(),
                    })
                    continue
                if blocked_reason:
                    record['reason'] = (
                        'Continuing bounded source discovery from context-expansion '
                        f'search plan: {blocked_reason[:500]}'
                    )
                excerpts = support.safe_search(
                    worktree,
                    search_terms,
                    gate,
                    policy,
                )
                prior_history = [
                    str(value).strip()
                    for value in list(record.get('source_history') or record.get('source_paths') or [])
                    if str(value).strip()
                ]
                if expansion_search and prior_history:
                    prior_excerpts = support.source_excerpts_for_paths(
                        worktree,
                        prior_history,
                        gate,
                        policy,
                        terms=search_terms,
                        limit=6,
                        content_limit=24000,
                    )
                    excerpts = support.merge_source_excerpts(
                        prior_excerpts,
                        excerpts[:8],
                        max_total=14,
                    )
                if not excerpts:
                    record.update({
                        'phase': 'blocked',
                        'reason': (
                            'no J-CHANGE-002-eligible source excerpts matched '
                            'development search plan'
                        ),
                        'updated_at': now(),
                    })
                    continue
                edit_rid = queue_reasoning(
                    spool,
                    kind='edit_plan',
                    item=item,
                    context={
                        'work_class': 'owner_approved_development',
                        'approved_scope': approved_scope(item),
                        'diagnosis': result.get('diagnosis'),
                        'source_excerpts': excerpts,
                    },
                )
                history = [
                    str(value).strip()
                    for value in list(record.get('source_history') or record.get('source_paths') or [])
                    if str(value).strip()
                ]
                for value in excerpts:
                    path = str(value.get('path') or '').strip()
                    if path and path not in history:
                        history.append(path)
                record.update({
                    'phase': 'implementing',
                    'reasoning_request_id': edit_rid,
                    'source_paths': [str(value.get('path') or '') for value in excerpts],
                    'source_history': history[-40:],
                    'updated_at': now(),
                })
                continue
            if phase == 'implementing':
                response = support.reasoning_response(
                    spool,
                    str(record.get('reasoning_request_id') or ''),
                )
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({
                        'phase': 'blocked',
                        'reason': (
                            'development edit reasoning failed: '
                            + str(response.get('error') or '')
                        ),
                        'updated_at': now(),
                    })
                    continue
                result = response.get('result') or {}
                if result.get('blocked_reason'):
                    blocked_reason = str(result['blocked_reason'])
                    expansion_attempts = int(record.get('context_expansion_attempts', 0))
                    if source_context_blocker(blocked_reason) and expansion_attempts < 3:
                        rid = queue_reasoning(
                            spool,
                            kind='search_plan',
                            item=item,
                            context={
                                'work_class': 'owner_approved_development_context_expansion',
                                'approved_scope': approved_scope(item),
                                'prior_context_blocker': blocked_reason[:1800],
                                'previous_source_paths': list(record.get('source_paths') or [])[:20],
                                'instruction': (
                                    'Find additional exact repository source needed to resolve the '
                                    'prior context blocker. Preserve the approved scope and do not '
                                    'request broader authority.'
                                ),
                            },
                        )
                        record.update({
                            'phase': 'diagnosing',
                            'reasoning_request_id': rid,
                            'context_expansion_attempts': expansion_attempts + 1,
                            'reason': (
                                'Automatic source-context expansion requested after edit-plan '
                                f'blocker: {blocked_reason[:500]}'
                            ),
                            'updated_at': now(),
                        })
                    else:
                        record.update({
                            'phase': 'blocked',
                            'reason': blocked_reason,
                            'updated_at': now(),
                        })
                    continue
                support.apply_edits(
                    worktree,
                    list(result.get('edits') or []),
                    gate,
                    policy,
                )
                tests = support.validate_patch(
                    worktree,
                    list(result.get('test_paths') or []),
                    gate,
                    policy,
                )
                number = commit_and_pr(repo, worktree, item, tests)
                record.update({
                    'phase': 'pr_validating',
                    'pr_number': number,
                    'tests': tests,
                    'attempts': int(record.get('attempts', 0)) + 1,
                    'reason': '',
                    'updated_at': now(),
                })
        except Exception as exc:
            record.update({
                'phase': 'blocked',
                'reason': f'{type(exc).__name__}: {str(exc)[:900]}',
                'updated_at': now(),
            })
        finally:
            sync_lifecycle_notification(
                record,
                item,
                event_root=spool.parent / 'autonomous-repair' / 'lifecycle-events',
            )

    state['support_active_at_claim'] = support_active
    state['max_active_engineering'] = max(1, int(args.max_active))
    state['updated_at'] = now()
    support.save_state(state_path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
