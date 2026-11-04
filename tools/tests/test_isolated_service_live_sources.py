from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from tools import isolated_service_live_sources as sources
from tools import isolated_service_shadow as shadow
from tools import source_baseline_monitor_service as baseline

NOW = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)


def test_provider_canary_adapter_uses_actual_healthy_field():
    src={"generated_at":NOW.isoformat(),"results":[
        {"provider":"autotask","healthy":True,"error_class":"none"},
        {"provider":"it_glue","healthy":False,"error_class":"execution_failed"},
    ]}
    result=sources.provider_canaries(src,now=NOW)
    assert result["status"]=="unhealthy"
    assert result["receipt_count"]==2
    assert result["providers"]==[{"provider":"autotask","health":"healthy"},{"provider":"it_glue","health":"unhealthy"}]
    assert "error_class" not in str(result)


def test_missing_provider_results_never_reports_healthy():
    assert sources.provider_canaries({"generated_at":NOW.isoformat(),"results":[]},now=NOW)["status"]=="unknown"
    assert sources.provider_canaries({"generated_at":NOW.isoformat(),"results":[{"provider":"abc"}]},now=NOW)["status"]=="unknown"


def test_stale_and_future_evidence_fails_closed():
    old={"generated_at":(NOW-timedelta(hours=1)).isoformat(),"results":[{"provider":"ok","healthy":True}]}
    future={"generated_at":(NOW+timedelta(hours=1)).isoformat(),"results":[{"provider":"ok","healthy":True}]}
    assert sources.provider_canaries(old,now=NOW)["status"]=="stale"
    assert sources.provider_canaries(future,now=NOW)["status"]=="stale"


def test_duplicate_providers_cannot_report_healthy():
    src={"generated_at":NOW.isoformat(),"results":[{"provider":"x","healthy":True},{"provider":"x","healthy":True}]}
    assert sources.provider_canaries(src,now=NOW)["status"]=="unknown"


def test_todo_adapter_normalizes_existing_object_form():
    src={"updated_at":NOW.isoformat(),"items":{
        "TODO-1":{"issue_number":2209,"phase":"development_blocked","reason":"stale worktree requires governed clean-source recovery"},
        "TODO-2":{"issue_number":952,"phase":"development_blocked","reason":"API details/credentials required"},
        "TODO-3":{"issue_number":951,"phase":"waiting_operational_acceptance","reason":"verify evidence"},
    }}
    result=sources.todo_commitments(src,now=NOW)
    assert result["status"]=="work_available"
    assert result["counts"]["recoverable"]==1
    assert result["counts"]["external"]==1
    assert result["counts"]["actionable"]==1


def test_todo_missing_or_stale_data_not_actionable():
    assert sources.todo_commitments({"updated_at":NOW.isoformat()},now=NOW)["status"]=="unknown"
    old={"updated_at":(NOW-timedelta(hours=1)).isoformat(),"items":{"TODO-1":{"phase":"waiting_development_merge"}}}
    assert sources.todo_commitments(old,now=NOW)["status"]=="stale"


def test_bounded_file_read_rejects_symlink_and_non_regular(tmp_path):
    src=tmp_path/"src.json";src.write_text('{"items": {}}')
    link=tmp_path/"link.json";link.symlink_to(src)
    with pytest.raises(OSError):
        sources.bounded_json(link)
    with pytest.raises(ValueError):
        sources.bounded_json(tmp_path)


def test_bounded_read_digests_exact_bytes(tmp_path):
    import hashlib
    src=tmp_path/"src.json";raw=b'{"healthy": true}'
    src.write_bytes(raw)
    result,digest=sources.bounded_json(src)
    assert result["healthy"] is True
    assert digest==hashlib.sha256(raw).hexdigest()


def test_shadow_output_cannot_target_existing_production_or_source(tmp_path):
    with pytest.raises(ValueError):
        shadow.run_one("ledger",repo=tmp_path,state_root=tmp_path)
    with pytest.raises(ValueError):
        shadow.run_one("ledger",repo=tmp_path,state_root=Path("/var/lib/jason/openclaw/services"))


def test_remote_source_baseline_reads_ref_without_fetch(monkeypatch,tmp_path):
    seen=[]
    def fake_git(repo,*args):
        seen.append(args)
        return "a"*40+"\trefs/heads/main"
    monkeypatch.setattr(baseline,"git",fake_git)
    assert baseline.check_remote(tmp_path,"a"*40)["status"]=="aligned"
    assert seen==[("ls-remote","--exit-code","origin","refs/heads/main")]
    assert baseline.check_remote(tmp_path,"b"*40)["status"]=="changed"
    with pytest.raises(ValueError):
        baseline.check_remote(tmp_path,"main")


def test_each_remaining_service_runs_without_making_authority_claim(tmp_path):
    repo=tmp_path/"repo";repo.mkdir()
    out=tmp_path/"out"
    for name in ("test_evidence_collection","dependency_conflict","rollback_readiness","operational_acceptance","source_baseline_monitor"):
        result=shadow.run_one(name,repo=repo,state_root=out,now=NOW)
        assert result["advisory_only"] is True
        assert result["production_authority"] is False
        assert result["status"] not in {"healthy","ready","accepted","clear","aligned","reusable"}


def test_dependency_shadow_reports_actual_declared_overlap(tmp_path):
    repo=tmp_path/"repo";repo.mkdir();out=tmp_path/"out"
    p=tmp_path/"items.json"
    p.write_text(json.dumps({"items":[{"id":"A","components":["auth"]},{"id":"B","components":["auth"]}]}))
    result=shadow.run_one("dependency_conflict",repo=repo,state_root=out,input_path=p,now=NOW)
    assert result["status"]=="conflict"
    assert result["conflicts"][0]["reasons"]==["components"]
