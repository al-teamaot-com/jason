"""Adversarial tests for the read-only, bounded engineering tool loop."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
for name in ("engineering_evidence_tools", "support_repair_host_worker"):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

evidence = sys.modules["engineering_evidence_tools"]
support = sys.modules["support_repair_host_worker"]


class Gate:
    def path_denial_reason(self, path, policy):
        if "secrets" in path or "credential" in path:
            return "denied-by-change-gate"
        return None


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True,
        check=True,
    ).stdout.strip()


def setup_session(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "config").mkdir()
    policy_path = TOOLS.parent / "config/engineering-supervisor-policy.json"
    (repo / "config/engineering-supervisor-policy.json").write_text(policy_path.read_text())
    for name, contents in {
        "tools/source.py": "def admission():\n    return 'working-source-code'\n",
        "tools/test_source.py": "def test_admission():\n    assert True\n",
        "tools/secrets.py": "password = 'never-disclose'\n",
    }.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Tests")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    item = {
        "id": "SUPPORT-OPS-100", "title": "Missing source",
        "evidence": "Need source definitions", "acceptance": "Tests pass",
    }
    spool = tmp_path / "spool"
    original = support.queue_reasoning(
        spool, kind="edit_plan", item=item,
        context={"diagnosis": "need more code", "source_excerpts": [
            {"path": "tools/test_source.py", "content": "old test"},
        ]},
    )
    record = {"phase": "implementing", "reasoning_request_id": original}
    return repo, spool, item, record


def call(repo, spool, item, record, requests, **overrides):
    result = {
        "summary": "Need read-only source evidence",
        "edits": [], "test_paths": [], "blocked_reason": None,
        "evidence_requests": requests,
    }
    result.update(overrides)
    return evidence.continue_evidence_session(
        response_result=result, record=record, item=item, spool=spool,
        worktree=repo, repo=repo, gate=Gate(), repair_policy={},
        support=support, queue_reasoning=support.queue_reasoning,
    )


def test_tracked_source_is_read_and_follow_up_is_content_addressed(tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    old = record["reasoning_request_id"]
    before = (repo / "tools/source.py").read_text()
    assert call(repo, spool, item, record, [
        {"tool": "read_source", "path": "tools/source.py", "query": None},
    ]) is True
    assert record["reasoning_request_id"] != old
    assert record["evidence_turn_count"] == 1
    assert record["evidence_source_revision"] == git(repo, "rev-parse", "HEAD")
    request = json.loads((spool / "reasoning/requests" /
                          (record["reasoning_request_id"] + ".json")).read_text())
    assert request["context"]["previous_reasoning_request_id"] == old
    assert "working-source-code" in request["context"]["source_excerpts"][0]["content"]
    assert request["context"]["read_only_tool_receipts"][0]["path"] == "tools/source.py"
    assert (repo / "tools/source.py").read_text() == before
    assert git(repo, "status", "--porcelain") == ""


def test_two_evidence_turns_are_possible_but_third_fails_closed(tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    requests = [{"tool": "read_source", "path": "tools/source.py", "query": None}]
    assert call(repo, spool, item, record, requests)
    first = record["reasoning_request_id"]
    assert call(repo, spool, item, record, [
        {"tool": "read_source", "path": "tools/test_source.py", "query": None},
    ])
    assert record["reasoning_request_id"] != first
    with pytest.raises(evidence.EvidenceToolError, match="budget exhausted"):
        call(repo, spool, item, record, requests)
    assert record["evidence_turn_count"] == 2


@pytest.mark.parametrize("requests", [
    [{"tool": "shell", "query": "rm -rf /", "path": None}],
    [{"tool": "read_source", "path": "../../etc/passwd", "query": None}],
    [{"tool": "read_source", "path": "/etc/passwd", "query": None}],
    [{"tool": "read_source", "path": "tools/secrets.py", "query": None}],
    [{"tool": "read_source", "path": "tools/untracked.py", "query": None}],
    [{"tool": "read_source", "path": "tools/source.py", "query": None, "exec": "yes"}],
    [{"tool": "search_source", "query": "x", "path": None}],
    [{"tool": "search_source", "query": "admission", "path": "tools/source.py"}],
])
def test_unauthorized_requests_fail_closed_without_queueing(tmp_path, requests):
    repo, spool, item, record = setup_session(tmp_path)
    (repo / "tools/untracked.py").write_text("password = 'untracked'")
    old = record["reasoning_request_id"]
    with pytest.raises(evidence.EvidenceToolError):
        call(repo, spool, item, record, requests)
    assert old == record["reasoning_request_id"]
    assert record.get("evidence_turn_count") is None
    assert len(list((spool / "reasoning/requests").glob("*.json"))) == 1


def test_denied_action_hidden_after_full_first_search_is_still_rejected(monkeypatch, tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    old = record["reasoning_request_id"]
    monkeypatch.setattr(support, "safe_search", lambda *a, **kw: [
        {"path": "tools/source.py", "content": "safe source"},
    ])
    with pytest.raises(evidence.EvidenceToolError, match="unapproved source tool"):
        call(repo, spool, item, record, [
            {"tool": "search_source", "query": "find source", "path": None},
            {"tool": "execute_shell", "path": None, "query": "echo never"},
        ])
    assert record["reasoning_request_id"] == old


def test_source_turn_refuses_stale_main_revision(tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    git(repo, "commit", "--allow-empty", "-m", "unpromoted local branch")
    old = record["reasoning_request_id"]
    with pytest.raises(evidence.EvidenceToolError, match="stale worktree"):
        call(repo, spool, item, record, [
            {"tool": "read_source", "path": "tools/source.py", "query": None},
        ])
    assert record["reasoning_request_id"] == old


def test_symlinked_tracked_source_is_denied(tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("private ignored bytes")
    source = repo / "tools/source.py"
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(evidence.EvidenceToolError):
        call(repo, spool, item, record, [
            {"tool": "read_source", "path": "tools/source.py", "query": None},
        ])


def test_repeated_request_and_mixed_edit_attempts_are_denied(tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    requests = [{"tool": "read_source", "path": "tools/source.py", "query": None}]
    old = record["reasoning_request_id"]
    with pytest.raises(evidence.EvidenceToolError, match="mixed"):
        call(repo, spool, item, record, requests, edits=[
            {"path": "tools/source.py", "old_text": "old", "new_text": "new"},
        ])
    record["evidence_last_source_request"] = old
    with pytest.raises(evidence.EvidenceToolError, match="already processed"):
        call(repo, spool, item, record, requests)
    record.pop("evidence_last_source_request")
    reqpath = spool / "reasoning/requests" / (old + ".json")
    original = json.loads(reqpath.read_text())
    original["title"] = "tampered"
    reqpath.write_text(json.dumps(original))
    with pytest.raises(evidence.EvidenceToolError, match="identity checks"):
        call(repo, spool, item, record, requests)


def test_dirty_source_and_disabled_policy_block_continuation(tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    requests = [{"tool": "read_source", "path": "tools/source.py", "query": None}]
    (repo / "tools/source.py").write_text("local edits")
    with pytest.raises(evidence.EvidenceToolError, match="dirty"):
        call(repo, spool, item, record, requests)
    git(repo, "checkout", "--", "tools/source.py")
    path = repo / "config/engineering-supervisor-policy.json"
    data = json.loads(path.read_text())
    data["enabled"] = False
    path.write_text(json.dumps(data))
    git(repo, "add", "config/engineering-supervisor-policy.json")
    git(repo, "commit", "-m", "verified policy changed")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    with pytest.raises(evidence.EvidenceToolError, match="disabled"):
        call(repo, spool, item, record, requests)


def test_search_evidence_and_missing_match(monkeypatch, tmp_path):
    repo, spool, item, record = setup_session(tmp_path)
    monkeypatch.setattr(support, "safe_search", lambda *a, **kw: [
        {"path": "tools/source.py", "content": "def admission():\n    return True"},
    ])
    assert call(repo, spool, item, record, [
        {"tool": "search_source", "query": "admission", "path": None},
    ])
    repo2, spool2, item2, record2 = setup_session(tmp_path / "other")
    monkeypatch.setattr(support, "safe_search", lambda *a, **kw: [])
    with pytest.raises(evidence.EvidenceToolError, match="no authorized"):
        call(repo2, spool2, item2, record2, [
            {"tool": "search_source", "query": "unmatched", "path": None},
        ])
