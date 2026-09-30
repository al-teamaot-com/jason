#!/usr/bin/env python3
"""Native host-side implementation worker for approved Project Jason SUPPORT defects.

The worker owns only isolated repository/GitHub mechanics. It never receives the
OpenAI key and never grants itself provider authority. Patch proposals are produced
by the Jason runtime through a bounded spool and are then deterministically validated
against J-CHANGE-002 path/size/test controls before any git mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = Path('/home/al/projects/jason')
DEFAULT_SPOOL = Path('/var/lib/jason/openclaw/support-repair')
SUPPORT_ROW = re.compile(r'^\|\s*(SUPPORT-[^|]+?)\s*\|\s*(P\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|')
SUPPORT_ID_PATTERN = r'SUPPORT-(?:[A-Z]+-[0-9]+|AUTO-[A-F0-9]{12})'
META = re.compile(rf'(?im)^\s*-\s*Support item\s*:\s*({SUPPORT_ID_PATTERN})\s*
PRIORITY = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}


class WorkerError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as handle:
        os.chmod(temp, 0o600)
        json.dump(dict(payload), handle, indent=2, sort_keys=True)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise WorkerError(f"command failed ({args[0]}): {(completed.stderr or completed.stdout)[:1000]}")
    return (completed.stdout or '').strip()


def load_gate(repo: Path):
    path = repo / 'tools' / 'autonomous_repair_release_gate.py'
    spec = importlib.util.spec_from_file_location('support_repair_release_gate', path)
    if spec is None or spec.loader is None:
        raise WorkerError('could not load autonomous repair release gate')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_support(text: str) -> list[dict[str, str]]:
    items = []
    for line in text.splitlines():
        match = SUPPORT_ROW.match(line)
        if not match:
            continue
        item_id, priority, status, title, evidence, acceptance = (value.strip() for value in match.groups())
        low = status.casefold()
        if any(word in low for word in ('closed', 'resolved', 'reclassified')):
            continue
        items.append({
            'id': item_id.upper(),
            'priority': priority.upper(),
            'status': status,
            'title': title,
            'evidence': evidence,
            'acceptance': acceptance,
        })
    items.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    return items


def request_id(payload: Mapping[str, Any]) -> str:
    material = {key: payload.get(key) for key in ('kind', 'support_item', 'title', 'evidence', 'acceptance', 'context')}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def queue_reasoning(spool: Path, *, kind: str, item: Mapping[str, str], context: Mapping[str, Any]) -> str:
    payload = {
        'kind': kind,
        'support_item': item['id'],
        'title': item['title'],
        'evidence': item['evidence'],
        'acceptance': item['acceptance'],
        'context': dict(context),
    }
    rid = request_id(payload)
    payload['request_id'] = rid
    path = spool / 'reasoning' / 'requests' / f'{rid}.json'
    if not path.exists():
        atomic_json(path, payload)
    return rid


def reasoning_response(spool: Path, rid: str) -> Mapping[str, Any] | None:
    path = spool / 'reasoning' / 'responses' / f'{rid}.json'
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload if isinstance(payload, Mapping) else None


def gh_json(args: list[str], *, cwd: Path) -> Any:
    raw = run(['gh', *args], cwd=cwd)
    return json.loads(raw) if raw else None


def open_prs(repo: Path) -> list[dict[str, Any]]:
    data = gh_json(['pr', 'list', '--state', 'open', '--limit', '100', '--json', 'number,title,body,headRefName,url,isDraft,statusCheckRollup'], cwd=repo)
    return list(data or [])


def support_id_from_title(title: str) -> str | None:
    match = SUPPORT_ID_IN_TITLE.search(str(title or ''))
    return match.group(1).upper() if match else None


def open_support_issue_ids(repo: Path) -> set[str]:
    data = gh_json([
        'issue', 'list', '--state', 'open', '--search', 'SUPPORT- in:title',
        '--limit', '100', '--json', 'number,title'
    ], cwd=repo) or []
    result = set()
    for issue in data:
        item_id = support_id_from_title(str(issue.get('title') or ''))
        if item_id:
            result.add(item_id)
    return result


def eligible_support_items(items: list[dict[str, str]], open_issue_ids: set[str]) -> list[dict[str, str]]:
    return [item for item in items if item['id'] in open_issue_ids]


def load_self_heal_incidents(root: Path = Path('/var/lib/jason/openclaw/self-heal')) -> list[dict[str, str]]:
    incidents: list[dict[str, str]] = []
    directory = root / 'incidents'
    if not directory.exists():
        return incidents
    for path in sorted(directory.glob('*.json'))[:100]:
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(value, Mapping) or value.get('state') != 'repair_required':
            continue
        item_id = str(value.get('support_item') or '').strip().upper()
        if not re.fullmatch(r'SUPPORT-AUTO-[A-F0-9]{12}', item_id):
            continue
        incidents.append({
            'id': item_id,
            'priority': str(value.get('priority') or 'P1').upper(),
            'status': 'Open - self-heal incident',
            'title': str(value.get('title') or 'Jason self-heal incident')[:240],
            'evidence': str(value.get('evidence') or '')[:1600],
            'acceptance': str(value.get('acceptance') or '')[:1600],
        })
    incidents.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    return incidents


def ensure_support_issue(repo: Path, item: Mapping[str, str]) -> None:
    existing = gh_json([
        'issue', 'list', '--state', 'open', '--search', f"{item['id']} in:title",
        '--limit', '10', '--json', 'number,title'
    ], cwd=repo) or []
    if any(item['id'].casefold() in str(issue.get('title') or '').casefold() for issue in existing):
        return
    body = (
        'Automatically created by Jason self-heal after bounded recovery did not restore '
        'an already-approved function.\n\n'
        f"- Support item: {item['id']}\n"
        f"- Evidence: {item['evidence']}\n"
        f"- Acceptance: {item['acceptance']}\n"
        '- Authority expansion: none\n'
        '- Host reboot/shutdown authority: none\n'
    )
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        run([
            'gh', 'issue', 'create',
            '--title', f"{item['id']} - {item['title'][:120]}",
            '--body-file', str(body_path),
        ], cwd=repo)
    finally:
        body_path.unlink(missing_ok=True)


def repair_pr_for(item_id: str, prs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for pr in prs:
        body = str(pr.get('body') or '')
        match = META.search(body)
        if match and match.group(1).upper() == item_id:
            return pr
        if item_id in body and 'autonomous-repair-candidate' in body:
            return pr
    return None


def branch_name(item_id: str) -> str:
    return 'repair/' + item_id.casefold().replace('_', '-').replace('/', '-')


def ensure_worktree(repo: Path, item_id: str, branch: str | None = None) -> Path:
    root = Path('/home/al/jason-worktrees/support-repair')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / item_id.casefold()
    if path.exists():
        return path
    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    selected = branch or branch_name(item_id)
    remote = run(['git', 'ls-remote', '--heads', 'origin', selected], cwd=repo, check=False)
    if remote:
        run(['git', 'worktree', 'add', '-B', selected, str(path), f'origin/{selected}'], cwd=repo)
    else:
        run(['git', 'worktree', 'add', '-b', selected, str(path), 'origin/main'], cwd=repo)
    return path


def safe_search(worktree: Path, terms: list[str], gate, policy: Mapping[str, Any]) -> list[dict[str, str]]:
    paths: list[str] = []
    for term in terms[:8]:
        if not isinstance(term, str) or len(term.strip()) < 2:
            continue
        output = run(['git', 'grep', '-l', '-I', '-i', '-F', term.strip()], cwd=worktree, check=False)
        for raw in output.splitlines():
            path = raw.strip()
            if not path or path in paths:
                continue
            if gate.path_denial_reason(path, dict(policy)):
                continue
            if path.startswith('.git'):
                continue
            paths.append(path)
            if len(paths) >= 10:
                break
        if len(paths) >= 10:
            break
    excerpts = []
    for path in paths:
        candidate = worktree / path
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        excerpts.append({'path': path, 'content': text[:14000]})
    return excerpts


def changed_files(worktree: Path) -> list[str]:
    output = run(['git', 'diff', '--name-only'], cwd=worktree)
    return [line.strip() for line in output.splitlines() if line.strip()]


def apply_edits(worktree: Path, edits: list[Mapping[str, Any]], gate, policy: Mapping[str, Any]) -> list[str]:
    if not edits or len(edits) > 12:
        raise WorkerError('repair proposal must contain between 1 and 12 edits')
    touched: list[str] = []
    total_delta = 0
    for edit in edits:
        path = str(edit.get('path') or '').strip()
        old = str(edit.get('old_text') or '')
        new = str(edit.get('new_text') or '')
        if not path or path.startswith('/') or '..' in Path(path).parts:
            raise WorkerError('invalid repair path')
        denial = gate.path_denial_reason(path, dict(policy))
        if denial:
            raise WorkerError('repair path denied by J-CHANGE-002: ' + denial)
        target = worktree / path
        if not target.is_file():
            raise WorkerError(f'repair path does not exist: {path}')
        text = target.read_text(encoding='utf-8')
        count = text.count(old)
        if count != 1:
            raise WorkerError(f'exact repair anchor must occur once in {path}; found {count}')
        total_delta += old.count('\n') + new.count('\n') + 2
        if total_delta > int(policy.get('max_changed_lines', 800)):
            raise WorkerError('proposed repair exceeds changed-line boundary')
        target.write_text(text.replace(old, new, 1), encoding='utf-8')
        if path not in touched:
            touched.append(path)
    if len(touched) > int(policy.get('max_changed_files', 25)):
        raise WorkerError('proposed repair exceeds changed-file boundary')
    return touched


def validate_patch(worktree: Path, test_paths: list[str], gate, policy: Mapping[str, Any]) -> list[str]:
    run(['git', 'diff', '--check'], cwd=worktree)
    files = changed_files(worktree)
    if not files:
        raise WorkerError('repair proposal produced no diff')
    for path in files:
        denial = gate.path_denial_reason(path, dict(policy))
        if denial:
            raise WorkerError('changed path denied by J-CHANGE-002: ' + denial)
    tests = [path for path in files if gate.is_test_path(path, dict(policy))]
    if not tests:
        raise WorkerError('autonomous support repair requires a changed regression test')
    declared = [str(path) for path in test_paths if str(path) in files and gate.is_test_path(str(path), dict(policy))]
    selected = declared or tests
    python = Path('/home/al/projects/jason/.venv/bin/python')
    python_cmd = str(python) if python.exists() else 'python3'
    py_files = [path for path in files if path.endswith('.py')]
    if py_files:
        run([python_cmd, '-m', 'py_compile', *py_files], cwd=worktree)
    run([python_cmd, '-m', 'pytest', '-q', *selected], cwd=worktree)
    return selected


def pr_body(item: Mapping[str, str], regression_test: str) -> str:
    return f'''## Autonomous repair release\n\n- Release class: autonomous-repair-candidate\n- Support item: {item['id']}\n- Previously approved behavior: {item['acceptance'][:500]}\n- Regression test: {regression_test}\n- Post deploy verification: Verify the support acceptance criteria against the deployed candidate before closing the support item.\n- New capability: no\n- Security impact: none\n- New authority or permission: no\n- Provider API contract change: no\n- Schema or migration: no\n- New dependency: no\n- Infrastructure or topology change: no\n- Client scope expansion: no\n- Disruptive operational behavior: no\n\n## Documentation impact\n- [x] No documentation impact\n- [ ] Documentation updated\nNo-documentation-impact reason: This repair restores previously approved runtime behavior and adds regression coverage.\n'''


def commit_and_pr(repo: Path, worktree: Path, item: Mapping[str, str], regression_test: str) -> int:
    branch = run(['git', 'branch', '--show-current'], cwd=worktree)
    run(['git', 'add', '--all'], cwd=worktree)
    run(['git', 'commit', '-m', f"Fix {item['id']}: {item['title'][:60]}"], cwd=worktree)
    run(['git', 'push', '-u', 'origin', branch], cwd=worktree)
    body = pr_body(item, regression_test)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        raw = run([
            'gh', 'pr', 'create', '--base', 'main', '--head', branch,
            '--title', f"Fix {item['id']}: {item['title'][:70]}", '--body-file', str(body_path),
        ], cwd=repo)
    finally:
        body_path.unlink(missing_ok=True)
    match = re.search(r'/pull/(\d+)', raw)
    if not match:
        raise WorkerError('could not determine created repair PR number')
    return int(match.group(1))


def pr_view(repo: Path, number: int) -> dict[str, Any]:
    value = gh_json([
        'pr', 'view', str(number), '--json',
        'number,title,body,headRefName,url,isDraft,statusCheckRollup,state,mergedAt,mergeCommit,mergeable,mergeStateStatus,files,additions,deletions'
    ], cwd=repo)
    return dict(value or {})


def diff_excerpts(worktree: Path, gate, policy: Mapping[str, Any]) -> list[dict[str, str]]:
    output = run(['git', 'diff', '--name-only', 'origin/main...HEAD'], cwd=worktree, check=False)
    excerpts = []
    for raw in output.splitlines():
        path = raw.strip()
        if not path or gate.path_denial_reason(path, dict(policy)):
            continue
        target = worktree / path
        if not target.is_file():
            continue
        try:
            text = target.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        excerpts.append({'path': path, 'content': text[:14000]})
        if len(excerpts) >= 10:
            break
    return excerpts


def failed_ci_context(repo: Path, branch: str) -> dict[str, Any]:
    runs = gh_json([
        'run', 'list', '--branch', branch, '--limit', '12', '--json',
        'databaseId,name,status,conclusion,headSha,url'
    ], cwd=repo) or []
    failed = [
        item for item in runs
        if str(item.get('conclusion') or '').casefold() in {'failure', 'cancelled', 'timed_out', 'action_required'}
    ]
    logs = []
    for item in failed[:3]:
        text = run(['gh', 'run', 'view', str(item['databaseId']), '--log-failed'], cwd=repo, check=False)
        logs.append({
            'name': str(item.get('name') or ''),
            'run_id': int(item['databaseId']),
            'conclusion': str(item.get('conclusion') or ''),
            'log': text[-16000:],
        })
    return {'failed_runs': logs}


def commit_existing(worktree: Path, item_id: str) -> None:
    run(['git', 'add', '--all'], cwd=worktree)
    if not run(['git', 'diff', '--cached', '--name-only'], cwd=worktree):
        raise WorkerError('CI repair proposal produced no staged change')
    run(['git', 'commit', '-m', f'Continue {item_id} repair after CI evidence'], cwd=worktree)
    run(['git', 'push'], cwd=worktree)


def production_state_from_main(repo: Path) -> dict[str, Any]:
    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    raw = run(['git', 'show', 'origin/main:docs/control/AUTOMATED-CHANGE-STATE.json'], cwd=repo, check=False)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def create_closure_pr(repo: Path, item: Mapping[str, str], merge_sha: str, acceptance_reason: str) -> int:
    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    root = Path('/home/al/jason-worktrees/support-repair-closure')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / item['id'].casefold()
    if path.exists():
        shutil.rmtree(path)
    branch = f"support-close/{item['id'].casefold()}-{merge_sha[:8]}"
    run(['git', 'worktree', 'add', '-b', branch, str(path), 'origin/main'], cwd=repo)
    support = path / 'SUPPORT.md'
    lines = support.read_text(encoding='utf-8').splitlines()
    changed = False
    date = datetime.now(timezone.utc).date().isoformat()
    evidence = (
        f"Production acceptance verified on deployed revision {merge_sha}: "
        + acceptance_reason.replace('|', '/')[:900]
    )
    for index, line in enumerate(lines):
        if not line.startswith('|'):
            continue
        parts = line.split('|')
        if len(parts) < 8 or parts[1].strip().upper() != item['id']:
            continue
        parts[3] = f' Closed {date} — production verified '
        existing = parts[5].strip()
        parts[5] = ' ' + ((existing + ' ' + evidence).strip()) + ' '
        lines[index] = '|'.join(parts)
        changed = True
        break
    if not changed and item['id'].startswith('SUPPORT-AUTO-'):
        lines.append(
            f"| {item['id']} | {item['priority']} | Closed {date} - production verified | "
            f"{item['title'].replace('|', '/')} | {evidence} | "
            f"{item['acceptance'].replace('|', '/')} |"
        )
        changed = True
    if not changed:
        raise WorkerError('support closure row not found')
    support.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    run(['git', 'add', 'SUPPORT.md'], cwd=path)
    run(['git', 'commit', '-m', f"Close {item['id']} after production acceptance"], cwd=path)
    run(['git', 'push', '-u', 'origin', branch], cwd=path)
    body = (
        'Closes the canonical support-list record only after production acceptance.\n\n'
        f"- Support item: {item['id']}\n"
        f"- Deployed revision: {merge_sha}\n"
        f"- Acceptance evidence: {acceptance_reason[:1000]}\n\n"
        '## Documentation impact\n'
        '- [x] Documentation updated\n'
        '- [ ] No documentation impact\n'
    )
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        raw = run([
            'gh', 'pr', 'create', '--base', 'main', '--head', branch,
            '--title', f"Close {item['id']} after production verification", '--body-file', str(body_path),
        ], cwd=repo)
    finally:
        body_path.unlink(missing_ok=True)
    match = re.search(r'/pull/(\d+)', raw)
    if not match:
        raise WorkerError('could not determine support closure PR number')
    return int(match.group(1))


def close_support_issue(repo: Path, item_id: str, merge_sha: str) -> None:
    issues = gh_json([
        'issue', 'list', '--state', 'open', '--search', f'{item_id} in:title', '--limit', '10', '--json', 'number,title'
    ], cwd=repo) or []
    exact = [issue for issue in issues if item_id.casefold() in str(issue.get('title') or '').casefold()]
    if len(exact) == 1:
        run([
            'gh', 'issue', 'close', str(exact[0]['number']), '--comment',
            f'Production acceptance passed and SUPPORT.md closure merged for deployed revision {merge_sha}.'
        ], cwd=repo)


def check_state(pr: Mapping[str, Any]) -> tuple[str, list[str]]:
    checks = list(pr.get('statusCheckRollup') or [])
    if not checks:
        return 'pending', []
    failures = []
    pending = []
    for check in checks:
        name = str(check.get('name') or check.get('context') or 'check')
        status = str(check.get('status') or '').upper()
        conclusion = str(check.get('conclusion') or '').upper()
        if status != 'COMPLETED':
            pending.append(name)
        elif conclusion not in {'SUCCESS', 'NEUTRAL', 'SKIPPED'}:
            failures.append(name)
    if failures:
        return 'failed', failures
    if pending:
        return 'pending', pending
    return 'passed', []


def eligible_premerge(repo: Path, pr_number: int, gate, policy: Mapping[str, Any]) -> tuple[bool, str]:
    data = gh_json(['pr', 'view', str(pr_number), '--json', 'body,isDraft,mergeable,mergeStateStatus,files,additions,deletions'], cwd=repo)
    if data.get('isDraft'):
        return False, 'PR is draft'
    if str(data.get('mergeable') or '').upper() != 'MERGEABLE':
        return False, 'PR is not mergeable'
    if str(data.get('mergeStateStatus') or '').upper() not in {'CLEAN', 'HAS_HOOKS'}:
        return False, 'PR merge state is not clean'
    metadata = gate.parse_metadata(str(data.get('body') or ''))
    for key, expected in (policy.get('required_metadata') or {}).items():
        if metadata.get(key, '').casefold() != str(expected).casefold():
            return False, f'metadata {key} does not match autonomous repair policy'
    for key in policy.get('required_nonempty_metadata', []):
        if not metadata.get(key, '').strip():
            return False, f'metadata {key} is missing'
    files = [str(item.get('path') or '') for item in data.get('files') or []]
    for path in files:
        reason = gate.path_denial_reason(path, dict(policy))
        if reason:
            return False, reason
    if not any(gate.is_test_path(path, dict(policy)) for path in files):
        return False, 'no changed regression test'
    changed = int(data.get('additions') or 0) + int(data.get('deletions') or 0)
    if changed > int(policy.get('max_changed_lines', 800)):
        return False, 'changed-line limit exceeded'
    return True, 'eligible'


def select_reconcile_ids(state: Mapping[str, Any], support: list[dict[str, str]], max_active: int) -> list[str]:
    items = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    terminal_phases = {'complete', 'blocked', 'escalated'}
    active_work_phases = {
        'identified', 'diagnosing', 'implementing',
        'ci_repair_needed', 'ci_repairing',
    }
    selected = [
        key for key, value in items.items()
        if isinstance(value, Mapping) and value.get('phase') not in terminal_phases
    ]
    active_count = sum(
        1 for value in items.values()
        if isinstance(value, Mapping) and value.get('phase') in active_work_phases
    )
    for item in support:
        item_id = item['id']
        if item_id in selected:
            continue
        existing = items.get(item_id) if isinstance(items, Mapping) else None
        existing = existing if isinstance(existing, Mapping) else {}
        if existing.get('phase') in terminal_phases:
            continue
        if active_count >= max(1, int(max_active)):
            break
        selected.append(item_id)
        active_count += 1
    return selected


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': '1.0', 'items': {}}
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {'schema_version': '1.0', 'items': {}}


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    atomic_json(path, state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--spool', type=Path, default=DEFAULT_SPOOL)
    parser.add_argument('--max-active', type=int, default=2)
    args = parser.parse_args()

    repo = args.repo.resolve()
    spool = args.spool.resolve()
    state_path = spool / 'state.json'
    state = load_state(state_path)
    state.setdefault('items', {})

    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    support_text = run(['git', 'show', 'origin/main:SUPPORT.md'], cwd=repo)
    parsed_support = parse_support(support_text)
    auto_incidents = load_self_heal_incidents()
    for item in auto_incidents:
        ensure_support_issue(repo, item)
    open_issue_ids = open_support_issue_ids(repo)
    support = eligible_support_items(parsed_support, open_issue_ids)
    support.extend(
        item for item in auto_incidents
        if item['id'] in open_issue_ids
        and item['id'] not in {existing['id'] for existing in support}
    )
    support.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    state['support_state_mismatches'] = {
        'support_open_issue_not_open': sorted(
            item['id'] for item in parsed_support if item['id'] not in open_issue_ids
        ),
        'issue_open_missing_support_row': sorted(
            item_id for item_id in open_issue_ids if item_id not in {item['id'] for item in parsed_support}
        ),
    }
    prs = open_prs(repo)
    gate = load_gate(repo)
    policy = gate.load_json(repo / 'config' / 'autonomous-repair-release-policy.json')

    selected = select_reconcile_ids(state, support, args.max_active)

    by_id = {item['id']: item for item in support}
    for item_id in selected:
        item = by_id.get(item_id)
        if item is None:
            continue
        record = state['items'].setdefault(
            item_id,
            {'phase': 'identified', 'attempts': 0, 'updated_at': now()},
        )
        phase = str(record.get('phase') or 'identified')

        try:
            # Complete a documentation-only closure PR after production acceptance.
            closure_pr_number = record.get('closure_pr_number')
            if closure_pr_number:
                closure = pr_view(repo, int(closure_pr_number))
                if closure.get('mergedAt'):
                    close_support_issue(repo, item_id, str(record.get('merge_sha') or ''))
                    record.update({'phase': 'complete', 'reason': '', 'updated_at': now()})
                    continue
                closure_phase, closure_detail = check_state(closure)
                if closure_phase == 'passed' and str(closure.get('mergeable') or '').upper() == 'MERGEABLE':
                    run(['gh', 'pr', 'merge', str(closure_pr_number), '--merge', '--delete-branch'], cwd=repo)
                    record.update({'phase': 'closure_merging', 'reason': '', 'updated_at': now()})
                elif closure_phase == 'failed':
                    record.update({
                        'phase': 'blocked',
                        'reason': 'support closure PR checks failed: ' + ', '.join(closure_detail),
                        'updated_at': now(),
                    })
                else:
                    record.update({'phase': 'closure_validating', 'reason': ', '.join(closure_detail), 'updated_at': now()})
                continue

            pr = repair_pr_for(item_id, prs)
            if pr is None and record.get('pr_number'):
                existing = pr_view(repo, int(record['pr_number']))
                if existing.get('mergedAt'):
                    merge_commit = existing.get('mergeCommit') or {}
                    merge_sha = str(merge_commit.get('oid') or merge_commit.get('sha') or '')
                    record.update({
                        'phase': 'merged_waiting_deployment',
                        'merge_sha': merge_sha,
                        'reason': '',
                        'updated_at': now(),
                    })
                    phase = 'merged_waiting_deployment'
                elif str(existing.get('state') or '').upper() == 'OPEN':
                    pr = existing

            if pr is not None:
                record['pr_number'] = int(pr['number'])
                record['branch'] = str(pr['headRefName'])

                # CI failures owned by this repair feed back through the same bounded
                # reasoning/apply/test path instead of waiting for a human prompt.
                if phase in {'ci_repair_needed', 'ci_repairing'}:
                    worktree = ensure_worktree(repo, item_id, record['branch'])
                    if phase == 'ci_repair_needed':
                        rid = queue_reasoning(
                            spool,
                            kind='edit_plan',
                            item=item,
                            context={
                                'mode': 'ci_repair',
                                'ci_failure': failed_ci_context(repo, record['branch']),
                                'source_excerpts': diff_excerpts(worktree, gate, policy),
                            },
                        )
                        record.update({
                            'phase': 'ci_repairing',
                            'reasoning_request_id': rid,
                            'updated_at': now(),
                        })
                        continue
                    response = reasoning_response(spool, str(record.get('reasoning_request_id') or ''))
                    if response is None:
                        continue
                    if response.get('status') != 'succeeded':
                        record.update({'phase': 'blocked', 'reason': 'CI repair reasoning failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                        continue
                    result = response.get('result') or {}
                    if result.get('blocked_reason'):
                        record.update({'phase': 'blocked', 'reason': str(result['blocked_reason']), 'updated_at': now()})
                        continue
                    apply_edits(worktree, list(result.get('edits') or []), gate, policy)
                    validate_patch(worktree, list(result.get('test_paths') or []), gate, policy)
                    commit_existing(worktree, item_id)
                    record.update({
                        'phase': 'pr_validating',
                        'attempts': int(record.get('attempts', 0)) + 1,
                        'reason': '',
                        'updated_at': now(),
                    })
                    continue

                fresh_pr = pr_view(repo, int(pr['number']))
                if str(fresh_pr.get('mergeStateStatus') or '').upper() == 'BEHIND':
                    run(['gh', 'pr', 'update-branch', str(pr['number'])], cwd=repo, check=False)
                    record.update({'phase': 'pr_validating', 'reason': 'branch update requested', 'updated_at': now()})
                    continue

                check_phase, detail = check_state(fresh_pr)
                if check_phase == 'passed':
                    eligible, reason = eligible_premerge(repo, int(pr['number']), gate, policy)
                    if not eligible:
                        record.update({'phase': 'blocked', 'reason': reason, 'updated_at': now()})
                    else:
                        run(['gh', 'pr', 'merge', str(pr['number']), '--merge', '--delete-branch'], cwd=repo)
                        merged = pr_view(repo, int(pr['number']))
                        merge_commit = merged.get('mergeCommit') or {}
                        merge_sha = str(merge_commit.get('oid') or merge_commit.get('sha') or '')
                        record.update({
                            'phase': 'merged_waiting_deployment',
                            'merge_sha': merge_sha,
                            'reason': '',
                            'updated_at': now(),
                        })
                elif check_phase == 'failed':
                    if int(record.get('attempts', 0)) >= 2:
                        record.update({
                            'phase': 'blocked',
                            'reason': 'repair-owned CI retry boundary exhausted: ' + ', '.join(detail),
                            'updated_at': now(),
                        })
                    else:
                        record.update({
                            'phase': 'ci_repair_needed',
                            'reason': ', '.join(detail),
                            'updated_at': now(),
                        })
                else:
                    record.update({'phase': 'pr_validating', 'reason': ', '.join(detail), 'updated_at': now()})
                continue

            if phase == 'merged_waiting_deployment':
                merge_sha = str(record.get('merge_sha') or '')
                prod_state = production_state_from_main(repo)
                production = prod_state.get('production') if isinstance(prod_state, Mapping) else {}
                production = production if isinstance(production, Mapping) else {}
                if (
                    str(production.get('status') or '') == 'aligned_and_healthy'
                    and str(production.get('revision') or '') == merge_sha
                ):
                    rid = record.get('acceptance_request_id')
                    if not rid:
                        rid = queue_reasoning(
                            spool,
                            kind='acceptance_review',
                            item=item,
                            context={
                                'merge_sha': merge_sha,
                                'production': dict(production),
                                'repair_pr_number': record.get('pr_number'),
                                'ci_required_checks_passed': True,
                            },
                        )
                        record.update({
                            'phase': 'production_verifying',
                            'acceptance_request_id': rid,
                            'updated_at': now(),
                        })
                else:
                    record.update({
                        'phase': 'merged_waiting_deployment',
                        'reason': 'waiting for governed deployment and reconciled production revision',
                        'updated_at': now(),
                    })
                continue

            if phase == 'production_verifying':
                response = reasoning_response(spool, str(record.get('acceptance_request_id') or ''))
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({'phase': 'blocked', 'reason': 'production acceptance review failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                    continue
                result = response.get('result') or {}
                if result.get('verified') is not True:
                    missing = result.get('missing_evidence') or []
                    record.update({
                        'phase': 'production_verifying',
                        'reason': 'acceptance evidence incomplete: ' + '; '.join(str(value) for value in missing)[:900],
                        'updated_at': now(),
                    })
                    continue
                closure_number = create_closure_pr(
                    repo,
                    item,
                    str(record.get('merge_sha') or ''),
                    str(result.get('reason') or 'acceptance criteria verified'),
                )
                record.update({
                    'phase': 'closure_validating',
                    'closure_pr_number': closure_number,
                    'acceptance_reason': str(result.get('reason') or ''),
                    'reason': '',
                    'updated_at': now(),
                })
                continue

            worktree = ensure_worktree(repo, item_id, record.get('branch'))
            record['branch'] = run(['git', 'branch', '--show-current'], cwd=worktree)

            if phase in {'identified', 'diagnosing'}:
                rid = record.get('reasoning_request_id')
                if not rid:
                    rid = queue_reasoning(spool, kind='search_plan', item=item, context={})
                    record.update({'phase': 'diagnosing', 'reasoning_request_id': rid, 'updated_at': now()})
                    continue
                response = reasoning_response(spool, str(rid))
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({'phase': 'blocked', 'reason': 'reasoning request failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                    continue
                result = response.get('result') or {}
                if result.get('blocked_reason'):
                    record.update({'phase': 'blocked', 'reason': str(result['blocked_reason']), 'updated_at': now()})
                    continue
                excerpts = safe_search(worktree, list(result.get('search_terms') or []), gate, policy)
                if not excerpts:
                    record.update({'phase': 'blocked', 'reason': 'no J-CHANGE-002-eligible source excerpts matched repair search plan', 'updated_at': now()})
                    continue
                edit_rid = queue_reasoning(
                    spool,
                    kind='edit_plan',
                    item=item,
                    context={'diagnosis': result.get('diagnosis'), 'source_excerpts': excerpts},
                )
                record.update({'phase': 'implementing', 'reasoning_request_id': edit_rid, 'updated_at': now()})
                continue

            if phase == 'implementing':
                response = reasoning_response(spool, str(record.get('reasoning_request_id') or ''))
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({'phase': 'blocked', 'reason': 'edit reasoning failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                    continue
                result = response.get('result') or {}
                if result.get('blocked_reason'):
                    record.update({'phase': 'blocked', 'reason': str(result['blocked_reason']), 'updated_at': now()})
                    continue
                apply_edits(worktree, list(result.get('edits') or []), gate, policy)
                tests = validate_patch(worktree, list(result.get('test_paths') or []), gate, policy)
                number = commit_and_pr(repo, worktree, item, tests[0])
                record.update({
                    'phase': 'pr_validating',
                    'pr_number': number,
                    'attempts': int(record.get('attempts', 0)) + 1,
                    'reason': '',
                    'updated_at': now(),
                })
                continue

        except Exception as exc:
            record.update({
                'phase': 'blocked',
                'reason': f'{type(exc).__name__}: {str(exc)[:900]}',
                'updated_at': now(),
            })

    state['updated_at'] = now()
    save_state(state_path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
)
SUPPORT_ID_IN_TITLE = re.compile(rf'\b({SUPPORT_ID_PATTERN})\b', re.IGNORECASE)
PRIORITY = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}


class WorkerError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as handle:
        os.chmod(temp, 0o600)
        json.dump(dict(payload), handle, indent=2, sort_keys=True)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def run(args: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise WorkerError(f"command failed ({args[0]}): {(completed.stderr or completed.stdout)[:1000]}")
    return (completed.stdout or '').strip()


def load_gate(repo: Path):
    path = repo / 'tools' / 'autonomous_repair_release_gate.py'
    spec = importlib.util.spec_from_file_location('support_repair_release_gate', path)
    if spec is None or spec.loader is None:
        raise WorkerError('could not load autonomous repair release gate')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_support(text: str) -> list[dict[str, str]]:
    items = []
    for line in text.splitlines():
        match = SUPPORT_ROW.match(line)
        if not match:
            continue
        item_id, priority, status, title, evidence, acceptance = (value.strip() for value in match.groups())
        low = status.casefold()
        if any(word in low for word in ('closed', 'resolved', 'reclassified')):
            continue
        items.append({
            'id': item_id.upper(),
            'priority': priority.upper(),
            'status': status,
            'title': title,
            'evidence': evidence,
            'acceptance': acceptance,
        })
    items.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    return items


def request_id(payload: Mapping[str, Any]) -> str:
    material = {key: payload.get(key) for key in ('kind', 'support_item', 'title', 'evidence', 'acceptance', 'context')}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def queue_reasoning(spool: Path, *, kind: str, item: Mapping[str, str], context: Mapping[str, Any]) -> str:
    payload = {
        'kind': kind,
        'support_item': item['id'],
        'title': item['title'],
        'evidence': item['evidence'],
        'acceptance': item['acceptance'],
        'context': dict(context),
    }
    rid = request_id(payload)
    payload['request_id'] = rid
    path = spool / 'reasoning' / 'requests' / f'{rid}.json'
    if not path.exists():
        atomic_json(path, payload)
    return rid


def reasoning_response(spool: Path, rid: str) -> Mapping[str, Any] | None:
    path = spool / 'reasoning' / 'responses' / f'{rid}.json'
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload if isinstance(payload, Mapping) else None


def gh_json(args: list[str], *, cwd: Path) -> Any:
    raw = run(['gh', *args], cwd=cwd)
    return json.loads(raw) if raw else None


def open_prs(repo: Path) -> list[dict[str, Any]]:
    data = gh_json(['pr', 'list', '--state', 'open', '--limit', '100', '--json', 'number,title,body,headRefName,url,isDraft,statusCheckRollup'], cwd=repo)
    return list(data or [])


def support_id_from_title(title: str) -> str | None:
    match = SUPPORT_ID_IN_TITLE.search(str(title or ''))
    return match.group(1).upper() if match else None


def open_support_issue_ids(repo: Path) -> set[str]:
    data = gh_json([
        'issue', 'list', '--state', 'open', '--search', 'SUPPORT- in:title',
        '--limit', '100', '--json', 'number,title'
    ], cwd=repo) or []
    result = set()
    for issue in data:
        item_id = support_id_from_title(str(issue.get('title') or ''))
        if item_id:
            result.add(item_id)
    return result


def eligible_support_items(items: list[dict[str, str]], open_issue_ids: set[str]) -> list[dict[str, str]]:
    return [item for item in items if item['id'] in open_issue_ids]


def load_self_heal_incidents(root: Path = Path('/var/lib/jason/openclaw/self-heal')) -> list[dict[str, str]]:
    incidents: list[dict[str, str]] = []
    directory = root / 'incidents'
    if not directory.exists():
        return incidents
    for path in sorted(directory.glob('*.json'))[:100]:
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(value, Mapping) or value.get('state') != 'repair_required':
            continue
        item_id = str(value.get('support_item') or '').strip().upper()
        if not re.fullmatch(r'SUPPORT-AUTO-[A-F0-9]{12}', item_id):
            continue
        incidents.append({
            'id': item_id,
            'priority': str(value.get('priority') or 'P1').upper(),
            'status': 'Open - self-heal incident',
            'title': str(value.get('title') or 'Jason self-heal incident')[:240],
            'evidence': str(value.get('evidence') or '')[:1600],
            'acceptance': str(value.get('acceptance') or '')[:1600],
        })
    incidents.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    return incidents


def ensure_support_issue(repo: Path, item: Mapping[str, str]) -> None:
    existing = gh_json([
        'issue', 'list', '--state', 'open', '--search', f"{item['id']} in:title",
        '--limit', '10', '--json', 'number,title'
    ], cwd=repo) or []
    if any(item['id'].casefold() in str(issue.get('title') or '').casefold() for issue in existing):
        return
    body = (
        'Automatically created by Jason self-heal after bounded recovery did not restore '
        'an already-approved function.\n\n'
        f"- Support item: {item['id']}\n"
        f"- Evidence: {item['evidence']}\n"
        f"- Acceptance: {item['acceptance']}\n"
        '- Authority expansion: none\n'
        '- Host reboot/shutdown authority: none\n'
    )
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        run([
            'gh', 'issue', 'create',
            '--title', f"{item['id']} - {item['title'][:120]}",
            '--body-file', str(body_path),
        ], cwd=repo)
    finally:
        body_path.unlink(missing_ok=True)


def repair_pr_for(item_id: str, prs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for pr in prs:
        body = str(pr.get('body') or '')
        match = META.search(body)
        if match and match.group(1).upper() == item_id:
            return pr
        if item_id in body and 'autonomous-repair-candidate' in body:
            return pr
    return None


def branch_name(item_id: str) -> str:
    return 'repair/' + item_id.casefold().replace('_', '-').replace('/', '-')


def ensure_worktree(repo: Path, item_id: str, branch: str | None = None) -> Path:
    root = Path('/home/al/jason-worktrees/support-repair')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / item_id.casefold()
    if path.exists():
        return path
    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    selected = branch or branch_name(item_id)
    remote = run(['git', 'ls-remote', '--heads', 'origin', selected], cwd=repo, check=False)
    if remote:
        run(['git', 'worktree', 'add', '-B', selected, str(path), f'origin/{selected}'], cwd=repo)
    else:
        run(['git', 'worktree', 'add', '-b', selected, str(path), 'origin/main'], cwd=repo)
    return path


def safe_search(worktree: Path, terms: list[str], gate, policy: Mapping[str, Any]) -> list[dict[str, str]]:
    paths: list[str] = []
    for term in terms[:8]:
        if not isinstance(term, str) or len(term.strip()) < 2:
            continue
        output = run(['git', 'grep', '-l', '-I', '-i', '-F', term.strip()], cwd=worktree, check=False)
        for raw in output.splitlines():
            path = raw.strip()
            if not path or path in paths:
                continue
            if gate.path_denial_reason(path, dict(policy)):
                continue
            if path.startswith('.git'):
                continue
            paths.append(path)
            if len(paths) >= 10:
                break
        if len(paths) >= 10:
            break
    excerpts = []
    for path in paths:
        candidate = worktree / path
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        excerpts.append({'path': path, 'content': text[:14000]})
    return excerpts


def changed_files(worktree: Path) -> list[str]:
    output = run(['git', 'diff', '--name-only'], cwd=worktree)
    return [line.strip() for line in output.splitlines() if line.strip()]


def apply_edits(worktree: Path, edits: list[Mapping[str, Any]], gate, policy: Mapping[str, Any]) -> list[str]:
    if not edits or len(edits) > 12:
        raise WorkerError('repair proposal must contain between 1 and 12 edits')
    touched: list[str] = []
    total_delta = 0
    for edit in edits:
        path = str(edit.get('path') or '').strip()
        old = str(edit.get('old_text') or '')
        new = str(edit.get('new_text') or '')
        if not path or path.startswith('/') or '..' in Path(path).parts:
            raise WorkerError('invalid repair path')
        denial = gate.path_denial_reason(path, dict(policy))
        if denial:
            raise WorkerError('repair path denied by J-CHANGE-002: ' + denial)
        target = worktree / path
        if not target.is_file():
            raise WorkerError(f'repair path does not exist: {path}')
        text = target.read_text(encoding='utf-8')
        count = text.count(old)
        if count != 1:
            raise WorkerError(f'exact repair anchor must occur once in {path}; found {count}')
        total_delta += old.count('\n') + new.count('\n') + 2
        if total_delta > int(policy.get('max_changed_lines', 800)):
            raise WorkerError('proposed repair exceeds changed-line boundary')
        target.write_text(text.replace(old, new, 1), encoding='utf-8')
        if path not in touched:
            touched.append(path)
    if len(touched) > int(policy.get('max_changed_files', 25)):
        raise WorkerError('proposed repair exceeds changed-file boundary')
    return touched


def validate_patch(worktree: Path, test_paths: list[str], gate, policy: Mapping[str, Any]) -> list[str]:
    run(['git', 'diff', '--check'], cwd=worktree)
    files = changed_files(worktree)
    if not files:
        raise WorkerError('repair proposal produced no diff')
    for path in files:
        denial = gate.path_denial_reason(path, dict(policy))
        if denial:
            raise WorkerError('changed path denied by J-CHANGE-002: ' + denial)
    tests = [path for path in files if gate.is_test_path(path, dict(policy))]
    if not tests:
        raise WorkerError('autonomous support repair requires a changed regression test')
    declared = [str(path) for path in test_paths if str(path) in files and gate.is_test_path(str(path), dict(policy))]
    selected = declared or tests
    python = Path('/home/al/projects/jason/.venv/bin/python')
    python_cmd = str(python) if python.exists() else 'python3'
    py_files = [path for path in files if path.endswith('.py')]
    if py_files:
        run([python_cmd, '-m', 'py_compile', *py_files], cwd=worktree)
    run([python_cmd, '-m', 'pytest', '-q', *selected], cwd=worktree)
    return selected


def pr_body(item: Mapping[str, str], regression_test: str) -> str:
    return f'''## Autonomous repair release\n\n- Release class: autonomous-repair-candidate\n- Support item: {item['id']}\n- Previously approved behavior: {item['acceptance'][:500]}\n- Regression test: {regression_test}\n- Post deploy verification: Verify the support acceptance criteria against the deployed candidate before closing the support item.\n- New capability: no\n- Security impact: none\n- New authority or permission: no\n- Provider API contract change: no\n- Schema or migration: no\n- New dependency: no\n- Infrastructure or topology change: no\n- Client scope expansion: no\n- Disruptive operational behavior: no\n\n## Documentation impact\n- [x] No documentation impact\n- [ ] Documentation updated\nNo-documentation-impact reason: This repair restores previously approved runtime behavior and adds regression coverage.\n'''


def commit_and_pr(repo: Path, worktree: Path, item: Mapping[str, str], regression_test: str) -> int:
    branch = run(['git', 'branch', '--show-current'], cwd=worktree)
    run(['git', 'add', '--all'], cwd=worktree)
    run(['git', 'commit', '-m', f"Fix {item['id']}: {item['title'][:60]}"], cwd=worktree)
    run(['git', 'push', '-u', 'origin', branch], cwd=worktree)
    body = pr_body(item, regression_test)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        raw = run([
            'gh', 'pr', 'create', '--base', 'main', '--head', branch,
            '--title', f"Fix {item['id']}: {item['title'][:70]}", '--body-file', str(body_path),
        ], cwd=repo)
    finally:
        body_path.unlink(missing_ok=True)
    match = re.search(r'/pull/(\d+)', raw)
    if not match:
        raise WorkerError('could not determine created repair PR number')
    return int(match.group(1))


def pr_view(repo: Path, number: int) -> dict[str, Any]:
    value = gh_json([
        'pr', 'view', str(number), '--json',
        'number,title,body,headRefName,url,isDraft,statusCheckRollup,state,mergedAt,mergeCommit,mergeable,mergeStateStatus,files,additions,deletions'
    ], cwd=repo)
    return dict(value or {})


def diff_excerpts(worktree: Path, gate, policy: Mapping[str, Any]) -> list[dict[str, str]]:
    output = run(['git', 'diff', '--name-only', 'origin/main...HEAD'], cwd=worktree, check=False)
    excerpts = []
    for raw in output.splitlines():
        path = raw.strip()
        if not path or gate.path_denial_reason(path, dict(policy)):
            continue
        target = worktree / path
        if not target.is_file():
            continue
        try:
            text = target.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        excerpts.append({'path': path, 'content': text[:14000]})
        if len(excerpts) >= 10:
            break
    return excerpts


def failed_ci_context(repo: Path, branch: str) -> dict[str, Any]:
    runs = gh_json([
        'run', 'list', '--branch', branch, '--limit', '12', '--json',
        'databaseId,name,status,conclusion,headSha,url'
    ], cwd=repo) or []
    failed = [
        item for item in runs
        if str(item.get('conclusion') or '').casefold() in {'failure', 'cancelled', 'timed_out', 'action_required'}
    ]
    logs = []
    for item in failed[:3]:
        text = run(['gh', 'run', 'view', str(item['databaseId']), '--log-failed'], cwd=repo, check=False)
        logs.append({
            'name': str(item.get('name') or ''),
            'run_id': int(item['databaseId']),
            'conclusion': str(item.get('conclusion') or ''),
            'log': text[-16000:],
        })
    return {'failed_runs': logs}


def commit_existing(worktree: Path, item_id: str) -> None:
    run(['git', 'add', '--all'], cwd=worktree)
    if not run(['git', 'diff', '--cached', '--name-only'], cwd=worktree):
        raise WorkerError('CI repair proposal produced no staged change')
    run(['git', 'commit', '-m', f'Continue {item_id} repair after CI evidence'], cwd=worktree)
    run(['git', 'push'], cwd=worktree)


def production_state_from_main(repo: Path) -> dict[str, Any]:
    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    raw = run(['git', 'show', 'origin/main:docs/control/AUTOMATED-CHANGE-STATE.json'], cwd=repo, check=False)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def create_closure_pr(repo: Path, item: Mapping[str, str], merge_sha: str, acceptance_reason: str) -> int:
    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    root = Path('/home/al/jason-worktrees/support-repair-closure')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / item['id'].casefold()
    if path.exists():
        shutil.rmtree(path)
    branch = f"support-close/{item['id'].casefold()}-{merge_sha[:8]}"
    run(['git', 'worktree', 'add', '-b', branch, str(path), 'origin/main'], cwd=repo)
    support = path / 'SUPPORT.md'
    lines = support.read_text(encoding='utf-8').splitlines()
    changed = False
    date = datetime.now(timezone.utc).date().isoformat()
    evidence = (
        f"Production acceptance verified on deployed revision {merge_sha}: "
        + acceptance_reason.replace('|', '/')[:900]
    )
    for index, line in enumerate(lines):
        if not line.startswith('|'):
            continue
        parts = line.split('|')
        if len(parts) < 8 or parts[1].strip().upper() != item['id']:
            continue
        parts[3] = f' Closed {date} — production verified '
        existing = parts[5].strip()
        parts[5] = ' ' + ((existing + ' ' + evidence).strip()) + ' '
        lines[index] = '|'.join(parts)
        changed = True
        break
    if not changed and item['id'].startswith('SUPPORT-AUTO-'):
        lines.append(
            f"| {item['id']} | {item['priority']} | Closed {date} - production verified | "
            f"{item['title'].replace('|', '/')} | {evidence} | "
            f"{item['acceptance'].replace('|', '/')} |"
        )
        changed = True
    if not changed:
        raise WorkerError('support closure row not found')
    support.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    run(['git', 'add', 'SUPPORT.md'], cwd=path)
    run(['git', 'commit', '-m', f"Close {item['id']} after production acceptance"], cwd=path)
    run(['git', 'push', '-u', 'origin', branch], cwd=path)
    body = (
        'Closes the canonical support-list record only after production acceptance.\n\n'
        f"- Support item: {item['id']}\n"
        f"- Deployed revision: {merge_sha}\n"
        f"- Acceptance evidence: {acceptance_reason[:1000]}\n\n"
        '## Documentation impact\n'
        '- [x] Documentation updated\n'
        '- [ ] No documentation impact\n'
    )
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as handle:
        handle.write(body)
        body_path = Path(handle.name)
    try:
        raw = run([
            'gh', 'pr', 'create', '--base', 'main', '--head', branch,
            '--title', f"Close {item['id']} after production verification", '--body-file', str(body_path),
        ], cwd=repo)
    finally:
        body_path.unlink(missing_ok=True)
    match = re.search(r'/pull/(\d+)', raw)
    if not match:
        raise WorkerError('could not determine support closure PR number')
    return int(match.group(1))


def close_support_issue(repo: Path, item_id: str, merge_sha: str) -> None:
    issues = gh_json([
        'issue', 'list', '--state', 'open', '--search', f'{item_id} in:title', '--limit', '10', '--json', 'number,title'
    ], cwd=repo) or []
    exact = [issue for issue in issues if item_id.casefold() in str(issue.get('title') or '').casefold()]
    if len(exact) == 1:
        run([
            'gh', 'issue', 'close', str(exact[0]['number']), '--comment',
            f'Production acceptance passed and SUPPORT.md closure merged for deployed revision {merge_sha}.'
        ], cwd=repo)


def check_state(pr: Mapping[str, Any]) -> tuple[str, list[str]]:
    checks = list(pr.get('statusCheckRollup') or [])
    if not checks:
        return 'pending', []
    failures = []
    pending = []
    for check in checks:
        name = str(check.get('name') or check.get('context') or 'check')
        status = str(check.get('status') or '').upper()
        conclusion = str(check.get('conclusion') or '').upper()
        if status != 'COMPLETED':
            pending.append(name)
        elif conclusion not in {'SUCCESS', 'NEUTRAL', 'SKIPPED'}:
            failures.append(name)
    if failures:
        return 'failed', failures
    if pending:
        return 'pending', pending
    return 'passed', []


def eligible_premerge(repo: Path, pr_number: int, gate, policy: Mapping[str, Any]) -> tuple[bool, str]:
    data = gh_json(['pr', 'view', str(pr_number), '--json', 'body,isDraft,mergeable,mergeStateStatus,files,additions,deletions'], cwd=repo)
    if data.get('isDraft'):
        return False, 'PR is draft'
    if str(data.get('mergeable') or '').upper() != 'MERGEABLE':
        return False, 'PR is not mergeable'
    if str(data.get('mergeStateStatus') or '').upper() not in {'CLEAN', 'HAS_HOOKS'}:
        return False, 'PR merge state is not clean'
    metadata = gate.parse_metadata(str(data.get('body') or ''))
    for key, expected in (policy.get('required_metadata') or {}).items():
        if metadata.get(key, '').casefold() != str(expected).casefold():
            return False, f'metadata {key} does not match autonomous repair policy'
    for key in policy.get('required_nonempty_metadata', []):
        if not metadata.get(key, '').strip():
            return False, f'metadata {key} is missing'
    files = [str(item.get('path') or '') for item in data.get('files') or []]
    for path in files:
        reason = gate.path_denial_reason(path, dict(policy))
        if reason:
            return False, reason
    if not any(gate.is_test_path(path, dict(policy)) for path in files):
        return False, 'no changed regression test'
    changed = int(data.get('additions') or 0) + int(data.get('deletions') or 0)
    if changed > int(policy.get('max_changed_lines', 800)):
        return False, 'changed-line limit exceeded'
    return True, 'eligible'


def select_reconcile_ids(state: Mapping[str, Any], support: list[dict[str, str]], max_active: int) -> list[str]:
    items = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    terminal_phases = {'complete', 'blocked', 'escalated'}
    active_work_phases = {
        'identified', 'diagnosing', 'implementing',
        'ci_repair_needed', 'ci_repairing',
    }
    selected = [
        key for key, value in items.items()
        if isinstance(value, Mapping) and value.get('phase') not in terminal_phases
    ]
    active_count = sum(
        1 for value in items.values()
        if isinstance(value, Mapping) and value.get('phase') in active_work_phases
    )
    for item in support:
        item_id = item['id']
        if item_id in selected:
            continue
        existing = items.get(item_id) if isinstance(items, Mapping) else None
        existing = existing if isinstance(existing, Mapping) else {}
        if existing.get('phase') in terminal_phases:
            continue
        if active_count >= max(1, int(max_active)):
            break
        selected.append(item_id)
        active_count += 1
    return selected


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': '1.0', 'items': {}}
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {'schema_version': '1.0', 'items': {}}


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    atomic_json(path, state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--spool', type=Path, default=DEFAULT_SPOOL)
    parser.add_argument('--max-active', type=int, default=2)
    args = parser.parse_args()

    repo = args.repo.resolve()
    spool = args.spool.resolve()
    state_path = spool / 'state.json'
    state = load_state(state_path)
    state.setdefault('items', {})

    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    support_text = run(['git', 'show', 'origin/main:SUPPORT.md'], cwd=repo)
    parsed_support = parse_support(support_text)
    auto_incidents = load_self_heal_incidents()
    for item in auto_incidents:
        ensure_support_issue(repo, item)
    open_issue_ids = open_support_issue_ids(repo)
    support = eligible_support_items(parsed_support, open_issue_ids)
    support.extend(
        item for item in auto_incidents
        if item['id'] in open_issue_ids
        and item['id'] not in {existing['id'] for existing in support}
    )
    support.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    state['support_state_mismatches'] = {
        'support_open_issue_not_open': sorted(
            item['id'] for item in parsed_support if item['id'] not in open_issue_ids
        ),
        'issue_open_missing_support_row': sorted(
            item_id for item_id in open_issue_ids if item_id not in {item['id'] for item in parsed_support}
        ),
    }
    prs = open_prs(repo)
    gate = load_gate(repo)
    policy = gate.load_json(repo / 'config' / 'autonomous-repair-release-policy.json')

    selected = select_reconcile_ids(state, support, args.max_active)

    by_id = {item['id']: item for item in support}
    for item_id in selected:
        item = by_id.get(item_id)
        if item is None:
            continue
        record = state['items'].setdefault(
            item_id,
            {'phase': 'identified', 'attempts': 0, 'updated_at': now()},
        )
        phase = str(record.get('phase') or 'identified')

        try:
            # Complete a documentation-only closure PR after production acceptance.
            closure_pr_number = record.get('closure_pr_number')
            if closure_pr_number:
                closure = pr_view(repo, int(closure_pr_number))
                if closure.get('mergedAt'):
                    close_support_issue(repo, item_id, str(record.get('merge_sha') or ''))
                    record.update({'phase': 'complete', 'reason': '', 'updated_at': now()})
                    continue
                closure_phase, closure_detail = check_state(closure)
                if closure_phase == 'passed' and str(closure.get('mergeable') or '').upper() == 'MERGEABLE':
                    run(['gh', 'pr', 'merge', str(closure_pr_number), '--merge', '--delete-branch'], cwd=repo)
                    record.update({'phase': 'closure_merging', 'reason': '', 'updated_at': now()})
                elif closure_phase == 'failed':
                    record.update({
                        'phase': 'blocked',
                        'reason': 'support closure PR checks failed: ' + ', '.join(closure_detail),
                        'updated_at': now(),
                    })
                else:
                    record.update({'phase': 'closure_validating', 'reason': ', '.join(closure_detail), 'updated_at': now()})
                continue

            pr = repair_pr_for(item_id, prs)
            if pr is None and record.get('pr_number'):
                existing = pr_view(repo, int(record['pr_number']))
                if existing.get('mergedAt'):
                    merge_commit = existing.get('mergeCommit') or {}
                    merge_sha = str(merge_commit.get('oid') or merge_commit.get('sha') or '')
                    record.update({
                        'phase': 'merged_waiting_deployment',
                        'merge_sha': merge_sha,
                        'reason': '',
                        'updated_at': now(),
                    })
                    phase = 'merged_waiting_deployment'
                elif str(existing.get('state') or '').upper() == 'OPEN':
                    pr = existing

            if pr is not None:
                record['pr_number'] = int(pr['number'])
                record['branch'] = str(pr['headRefName'])

                # CI failures owned by this repair feed back through the same bounded
                # reasoning/apply/test path instead of waiting for a human prompt.
                if phase in {'ci_repair_needed', 'ci_repairing'}:
                    worktree = ensure_worktree(repo, item_id, record['branch'])
                    if phase == 'ci_repair_needed':
                        rid = queue_reasoning(
                            spool,
                            kind='edit_plan',
                            item=item,
                            context={
                                'mode': 'ci_repair',
                                'ci_failure': failed_ci_context(repo, record['branch']),
                                'source_excerpts': diff_excerpts(worktree, gate, policy),
                            },
                        )
                        record.update({
                            'phase': 'ci_repairing',
                            'reasoning_request_id': rid,
                            'updated_at': now(),
                        })
                        continue
                    response = reasoning_response(spool, str(record.get('reasoning_request_id') or ''))
                    if response is None:
                        continue
                    if response.get('status') != 'succeeded':
                        record.update({'phase': 'blocked', 'reason': 'CI repair reasoning failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                        continue
                    result = response.get('result') or {}
                    if result.get('blocked_reason'):
                        record.update({'phase': 'blocked', 'reason': str(result['blocked_reason']), 'updated_at': now()})
                        continue
                    apply_edits(worktree, list(result.get('edits') or []), gate, policy)
                    validate_patch(worktree, list(result.get('test_paths') or []), gate, policy)
                    commit_existing(worktree, item_id)
                    record.update({
                        'phase': 'pr_validating',
                        'attempts': int(record.get('attempts', 0)) + 1,
                        'reason': '',
                        'updated_at': now(),
                    })
                    continue

                fresh_pr = pr_view(repo, int(pr['number']))
                if str(fresh_pr.get('mergeStateStatus') or '').upper() == 'BEHIND':
                    run(['gh', 'pr', 'update-branch', str(pr['number'])], cwd=repo, check=False)
                    record.update({'phase': 'pr_validating', 'reason': 'branch update requested', 'updated_at': now()})
                    continue

                check_phase, detail = check_state(fresh_pr)
                if check_phase == 'passed':
                    eligible, reason = eligible_premerge(repo, int(pr['number']), gate, policy)
                    if not eligible:
                        record.update({'phase': 'blocked', 'reason': reason, 'updated_at': now()})
                    else:
                        run(['gh', 'pr', 'merge', str(pr['number']), '--merge', '--delete-branch'], cwd=repo)
                        merged = pr_view(repo, int(pr['number']))
                        merge_commit = merged.get('mergeCommit') or {}
                        merge_sha = str(merge_commit.get('oid') or merge_commit.get('sha') or '')
                        record.update({
                            'phase': 'merged_waiting_deployment',
                            'merge_sha': merge_sha,
                            'reason': '',
                            'updated_at': now(),
                        })
                elif check_phase == 'failed':
                    if int(record.get('attempts', 0)) >= 2:
                        record.update({
                            'phase': 'blocked',
                            'reason': 'repair-owned CI retry boundary exhausted: ' + ', '.join(detail),
                            'updated_at': now(),
                        })
                    else:
                        record.update({
                            'phase': 'ci_repair_needed',
                            'reason': ', '.join(detail),
                            'updated_at': now(),
                        })
                else:
                    record.update({'phase': 'pr_validating', 'reason': ', '.join(detail), 'updated_at': now()})
                continue

            if phase == 'merged_waiting_deployment':
                merge_sha = str(record.get('merge_sha') or '')
                prod_state = production_state_from_main(repo)
                production = prod_state.get('production') if isinstance(prod_state, Mapping) else {}
                production = production if isinstance(production, Mapping) else {}
                if (
                    str(production.get('status') or '') == 'aligned_and_healthy'
                    and str(production.get('revision') or '') == merge_sha
                ):
                    rid = record.get('acceptance_request_id')
                    if not rid:
                        rid = queue_reasoning(
                            spool,
                            kind='acceptance_review',
                            item=item,
                            context={
                                'merge_sha': merge_sha,
                                'production': dict(production),
                                'repair_pr_number': record.get('pr_number'),
                                'ci_required_checks_passed': True,
                            },
                        )
                        record.update({
                            'phase': 'production_verifying',
                            'acceptance_request_id': rid,
                            'updated_at': now(),
                        })
                else:
                    record.update({
                        'phase': 'merged_waiting_deployment',
                        'reason': 'waiting for governed deployment and reconciled production revision',
                        'updated_at': now(),
                    })
                continue

            if phase == 'production_verifying':
                response = reasoning_response(spool, str(record.get('acceptance_request_id') or ''))
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({'phase': 'blocked', 'reason': 'production acceptance review failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                    continue
                result = response.get('result') or {}
                if result.get('verified') is not True:
                    missing = result.get('missing_evidence') or []
                    record.update({
                        'phase': 'production_verifying',
                        'reason': 'acceptance evidence incomplete: ' + '; '.join(str(value) for value in missing)[:900],
                        'updated_at': now(),
                    })
                    continue
                closure_number = create_closure_pr(
                    repo,
                    item,
                    str(record.get('merge_sha') or ''),
                    str(result.get('reason') or 'acceptance criteria verified'),
                )
                record.update({
                    'phase': 'closure_validating',
                    'closure_pr_number': closure_number,
                    'acceptance_reason': str(result.get('reason') or ''),
                    'reason': '',
                    'updated_at': now(),
                })
                continue

            worktree = ensure_worktree(repo, item_id, record.get('branch'))
            record['branch'] = run(['git', 'branch', '--show-current'], cwd=worktree)

            if phase in {'identified', 'diagnosing'}:
                rid = record.get('reasoning_request_id')
                if not rid:
                    rid = queue_reasoning(spool, kind='search_plan', item=item, context={})
                    record.update({'phase': 'diagnosing', 'reasoning_request_id': rid, 'updated_at': now()})
                    continue
                response = reasoning_response(spool, str(rid))
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({'phase': 'blocked', 'reason': 'reasoning request failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                    continue
                result = response.get('result') or {}
                if result.get('blocked_reason'):
                    record.update({'phase': 'blocked', 'reason': str(result['blocked_reason']), 'updated_at': now()})
                    continue
                excerpts = safe_search(worktree, list(result.get('search_terms') or []), gate, policy)
                if not excerpts:
                    record.update({'phase': 'blocked', 'reason': 'no J-CHANGE-002-eligible source excerpts matched repair search plan', 'updated_at': now()})
                    continue
                edit_rid = queue_reasoning(
                    spool,
                    kind='edit_plan',
                    item=item,
                    context={'diagnosis': result.get('diagnosis'), 'source_excerpts': excerpts},
                )
                record.update({'phase': 'implementing', 'reasoning_request_id': edit_rid, 'updated_at': now()})
                continue

            if phase == 'implementing':
                response = reasoning_response(spool, str(record.get('reasoning_request_id') or ''))
                if response is None:
                    continue
                if response.get('status') != 'succeeded':
                    record.update({'phase': 'blocked', 'reason': 'edit reasoning failed: ' + str(response.get('error') or ''), 'updated_at': now()})
                    continue
                result = response.get('result') or {}
                if result.get('blocked_reason'):
                    record.update({'phase': 'blocked', 'reason': str(result['blocked_reason']), 'updated_at': now()})
                    continue
                apply_edits(worktree, list(result.get('edits') or []), gate, policy)
                tests = validate_patch(worktree, list(result.get('test_paths') or []), gate, policy)
                number = commit_and_pr(repo, worktree, item, tests[0])
                record.update({
                    'phase': 'pr_validating',
                    'pr_number': number,
                    'attempts': int(record.get('attempts', 0)) + 1,
                    'reason': '',
                    'updated_at': now(),
                })
                continue

        except Exception as exc:
            record.update({
                'phase': 'blocked',
                'reason': f'{type(exc).__name__}: {str(exc)[:900]}',
                'updated_at': now(),
            })

    state['updated_at'] = now()
    save_state(state_path, state)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
