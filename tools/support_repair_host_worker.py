#!/usr/bin/env python3
"""Native host-side implementation worker for approved Project Jason SUPPORT defects.

The worker owns only isolated repository/GitHub mechanics. It never receives the
OpenAI key and never grants itself provider authority. Patch proposals are produced
by the Jason runtime through a bounded spool and are then deterministically validated
against J-CHANGE-002 path/size/test controls before any git mutation.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import logging
import os
import re
import sqlite3
import stat
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
# Tests and production both load tools by exact file path; pin our sibling module.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import engineering_evidence_tools

DEFAULT_REPO = Path('/home/al/projects/jason')
DEFAULT_SPOOL = Path('/var/lib/jason/openclaw/support-repair')
DEFAULT_LIFECYCLE_EVENT_ROOT = Path('/var/lib/jason/openclaw/autonomous-repair/lifecycle-events')
SUPPORT_ROW = re.compile(r'^\|\s*(SUPPORT-[^|]+?)\s*\|\s*(P\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|')
SUPPORT_ID_PATTERN = r'SUPPORT-(?:[A-Z]+-[0-9]+|AUTO-[A-F0-9]{12})'
META = re.compile(rf'(?im)^\s*-\s*Support item\s*:\s*({SUPPORT_ID_PATTERN})\s*$')
SUPPORT_ID_IN_TITLE = re.compile(rf'\b({SUPPORT_ID_PATTERN})\b', re.IGNORECASE)
PRIORITY = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
logger = logging.getLogger(__name__)


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


def emit_lifecycle_event(
    *,
    event_type: str,
    work_id: str,
    work_title: str,
    summary: str,
    owner_action: str = '',
    event_root: Path | None = None,
) -> str:
    event_root = Path(event_root or DEFAULT_LIFECYCLE_EVENT_ROOT)
    event_type = str(event_type).strip().casefold()
    if event_type not in {'work_started', 'work_blocked', 'work_completed'}:
        raise WorkerError('unsupported lifecycle event type')
    work_id = str(work_id).strip()[:80]
    work_title = str(work_title).strip()[:180]
    summary = str(summary).strip()[:400]
    owner_action = str(owner_action).strip()[:300]
    if not work_id or not work_title or not summary:
        raise WorkerError('lifecycle event requires work id, title, and summary')
    fingerprint = hashlib.sha256(
        '|'.join((event_type, work_id, work_title, summary, owner_action)).encode('utf-8')
    ).hexdigest()[:24]
    atomic_json(
        event_root / f'{fingerprint}.json',
        {
            'event_type': event_type,
            'work_id': work_id,
            'work_title': work_title,
            'summary': summary,
            'owner_action': owner_action,
            'fingerprint': fingerprint,
            'created_at': now(),
        },
    )
    return fingerprint


def run(args: list[str], *, cwd: Path | None = None, check: bool = True,
        env: Mapping[str, str] | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=dict(env) if env is not None else None,
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
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            raw = run(['gh', *args], cwd=cwd)
            return json.loads(raw) if raw else None
        except (WorkerError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1.0)
    raise WorkerError(
        'GitHub JSON command failed after 3 bounded attempts: '
        + str(last_error or 'unknown error')[:500]
    ) from last_error


def transient_github_listing_failure(exc: Exception) -> bool:
    """Defer only transient GitHub transport failures, never permission errors."""
    detail = str(exc)
    return any(marker in detail for marker in (
        'HTTP 502', 'HTTP 503', 'HTTP 504', 'unexpected end of JSON input',
    ))


def open_prs(repo: Path) -> list[dict[str, Any]]:
    # Selected PRs get full CI checks through pr_view; bulk discovery needs
    # only metadata and body. A complete list is mandatory before reconciling.
    limit = 1000
    fields = 'number,title,body,headRefName,url,isDraft'
    data = gh_json(['pr', 'list', '--state', 'open', '--limit', str(limit), '--json', fields], cwd=repo)
    if not isinstance(data, list) or len(data) >= limit:
        raise WorkerError('GitHub open PR listing is incomplete or invalid; refusing partial reconciliation')
    if any(not isinstance(item, dict) or not isinstance(item.get('number'), int)
           or not isinstance(item.get('headRefName'), str)
           or not isinstance(item.get('body'), str) for item in data):
        raise WorkerError('GitHub open PR listing contains an invalid record')
    if len({item['number'] for item in data}) != len(data):
        raise WorkerError('GitHub open PR listing contains duplicate identities')
    return data


def support_id_from_title(title: str) -> str | None:
    match = SUPPORT_ID_IN_TITLE.search(str(title or ''))
    return match.group(1).upper() if match else None


def open_support_issue_records(repo: Path) -> dict[str, dict[str, Any]]:
    """Preserve every GitHub issue number; an ID alone is not an issue identity.

    Automatically detected incident IDs represent one fingerprinted repair even
    if duplicate GitHub reports exist. Distinct manual SUPPORT issues sharing
    an ID cannot be safely admitted or closed until their identities are fixed.
    """
    limit = 1000
    # GitHub search result pages can shift while issues are updated; fixed
    # creation ordering narrows that race but does not establish a snapshot.
    command = [
        'issue', 'list', '--state', 'open',
        '--search', 'SUPPORT- in:title sort:created-asc',
        '--limit', str(limit), '--json', 'number,title',
    ]

    def validated_snapshot(raw: Any) -> tuple[dict[int, str], bool]:
        if not isinstance(raw, list) or len(raw) >= limit:
            raise WorkerError('GitHub open SUPPORT listing incomplete; refusing partial admission')
        seen: dict[int, str] = {}
        repeated_identical = False
        for issue in raw:
            if not isinstance(issue, Mapping):
                raise WorkerError('GitHub SUPPORT issue record is not an object')
            number = issue.get('number')
            if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
                raise WorkerError('GitHub SUPPORT issue number missing or repeated')
            title = issue.get('title')
            if not isinstance(title, str) or not title:
                raise WorkerError('GitHub SUPPORT issue title missing or invalid')
            if number in seen:
                # Two DIFFERENT records claiming one immutable issue number are
                # never an admissible pagination artifact.
                if seen[number] != title:
                    raise WorkerError('GitHub SUPPORT issue number missing or repeated')
                repeated_identical = True
            else:
                seen[number] = title
        return seen, repeated_identical

    numbers, repeated = validated_snapshot(gh_json(command, cwd=repo))
    if repeated:
        # Never silently deduplicate a malformed GitHub result. Re-fetch two
        # clean complete listings independently and require identical
        # number/title identities before any SUPPORT admission or closure.
        logger.warning(
            'GITHUB_SUPPORT_LISTING_INCONSISTENT kind=repeated_identical_issue '
            'unique_issue_numbers=%d; checking two bounded fresh snapshots',
            len(numbers),
        )
        verified, again = validated_snapshot(gh_json(command, cwd=repo))
        if again:
            raise WorkerError('GitHub SUPPORT issue number missing or repeated after bounded recheck')
        confirmation, again = validated_snapshot(gh_json(command, cwd=repo))
        if again or verified != confirmation:
            raise WorkerError('GitHub SUPPORT issue listing inconsistent after bounded recheck')
        numbers = confirmation

    grouped: dict[str, list[tuple[int, str]]] = {}
    for number, title in numbers.items():
        item_id = support_id_from_title(title)
        if item_id:
            grouped.setdefault(item_id, []).append((number, title))

    records: dict[str, dict[str, Any]] = {}
    for item_id, issues in grouped.items():
        ordered = sorted(issues)
        records[item_id] = {
            'title': ordered[0][1],
            'priority': 'P0' if any(re.search(r'\bP0\b', title, re.I)
                                    for _, title in ordered) else 'unknown',
            'issue_numbers': [number for number, _ in ordered],
            'issue_count': len(ordered),
            'duplicate_issue_records': len(ordered) > 1,
            # A fingerprinted AUTO item remains one logical work item. All
            # its GitHub reports still require explicit closure reconciliation.
            'identity_conflict': (len(ordered) > 1
                                  and not item_id.startswith('SUPPORT-AUTO-')),
        }
    return records

def open_support_issue_ids(repo: Path) -> set[str]:
    return {
        item_id for item_id, issue in open_support_issue_records(repo).items()
        if not issue.get('identity_conflict')
    }


def audit_support_admission(issues: Mapping[str, Mapping[str, Any]],
                            support: list[dict[str, str]],
                            state: dict[str, Any], *,
                            event_root: Path | None = None) -> list[str]:
    """Audit real issue identities, including collisions hidden by ID grouping."""
    known = {item['id'] for item in support}
    priorities = {item['id']: item.get('priority') for item in support}
    conflicts = {
        key: list(value.get('issue_numbers') or [])
        for key, value in issues.items() if value.get('identity_conflict')
    }
    duplicates = {
        key: list(value.get('issue_numbers') or [])
        for key, value in issues.items() if value.get('duplicate_issue_records')
    }
    missing = sorted(
        item_id for item_id, issue in issues.items()
        if (issue.get('priority') == 'P0' or priorities.get(item_id) == 'P0')
        and (item_id not in known or item_id in conflicts)
    )
    state['admission_audit'] = {
        'checked_at': now(),
        'open_issue_count': sum(int(value.get('issue_count') or 1)
                                for value in issues.values()),
        'logical_work_id_count': len(issues),
        'identity_conflicts': conflicts,
        'duplicate_issue_records': duplicates,
        'unadmitted_p0': missing,
        'status': 'degraded' if missing or duplicates else 'healthy',
    }
    for item_id in missing:
        if item_id in conflicts:
            summary = ('Multiple open GitHub issues share one manual SUPPORT ID; '
                       'no issue may be selected or closed by ambiguous ID.')
            owner_action = ('Assign distinct canonical IDs to GitHub issues '
                            + ', '.join(str(n) for n in conflicts[item_id][:8])
                            + ' through reviewed source and issue reconciliation.')
        else:
            summary = 'Open P0 SUPPORT issue has no canonical support source row; admission is blocked.'
            owner_action = 'Reconcile issue with canonical SUPPORT.md through reviewed GitHub PR.'
        emit_lifecycle_event(
            event_type='work_blocked', work_id=item_id,
            work_title=issues[item_id]['title'],
            summary=summary, owner_action=owner_action, event_root=event_root,
        )
    auto_duplicates = [key for key in duplicates if key.startswith('SUPPORT-AUTO-')]
    if auto_duplicates:
        emit_lifecycle_event(
            event_type='work_blocked', work_id='SUPPORT-AUTO-IDENTITY-AUDIT',
            work_title='Duplicate automatic support incident records',
            summary=(f'{len(auto_duplicates)} fingerprinted support items have '
                     'multiple open GitHub reports. Logical work is deduplicated, '
                     'but each report remains open pending explicit verification.'),
            owner_action=('Reconcile duplicate GitHub issue numbers before closure; '
                          'never discard differing incident evidence.'),
            event_root=event_root,
        )
    return missing

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
        root_invariant = str(value.get('root_invariant') or '').strip()
        occurrence_count = int(value.get('occurrence_count') or 1)
        repair_level = int(value.get('repair_level') or 2)
        repair_class = str(value.get('repair_class') or 'bounded_autonomous_repair').strip()
        verification = value.get('verification_contract') if isinstance(value.get('verification_contract'), Mapping) else {}
        required_checks = verification.get('required_checks') if isinstance(verification.get('required_checks'), list) else []
        evidence = str(value.get('evidence') or '').strip()
        if root_invariant:
            evidence = (evidence + '; root invariant: ' + root_invariant).strip('; ')
        evidence += f'; repair level: L{repair_level} {repair_class}; occurrence: {occurrence_count}'
        acceptance = str(value.get('acceptance') or '').strip()
        if required_checks:
            acceptance += ' Verification contract: ' + '; '.join(str(item) for item in required_checks[:5]) + '.'
        incidents.append({
            'id': item_id,
            'priority': str(value.get('priority') or 'P1').upper(),
            'status': 'Open - self-heal incident',
            'title': str(value.get('title') or 'Jason self-heal incident')[:240],
            'evidence': evidence[:1600],
            'acceptance': acceptance[:1600],
        })
    incidents.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    return incidents


def load_development_recovery_incidents(spool: Path) -> list[dict[str, str]]:
    """Admit only approved, validated handoffs routed by development worker."""
    path = spool / 'development-state.json'
    if not path.is_file():
        return []
    state = load_state(path)
    records = state.get('items') if isinstance(state.get('items'), Mapping) else {}
    incidents = []
    for item_id, record in records.items():
        if not isinstance(record, Mapping) or record.get('phase') != 'blocked':
            continue
        intake = record.get('recovery_handoff_intake')
        if not isinstance(intake, Mapping) or intake.get('status') != 'awaiting_governed_repair':
            continue
        issue = record.get('issue_number')
        if not isinstance(issue, int) or issue < 1:
            continue
        identifier = f'SUPPORT-DEV-{issue}'
        if record.get('recovery_support_issue_raised') != identifier:
            continue
        if intake.get('handoff_id') != record.get('recovery_handoff_id'):
            continue
        incidents.append({
            'id': identifier, 'priority': 'P0',
            'status': 'Open - governed development recovery',
            'title': f'Repair exhausted development #{issue}',
            'evidence': (f'Original item {item_id}; handoff {intake["handoff_id"]}; '
                f'blocker {str(record.get("reason") or "")[:900]}; '
                f'diagnosis {str(record.get("recovery_diagnostic_summary") or "")[:500]}')[:1600],
            'acceptance': (
                'Source regression tests and release evidence must prove the repair; '
                're-admission requires independent upstream-dependency and production acceptance.'
            ),
        })
    return sorted(incidents, key=lambda item: item['id'])



def self_heal_post_production_verification(
    repo: Path,
    item_id: str,
    root: Path = Path('/var/lib/jason/openclaw/self-heal'),
) -> tuple[bool, str, dict[str, Any]]:
    if not item_id.startswith('SUPPORT-AUTO-'):
        return True, 'not a self-heal incident', {}

    incident: dict[str, Any] | None = None
    for path in sorted((root / 'incidents').glob('*.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, Mapping) and str(value.get('support_item') or '').upper() == item_id:
            incident = dict(value)
            break
    if incident is None:
        return False, 'self-heal incident evidence is missing', {}

    family = str(incident.get('family') or '').strip()
    if not family:
        return True, 'legacy self-heal incident has no family verification contract', {'legacy': True}
    verification = incident.get('verification_contract') if isinstance(incident.get('verification_contract'), Mapping) else {}
    related = verification.get('related_families_must_be_healthy') if isinstance(verification.get('related_families_must_be_healthy'), list) else [family]

    code = (
        "import json; from pathlib import Path; "
        "import jason_self_heal_watchdog as w; "
        "from issue_resolution_engine import failure_family; "
        f"failures,_=w.detect(Path({str(root)!r})); "
        "print(json.dumps({'failures':failures,'families':sorted(set(failure_family(x) for x in failures))}))"
    )
    try:
        raw = run(
            [
                '/usr/bin/env',
                f'PYTHONPATH={repo / "tools"}',
                '/usr/bin/python3',
                '-c',
                code,
            ],
            cwd=repo,
        )
        observed = json.loads(raw)
    except (WorkerError, ValueError, json.JSONDecodeError) as exc:
        return False, f'post-production detector execution failed: {type(exc).__name__}', {}

    families = {str(value) for value in observed.get('families', [])}
    still_degraded = sorted(families.intersection(str(value) for value in related))
    if still_degraded:
        return False, 'related invariant families remain degraded: ' + ', '.join(still_degraded), dict(observed)
    return True, 'original detector family and related invariants are healthy', dict(observed)


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


def support_worktree_path(item_id: str, branch: str | None = None) -> Path:
    # An exact failed-anchor incident may need a fresh, separately named
    # worktree. Its previous partial proposal remains untouched for audit.
    if re.fullmatch(SUPPORT_ID_PATTERN, item_id) is None:
        raise WorkerError('invalid support identity for repair worktree')
    normal = branch_name(item_id)
    if branch and re.fullmatch(re.escape(normal) + r'-(?:anchor|context|evidence)-[0-9a-f]{12}', branch):
        return Path('/home/al/jason-worktrees/support-repair') / branch.split('/')[-1]
    return Path('/home/al/jason-worktrees/support-repair') / item_id.casefold()


def ensure_worktree(repo: Path, item_id: str, branch: str | None = None) -> Path:
    root = Path('/home/al/jason-worktrees/support-repair')
    if root.is_symlink():
        raise WorkerError('repair worktree root must not be a symlink')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = support_worktree_path(item_id, branch)
    if path.is_symlink():
        raise WorkerError('repair worktree path is a symlink')
    if path.exists():
        if (branch and branch != branch_name(item_id)
                and run(['git', 'branch', '--show-current'], cwd=path) != branch):
            raise WorkerError('recovery worktree does not match its pinned branch')
        return path
    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    selected = branch or branch_name(item_id)
    remote = run(['git', 'ls-remote', '--heads', 'origin', selected], cwd=repo, check=False)
    if remote:
        run(['git', 'worktree', 'add', '-B', selected, str(path), f'origin/{selected}'], cwd=repo)
    else:
        run(['git', 'worktree', 'add', '-b', selected, str(path), 'origin/main'], cwd=repo)
    return path


_SEARCH_STOP_WORDS = {
    'about', 'after', 'against', 'because', 'between', 'compare', 'could', 'defect',
    'during', 'from', 'into', 'issue', 'jason', 'likely', 'logic', 'more', 'process',
    'repair', 'reported', 'should', 'state', 'support', 'than', 'that', 'their', 'there',
    'these', 'this', 'through', 'using', 'when', 'where', 'which', 'with', 'worker',
}


def expanded_search_terms(terms: list[str]) -> list[str]:
    """Turn model search phrases into deterministic literal grep candidates.

    The reasoning model often returns descriptive multi-word phrases that are useful
    to a human but too specific for fixed-string repository grep. Preserve each
    original phrase, then add bounded identifier/keyword tokens so exact source
    symbols such as ``selected_gt_active_slots`` can still be located.
    """
    expanded: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = value.strip()
        key = value.casefold()
        if len(value) < 2 or key in seen:
            return
        seen.add(key)
        expanded.append(value)

    for raw in terms[:8]:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if len(text) < 2:
            continue
        add(text)
        for token in re.findall(r'[A-Za-z0-9_.:/-]{4,}', text):
            if token.casefold() in _SEARCH_STOP_WORDS:
                continue
            add(token)
            for part in re.split(r'[_:/.\-]+', token):
                if len(part) >= 4 and part.casefold() not in _SEARCH_STOP_WORDS:
                    add(part)
            if len(expanded) >= 40:
                break
        if len(expanded) >= 40:
            break
    return expanded[:40]




def search_path_priority(path: str) -> tuple[int, str]:
    """Prefer implementation-bearing source over narrative documentation."""
    normalized = path.casefold()
    if normalized.startswith('implementation/'):
        rank = 0
    elif normalized.startswith('tools/'):
        rank = 1
    elif normalized.startswith('config/'):
        rank = 2
    elif normalized.startswith('infrastructure/'):
        rank = 3
    elif normalized.startswith('scripts/'):
        rank = 4
    elif normalized.startswith('.github/'):
        rank = 5
    elif normalized.startswith('docs/'):
        rank = 8
    elif normalized in {'readme.md', 'support.md'}:
        rank = 9
    else:
        rank = 6
    return rank, normalized

def companion_source_paths(path: str) -> list[str]:
    """Return deterministic source/test companions for common repository layouts."""
    candidate = Path(path)
    parts = list(candidate.parts)
    companions: list[str] = []

    def add(value: Path) -> None:
        normalized = value.as_posix()
        if normalized not in companions:
            companions.append(normalized)

    if candidate.name.startswith('test_'):
        add(candidate.parent / candidate.name[5:])

    if 'tests' in parts and candidate.name.startswith('test_'):
        test_index = len(parts) - 1 - parts[::-1].index('tests')
        project_root = Path(*parts[:test_index])
        source_name = candidate.name[5:]
        source_stem = Path(source_name).stem
        add(project_root / source_name)
        add(project_root / 'src' / source_name)
        # Package-level registry/service tests commonly use test_<package>.py
        # while implementation lives in <package>/service.py and contracts.py.
        add(project_root / source_stem / 'service.py')
        add(project_root / source_stem / 'contracts.py')
        add(project_root / source_stem / 'repository.py')
        # Common Python package layout: project/tests/test_x.py maps to
        # project/src/<package>/x.py. Exact package resolution is completed by
        # bounded repository matching in safe_search.
        return companions

    if candidate.suffix != '.py':
        return companions

    test_name = f'test_{candidate.name}'
    add(candidate.parent / test_name)
    add(candidate.parent / 'tests' / test_name)

    # Map project/src/package/module.py to project/tests/test_module.py.
    if 'src' in parts:
        src_index = parts.index('src')
        if src_index > 0:
            project_root = Path(*parts[:src_index])
            add(project_root / 'tests' / test_name)

    # Map project/package/module.py to project/tests/test_module.py for the
    # repository's implementation/<component>/... layout.
    if len(parts) >= 3 and parts[0] == 'implementation':
        project_root = Path(*parts[:2])
        add(project_root / 'tests' / test_name)

    return companions


def safe_search(worktree: Path, terms: list[str], gate, policy: Mapping[str, Any]) -> list[dict[str, str]]:
    candidate_scores: dict[str, int] = {}
    concept_scores: list[tuple[dict[str, int], set[str], str | None]] = []

    def eligible_path(path: str) -> str | None:
        path = path.strip()
        if not path or path.startswith('.git'):
            return None
        if gate.path_denial_reason(path, dict(policy)):
            return None
        if not (worktree / path).is_file():
            return None
        return path

    def normalized_tokens(value: str) -> set[str]:
        tokens: set[str] = set()
        for raw in re.split(r'[^a-z0-9]+', value.casefold()):
            if len(raw) < 4:
                continue
            token = raw
            if token.endswith('ies') and len(token) > 4:
                token = token[:-3] + 'y'
            elif token.endswith('s') and len(token) > 4:
                token = token[:-1]
            tokens.add(token)
        return tokens

    # Score each reasoning concept separately. This preserves conceptual coverage
    # across multi-part engineering work instead of letting one broad subsystem or
    # one high-frequency token consume every excerpt slot. Candidate metadata is
    # bounded by repository paths; actual file reads remain bounded below.
    for raw_concept in terms[:8]:
        if not isinstance(raw_concept, str) or len(raw_concept.strip()) < 2:
            continue
        group: dict[str, int] = {}
        expanded = expanded_search_terms([raw_concept])
        for term in expanded:
            output = run(['git', 'grep', '-l', '-I', '-i', '-F', term], cwd=worktree, check=False)
            matched_this_term: set[str] = set()
            for raw in output.splitlines():
                path = eligible_path(raw)
                if path is None or path in matched_this_term:
                    continue
                group[path] = group.get(path, 0) + 1
                candidate_scores[path] = candidate_scores.get(path, 0) + 1
                matched_this_term.add(path)
        if group:
            concept_tokens = normalized_tokens(raw_concept)
            ordered = [
                token
                for token in re.split(r'[^a-z0-9]+', raw_concept.casefold())
                if len(token) >= 4
            ]
            subject = None
            if ordered:
                subject = ordered[0]
                if subject.endswith('ies') and len(subject) > 4:
                    subject = subject[:-3] + 'y'
                elif subject.endswith('s') and len(subject) > 4:
                    subject = subject[:-1]
            concept_scores.append((group, concept_tokens, subject))

    query_tokens = normalized_tokens(' '.join(str(term) for term in terms[:8]))

    def relevance_key(
        path: str,
        score: int,
        tokens: set[str],
        subject: str | None = None,
    ) -> tuple[int, int, int, str]:
        path_tokens = normalized_tokens(path)
        path_overlap = len(tokens & path_tokens)
        subject_bonus = 5 if subject is not None and subject in path_tokens else 0
        source_rank, normalized = search_path_priority(path)
        return (
            source_rank,
            -(score + (3 * path_overlap) + subject_bonus),
            -score,
            normalized,
        )

    # Content-only grep can select tests mentioning a provider while missing
    # short implementation modules whose names (not bodies) identify it.
    # Admit a bounded set of real, policy-eligible implementation filenames,
    # weighted toward uncommon query tokens. No document text or provider data
    # is consulted; these are paths from the checked-out repository only.
    tracked_paths = [
        path for raw in run(['git', 'ls-files', '--', '*.py'], cwd=worktree,
                            check=False).splitlines()
        if (path := eligible_path(raw)) is not None
        and path.startswith('implementation/')
        and '/tests/' not in path
        and not path.endswith('/__init__.py')
    ]
    names = {path: normalized_tokens(path) for path in tracked_paths}
    frequencies: dict[str, int] = {}
    for tokens in names.values():
        for token in tokens:
            frequencies[token] = frequencies.get(token, 0) + 1

    ranked_names: list[tuple[float, int, str]] = []
    for path, tokens in names.items():
        matching = tokens & query_tokens
        if not matching or not any(frequencies[t] <= 32 for t in matching):
            continue
        specificity = sum(1.0 / frequencies[t] for t in matching)
        ranked_names.append((-specificity, -len(matching), path))

    paths: list[str] = [
        path for _, _, path in sorted(ranked_names)[:5]
    ]

    # First pass: one best source candidate per reasoning concept.
    for group, concept_tokens, subject in concept_scores:
        ranked = sorted(
            group,
            key=lambda path: relevance_key(
                path, group[path], concept_tokens, subject
            ),
        )
        for path in ranked:
            if path not in paths:
                paths.append(path)
                break
        if len(paths) >= 8:
            break

    # Second pass: fill any remaining slots by aggregate relevance.
    if len(paths) < 8:
        ranked_all = sorted(
            candidate_scores,
            key=lambda path: relevance_key(
                path, candidate_scores[path], query_tokens
            ),
        )
        for path in ranked_all:
            if path not in paths:
                paths.append(path)
            if len(paths) >= 8:
                break

    # Add deterministic implementation/test companions where they exist.
    for path in list(paths):
        for companion in companion_source_paths(path):
            eligible = eligible_path(companion)
            if eligible is not None and eligible not in paths:
                paths.append(eligible)
            if len(paths) >= 12:
                break
        if len(paths) >= 12:
            break

    excerpts = []
    expanded_terms = expanded_search_terms(terms)
    for path in paths:
        candidate = worktree / path
        try:
            text = candidate.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        excerpts.append({
            'path': path,
            'content': bounded_relevant_excerpt(text, expanded_terms, content_limit=14000),
        })
    return excerpts


def bounded_relevant_excerpt(
    text: str,
    terms: list[str],
    *,
    content_limit: int = 14000,
) -> str:
    """Return bounded file context that includes literal match neighborhoods.

    Long implementation files previously contributed only their prefix, which could
    omit the exact function a search term matched. Keep a small prefix for imports
    and definitions, then add bounded windows around literal matches.
    """
    limit = max(1000, int(content_limit))
    if len(text) <= limit:
        return text

    prefix_limit = min(2000, limit // 4)
    chunks = [text[:prefix_limit]]
    remaining = limit - len(chunks[0])
    seen_ranges: list[tuple[int, int]] = []
    lowered = text.casefold()

    for raw in terms[:40]:
        term = str(raw or '').strip()
        if len(term) < 2:
            continue
        pos = lowered.find(term.casefold())
        if pos < 0:
            continue
        half = min(3000, max(800, remaining // 2))
        start = max(0, pos - half)
        end = min(len(text), pos + len(term) + half)
        if any(not (end <= a or start >= b) for a, b in seen_ranges):
            continue
        chunk = text[start:end]
        if len(chunk) > remaining:
            chunk = chunk[:remaining]
            end = start + len(chunk)
        if not chunk:
            break
        chunks.append(f'\n... excerpt near match {term!r} ...\n' + chunk)
        seen_ranges.append((start, end))
        remaining = limit - sum(len(value) for value in chunks)
        if remaining < 800:
            break

    return ''.join(chunks)[:limit]


def bounded_symbol_excerpt(text: str, symbols: list[str], *, content_limit: int) -> str | None:
    """Keep complete matching Python definitions, never mid-function fragments."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    wanted = {value for value in symbols if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value)}
    if not wanted:
        return None
    lines = text.splitlines(keepends=True)
    matches = [node for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               and node.name in wanted]
    if not matches:
        return None
    # A raw character prefix can end inside an unrelated function, making an
    # otherwise complete symbol excerpt appear truncated to the edit planner.
    # Admit only complete top-level syntax nodes within the bounded preamble.
    preamble_limit = min(1300, content_limit // 6)
    preamble_end = 0
    for node in tree.body:
        ending = sum(len(line) for line in lines[:node.end_lineno])
        if ending > preamble_limit:
            break
        preamble_end = ending
    chunks = [text[:preamble_end]]
    for node in sorted(matches, key=lambda n: n.lineno):
        start = min([node.lineno, *[d.lineno for d in getattr(node, 'decorator_list', [])]]) - 1
        snippet = ''.join(lines[start:node.end_lineno])
        if sum(map(len, chunks)) + len(snippet) + 32 > content_limit:
            continue
        chunks.append(f'\n# Complete definition at line {start + 1}\n' + snippet)
    return ''.join(chunks) if len(chunks) > 1 else None


def source_excerpts_for_paths(
    worktree: Path,
    paths: list[str],
    gate,
    policy: Mapping[str, Any],
    *,
    terms: list[str] | None = None,
    limit: int = 6,
    content_limit: int = 24000,
    full_file_paths: list[str] | None = None,
) -> list[dict[str, str]]:
    """Read policy-eligible source, requiring complete bytes for requested files."""
    excerpts: list[dict[str, str]] = []
    seen: set[str] = set()
    required_full = set(full_file_paths or [])
    for raw in paths:
        path = str(raw or '').strip()
        if not path or path in seen or path.startswith('.git'):
            continue
        if gate.path_denial_reason(path, dict(policy)):
            continue
        candidate = worktree / path
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if path in required_full and len(text) > content_limit:
            raise WorkerError('required complete source exceeds bounded limit: ' + path)
        symbols = [] if path in required_full else [
            word for term in list(terms or []) for word in re.findall(
                r'[A-Za-z_][A-Za-z0-9_]*', str(term))]
        exact = bounded_symbol_excerpt(text, symbols, content_limit=content_limit)
        content = exact or (
            text
            if len(text) <= content_limit
            else bounded_relevant_excerpt(
                text,
                [str(value) for value in list(terms or [])],
                content_limit=content_limit,
            )
        )
        excerpts.append({'path': path, 'content': content})
        seen.add(path)
        if len(excerpts) >= max(0, int(limit)):
            break
    return excerpts


def merge_source_excerpts(
    prior: list[dict[str, str]],
    current: list[dict[str, str]],
    *,
    max_total: int = 14,
) -> list[dict[str, str]]:
    """Keep prior context while admitting fresh discovery, without unbounded growth."""
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    # Previous context is deliberately sticky during a bounded expansion because
    # later searches are meant to add missing call sites, not replace already
    # useful registry/service/repository evidence.
    for item in [*prior, *current]:
        path = str(item.get('path') or '').strip()
        if not path or path in seen:
            continue
        merged.append({'path': path, 'content': str(item.get('content') or '')})
        seen.add(path)
        if len(merged) >= max(1, int(max_total)):
            break
    return merged


def changed_files(worktree: Path) -> list[str]:
    output = run(['git', 'diff', '--name-only'], cwd=worktree)
    return [line.strip() for line in output.splitlines() if line.strip()]


def apply_edits(worktree: Path, edits: list[Mapping[str, Any]], gate, policy: Mapping[str, Any]) -> list[str]:
    """Prevalidate all bounded anchors before any source-file mutation.

    A late invalid regression-test anchor must not leave earlier source edits
    partially written in the isolated worktree. Consecutive edits to one file
    still operate on the staged replacement, never on unvalidated disk writes.
    """
    if not edits or len(edits) > 12:
        raise WorkerError('repair proposal must contain between 1 and 12 edits')
    touched: list[str] = []
    pending: dict[str, tuple[Path, str]] = {}
    total_delta = 0
    root = worktree.resolve()
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
        parent = target.parent.resolve()
        if parent != root and root not in parent.parents:
            raise WorkerError('invalid repair path')
        if path in pending:
            text = pending[path][1]
            exists = True
        elif target.exists():
            if not target.is_file():
                raise WorkerError(f'repair path is not a file: {path}')
            text = target.read_text(encoding='utf-8')
            exists = True
        else:
            text = ''
            exists = False
        if exists:
            if old == '':
                raise WorkerError(f'new-file repair path already exists: {path}')
            count = text.count(old)
            if count != 1:
                raise WorkerError(f'exact repair anchor must occur once in {path}; found {count}')
            replacement = text.replace(old, new, 1)
        else:
            if old != '':
                raise WorkerError(f'repair path does not exist: {path}')
            replacement = new
        total_delta += old.count('\n') + new.count('\n') + 2
        if total_delta > int(policy.get('max_changed_lines', 800)):
            raise WorkerError('proposed repair exceeds changed-line boundary')
        pending[path] = (target, replacement)
        if path not in touched:
            touched.append(path)
        if len(touched) > int(policy.get('max_changed_files', 25)):
            raise WorkerError('proposed repair exceeds changed-file boundary')
    # Nothing is written until every path, anchor, and size gate has passed.
    for path in touched:
        target, replacement = pending[path]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(replacement, encoding='utf-8')
    return touched


def queue_bounded_anchor_correction(
    spool: Path,
    worktree: Path,
    item: Mapping[str, str],
    record: dict[str, Any],
    edits: list[Mapping[str, Any]],
    test_paths: list[str],
    failure: WorkerError,
    gate,
    policy: Mapping[str, Any],
) -> bool:
    """Retry an invalid exact anchor at most twice with fresh governed source.

    An already-dirty worktree must stop for review: it might contain prior
    partial edits and must never be silently reset or folded into a retry.
    Denied paths, missing authority, and test failures are not anchor retries.
    """
    detail = str(failure)
    if not detail.startswith('exact repair anchor must occur once in '):
        return False
    attempts = int(record.get('proposal_retries') or 0)
    if attempts >= 2:
        return False
    if run(['git', 'status', '--porcelain'], cwd=worktree).strip():
        return False
    paths = [str(edit.get('path') or '').strip() for edit in edits]
    paths.extend(str(path).strip() for path in test_paths)
    excerpts = source_excerpts_for_paths(
        worktree, paths, gate, policy, limit=8, content_limit=14000,
    )
    if not excerpts:
        return False
    request_id = queue_reasoning(
        spool, kind='edit_plan', item=item,
        context={
            'validation_feedback': (
                'The bounded host validator rejected an exact-text anchor: '
                + detail[:350]
                + '. Use only fresh eligible source excerpts. Every old_text '
                'must appear exactly once, and the proposal must edit a '
                'declared regression test. Never weaken the path or authority gate.'
            ),
            'retry_number': attempts + 1,
            'source_excerpts': excerpts,
        },
    )
    if request_id == str(record.get('reasoning_request_id') or ''):
        return False
    record.update({
        'phase': 'implementing',
        'reasoning_request_id': request_id,
        'proposal_retries': attempts + 1,
        'last_anchor_failure': detail[:350],
        'reason': 'bounded exact-anchor correction queued; no edits applied',
        'updated_at': now(),
    })
    return True



def proposed_test_edits(
    edits: list[Mapping[str, Any]],
    test_paths: list[str],
    gate,
    policy: Mapping[str, Any],
) -> list[str]:
    declared = {str(path).strip() for path in test_paths if str(path).strip()}
    changed_tests: list[str] = []
    for edit in edits:
        path = str(edit.get('path') or '').strip()
        if not path or gate.path_denial_reason(path, dict(policy)):
            continue
        if gate.is_test_path(path, dict(policy)):
            changed_tests.append(path)
    if declared:
        return [path for path in changed_tests if path in declared]
    return changed_tests


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
    # Tools tests import sibling modules (for example support_repair_host_worker).
    # An isolated issue worktree must resolve its OWN tools tree, not the host's
    # checkout or a globally installed package. Preserve any caller PYTHONPATH.
    test_env = dict(os.environ)
    own_tools = str((worktree / 'tools').resolve())
    previous_path = test_env.get('PYTHONPATH', '')
    test_env['PYTHONPATH'] = os.pathsep.join(
        [own_tools, previous_path] if previous_path else [own_tools]
    )
    run([python_cmd, '-m', 'pytest', '-q', *selected],
        cwd=worktree, env=test_env)
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


def classify_ci_failure(log: str) -> str:
    text = str(log or '').casefold()
    if (
        'documentationimpacterror' in text
        or "missing required '## documentation impact' section" in text
        or 'documentation impact requires' in text
    ):
        return 'pr_governance_metadata_defect'
    if 'change-integration: fail' in text or 'active implementation overlap with pr #' in text:
        return 'integration_collision'
    if (
        "modulenotfounderror: no module named 'pytest'" in text
        or 'command not found: pytest' in text
        or 'no module named pytest' in text
    ):
        return 'dependency_environment_defect'
    if 'production_health' in text or 'production health' in text:
        return 'production_defect'
    if 'assertionerror' in text or 'failed (' in text or 'failed]' in text:
        return 'code_or_test_defect'
    return 'unclassified_ci_failure'


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
        log_tail = text[-16000:]
        logs.append({
            'name': str(item.get('name') or ''),
            'run_id': int(item['databaseId']),
            'conclusion': str(item.get('conclusion') or ''),
            'classification': classify_ci_failure(log_tail),
            'log': log_tail,
        })
    return {
        'failed_runs': logs,
        'failure_classes': sorted({str(item['classification']) for item in logs}),
    }


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
    if not changed and item['id'].startswith(('SUPPORT-AUTO-', 'SUPPORT-DEV-')):
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
    limit = 20
    issues = gh_json([
        'issue', 'list', '--state', 'open', '--search', f'{item_id} in:title',
        '--limit', str(limit), '--json', 'number,title'
    ], cwd=repo) or []
    if not isinstance(issues, list) or len(issues) >= limit:
        raise WorkerError('GitHub support closure listing is incomplete')
    exact = [issue for issue in issues
             if support_id_from_title(str(issue.get('title') or '')) == item_id.upper()]
    if len(exact) > 1:
        raise WorkerError('ambiguous GitHub issue identity; closure requires unique issue number')
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
    queued_phases = {'identified'}
    active_work_phases = {
        'diagnosing', 'implementing',
        'ci_repair_needed', 'ci_repairing',
    }

    # Passive lifecycle states such as PR validation, deployment waiting, and
    # production verification must continue to reconcile, but queued/identified
    # work does not consume a repair slot until it is explicitly selected below.
    selected = [
        key for key, value in items.items()
        if isinstance(value, Mapping)
        and value.get('phase') not in terminal_phases
        and value.get('phase') not in queued_phases
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
        phase = existing.get('phase')
        if phase in terminal_phases:
            continue
        if phase not in queued_phases and phase is not None:
            # Another nonterminal state was already selected above or is an
            # unknown state that should not be silently promoted into active work.
            continue
        if active_count >= max(1, int(max_active)):
            break
        selected.append(item_id)
        active_count += 1
    return selected



def reassess_model_scope_blocks(
    state: dict[str, Any], support: list[dict[str, str]], spool: Path,
    max_active: int,
) -> list[str]:
    """Retry a model-only scope judgement once, never a denied host gate.

    The reconsideration only queues a search plan. It grants no filesystem,
    code-write, provider, deployment, or root authority; all existing host
    gates still apply. An independently repeated block remains terminal.
    """
    items = state.get('items')
    if not isinstance(items, dict):
        return []
    active = {'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'}
    slots = max(0, max(1, int(max_active)) - sum(
        1 for value in items.values()
        if isinstance(value, Mapping) and value.get('phase') in active
    ))
    resumed: list[str] = []
    for item in support:
        if slots <= 0:
            break
        record = items.get(item['id'])
        if not isinstance(record, dict) or record.get('phase') != 'blocked':
            continue
        if record.get('scope_review_attempted'):
            continue
        reason = str(record.get('reason') or '')
        prior_id = str(record.get('reasoning_request_id') or '')
        if not reason or not prior_id:
            continue
        response = reasoning_response(spool, prior_id)
        if not isinstance(response, Mapping) or response.get('status') != 'succeeded':
            continue
        result = response.get('result')
        if not isinstance(result, Mapping) or str(result.get('blocked_reason') or '') != reason:
            continue
        review_id = queue_reasoning(
            spool, kind='search_plan', item=item,
            context={
                'scope_review': 'source_diagnosis_only',
                'prior_blocked_reason': reason[:1000],
                'boundary': 'No new authority, privileged operation, security change, or production deployment; existing governed approvals remain mandatory.',
            },
        )
        if review_id == prior_id:
            continue
        record.update({
            'phase': 'diagnosing',
            'reasoning_request_id': review_id,
            'scope_review_request_id': review_id,
            'scope_review_attempted': True,
            'reason': 'bounded source-only scope reassessment; no authorization granted',
            'updated_at': now(),
        })
        resumed.append(item['id'])
        slots -= 1
    return resumed



def readmit_recovered_reasoning(
    state: dict[str, Any], eligible: list[dict[str, str]], spool: Path,
    *, max_active: int,
) -> list[str]:
    """Resume at most available repair slots after exact failed reasoning recovers.

    No new request, approval, provider write, or source patch is authorized here.
    The existing implementation and independent acceptance gates remain mandatory.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(1 for record in records.values() if isinstance(record, Mapping)
                 and record.get('phase') in {'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'})
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if slots == 0:
            break
        record = records.get(item['id'])
        if not isinstance(record, dict) or record.get('phase') != 'blocked':
            continue
        reason = str(record.get('reason') or '')
        if reason.startswith('edit reasoning failed: HTTP transport failed'):
            phase, expected_kind = 'implementing', 'edit_plan'
        elif reason.startswith('reasoning request failed: HTTP transport failed'):
            phase, expected_kind = 'diagnosing', 'search_plan'
        else:
            continue
        rid = str(record.get('reasoning_request_id') or '')
        if not re.fullmatch(r'[a-f0-9]{64}', rid):
            continue
        response = reasoning_response(spool, rid)
        if not isinstance(response, Mapping) or response.get('status') != 'succeeded':
            continue
        if response.get('request_id') != rid or response.get('kind') != expected_kind:
            continue
        if response.get('support_item') != item['id']:
            continue
        if record.get('reasoning_recovered_request_id') == rid:
            continue
        record.update({'phase': phase, 'reason': 'Re-admitted after exact reasoning request recovered.',
                       'reasoning_recovered_request_id': rid, 'updated_at': now()})
        resumed.append(item['id'])
        slots -= 1
    return resumed




def verified_later_reasoning_success(
    spool: Path, *, failed_rid: str, item_id: str, kind: str,
    max_proof_age_hours: int = 12,
) -> tuple[dict[str, Any], str] | None:
    """Require newer, independent, same-schema success before one transport retry.

    This only reads the protected reasoning spool; it does not retry the failed
    response, assert provider billing recovery, or authorize code/provider writes.
    HTTP 400 receives the additional safeguard of an equal-or-larger successfully
    handled request of the same kind. Known billing/authority errors never qualify.
    """
    if re.fullmatch(r'[0-9a-f]{64}', failed_rid) is None:
        return None
    req_path = spool / 'reasoning' / 'requests' / (failed_rid + '.json')
    response_dir = spool / 'reasoning' / 'responses'
    if not req_path.is_file() or not response_dir.is_dir():
        return None
    try:
        if req_path.stat().st_size > 200_000:
            return None
        request = json.loads(req_path.read_text(encoding='utf-8'))
        failure = reasoning_response(spool, failed_rid)
        if (not isinstance(request, dict) or request_id(request) != failed_rid
                or request.get('request_id') != failed_rid
                or request.get('support_item') != item_id or request.get('kind') != kind
                or not isinstance(request.get('context'), dict)
                or not isinstance(failure, Mapping) or failure.get('status') != 'failed'
                or failure.get('error_type') != 'ConnectorTransportError'
                or failure.get('provider_error_code')
                or failure.get('primary_provider_error_code')
                or failure.get('required_owner_action')):
            return None
        error = str(failure.get('error') or '')
        if error not in {'HTTP transport failed', 'HTTP transport failed with status 400'}:
            return None
        failed_at = datetime.fromisoformat(str(failure.get('completed_at') or '').replace('Z', '+00:00'))
        if failed_at.tzinfo is None:
            return None
        current = datetime.now(timezone.utc)
        if failed_at > current:
            return None
        original_size = req_path.stat().st_size
        candidates = sorted(response_dir.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)[:128]
        for candidate in candidates:
            if candidate.stem == failed_rid or re.fullmatch(r'[0-9a-f]{64}', candidate.stem) is None:
                continue
            try:
                if candidate.stat().st_size > 200_000:
                    continue
                proof = json.loads(candidate.read_text(encoding='utf-8'))
                if (not isinstance(proof, dict) or proof.get('status') != 'succeeded'
                        or proof.get('request_id') != candidate.stem
                        or proof.get('kind') != kind or not isinstance(proof.get('result'), dict)):
                    continue
                at = datetime.fromisoformat(str(proof.get('completed_at') or '').replace('Z', '+00:00'))
                if (at.tzinfo is None or at <= failed_at
                        or not 0 <= (current - at).total_seconds() <= max_proof_age_hours * 3600):
                    continue
                source = spool / 'reasoning' / 'requests' / candidate.name
                if not source.is_file() or source.stat().st_size > 200_000:
                    continue
                probe_request = json.loads(source.read_text(encoding='utf-8'))
                if (not isinstance(probe_request, dict)
                        or probe_request.get('request_id') != candidate.stem
                        or request_id(probe_request) != candidate.stem
                        or probe_request.get('kind') != kind):
                    continue
                if error.endswith('status 400') and source.stat().st_size < original_size:
                    continue
                return request, candidate.stem
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def readmit_after_verified_transport_recovery(
    state: dict[str, Any], eligible: list[dict[str, str]], spool: Path,
    *, max_active: int,
) -> list[str]:
    """Queue ONE new scoped support diagnostic after independently proven recovery.

    Never overwrite historical failed responses, clear original retry counters,
    re-admit a closed/non-P0 issue, or bypass a pending governed repair handoff.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(1 for record in records.values() if isinstance(record, Mapping)
                 and record.get('phase') in {'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'})
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if not slots:
            break
        if item.get('priority') != 'P0':
            continue
        record = records.get(item['id'])
        if not isinstance(record, dict) or record.get('phase') != 'blocked':
            continue
        handoff = record.get('recovery_handoff_intake')
        if (record.get('provider_recovery_requeue_id') or record.get('pr_number')
                or record.get('blocker_class') in {'external_authority', 'blocked_by_dependency'}
                or (isinstance(handoff, Mapping) and handoff.get('status') == 'awaiting_governed_repair')):
            continue
        reason = str(record.get('reason') or '')
        if reason == 'edit reasoning failed: HTTP transport failed with status 400':
            kind, phase = 'edit_plan', 'implementing'
        elif reason == 'reasoning request failed: HTTP transport failed':
            kind, phase = 'search_plan', 'diagnosing'
        else:
            continue
        failed_id = str(record.get('reasoning_request_id') or '')
        verified = verified_later_reasoning_success(
            spool, failed_rid=failed_id, item_id=item['id'], kind=kind,
        )
        if verified is None:
            continue
        original, proof_id = verified
        context = dict(original['context'])
        if 'verified_transport_recovery' in context:
            continue  # Never recursively requeue an already retried request.
        context['verified_transport_recovery'] = {
            'failed_request_id': failed_id, 'newer_success_id': proof_id,
            'retry_limit': 1, 'purpose': 'bounded_same_schema_provider_recovery',
        }
        new_id = queue_reasoning(spool, kind=kind, item=item, context=context)
        if new_id == failed_id:
            continue
        record.update({
            'phase': phase, 'reason': 'One bounded new request after verified reasoning transport recovery.',
            'provider_recovery_original_failure_id': failed_id,
            'provider_recovery_proof_id': proof_id,
            'provider_recovery_requeue_id': new_id,
            'reasoning_request_id': new_id,
            'updated_at': now(),
        })
        resumed.append(item['id'])
        slots -= 1
    return resumed


def verified_credit_reload_receipt(
    ledger_path: Path, *, failed_at: datetime, max_age_hours: int = 12,
) -> dict[str, str] | None:
    """Read a recent metered provider receipt from a dedicated diagnostic.

    This proves only that the configured hosted reasoning provider accepted a
    later small request. It does not prove the original large request will pass,
    authorize endpoint changes, or modify the original retry history.
    """
    path = Path(ledger_path)
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or failed_at.tzinfo is None):
            return None
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2.0)
        try:
            rows = db.execute(
                'SELECT payload_json FROM model_usage_entries '
                'ORDER BY rowid DESC LIMIT 256'
            ).fetchall()
        finally:
            db.close()
        observed_now = datetime.now(timezone.utc)
        for (raw,) in rows:
            entry = json.loads(raw)
            if not isinstance(entry, Mapping):
                continue
            context = entry.get('context')
            tokens = entry.get('tokens')
            if (entry.get('provider') != 'openai'
                    or entry.get('outcome') != 'completed'
                    or entry.get('usage_source') != 'provider_reported'
                    or not isinstance(context, Mapping)
                    or context.get('workflow_id') != 'provider-credit-verify'
                    or context.get('routing_profile') != 'operator-authorized-diagnostic'
                    or not isinstance(tokens, Mapping)
                    or int(tokens.get('total_tokens') or 0) <= 0):
                continue
            at = datetime.fromisoformat(str(entry.get('completed_at') or '').replace('Z', '+00:00'))
            if (at.tzinfo is None or at <= failed_at
                    or not 0 <= (observed_now - at).total_seconds() <= max_age_hours * 3600):
                continue
            receipt = str(entry.get('entry_id') or '')
            model = str(entry.get('model') or '')
            if not receipt or not model:
                continue
            return {'entry_id': receipt, 'model': model, 'completed_at': at.isoformat()}
    except (OSError, ValueError, TypeError, sqlite3.Error, json.JSONDecodeError):
        return None
    return None


def readmit_after_verified_credit_replenishment(
    state: dict[str, Any], eligible: list[dict[str, str]], spool: Path,
    *, max_active: int, usage_ledger_path: Path | None = None,
) -> list[str]:
    """One new scoped P0 support request after independently verified API credits.

    Credit failures are deliberately non-retryable at the model boundary.
    Preserve that failure and its exhausted budget; only the host-side support
    worker may queue one new content-addressed request with a metered provider
    success receipt. This is a planning request, never a release/approval action.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(
        1 for record in records.values()
        if isinstance(record, Mapping)
        and record.get('phase') in {'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'}
    )
    slots = max(0, max(1, int(max_active)) - active)
    ledger_path = Path(usage_ledger_path) if usage_ledger_path is not None else spool.parent / 'model-usage.sqlite3'
    resumed = []
    for item in eligible:
        if not slots:
            break
        if item.get('priority') != 'P0':
            continue
        record = records.get(item['id'])
        if not isinstance(record, dict) or record.get('phase') != 'blocked':
            continue
        handoff = record.get('recovery_handoff_intake')
        if (record.get('provider_credit_requeue_id') or record.get('pr_number')
                or (isinstance(handoff, Mapping)
                    and handoff.get('status') == 'awaiting_governed_repair')):
            continue
        reason = str(record.get('reason') or '')
        if reason.startswith('edit reasoning failed: Hosted reasoning blocked: credit_balance_exhausted'):
            kind, phase = 'edit_plan', 'implementing'
        elif reason.startswith('reasoning request failed: Hosted reasoning blocked: credit_balance_exhausted'):
            kind, phase = 'search_plan', 'diagnosing'
        else:
            continue
        failed_id = str(record.get('reasoning_request_id') or '')
        if not re.fullmatch(r'[a-f0-9]{64}', failed_id):
            continue
        prior = reasoning_response(spool, failed_id)
        if (not isinstance(prior, Mapping) or prior.get('status') != 'failed'
                or prior.get('request_id') != failed_id
                or prior.get('primary_provider_error_code') != 'credit_balance_exhausted'
                or prior.get('required_owner_action') != 'restore_provider_credits'
                or prior.get('primary_http_status') != 429
                or prior.get('retryable') is not False):
            continue
        try:
            failed_at = datetime.fromisoformat(str(prior['completed_at']).replace('Z', '+00:00'))
            receipt = verified_credit_reload_receipt(ledger_path, failed_at=failed_at)
            source = spool / 'reasoning' / 'requests' / (failed_id + '.json')
            if not source.is_file() or source.stat().st_size > 200_000 or receipt is None:
                continue
            original = json.loads(source.read_text(encoding='utf-8'))
            if (not isinstance(original, dict) or request_id(original) != failed_id
                    or original.get('request_id') != failed_id
                    or original.get('support_item') != item['id']
                    or original.get('kind') != kind
                    or not isinstance(original.get('context'), dict)):
                continue
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        context = dict(original['context'])
        if 'verified_credit_recovery' in context:
            continue
        context['verified_credit_recovery'] = {
            'failed_request_id': failed_id,
            'metered_receipt_id': receipt['entry_id'],
            'provider_model': receipt['model'],
            'verified_at': receipt['completed_at'],
            'retry_limit': 1,
        }
        new_id = queue_reasoning(spool, kind=kind, item=item, context=context)
        if new_id == failed_id:
            continue
        record.update({
            'phase': phase,
            'reason': 'One bounded new request after verified API credit replenishment.',
            'provider_credit_original_failure_id': failed_id,
            'provider_credit_receipt_id': receipt['entry_id'],
            'provider_credit_requeue_id': new_id,
            'reasoning_request_id': new_id,
            'updated_at': now(),
        })
        resumed.append(item['id'])
        slots -= 1
    return resumed


def original_partial_edits_match_known_proposal(
    worktree: Path,
    edits: list[Mapping[str, Any]],
    dirty_paths: list[str],
    failure: str,
    gate,
    policy: Mapping[str, Any],
) -> bool:
    """Replay original proposals in memory; never modify the old worktree.

    Recovery is not permitted for a technician's unrelated modification,
    even if it happened in the same path a model suggested changing.
    """
    originals: dict[str, str] = {}
    staged: dict[str, str] = {}
    failed_at_exact_anchor = False
    for edit in edits:
        if not isinstance(edit, Mapping):
            return False
        path = str(edit.get('path') or '')
        old_text = str(edit.get('old_text') or '')
        new_text = str(edit.get('new_text') or '')
        loc = Path(path)
        if (not path or loc.is_absolute() or '..' in loc.parts
                or gate.path_denial_reason(path, dict(policy))):
            return False
        target = worktree / path
        if target.is_symlink() or not target.is_file():
            return False  # No new/untracked paths in this legacy replay.
        if target.resolve() != worktree.resolve() / path:
            return False
        if path not in originals:
            output = subprocess.run(
                ['git', 'show', 'HEAD:' + path],
                cwd=worktree, check=False, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if output.returncode or len(output.stdout) > 200000:
                return False
            try:
                originals[path] = output.stdout.decode('utf-8')
            except UnicodeDecodeError:
                return False
        before = staged.get(path, originals[path])
        count = before.count(old_text) if old_text else 0
        if count != 1:
            failed_at_exact_anchor = (
                failure == f'WorkerError: exact repair anchor must occur once in {path}; found {count}'
            )
            break
        staged[path] = before.replace(old_text, new_text, 1)
    if not failed_at_exact_anchor:
        return False
    actual_paths = set(dirty_paths)
    expected_paths = {path for path, value in staged.items()
                      if value != originals[path]}
    if actual_paths != expected_paths:
        return False
    try:
        return all(
            (worktree / path).read_text(encoding='utf-8') == staged[path]
            for path in actual_paths
        )
    except (OSError, UnicodeError):
        return False


def verified_support_context_recipe(item: Mapping[str, str]) -> tuple[list[str], list[str]] | None:
    """Select audited repository sources from the approved support scope.

    Never accept arbitrary file paths from a model's blocked explanation.
    Unknown issue classes fail closed until their exact source recipe is reviewed.
    """
    summary = ' '.join(str(item.get(key) or '') for key in ('title', 'evidence', 'acceptance')).casefold()
    if ('support' in summary and 'issue' in summary
            and ('admission' in summary or 'reconcil' in summary)
            and ('p0' in summary or 'priority' in summary)):
        return (
            ['tools/support_repair_host_worker.py',
             'tools/tests/test_support_repair_host_worker.py',
             'tools/engineering_pipeline.py',
             'tools/tests/test_engineering_pipeline.py'],
            ['audit_support_admission', 'eligible_support_items',
             'support_id_from_title', 'support_state_mismatches',
             'blocked_critical_support', 'unadmitted_p0'],
        )
    return None


def readmit_verified_stale_clean_source(
    state: dict[str, Any], eligible: list[dict[str, str]],
    repo: Path, spool: Path, gate, policy: Mapping[str, Any],
    *, max_active: int,
) -> list[str]:
    """Reissue one source-only P0 edit turn after a clean worktree becomes stale.

    Never fast-forward, reset, delete or reuse the old worktree; its immutable
    source/reasoning evidence remains available. A new isolated branch must
    match current origin/main, and the original model's requests pass the
    existing read-only source gates again before a new request is admitted.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(
        1 for rec in records.values()
        if isinstance(rec, Mapping)
        and rec.get('phase') in {'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'}
    )
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if not slots:
            break
        item_id = str(item.get('id') or '')
        record = records.get(item_id)
        if (item.get('priority') != 'P0'
                or not isinstance(record, dict)
                or record.get('phase') != 'blocked'
                or record.get('reason') !=
                    'EvidenceToolError: stale worktree requires governed clean-source recovery'
                or record.get('stale_source_recovery_request_id')
                or record.get('pr_number')
                or record.get('blocker_class') in {'external_authority', 'blocked_by_dependency'}
                or (isinstance(record.get('recovery_handoff_intake'), Mapping)
                    and record['recovery_handoff_intake'].get('status') == 'awaiting_governed_repair')):
            continue
        previous_id = str(record.get('reasoning_request_id') or '')
        old_sha = str(record.get('evidence_source_revision') or '')
        old_branch = str(record.get('branch') or '')
        allowed_branch = (re.escape(branch_name(item_id))
                          + r'-(?:anchor|context|evidence)-[0-9a-f]{12}')
        if (re.fullmatch(r'[0-9a-f]{64}', previous_id) is None
                or re.fullmatch(r'[0-9a-f]{40}', old_sha) is None
                or re.fullmatch(allowed_branch, old_branch) is None):
            continue
        try:
            path = spool / 'reasoning' / 'requests' / (previous_id + '.json')
            if not path.is_file() or path.stat().st_size > 200000:
                continue
            old_request = json.loads(path.read_text(encoding='utf-8'))
            old_response = reasoning_response(spool, previous_id)
            if (not isinstance(old_request, dict)
                    or old_request.get('request_id') != previous_id
                    or request_id(old_request) != previous_id
                    or old_request.get('kind') != 'edit_plan'
                    or old_request.get('support_item') != item_id
                    or not isinstance(old_request.get('context'), dict)
                    or 'stale_clean_source_recovery' in old_request['context']
                    or not isinstance(old_response, Mapping)
                    or old_response.get('status') != 'succeeded'
                    or old_response.get('request_id') != previous_id
                    or old_response.get('kind') != 'edit_plan'
                    or old_response.get('support_item') != item_id):
                continue
            result = old_response.get('result')
            if (not isinstance(result, Mapping)
                    or result.get('edits') or result.get('test_paths')
                    or result.get('blocked_reason')
                    or not isinstance(result.get('evidence_requests'), list)
                    or not result['evidence_requests']):
                continue

            previous_tree = support_worktree_path(item_id, old_branch)
            if (previous_tree.is_symlink() or not previous_tree.is_dir()
                    or run(['git', 'branch', '--show-current'], cwd=previous_tree) != old_branch
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=previous_tree)
                    or run(['git', 'rev-parse', 'HEAD'], cwd=previous_tree) != old_sha):
                continue
            run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
            current_sha = run(['git', 'rev-parse', 'origin/main'], cwd=repo)
            if (re.fullmatch(r'[0-9a-f]{40}', current_sha) is None
                    or current_sha == old_sha):
                continue
            run(['git', 'merge-base', '--is-ancestor', old_sha, current_sha], cwd=repo)

            branch = branch_name(item_id) + '-context-' + previous_id[:12]
            current_tree = ensure_worktree(repo, item_id, branch)
            if (run(['git', 'branch', '--show-current'], cwd=current_tree) != branch
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=current_tree)
                    or run(['git', 'rev-parse', 'HEAD'], cwd=current_tree) != current_sha):
                continue
            evidence_policy = engineering_evidence_tools.load_policy(repo)
            excerpts, receipts = engineering_evidence_tools.execute_tools(
                worktree=current_tree, requests=result['evidence_requests'],
                gate=gate, repair_policy=policy, support=sys.modules[__name__],
                policy=evidence_policy,
            )
            if not excerpts or not receipts:
                continue
            context = {
                'stale_clean_source_recovery': {
                    'previous_request_id': previous_id,
                    'previous_source_revision': old_sha,
                    'current_source_revision': current_sha,
                    'retry_limit': 1,
                },
                'validation_feedback': (
                    'Source changed while previously reviewed evidence was waiting. '
                    'Only the newly read, policy-filtered current-source excerpts '
                    'are authoritative. Preserve all approvals, provider boundaries '
                    'and independent test/release gates. If these exact excerpts '
                    'are insufficient, return a genuine blocker, not imagined edits.'
                ),
                'source_excerpts': excerpts,
                'read_only_tool_receipts': receipts,
                'pinned_source_revision': current_sha,
            }
            new_id = queue_reasoning(spool, kind='edit_plan', item=item, context=context)
            if new_id == previous_id or re.fullmatch(r'[0-9a-f]{64}', new_id) is None:
                continue
            record.update({
                'phase': 'implementing',
                'branch': branch,
                'reasoning_request_id': new_id,
                'evidence_source_revision': current_sha,
                'evidence_last_receipts': receipts,
                'stale_source_recovery_request_id': new_id,
                'stale_source_recovery_original_request_id': previous_id,
                'stale_source_recovery_previous_revision': old_sha,
                'stale_source_recovery_current_revision': current_sha,
                'reason': 'One bounded clean-source re-evaluation queued; old evidence preserved.',
                'updated_at': now(),
            })
            resumed.append(item_id)
            slots -= 1
        except (WorkerError, OSError, ValueError, TypeError, json.JSONDecodeError,
                engineering_evidence_tools.EvidenceToolError):
            continue
    return resumed


def readmit_missing_support_source_context(
    state: dict[str, Any], eligible: list[dict[str, str]],
    repo: Path, spool: Path, gate, policy: Mapping[str, Any],
    *, max_active: int,
) -> list[str]:
    """One scoped context re-evaluation, never a blind failed-request replay.

    The new request is authorized solely to analyze read-only source excerpts.
    Its normal edits, validation, protected CI and deployment gates still apply.
    Old worktrees and retry counters are preserved; a clean current-main
    worktree is created under a distinct bounded branch before re-admission.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active_phases = {'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'}
    active = sum(1 for record in records.values()
                 if isinstance(record, Mapping) and record.get('phase') in active_phases)
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if not slots:
            break
        item_id = str(item.get('id') or '')
        record = records.get(item_id)
        if (item.get('priority') != 'P0' or not isinstance(record, dict)
                or record.get('phase') != 'blocked' or record.get('pr_number')
                or record.get('source_context_recovery_request_id')):
            continue
        reason = str(record.get('reason') or '')
        lowered = reason.casefold()
        if (not ('source excerpt' in lowered and
                 ('missing' in lowered or 'not provided' in lowered
                  or 'not available' in lowered or 'not supplied' in lowered))
                or any(word in lowered for word in (
                    'permission denied', 'access denied', 'authorization denied',
                    'credential required', 'authority required', 'secret required'))):
            continue
        recipe = verified_support_context_recipe(item)
        if recipe is None:
            continue
        previous_id = str(record.get('reasoning_request_id') or '')
        if re.fullmatch(r'[0-9a-f]{64}', previous_id) is None:
            continue
        try:
            original_path = spool / 'reasoning' / 'requests' / (previous_id + '.json')
            if not original_path.is_file() or original_path.stat().st_size > 200000:
                continue
            original = json.loads(original_path.read_text(encoding='utf-8'))
            response = reasoning_response(spool, previous_id)
            if (not isinstance(original, dict)
                    or original.get('request_id') != previous_id
                    or request_id(original) != previous_id
                    or original.get('kind') != 'edit_plan'
                    or original.get('support_item') != item_id
                    or not isinstance(response, Mapping)
                    or response.get('status') != 'succeeded'
                    or response.get('request_id') != previous_id
                    or response.get('kind') != 'edit_plan'
                    or response.get('support_item') != item_id
                    or not isinstance(response.get('result'), Mapping)
                    or response['result'].get('blocked_reason') != reason):
                continue
            branch = branch_name(item_id) + '-context-' + previous_id[:12]
            fresh = ensure_worktree(repo, item_id, branch)
            if (run(['git', 'branch', '--show-current'], cwd=fresh) != branch
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=fresh)
                    or run(['git', 'rev-parse', 'HEAD'], cwd=fresh)
                       != run(['git', 'rev-parse', 'origin/main'], cwd=repo)):
                continue
            paths, symbols = recipe
            excerpts = source_excerpts_for_paths(
                fresh, paths, gate, policy, terms=symbols,
                limit=4, content_limit=12000,
            )
            if (len(excerpts) < 2
                    or excerpts[0]['path'] != paths[0]
                    or excerpts[1]['path'] != paths[1]):
                continue
            head = run(['git', 'rev-parse', 'HEAD'], cwd=fresh)
            request = queue_reasoning(
                spool, kind='edit_plan', item=item,
                context={
                    'source_context_recovery': {
                        'previous_request_id': previous_id,
                        'source_revision': head, 'retry_limit': 1,
                        'reason': 'model_reported_missing_source',
                    },
                    'validation_feedback': (
                        'A verified previous edit proposal was blocked because its '
                        'source excerpts omitted this approved support subsystem. '
                        'Use only the newly provided exact current-source excerpts. '
                        'Preserve existing governance and admission rules; return '
                        'an evidence-backed blocked_reason if an exact safe edit '
                        'and regression test cannot be formed.'
                    ),
                    'source_excerpts': excerpts,
                },
            )
            if request == previous_id:
                continue
            record.update({
                'phase': 'implementing', 'branch': branch,
                'reasoning_request_id': request,
                'source_context_recovery_request_id': request,
                'source_context_recovery_original_id': previous_id,
                'source_context_recovery_revision': head,
                'reason': 'One bounded source-context recovery request queued; old worktree preserved.',
                'updated_at': now(),
            })
            resumed.append(item_id)
            slots -= 1
        except (WorkerError, OSError, ValueError, TypeError, json.JSONDecodeError):
            continue  # No authorization or state mutation on missing evidence.
    return resumed


def readmit_verified_evidence_starvation_after_upgrade(
    state: dict[str, Any], eligible: list[dict[str, str]],
    repo: Path, spool: Path, gate, policy: Mapping[str, Any],
    *, max_active: int,
) -> list[str]:
    """Recover one P0 item only when a verified older tool dropped an explicit read.

    Never blindly replay a completed reasoning turn or reset a historical
    budget. Requires: same canonical P0; content-addressed request+response
    ancestry; an actual, previously requested but omitted tracked source file;
    a *changed* host evidence executor at fetched main; and a fresh clean,
    isolated worktree. A prior recovery marker prevents any second admission.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(1 for rec in records.values() if isinstance(rec, Mapping)
                 and rec.get('phase') in {'diagnosing', 'implementing',
                                          'ci_repair_needed', 'ci_repairing'})
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if not slots:
            break
        record = records.get(item['id'])
        if (item.get('priority') != 'P0' or not isinstance(record, dict)
                or record.get('phase') != 'blocked'
                or record.get('reason') != 'EvidenceToolError: source evidence turn budget exhausted'
                or record.get('evidence_upgrade_recovery_request_id')
                or record.get('pr_number')
                or record.get('blocker_class') in {'external_authority', 'blocked_by_dependency'}
                or (isinstance(record.get('recovery_handoff_intake'), Mapping)
                    and record['recovery_handoff_intake'].get('status') == 'awaiting_governed_repair')
                or type(record.get('evidence_turn_count')) is not int
                or record['evidence_turn_count'] < 2):
            continue
        last_id = str(record.get('reasoning_request_id') or '')
        old_sha = str(record.get('evidence_source_revision') or '')
        if not re.fullmatch(r'[0-9a-f]{64}', last_id) or not re.fullmatch(r'[0-9a-f]{40}', old_sha):
            continue
        try:
            head = run(['git', 'rev-parse', 'origin/main'], cwd=repo)
            if not re.fullmatch(r'[0-9a-f]{40}', head) or head == old_sha:
                continue
            old_blob = run(['git', 'rev-parse', f'{old_sha}:tools/engineering_evidence_tools.py'], cwd=repo)
            new_blob = run(['git', 'rev-parse', f'{head}:tools/engineering_evidence_tools.py'], cwd=repo)
            if old_blob == new_blob:
                continue

            # Walk no more than two prior evidence turns to prove that the
            # previously authorized explicit read was starved by broad search.
            current = last_id
            lost_reads: list[str] = []
            symbol_terms: list[str] = []
            for _ in range(3):
                req_path = spool / 'reasoning' / 'requests' / (current + '.json')
                if not req_path.is_file() or req_path.stat().st_size > 250000:
                    break
                request = json.loads(req_path.read_text(encoding='utf-8'))
                response = reasoning_response(spool, current)
                if (not isinstance(request, dict)
                        or request.get('request_id') != current
                        or request_id(request) != current
                        or request.get('kind') != 'edit_plan'
                        or request.get('support_item') != item['id']
                        or not isinstance(response, Mapping)
                        or response.get('status') != 'succeeded'
                        or response.get('request_id') != current
                        or response.get('kind') != 'edit_plan'
                        or response.get('support_item') != item['id']
                        or not isinstance(response.get('result'), Mapping)):
                    break
                result = response['result']
                if result.get('blocked_reason') or result.get('edits'):
                    break
                context = request.get('context')
                if not isinstance(context, Mapping):
                    break
                ancestor = str(context.get('previous_reasoning_request_id') or '')
                if re.fullmatch(r'[0-9a-f]{64}', ancestor) is None:
                    break
                prev_path = spool / 'reasoning' / 'requests' / (ancestor + '.json')
                if not prev_path.is_file() or prev_path.stat().st_size > 250000:
                    break
                previous = json.loads(prev_path.read_text(encoding='utf-8'))
                previous_result = reasoning_response(spool, ancestor)
                if (not isinstance(previous, dict)
                        or previous.get('request_id') != ancestor
                        or request_id(previous) != ancestor
                        or previous.get('kind') != 'edit_plan'
                        or previous.get('support_item') != item['id']
                        or not isinstance(previous_result, Mapping)
                        or previous_result.get('status') != 'succeeded'
                        or previous_result.get('request_id') != ancestor
                        or previous_result.get('kind') != 'edit_plan'
                        or previous_result.get('support_item') != item['id']
                        or not isinstance(previous_result.get('result'), Mapping)):
                    break
                source_rows = context.get('source_excerpts')
                if not isinstance(source_rows, list):
                    break
                delivered = {str(entry.get('path')) for entry in source_rows
                             if isinstance(entry, Mapping)}
                for asked in previous_result['result'].get('evidence_requests') or []:
                    if not isinstance(asked, Mapping):
                        continue
                    path = asked.get('path')
                    if asked.get('tool') == 'read_source' and isinstance(path, str):
                        if path not in delivered and path not in lost_reads:
                            lost_reads.append(path)
                    elif asked.get('tool') == 'search_source':
                        query = str(asked.get('query') or '')
                        for term in re.findall(r'[A-Za-z_][A-Za-z0-9_]{7,}', query):
                            if '_' in term and term not in symbol_terms:
                                symbol_terms.append(term)
                current = ancestor

            if not lost_reads:
                continue
            branch = branch_name(item['id']) + '-evidence-' + last_id[:12]
            fresh = ensure_worktree(repo, item['id'], branch)
            if (run(['git', 'branch', '--show-current'], cwd=fresh) != branch
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=fresh)
                    or run(['git', 'rev-parse', 'HEAD'], cwd=fresh) != head):
                continue
            paths = [path for path in lost_reads
                     if engineering_evidence_tools._safe_path(fresh, path, gate, policy)][:2]
            if not paths:
                continue
            companions = []
            for path in paths:
                candidate = Path(path)
                test_path = (candidate.parent / 'tests' / ('test_' + candidate.name)).as_posix()
                if engineering_evidence_tools._safe_path(fresh, test_path, gate, policy):
                    companions.append(test_path)
            excerpts = source_excerpts_for_paths(
                fresh, paths + companions, gate, policy, terms=symbol_terms[:12],
                limit=4, content_limit=12000,
            )
            if not excerpts or excerpts[0]['path'] != paths[0]:
                continue
            new_id = queue_reasoning(spool, kind='edit_plan', item=item, context={
                'evidence_starvation_recovery': {
                    'previous_request_id': last_id,
                    'previous_source_revision': old_sha,
                    'corrected_source_revision': head,
                    'missed_exact_reads': paths,
                    'retry_limit': 1,
                },
                'validation_feedback': (
                    'A verified old executor starved an explicit source read behind broad '
                    'search results. Exact missing source files and companion tests now '
                    'take priority. Use these pinned excerpts for exact edits and regression '
                    'tests. If more evidence is essential, use bounded read_source with a '
                    'specific function symbol. Never propose unseen code or new authority.'
                ),
                'source_excerpts': excerpts,
            })
            if new_id == last_id:
                continue
            record.update({
                'phase': 'implementing',
                'branch': branch,
                'reasoning_request_id': new_id,
                'evidence_upgrade_recovery_request_id': new_id,
                'evidence_upgrade_original_request_id': last_id,
                'evidence_upgrade_source_revision': head,
                'evidence_prior_exhausted_turns': int(record['evidence_turn_count']),
                'reason': 'One verified source-starvation recovery admitted on corrected worker.',
                'updated_at': now(),
            })
            resumed.append(item['id'])
            slots -= 1
        except (WorkerError, OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return resumed


def resume_verified_recovery_interrupted_by_rollback(
    state: dict[str, Any], eligible: list[dict[str, str]],
    repo: Path, spool: Path, gate, policy: Mapping[str, Any],
    *, max_active: int,
) -> list[str]:
    """One bounded recovery of a preexisting read-only request after rollback.

    A previous runtime produced an evidence branch unknown to the older LKG
    worker. Preserve the original request, response and worktree; do not replay
    an old patch or reset the reasoning budget. New branch uses the historical
    context suffix supported by the LKG worker.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(1 for entry in records.values() if isinstance(entry, Mapping)
                 and entry.get('phase') in {'diagnosing', 'implementing',
                                            'ci_repair_needed', 'ci_repairing'})
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if not slots:
            break
        item_id = str(item.get('id') or '')
        record = records.get(item_id)
        if (item.get('priority') != 'P0' or not isinstance(record, dict)
                or record.get('phase') != 'blocked'
                or record.get('reason') != 'WorkerError: recovery worktree does not match its pinned branch'
                or record.get('interrupted_recovery_request_id') or record.get('pr_number')
                or record.get('blocker_class') in {'external_authority', 'blocked_by_dependency'}
                or (isinstance(record.get('recovery_handoff_intake'), Mapping)
                    and record['recovery_handoff_intake'].get('status') == 'awaiting_governed_repair')):
            continue
        previous_id = str(record.get('reasoning_request_id') or '')
        old_sha = str(record.get('evidence_upgrade_source_revision') or '')
        branch = str(record.get('branch') or '')
        if (not re.fullmatch(r'[0-9a-f]{64}', previous_id)
                or not re.fullmatch(r'[0-9a-f]{40}', old_sha)
                or record.get('evidence_upgrade_recovery_request_id') != previous_id
                or not re.fullmatch(r'[0-9a-f]{64}',
                                    str(record.get('evidence_upgrade_original_request_id') or ''))
                or not re.fullmatch(
                    re.escape(branch_name(item_id)) + r'-evidence-[a-f0-9]{12}', branch)):
            continue
        try:
            head = run(['git', 'rev-parse', 'origin/main'], cwd=repo)
            if not re.fullmatch(r'[0-9a-f]{40}', head):
                continue
            old_worktree = support_worktree_path(item_id, branch)
            if (not old_worktree.is_dir() or old_worktree.is_symlink()
                    or run(['git', 'branch', '--show-current'], cwd=old_worktree) != branch
                    or run(['git', 'rev-parse', 'HEAD'], cwd=old_worktree) != old_sha
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'],
                           cwd=old_worktree)):
                continue
            original = spool / 'reasoning' / 'requests' / (previous_id + '.json')
            if not original.is_file() or original.stat().st_size > 250000:
                continue
            request = json.loads(original.read_text(encoding='utf-8'))
            response = reasoning_response(spool, previous_id)
            if (not isinstance(request, dict)
                    or request.get('request_id') != previous_id
                    or request_id(request) != previous_id
                    or request.get('kind') != 'edit_plan'
                    or request.get('support_item') != item_id
                    or not isinstance(response, Mapping)
                    or response.get('status') != 'succeeded'
                    or response.get('request_id') != previous_id
                    or response.get('kind') != 'edit_plan'
                    or response.get('support_item') != item_id
                    or not isinstance(response.get('result'), Mapping)):
                continue
            result = response['result']
            if (result.get('blocked_reason') or result.get('edits')
                    or result.get('test_paths')
                    or not isinstance(result.get('evidence_requests'), list)):
                continue
            paths: list[str] = []
            terms: list[str] = []
            for action in result['evidence_requests'][:3]:
                if not isinstance(action, Mapping) or action.get('tool') != 'read_source':
                    continue
                path = action.get('path')
                if not isinstance(path, str):
                    continue
                if path not in paths:
                    paths.append(path)
                for word in re.findall(r'[A-Za-z_][A-Za-z0-9_]{7,}',
                                       str(action.get('query') or '')):
                    if '_' in word and word not in terms:
                        terms.append(word)
            if not paths:
                continue
            new_branch = branch_name(item_id) + '-context-' + previous_id[:12]
            fresh = ensure_worktree(repo, item_id, new_branch)
            if (run(['git', 'branch', '--show-current'], cwd=fresh) != new_branch
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=fresh)
                    or run(['git', 'rev-parse', 'HEAD'], cwd=fresh) != head):
                continue
            authorized = [
                path for path in paths[:2]
                if engineering_evidence_tools._safe_path(fresh, path, gate, policy)
            ]
            tests: list[str] = []
            for path in authorized:
                candidate = Path(path)
                test_name = (candidate.parent / 'tests' / ('test_' + candidate.name)).as_posix()
                if engineering_evidence_tools._safe_path(fresh, test_name, gate, policy):
                    tests.append(test_name)
            if not authorized or not tests:
                continue
            excerpts = source_excerpts_for_paths(
                fresh, authorized + tests, gate, policy,
                terms=terms[:12], limit=4, content_limit=12000,
            )
            if (not excerpts or excerpts[0]['path'] != authorized[0]
                    or not any(entry['path'] in tests for entry in excerpts)):
                continue
            next_id = queue_reasoning(spool, kind='edit_plan', item=item, context={
                'verified_rollback_interruption': {
                    'previous_request_id': previous_id,
                    'previous_source_revision': old_sha,
                    'new_source_revision': head,
                    'original_branch': branch,
                    'retry_limit': 1,
                },
                'validation_feedback': (
                    'The earlier LKG worker did not recognize the new recovery '
                    'branch before processing the completed read-only source request. '
                    'Use the freshly pinned source and regression excerpts. Return '
                    'exact verified edits and tests or a genuine blocked reason; '
                    'do not invent unseen code, authority or deployment steps.'
                ),
                'source_excerpts': excerpts,
            })
            if next_id == previous_id:
                continue
            record.update({
                'phase': 'implementing',
                'reason': 'Verified read-only work resumed after rollback branch mismatch.',
                'branch': new_branch,
                'reasoning_request_id': next_id,
                'interrupted_recovery_request_id': next_id,
                'interrupted_recovery_original_request_id': previous_id,
                'interrupted_recovery_source_revision': head,
                'updated_at': now(),
            })
            resumed.append(item_id)
            slots -= 1
        except (WorkerError, OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return resumed



def normalize_verified_legacy_source_search(
    result: Mapping[str, Any],
) -> tuple[dict[str, Any], int] | None:
    """Drop legacy advisory path hints ONLY for bounded repository searches.

    Never use the model path for file selection, authorization or search scope.
    The normal source executor independently checks every resulting tool call.
    Reject mixed edits, hidden arguments, malformed queries, and non-search
    actions with unexpected shapes; do not make a generic schema repair.
    """
    calls = result.get('evidence_requests')
    if (result.get('blocked_reason') or result.get('edits') or result.get('test_paths')
            or not isinstance(calls, list) or not 1 <= len(calls) <= 4):
        return None
    rewritten: list[dict[str, Any]] = []
    discarded = 0
    for action in calls:
        if not isinstance(action, dict) or set(action) - {'tool', 'query', 'path'}:
            return None
        name = action.get('tool')
        query, hint = action.get('query'), action.get('path')
        if name == 'search_source':
            if (not isinstance(query, str) or
                    re.fullmatch(r'[A-Za-z0-9_ ,:./#-]{3,100}', query) is None):
                return None
            if hint is not None:
                if (not isinstance(hint, str)
                        or re.fullmatch(r'[A-Za-z0-9_./-]{4,240}', hint) is None
                        or Path(hint).is_absolute()
                        or any(part in {'.', '..'} or part.startswith('.')
                               for part in Path(hint).parts)):
                    return None
                discarded += 1
            rewritten.append({'tool': 'search_source', 'query': query, 'path': None})
        elif name == 'read_source':
            rewritten.append(dict(action))
        else:
            return None
    if discarded == 0:
        return None
    return {**result, 'evidence_requests': rewritten}, discarded


def readmit_verified_legacy_search_shape_after_upgrade(
    state: dict[str, Any], eligible: list[dict[str, str]],
    repo: Path, spool: Path, gate, policy: Mapping[str, Any],
    *, max_active: int,
) -> list[str]:
    """One source-upgrade-bound P0 recovery for a malformed READ-ONLY search.

    The original malformed model response remains immutable. Require exact
    content-addressed request/response ancestry, clean old and current source,
    and a changed reviewed host worker. A discarded advisory path must never
    become a read path or executable code. No retries without spare capacity.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(1 for entry in records.values() if isinstance(entry, Mapping)
                 and entry.get('phase') in {'diagnosing', 'implementing',
                                            'ci_repair_needed', 'ci_repairing'})
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if not slots:
            break
        item_id = str(item.get('id') or '')
        record = records.get(item_id)
        if (item.get('priority') != 'P0' or not isinstance(record, dict)
                or record.get('phase') != 'blocked'
                or record.get('reason') != 'EvidenceToolError: invalid source search'
                or record.get('search_shape_recovery_request_id')
                or record.get('pr_number')
                or record.get('blocker_class') in {'external_authority', 'blocked_by_dependency'}
                or (isinstance(record.get('recovery_handoff_intake'), Mapping)
                    and record['recovery_handoff_intake'].get('status') == 'awaiting_governed_repair')
                or type(record.get('evidence_turn_count')) is not int
                or not 0 <= record['evidence_turn_count'] < 4):
            continue
        prior_id = str(record.get('reasoning_request_id') or '')
        ancestor_id = str(record.get('evidence_last_source_request') or '')
        old_sha = str(record.get('evidence_source_revision') or '')
        old_branch = str(record.get('branch') or '')
        if (not re.fullmatch(r'[0-9a-f]{64}', prior_id)
                or not re.fullmatch(r'[0-9a-f]{64}', ancestor_id)
                or not re.fullmatch(r'[0-9a-f]{40}', old_sha)
                or old_branch != branch_name(item_id)):
            continue
        try:
            head = run(['git', 'rev-parse', 'origin/main'], cwd=repo)
            if not re.fullmatch(r'[0-9a-f]{40}', head) or head == old_sha:
                continue
            old_blob = run(['git', 'rev-parse',
                            f'{old_sha}:tools/support_repair_host_worker.py'], cwd=repo)
            new_blob = run(['git', 'rev-parse',
                            f'{head}:tools/support_repair_host_worker.py'], cwd=repo)
            if old_blob == new_blob:
                continue
            original = support_worktree_path(item_id, old_branch)
            if (not original.is_dir() or original.is_symlink()
                    or run(['git', 'branch', '--show-current'], cwd=original) != old_branch
                    or run(['git', 'rev-parse', 'HEAD'], cwd=original) != old_sha
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'],
                           cwd=original)):
                continue
            req_path = spool / 'reasoning/requests' / (prior_id + '.json')
            ancestor_path = spool / 'reasoning/requests' / (ancestor_id + '.json')
            if (not req_path.is_file() or req_path.stat().st_size > 250000
                    or not ancestor_path.is_file()
                    or ancestor_path.stat().st_size > 250000):
                continue
            request = json.loads(req_path.read_text(encoding='utf-8'))
            ancestor = json.loads(ancestor_path.read_text(encoding='utf-8'))
            response = reasoning_response(spool, prior_id)
            ancestor_response = reasoning_response(spool, ancestor_id)
            if (not isinstance(request, dict)
                    or request.get('request_id') != prior_id
                    or request_id(request) != prior_id
                    or request.get('kind') != 'edit_plan'
                    or request.get('support_item') != item_id
                    or not isinstance(request.get('context'), dict)
                    or request['context'].get('pinned_source_revision') != old_sha
                    or request['context'].get('previous_reasoning_request_id') != ancestor_id
                    or not isinstance(ancestor, dict)
                    or ancestor.get('request_id') != ancestor_id
                    or request_id(ancestor) != ancestor_id
                    or ancestor.get('kind') != 'edit_plan'
                    or ancestor.get('support_item') != item_id
                    or not isinstance(ancestor_response, Mapping)
                    or ancestor_response.get('status') != 'succeeded'
                    or ancestor_response.get('request_id') != ancestor_id
                    or ancestor_response.get('support_item') != item_id
                    or not isinstance(response, Mapping)
                    or response.get('status') != 'succeeded'
                    or response.get('request_id') != prior_id
                    or response.get('kind') != 'edit_plan'
                    or response.get('support_item') != item_id
                    or not isinstance(response.get('result'), Mapping)):
                continue
            normalized = normalize_verified_legacy_source_search(response['result'])
            if normalized is None:
                continue
            sanitized_result, discard_count = normalized
            branch = branch_name(item_id) + '-context-' + prior_id[:12]
            fresh = ensure_worktree(repo, item_id, branch)
            if (run(['git', 'branch', '--show-current'], cwd=fresh) != branch
                    or run(['git', 'rev-parse', 'HEAD'], cwd=fresh) != head
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'],
                           cwd=fresh)):
                continue
            context = dict(request['context'])
            context['verified_search_shape_recovery'] = {
                'previous_request_id': prior_id,
                'original_source_revision': old_sha,
                'source_revision': head,
                'ignored_advisory_path_count': discard_count,
                'retry_limit': 1,
            }
            context['validation_feedback'] = (
                'One verified legacy read-only search included an advisory path '
                'which was not used for searching or reading. The recovered '
                'queries are repository searches only; source access remains '
                'strictly Git-tracked, bounded and governed. Form an exact '
                'evidence-backed edit or return a real blocked_reason.'
            )
            next_record = dict(record)
            ok = engineering_evidence_tools.continue_evidence_session(
                response_result=sanitized_result, record=next_record,
                item=item, spool=spool, worktree=fresh, repo=repo,
                gate=gate, repair_policy=policy,
                support=sys.modules[__name__], queue_reasoning=queue_reasoning,
                context_base=context,
            )
            if not ok or next_record.get('reasoning_request_id') == prior_id:
                continue
            record.update(next_record)
            record.update({
                'phase': 'implementing', 'branch': branch,
                'reason': 'Verified bounded read-only search resumed; original malformed path ignored.',
                'search_shape_recovery_request_id': next_record['reasoning_request_id'],
                'search_shape_recovery_original_request_id': prior_id,
                'search_shape_recovery_source_revision': head,
                'updated_at': now(),
            })
            resumed.append(item_id)
            slots -= 1
        except (WorkerError, engineering_evidence_tools.EvidenceToolError,
                OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return resumed

def readmit_verified_malformed_source_symbol_after_upgrade(
    state: dict[str, Any], eligible: list[dict[str, str]],
    repo: Path, spool: Path, gate, policy: Mapping[str, Any],
    *, max_active: int,
) -> list[str]:
    """Repair a precisely attested P0 source-read selector after tool upgrade.

    Only the previously successful model response, the same clean pinned
    read-only worktree and a source-version change to the evidence executor
    can authorize one new source-evidence turn. The new executor independently
    validates every request before reading; old model output is never treated
    as edits, approval or a shell operation.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active = sum(1 for entry in records.values() if isinstance(entry, Mapping)
                 and entry.get('phase') in {'diagnosing', 'implementing',
                                            'ci_repair_needed', 'ci_repairing'})
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if not slots:
            break
        item_id = str(item.get('id') or '')
        record = records.get(item_id)
        if (item.get('priority') != 'P0' or not isinstance(record, dict)
                or record.get('phase') != 'blocked'
                or record.get('reason') != 'EvidenceToolError: invalid exact source symbol'
                or record.get('symbol_read_recovery_request_id')
                or record.get('pr_number')
                or record.get('blocker_class') in {'external_authority', 'blocked_by_dependency'}
                or (isinstance(record.get('recovery_handoff_intake'), Mapping)
                    and record['recovery_handoff_intake'].get('status') == 'awaiting_governed_repair')
                or type(record.get('evidence_turn_count')) is not int
                or not 0 <= record['evidence_turn_count'] < 4):
            continue
        prior_id = str(record.get('reasoning_request_id') or '')
        original_id = str(record.get('interrupted_recovery_original_request_id') or '')
        old_sha = str(record.get('interrupted_recovery_source_revision') or '')
        old_branch = str(record.get('branch') or '')
        if (not re.fullmatch(r'[0-9a-f]{64}', prior_id)
                or not re.fullmatch(r'[0-9a-f]{64}', original_id)
                or not re.fullmatch(r'[0-9a-f]{40}', old_sha)
                or record.get('interrupted_recovery_request_id') != prior_id
                or old_branch != branch_name(item_id) + '-context-' + original_id[:12]):
            continue
        try:
            head = run(['git', 'rev-parse', 'origin/main'], cwd=repo)
            if not re.fullmatch(r'[0-9a-f]{40}', head) or head == old_sha:
                continue
            old_blob = run(['git', 'rev-parse',
                            f'{old_sha}:tools/engineering_evidence_tools.py'], cwd=repo)
            new_blob = run(['git', 'rev-parse',
                            f'{head}:tools/engineering_evidence_tools.py'], cwd=repo)
            if old_blob == new_blob:
                continue
            original = support_worktree_path(item_id, old_branch)
            if (not original.is_dir() or original.is_symlink()
                    or run(['git', 'branch', '--show-current'], cwd=original) != old_branch
                    or run(['git', 'rev-parse', 'HEAD'], cwd=original) != old_sha
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'],
                           cwd=original)):
                continue
            request_path = spool / 'reasoning' / 'requests' / (prior_id + '.json')
            if not request_path.is_file() or request_path.stat().st_size > 250000:
                continue
            request = json.loads(request_path.read_text(encoding='utf-8'))
            response = reasoning_response(spool, prior_id)
            if (not isinstance(request, Mapping)
                    or request.get('request_id') != prior_id
                    or request_id(request) != prior_id
                    or request.get('kind') != 'edit_plan'
                    or request.get('support_item') != item_id
                    or not isinstance(request.get('context'), Mapping)
                    or not isinstance(response, Mapping)
                    or response.get('status') != 'succeeded'
                    or response.get('request_id') != prior_id
                    or response.get('kind') != 'edit_plan'
                    or response.get('support_item') != item_id
                    or not isinstance(response.get('result'), Mapping)):
                continue
            ancestry = request['context'].get('verified_rollback_interruption')
            if (not isinstance(ancestry, Mapping)
                    or ancestry.get('previous_request_id') != original_id
                    or ancestry.get('new_source_revision') != old_sha
                    or ancestry.get('retry_limit') != 1):
                continue
            result = response['result']
            source_calls = result.get('evidence_requests')
            if (result.get('blocked_reason') or result.get('edits')
                    or result.get('test_paths')
                    or not isinstance(source_calls, list)
                    or not 1 <= len(source_calls) <= 3):
                continue
            malformed: list[Mapping[str, Any]] = []
            for action in source_calls:
                if not isinstance(action, Mapping):
                    continue
                if action.get('tool') == 'read_source':
                    q = action.get('query')
                    if (isinstance(q, str)
                            and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{2,79}', q) is None):
                        malformed.append(action)
            if len(malformed) != 1:
                continue
            branch = branch_name(item_id) + '-context-' + prior_id[:12]
            worktree = ensure_worktree(repo, item_id, branch)
            if (run(['git', 'branch', '--show-current'], cwd=worktree) != branch
                    or run(['git', 'rev-parse', 'HEAD'], cwd=worktree) != head
                    or run(['git', 'status', '--porcelain', '--untracked-files=all'],
                           cwd=worktree)):
                continue
            # The repaired parser must validate the exact previously rejected
            # selector. It cannot normalize tool names, paths, shell commands,
            # or any hidden extras supplied by the model.
            validated = engineering_evidence_tools.exact_source_symbols(
                malformed[0].get('query')
            )
            if (len(validated) != 2
                    or not engineering_evidence_tools._safe_path(
                        worktree, str(malformed[0].get('path')), gate, policy)):
                continue
            next_record = dict(record)
            ok = engineering_evidence_tools.continue_evidence_session(
                response_result=result, record=next_record, item=item, spool=spool,
                worktree=worktree, repo=repo, gate=gate,
                repair_policy=policy, support=sys.modules[__name__],
                queue_reasoning=queue_reasoning, context_base=request['context'],
            )
            if not ok or next_record.get('reasoning_request_id') == prior_id:
                continue
            record.update(next_record)
            record.update({
                'phase': 'implementing',
                'branch': branch,
                'reason': 'Pinned invalid source symbol corrected by approved read-only evidence tool.',
                'symbol_read_recovery_request_id': next_record['reasoning_request_id'],
                'symbol_read_recovery_original_request_id': prior_id,
                'symbol_read_recovery_source_revision': head,
                'updated_at': now(),
            })
            resumed.append(item_id)
            slots -= 1
        except (WorkerError, engineering_evidence_tools.EvidenceToolError,
                OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return resumed


def readmit_preserved_anchor_failure(
    state: dict[str, Any],
    eligible: list[dict[str, str]],
    repo: Path,
    spool: Path,
    gate,
    policy: Mapping[str, Any],
    *,
    max_active: int,
) -> list[str]:
    """Preserve a legacy partial repair and resume in a NEW clean worktree.

    Only the original exact, successfully answered edit request can authorize
    a one-time correction. No prior worktree is reset, stashed, or discarded.
    The original partial diff is durably captured for later review.
    """
    records = state.get('items') if isinstance(state.get('items'), dict) else {}
    active_phases = {'diagnosing', 'implementing', 'ci_repair_needed', 'ci_repairing'}
    active = sum(1 for value in records.values() if isinstance(value, Mapping)
                 and value.get('phase') in active_phases)
    slots = max(0, max(1, int(max_active)) - active)
    resumed: list[str] = []
    for item in eligible:
        if slots <= 0:
            break
        item_id = str(item.get('id') or '')
        record = records.get(item_id)
        if not isinstance(record, dict) or record.get('phase') != 'blocked':
            continue
        if record.get('anchor_preserved_recovery_id') or record.get('pr_number'):
            continue
        if int(record.get('proposal_retries') or 0) >= 2:
            continue
        reason = str(record.get('reason') or '')
        if re.fullmatch(
                r'WorkerError: exact repair anchor must occur once in [^\n;]{1,240}; found (?:0|[2-9][0-9]*)',
                reason) is None:
            continue
        rid = str(record.get('reasoning_request_id') or '')
        if re.fullmatch(r'[0-9a-f]{64}', rid) is None:
            continue
        response = reasoning_response(spool, rid)
        if (not isinstance(response, Mapping)
                or response.get('status') != 'succeeded'
                or response.get('request_id') != rid
                or response.get('kind') != 'edit_plan'
                or response.get('support_item') != item_id):
            continue
        result = response.get('result')
        if not isinstance(result, Mapping) or result.get('blocked_reason'):
            continue
        edits = result.get('edits')
        if not isinstance(edits, list) or not edits or len(edits) > 12:
            continue
        original_branch = branch_name(item_id)
        if record.get('branch') != original_branch:
            continue  # Never replace a branch chosen by a technician.
        old = support_worktree_path(item_id, original_branch)
        if old.is_symlink() or not old.is_dir():
            continue
        if run(['git', 'rev-parse', '--show-toplevel'], cwd=old) != str(old.resolve()):
            continue
        if run(['git', 'branch', '--show-current'], cwd=old) != original_branch:
            continue
        # Confirm the dirty bytes are only tracked edits named by the original
        # model proposal. Unknown, staged or untracked work remains human-held.
        if run(['git', 'diff', '--cached', '--name-only'], cwd=old):
            continue
        if run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=old):
            continue
        dirty_paths = run(['git', 'diff', '--name-only'], cwd=old).splitlines()
        proposed_paths = {str(edit.get('path') or '') for edit in edits
                          if isinstance(edit, Mapping)}
        if (not dirty_paths or len(dirty_paths) > 12
                or any(path not in proposed_paths
                       or gate.path_denial_reason(path, dict(policy))
                       for path in dirty_paths)):
            continue
        if not original_partial_edits_match_known_proposal(
                old, edits, dirty_paths, reason, gate, policy):
            continue
        original_patch = run(['git', 'diff', '--binary'], cwd=old)
        if not original_patch or len(original_patch) > 50000:
            continue
        old_head = run(['git', 'rev-parse', 'HEAD'], cwd=old)
        if re.fullmatch(r'[0-9a-f]{40}', old_head) is None:
            continue
        recovery_branch = original_branch + '-anchor-' + rid[:12]
        clean = ensure_worktree(repo, item_id, recovery_branch)
        if (run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=clean)
                or run(['git', 'rev-parse', 'HEAD'], cwd=clean)
                     != run(['git', 'rev-parse', 'origin/main'], cwd=repo)):
            continue  # No retry against stale or independently modified code.
        paths = [str(edit.get('path') or '') for edit in edits
                 if isinstance(edit, Mapping)]
        paths.extend(str(path) for path in (result.get('test_paths') or []))
        excerpt_terms = [
            str(edit.get('old_text') or '')[:120]
            for edit in edits if isinstance(edit, Mapping) and edit.get('old_text')
        ]
        excerpts = source_excerpts_for_paths(
            clean, paths, gate, policy, terms=excerpt_terms,
            limit=8, content_limit=14000)
        if not excerpts:
            continue
        patch_sha = hashlib.sha256(original_patch.encode('utf-8')).hexdigest()
        evidence_root = spool / 'recovery-evidence'
        evidence_path = evidence_root / (rid + '.json')
        immutable_evidence = {
            'schema_version': 'jason.support-anchor-evidence.v1',
            'support_item': item_id, 'failed_reasoning_request_id': rid,
            'old_branch': original_branch, 'old_source_sha': old_head,
            'original_patch_sha256': patch_sha,
            'original_dirty_paths': dirty_paths,
            'preserved_original_patch': original_patch,
            'recovery_branch': recovery_branch,
        }
        if evidence_path.exists():
            stored = json.loads(evidence_path.read_text(encoding='utf-8'))
            if stored != immutable_evidence:
                raise WorkerError('preserved anchor evidence conflicts with current source')
        else:
            atomic_json(evidence_path, immutable_evidence)
        new_rid = queue_reasoning(
            spool, kind='edit_plan', item=item,
            context={
                'validation_feedback': (
                    'The original proposal failed exact anchor validation: '
                    + reason[:340]
                    + '. Its partially applied earlier source edits are preserved '
                    'unchanged in the old isolated worktree. Correct the proposal '
                    'using ONLY current clean source excerpts. Every old_text must '
                    'occur once. Include an exact test edit. Do not reclassify '
                    'SUPPORT-DEV as a DEV task or weaken any authority gate.'
                ),
                'retry_number': int(record.get('proposal_retries') or 0) + 1,
                'preserved_patch_sha256': patch_sha,
                'source_excerpts': excerpts,
            },
        )
        if new_rid == rid:
            continue
        record.update({
            'phase': 'implementing', 'branch': recovery_branch,
            'anchor_preserved_recovery_id': rid,
            'preserved_anchor_patch_sha256': patch_sha,
            'preserved_anchor_source_sha': old_head,
            'reasoning_request_id': new_rid,
            'proposal_retries': int(record.get('proposal_retries') or 0) + 1,
            'reason': 'bounded clean-worktree correction; old source preserved for audit',
            'updated_at': now(),
        })
        resumed.append(item_id)
        slots -= 1
    return resumed


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {'schema_version': '1.0', 'items': {}}
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {'schema_version': '1.0', 'items': {}}


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    atomic_json(path, state)


def sync_support_lifecycle_notification(
    record: dict[str, Any],
    item: Mapping[str, Any],
    *,
    event_root: Path,
) -> None:
    try:
        if not record.get('lifecycle_started_fingerprint'):
            record['lifecycle_started_fingerprint'] = emit_lifecycle_event(
                event_type='work_started',
                work_id=str(item['id']),
                work_title=str(item['title']),
                summary='Autonomous support repair has started.',
                event_root=event_root,
            )
        phase = str(record.get('phase') or '')
        if (phase == 'blocked'
                and record.get('notification_class') == 'owner_action_required'
                and not record.get('lifecycle_blocked_fingerprint')):
            reason = str(record.get('reason') or 'Support repair stopped at an owner-action blocker.').strip()
            owner_action = str(record.get('owner_action') or '').strip()
            if not owner_action:
                raise ValueError('owner_action_required blocker must include owner_action')
            record['lifecycle_blocked_fingerprint'] = emit_lifecycle_event(
                event_type='work_blocked',
                work_id=str(item['id']),
                work_title=str(item['title']),
                summary=reason,
                owner_action=owner_action,
                event_root=event_root,
            )
        if phase == 'complete' and not record.get('lifecycle_completed_fingerprint'):
            record['lifecycle_completed_fingerprint'] = emit_lifecycle_event(
                event_type='work_completed',
                work_id=str(item['id']),
                work_title=str(item['title']),
                summary='Production acceptance and support closure are verified complete.',
                event_root=event_root,
            )
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
    state_path = spool / 'state.json'
    state = load_state(state_path)
    state.setdefault('items', {})

    run(['git', 'fetch', '--no-tags', 'origin', 'main'], cwd=repo)
    support_text = run(['git', 'show', 'origin/main:SUPPORT.md'], cwd=repo)
    parsed_support = parse_support(support_text)
    auto_incidents = load_self_heal_incidents()
    development_recovery_incidents = load_development_recovery_incidents(spool)
    for item in auto_incidents:
        ensure_support_issue(repo, item)
    open_issue_records = open_support_issue_records(repo)
    # Manual ID collisions are not authoritative issue selectors. Automated
    # fingerprint duplicates remain one item, with every GitHub ID audited.
    open_issue_ids = {
        item_id for item_id, info in open_issue_records.items()
        if not info.get('identity_conflict')
    }
    unadmitted_p0 = audit_support_admission(
        open_issue_records, parsed_support + auto_incidents + development_recovery_incidents, state,
    )
    support = eligible_support_items(parsed_support, open_issue_ids)
    support.extend(
        item for item in auto_incidents
        if item['id'] in open_issue_ids
        and item['id'] not in {existing['id'] for existing in support}
    )
    support.extend(
        item for item in development_recovery_incidents
        if item['id'] in open_issue_ids
        and item['id'] not in {existing['id'] for existing in support}
    )
    support.sort(key=lambda item: (PRIORITY.get(item['priority'], 99), item['id']))
    state['support_state_mismatches'] = {
        'support_open_issue_not_open': sorted(
            item['id'] for item in parsed_support if item['id'] not in open_issue_records
        ),
        'issue_open_missing_support_row': sorted(
            item_id for item_id in open_issue_ids if item_id not in {item['id'] for item in parsed_support}
        ),
        'identity_conflicts': state['admission_audit']['identity_conflicts'],
        'duplicate_issue_records': state['admission_audit']['duplicate_issue_records'],
    }
    try:
        prs = open_prs(repo)
    except WorkerError as exc:
        # Preserve existing work and defer the entire reconciliation, not a
        # partial PR listing, when GitHub has a transient gateway outage.
        if not transient_github_listing_failure(exc):
            raise
        state['upstream_deferred'] = {
            'provider': 'github', 'reason': 'transient_gateway_error',
            'observed_at': now(),
        }
        state['updated_at'] = now()
        save_state(state_path, state)
        print('SUPPORT_REPAIR_DEFERRED=github_transient_gateway_error')
        return 0
    state.pop('upstream_deferred', None)
    gate = load_gate(repo)
    policy = gate.load_json(repo / 'config' / 'autonomous-repair-release-policy.json')

    readmit_recovered_reasoning(state, support, spool, max_active=args.max_active)
    readmit_after_verified_transport_recovery(state, support, spool, max_active=args.max_active)
    readmit_after_verified_credit_replenishment(state, support, spool, max_active=args.max_active)
    readmit_verified_stale_clean_source(
        state, support, repo, spool, gate, policy, max_active=args.max_active,
    )
    readmit_missing_support_source_context(
        state, support, repo, spool, gate, policy, max_active=args.max_active,
    )
    readmit_verified_evidence_starvation_after_upgrade(
        state, support, repo, spool, gate, policy, max_active=args.max_active,
    )
    resume_verified_recovery_interrupted_by_rollback(
        state, support, repo, spool, gate, policy, max_active=args.max_active,
    )
    readmit_verified_malformed_source_symbol_after_upgrade(
        state, support, repo, spool, gate, policy, max_active=args.max_active,
    )
    readmit_verified_legacy_search_shape_after_upgrade(
        state, support, repo, spool, gate, policy, max_active=args.max_active,
    )
    reassess_model_scope_blocks(state, support, spool, args.max_active)
    readmit_preserved_anchor_failure(
        state, support, repo, spool, gate, policy, max_active=args.max_active)
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
                    detector_verified, detector_reason, detector_evidence = self_heal_post_production_verification(repo, item_id)
                    record['detector_verification'] = detector_evidence
                    if not detector_verified:
                        record.update({
                            'phase': 'diagnosing',
                            'reason': 'post-production detector verification failed: ' + detector_reason,
                            'reasoning_request_id': '',
                            'acceptance_request_id': '',
                            'updated_at': now(),
                        })
                        continue
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
                                'self_heal_detector_verified': True,
                                'self_heal_detector_reason': detector_reason,
                                'self_heal_detector_evidence': detector_evidence,
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
                if engineering_evidence_tools.continue_evidence_session(
                    response_result=result, record=record, item=item, spool=spool,
                    worktree=worktree, repo=repo, gate=gate, repair_policy=policy,
                    support=SimpleNamespace(
                        run=run, request_id=request_id, safe_search=safe_search,
                        source_excerpts_for_paths=source_excerpts_for_paths,
                        merge_source_excerpts=merge_source_excerpts,
                    ), queue_reasoning=queue_reasoning,
                ):
                    record['updated_at'] = now()
                    continue
                if result.get('blocked_reason'):
                    record.update({'phase': 'blocked', 'reason': str(result['blocked_reason']), 'updated_at': now()})
                    continue
                edits = list(result.get('edits') or [])
                test_paths = list(result.get('test_paths') or [])
                changed_tests = proposed_test_edits(edits, test_paths, gate, policy)
                if not changed_tests:
                    retries = int(record.get('proposal_retries', 0))
                    if retries >= 2:
                        record.update({
                            'phase': 'blocked',
                            'reason': 'repair proposal retry boundary exhausted without a changed regression test',
                            'updated_at': now(),
                        })
                        continue
                    context_paths = [
                        str(edit.get('path') or '').strip()
                        for edit in edits
                        if str(edit.get('path') or '').strip()
                    ] + [str(path) for path in test_paths]
                    retry_excerpts = source_excerpts_for_paths(
                        worktree, context_paths, gate, policy, limit=8, content_limit=14000
                    )
                    retry_rid = queue_reasoning(
                        spool,
                        kind='edit_plan',
                        item=item,
                        context={
                            'validation_feedback': (
                                'The previous proposal did not include an actual edit to a regression test. '
                                'Return the smallest source repair plus at least one exact-text edit to a '
                                'declared regression test path. Do not omit the test edit.'
                            ),
                            'source_excerpts': retry_excerpts,
                        },
                    )
                    record.update({
                        'phase': 'implementing',
                        'reasoning_request_id': retry_rid,
                        'proposal_retries': retries + 1,
                        'reason': 're-prompted repair proposal for missing changed regression test',
                        'updated_at': now(),
                    })
                    continue
                try:
                    apply_edits(worktree, edits, gate, policy)
                except WorkerError as exc:
                    if queue_bounded_anchor_correction(
                        spool, worktree, item, record, edits, test_paths,
                        exc, gate, policy,
                    ):
                        continue
                    raise
                tests = validate_patch(worktree, test_paths, gate, policy)
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
        finally:
            sync_support_lifecycle_notification(
                record,
                item,
                event_root=spool.parent / 'autonomous-repair' / 'lifecycle-events',
            )

    state['updated_at'] = now()
    save_state(state_path, state)
    if unadmitted_p0:
        print('SUPPORT_ADMISSION_HEALTH=DEGRADED unmatched_p0=' + ','.join(unadmitted_p0))
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
