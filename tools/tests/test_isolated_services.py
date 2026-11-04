from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


docs = load("documentation_assurance_service")
providers = load("provider_health_monitor_service")
evidence = load("test_evidence_collection_service")
work = load("work_reconciliation_service")

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


def test_documentation_flags_material_change_without_docs():
    result = docs.classify(["implementation/runtime_service/src/app.py"])
    assert result["status"] == "attention"
    assert result["requires_documentation_review"] is True


def test_documentation_accepts_material_change_with_docs():
    result = docs.classify(["implementation/runtime_service/src/app.py", "docs/operations/runtime.md"])
    assert result["status"] == "current"


def test_provider_monitor_separates_stale_and_unhealthy():
    receipts = [
        {"provider": "autotask", "status": "ok", "observed_at": (NOW - timedelta(seconds=30)).isoformat(), "source": "probe-a"},
        {"provider": "drmm", "status": "ok", "observed_at": (NOW - timedelta(hours=2)).isoformat(), "source": "probe-b"},
    ]
    result = providers.evaluate(receipts, max_age_seconds=900, now=NOW)
    assert result["status"] == "degraded"
    assert result["providers"][1]["health"] == "stale"


def test_provider_monitor_marks_real_failure_unhealthy():
    receipts = [{"provider": "kfs", "status": "failed", "observed_at": NOW.isoformat(), "source": "probe"}]
    assert providers.evaluate(receipts, now=NOW)["status"] == "unhealthy"


def test_evidence_reused_only_for_exact_candidate_and_fresh_receipt(tmp_path):
    receipt = tmp_path / "test.json"
    receipt.write_text(json.dumps({"status": "passed", "candidate_sha": "a" * 40, "observed_at": NOW.isoformat()}))
    result = evidence.collect([receipt], tmp_path / "index.json", candidate_sha="a" * 40, now=NOW)
    assert result["status"] == "reusable"
    assert result["records"][0]["reusable"] is True


def test_evidence_refreshes_when_candidate_changes(tmp_path):
    receipt = tmp_path / "test.json"
    receipt.write_text(json.dumps({"status": "passed", "candidate_sha": "a" * 40, "observed_at": NOW.isoformat()}))
    result = evidence.collect([receipt], tmp_path / "index.json", candidate_sha="b" * 40, now=NOW)
    assert result["status"] == "refresh_required"


def test_work_reconciler_does_not_turn_external_credentials_into_retry():
    source = {"items": [{"todo_id": "TODO-X", "phase": "development_blocked", "reason": "API details/credentials required"}]}
    result = work.reconcile(source)
    assert result["counts"]["external"] == 1
    assert result["counts"]["recoverable"] == 0


def test_work_reconciler_surfaces_stale_worktree_as_recoverable():
    source = {"items": [{"todo_id": "TODO-Y", "phase": "development_blocked", "reason": "stale worktree requires governed clean-source recovery"}]}
    result = work.reconcile(source)
    assert result["status"] == "work_available"
    assert result["counts"]["recoverable"] == 1


def test_work_reconciler_surfaces_merge_and_acceptance_as_actionable():
    source = {"items": [
        {"todo_id": "A", "phase": "waiting_development_merge", "reason": "checks passed"},
        {"todo_id": "B", "phase": "waiting_operational_acceptance", "reason": "verify outcome"},
    ]}
    result = work.reconcile(source)
    assert result["counts"]["actionable"] == 2

dependency = load("dependency_conflict_service")
baseline = load("source_baseline_monitor_service")
rollback = load("rollback_readiness_service")
acceptance = load("operational_acceptance_service")

def test_dependency_conflict_detects_shared_component():
    result=dependency.analyze([{"id":"A","components":["release"]},{"id":"B","components":["release"]}])
    assert result["status"]=="conflict"

def test_dependency_conflict_allows_independent_work():
    result=dependency.analyze([{"id":"A","components":["docs"]},{"id":"B","components":["kfs"]}])
    assert result["status"]=="clear"

def test_rollback_readiness_requires_complete_verified_manifest():
    assert rollback.evaluate({"rollback_sha":"a","runtime_image":"r","mcp_image":"m","host_release":"h","verified":True})["status"]=="ready"
    assert rollback.evaluate({"rollback_sha":"a","verified":True})["status"]=="not_ready"

def test_operational_acceptance_requires_all_checks():
    assert acceptance.evaluate([{"name":"smoke","status":"pass"},{"name":"health","status":"healthy"}])["status"]=="accepted"
    assert acceptance.evaluate([{"name":"smoke","status":"fail"}])["status"]=="failed"

ledger = load("isolated_service_ledger")
supervisor = load("isolated_service_supervisor")

def test_ledger_marks_optional_missing_without_blocking(tmp_path):
    cfg={"services":[{"name":"docs","state_file":"docs.json","max_age_seconds":60,"required":False}]}
    result=ledger.build(cfg,tmp_path,now=NOW)
    assert result["status"]=="available"
    assert result["entries"][0]["freshness"]=="missing"

def test_ledger_required_missing_is_degraded(tmp_path):
    cfg={"services":[{"name":"critical","state_file":"critical.json","max_age_seconds":60,"required":True}]}
    assert ledger.build(cfg,tmp_path,now=NOW)["status"]=="degraded"

def test_supervisor_does_not_turn_optional_service_failure_into_global_block():
    result=supervisor.classify({"entries":[{"name":"docs","required":False,"freshness":"fresh","service_status":"attention"}]})
    assert result["status"]=="degraded"
    assert result["problems"]==[]

def test_supervisor_blocks_only_required_missing_or_stale_service():
    result=supervisor.classify({"entries":[{"name":"critical","required":True,"freshness":"stale","service_status":"healthy"}]})
    assert result["status"]=="blocked"
