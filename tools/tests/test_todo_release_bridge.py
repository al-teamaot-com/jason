import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

MODULE_PATH = TOOLS / "todo_release_bridge.py"
SPEC = importlib.util.spec_from_file_location("todo_release_bridge", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

SHA = "a" * 40
SHA_B = "b" * 40


def release_record(state="closed"):
    return {
        "release_id": "release-" + "a" * 16,
        "state": state,
        "updated_at": "2026-10-02T23:45:00+00:00",
        "production": {
            "live_sha": SHA,
            "verified_at": "2026-10-02T23:44:00+00:00",
        },
    }


class TodoReleaseBridgeTests(unittest.TestCase):
    def test_todo_inventory_covers_older_approved_issues(self):
        issue = {"number": 950, "title": "TODO-CONN-005", "body": "- TODO item: TODO-CONN-005", "url": "https://github.com/a/b/issues/950", "updatedAt": "2026-10-15"}
        with patch.object(module, "gh_json", return_value=[issue]) as gh:
            observed = module.todo_issues(Path("/tmp/repo"))
        self.assertEqual(observed[0]["issue_number"], 950)
        self.assertEqual(gh.call_args.args[0][5], "5000")

    def test_todo_inventory_does_not_silently_truncate(self):
        with patch.object(module, "gh_json", return_value=[{}] * 5000):
            with self.assertRaises(module.TodoReleaseBridgeError):
                module.todo_issues(Path("/tmp/repo"))

    def test_release_id_requires_exact_sha(self):
        self.assertEqual(module.release_id(SHA), "release-" + "a" * 16)
        with self.assertRaises(module.TodoReleaseBridgeError):
            module.release_id("main")

    def test_update_todo_text_requires_closed_release(self):
        source = """# Backlog

### TODO-OPS-010 — Build thing

- **Priority:** P1
- **Status:** Planned
- **Idea:** Build it.

### TODO-OPS-011 — Other thing

- **Priority:** P2
- **Status:** Planned
"""
        updated = module.update_todo_text(
            source,
            todo_id="TODO-OPS-010",
            release=release_record(),
        )
        self.assertIn("**Status:** Implemented", updated)
        self.assertIn("release-" + "a" * 16, updated)
        self.assertIn(SHA, updated)
        self.assertIn("**Implementation evidence:**", updated)
        other = updated.split("### TODO-OPS-011", 1)[1]
        self.assertIn("**Status:** Planned", other)

        with self.assertRaises(module.TodoReleaseBridgeError):
            module.update_todo_text(
                source,
                todo_id="TODO-OPS-010",
                release=release_record("production_eligible"),
            )

    def test_release_record_reads_exact_merge_sha(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "records" / f"{module.release_id(SHA)}.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(release_record()), encoding="utf-8")
            observed = module.release_record(root, SHA)
            self.assertIsNotNone(observed)
            self.assertEqual(observed["state"], "closed")

    def test_effective_release_prefers_exact_closed_record(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = root / "records"
            records.mkdir(parents=True)
            exact = release_record()
            (records / f"{module.release_id(SHA)}.json").write_text(
                json.dumps(exact), encoding="utf-8"
            )
            with patch.object(module, "commit_is_ancestor") as ancestor:
                observed = module.effective_release_record(Path(td), root, SHA)
            self.assertEqual(observed["release_id"], exact["release_id"])
            ancestor.assert_not_called()

    def test_effective_release_accepts_closed_verified_descendant(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = root / "records"
            records.mkdir(parents=True)
            exact = release_record("failed")
            (records / f"{module.release_id(SHA)}.json").write_text(
                json.dumps(exact), encoding="utf-8"
            )
            descendant = {
                "release_id": "release-" + "b" * 16,
                "state": "closed",
                "updated_at": "2026-10-07T18:40:00+00:00",
                "production": {
                    "live_sha": SHA_B,
                    "verified_at": "2026-10-07T18:39:00+00:00",
                },
            }
            (records / f"{module.release_id(SHA_B)}.json").write_text(
                json.dumps(descendant), encoding="utf-8"
            )
            with patch.object(
                module,
                "commit_is_ancestor",
                side_effect=lambda repo, ancestor, child: ancestor == SHA and child == SHA_B,
            ):
                observed = module.effective_release_record(Path(td), root, SHA)
            self.assertEqual(observed["release_id"], descendant["release_id"])
            self.assertEqual(observed["production"]["live_sha"], SHA_B)

    def test_prepare_release_delegates_to_release_manager(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner = root / "release_manager_host_runner.py"
            runner.write_text("# runner", encoding="utf-8")
            source = root / "source"
            source.mkdir()
            state = root / "state"
            state.mkdir()

            payload = {
                **release_record("production_eligible"),
                "release_id": module.release_id(SHA),
            }
            with patch.object(module, "run", return_value=json.dumps(payload)) as run_cmd:
                result = module.prepare_release(
                    repo=root,
                    merge_sha=SHA,
                    release_runner=runner,
                    release_source=source,
                    release_state=state,
                )
            self.assertEqual(result["state"], "production_eligible")
            args = run_cmd.call_args.args[0]
            self.assertIn("prepare", args)
            self.assertEqual(args[args.index("--repo") + 1], str(root))
            self.assertIn("--candidate-sha", args)
            self.assertIn(SHA, args)
            self.assertIn("--change-class", args)
            self.assertIn("todo", args)

    def test_todo_and_development_metadata_patterns_are_exact(self):
        self.assertTrue(module.TODO_META.search("- TODO item: TODO-OPS-010"))
        self.assertFalse(module.TODO_META.search("- TODO: TODO-OPS-010"))
        self.assertTrue(module.DEV_META.search("- Development issue: #123"))


if __name__ == "__main__":
    unittest.main()


def test_upstream_commitment_state_reports_real_development_blocker():
    phase, reason = module.upstream_commitment_state(
        {'phase': 'blocked', 'reason': 'provider consent required'}
    )
    assert phase == 'development_blocked'
    assert reason == 'provider consent required'
    phase, _ = module.upstream_commitment_state({'phase': 'pr_ready'})
    assert phase == 'waiting_development_merge'
    phase, reason = module.upstream_commitment_state(
        {'phase': 'waiting_external_dependency', 'reason': 'provider consent required'}
    )
    assert phase == 'waiting_external_dependency'
    assert reason == 'provider consent required'
    phase, _ = module.upstream_commitment_state({'phase': 'waiting_operational_acceptance'})
    assert phase == 'waiting_operational_acceptance'
    phase, _ = module.upstream_commitment_state({'phase': 'waiting_sequenced_work'})
    assert phase == 'waiting_sequenced_work'


def test_commitment_summary_flags_empty_release_queue_with_upstream_work():
    summary = module.commitment_summary(
        {
            'TODO-OPS-001': {'phase': 'development_in_progress'},
            'TODO-OPS-002': {'phase': 'waiting_external_dependency'},
            'TODO-OPS-003': {'phase': 'complete'},
        }
    )
    assert summary['approved_commitment_count'] == 3
    assert summary['outstanding_count'] == 2
    assert summary['blocked_count'] == 0
    assert summary['upstream_pending_count'] == 2
    assert summary['release_pending_count'] == 0
    assert summary['release_queue_empty_but_upstream_pending'] is True


def test_development_records_by_issue_reads_durable_worker_state(tmp_path):
    (tmp_path / 'development-state.json').write_text(
        json.dumps({'items': {'DEV-42': {'issue_number': 42, 'phase': 'blocked'}}}),
        encoding='utf-8',
    )
    records = module.development_records_by_issue(tmp_path)
    assert records[42]['phase'] == 'blocked'


def test_merged_canonical_closure_recovers_stale_blocked_ledger(tmp_path):
    rid = module.release_id(SHA_B)
    path = tmp_path / 'records' / f'{rid}.json'
    path.parent.mkdir()
    path.write_text(json.dumps({
        'release_id': rid, 'state': 'closed',
        'release_candidate': {'candidate_sha': SHA_B},
        'production': {'live_sha': SHA_B, 'verified_at': '2026-10-16T08:20:00Z',
                       'alignment_verified': True},
    }))
    item = {'issue_number': 950, 'closure_pr': 1487, 'release_id': rid,
            'merge_sha': SHA, 'phase': 'development_blocked',
            'reason': 'stale duplicate worker HTTP failure'}
    closure = {'number': 1487, 'mergedAt': '2026-10-16T08:29:19Z',
               'body': f'- TODO closure: TODO-CONN-005\n- Development issue: #950\n- Release ID: {rid}\n- Production SHA: {SHA_B}'}
    issue = {'number': 950, 'state': 'CLOSED', 'body': '- TODO item: TODO-CONN-005'}
    with patch.object(module, 'gh_json', side_effect=[closure, issue]), \
         patch.object(module, 'commit_is_ancestor', return_value=True):
        module.reconcile_verified_closed_issues(
            tmp_path, tmp_path, {'TODO-CONN-005': item})
    assert item['phase'] == 'complete'
    assert item['verified_operational_evidence']['canonical_issue'] == 950


def test_unmerged_or_wrong_issue_never_closes_ledger(tmp_path):
    rid = module.release_id(SHA)
    path = tmp_path / 'records' / f'{rid}.json'
    path.parent.mkdir()
    path.write_text(json.dumps({
        'release_id': rid, 'state': 'closed',
        'release_candidate': {'candidate_sha': SHA},
        'production': {'live_sha': SHA, 'verified_at': 'now', 'alignment_verified': True},
    }))
    base = {'issue_number': 950, 'closure_pr': 1487, 'release_id': rid,
            'merge_sha': SHA, 'phase': 'development_blocked'}
    text = f'- TODO closure: TODO-CONN-005\n- Development issue: #950\n- Release ID: {rid}\n- Production SHA: {SHA}'
    for closure, issue in [
        ({'number': 1487, 'mergedAt': None, 'body': text}, None),
        ({'number': 1487, 'mergedAt': 'today', 'body': text},
         {'number': 1444, 'state': 'CLOSED', 'body': '- TODO item: TODO-CONN-005'}),
        ({'number': 1487, 'mergedAt': 'today', 'body': text},
         {'number': 950, 'state': 'OPEN', 'body': '- TODO item: TODO-CONN-005'}),
        ({'number': 1487, 'mergedAt': 'today', 'body': text.replace('950', '1444')}, None),
    ]:
        item = dict(base)
        evidence = [closure] if issue is None else [closure, issue]
        with patch.object(module, 'gh_json', side_effect=evidence):
            module.reconcile_verified_closed_issues(
                tmp_path, tmp_path, {'TODO-CONN-005': item})
        assert item['phase'] == 'development_blocked'
