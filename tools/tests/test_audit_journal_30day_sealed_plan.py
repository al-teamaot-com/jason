import json
from datetime import datetime,timezone,timedelta
from pathlib import Path

import pytest
from tools import audit_journal_30day_sealed_plan as plan

ROOT=Path(__file__).resolve().parents[2]
POLICY=ROOT/"config/jason-orchestration-30day-retention-proposal-v1.json"


def inputs():
    now=datetime(2026,11,25,12,0,tzinfo=timezone.utc)
    seg1="a"*32;seg2="b"*32
    catalog={"mode":"segmented","generation":2,"segments":[
        {"id":seg1,"state":"sealed","proof":{"events":10,"file_sha256":"c"*64}},
        {"id":seg2,"state":"sealed","proof":{"events":5,"file_sha256":"d"*64}},
    ]}
    stats={seg1:{"retained":4,"expired":6,"file_sha256":"c"*64},
           seg2:{"retained":0,"expired":5,"file_sha256":"d"*64}}
    return {"catalog":catalog,"statistics":stats,"now":now,
            "source_main_sha":"e"*40,"prior_catalog_sha256":"f"*64}


def test_sealed_history_is_in_scope_as_well_as_active_database():
    cfg=json.loads(POLICY.read_text())
    assert cfg["activation"]=="disabled_source_only_policy_proposal"
    assert cfg["permanent_deletion_authorized"] is False
    assert cfg["retention_days"]==30
    assert len(cfg["requires_governance_exception_to"])==2
    assert cfg["targets"][:2]==[
        "canonical_active_orchestration_events","all_root_sealed_orchestration_history_segments"]
    assert "Root_Owner_authorization_ledgers" in cfg["excluded_from_scope"]


def test_read_only_plan_preserves_recent_rows_in_mixed_archive():
    result=plan.draft_segment_plan(**inputs())
    assert plan.verify_draft(result)
    p=result["proposal"]
    assert p["cutoff_utc"]=="2026-10-26T12:00:00+00:00"
    assert p["archives"][0]["required_action"]=="stage_verified_recent_only_copy_then_root_seal_swap"
    assert p["archives"][1]["required_action"]=="root_remove_only_after_exact_accepted_proof"
    assert p["expired_records_deleted"] is False


@pytest.mark.parametrize("mutation",["unsealed","counter","hash","missing","negative","source"])
def test_inconsistent_or_unsealed_segment_denies_release_scope(mutation):
    a=inputs()
    if mutation=="unsealed":a["catalog"]["segments"][0]["state"]="pending"
    elif mutation=="counter":a["statistics"]["a"*32]["expired"]=7
    elif mutation=="hash":a["statistics"]["a"*32]["file_sha256"]="0"*64
    elif mutation=="missing":a["statistics"].pop("a"*32)
    elif mutation=="negative":a["statistics"]["a"*32]["retained"]=-1
    else:a["source_main_sha"]="changed"
    with pytest.raises(ValueError,match="AUDIT_30DAY_SEALED_"):
        plan.draft_segment_plan(**a)


def test_cutoff_rejects_naive_time_and_scope_rewrite():
    a=inputs();a["now"]=datetime(2026,11,25,12,0)
    with pytest.raises(ValueError,match="AWARE_CUTOFF_REQUIRED"):
        plan.draft_segment_plan(**a)
    result=plan.draft_segment_plan(**inputs())
    result["proposal"]["approved"]=True
    with pytest.raises(ValueError,match="PROPOSAL_CHANGED"):
        plan.verify_draft(result)


def test_plan_module_exposes_no_mutating_production_operations():
    src=(ROOT/"tools/audit_journal_30day_sealed_plan.py").read_text()
    for token in ("os.unlink","os.remove","os.replace","shutil.rmtree",
                  "DELETE FROM","DROP TABLE","docker stop","systemctl restart"):
        assert token not in src
