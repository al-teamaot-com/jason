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
TERMINAL_PHASES = {'pr_ready', 'blocked', 'complete'}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        'issue', 'list', '--state', 'open', '--limit', '100',
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
            'body': body[:12000],
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
        if isinstance(value, Mapping) and str(value.get('phase') or '') in ACTIVE_PHASES
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
- Integration automation: disabled
- Production-impacting change: source only; deployment remains separately governed
- Intended production release candidate: no automatic production promotion

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


def commit_and_pr(repo: Path, worktree: Path, item: Mapping[str, Any], tests: list[str]) -> int:
    branch = support.run(['git', 'branch', '--show-current'], cwd=worktree)
    support.run(['git', 'add', '--all'], cwd=worktree)
    support.run(['git', 'commit', '-m', f"Implement owner-approved issue #{item['issue_number']}: {item['title'][:55]}"], cwd=worktree)
    support.run(['git', 'push', '-u', 'origin', branch], cwd=worktree)
    body = pr_body(repo, item, worktree, tests)
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
    if capacity <= 0:
        return []
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    eligible_ids = {item['id'] for item in eligible}
    selected = [
        item_id for item_id, record in records.items()
        if item_id in eligible_ids
        and isinstance(record, Mapping)
        and str(record.get('phase') or '') not in TERMINAL_PHASES
    ][:capacity]
    for item in eligible:
        if len(selected) >= capacity:
            break
        if item['id'] in selected:
            continue
        record = records.get(item['id'])
        if isinstance(record, Mapping) and str(record.get('phase') or '') in TERMINAL_PHASES:
            continue
        selected.append(item['id'])
    return selected


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
    reconcile_removed_approval(state, eligible_ids)
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
    selected = select_items(state, eligible, capacity=capacity)
    by_id = {item['id']: item for item in eligible}
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
                            'approved_scope': item['body'][:5000],
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
                            'approved_scope': item['body'][:5000],
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
                if result.get('blocked_reason'):
                    record.update({
                        'phase': 'blocked',
                        'reason': str(result['blocked_reason']),
                        'updated_at': now(),
                    })
                    continue
                excerpts = support.safe_search(
                    worktree,
                    list(result.get('search_terms') or []),
                    gate,
                    policy,
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
                        'approved_scope': item['body'][:5000],
                        'diagnosis': result.get('diagnosis'),
                        'source_excerpts': excerpts,
                    },
                )
                record.update({
                    'phase': 'implementing',
                    'reasoning_request_id': edit_rid,
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

    state['support_active_at_claim'] = support_active
    state['max_active_engineering'] = max(1, int(args.max_active))
    state['updated_at'] = now()
    support.save_state(state_path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
