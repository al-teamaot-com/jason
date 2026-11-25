"""Root forensic census: read-only and sanitized, no owner/production action."""
import ast,json,os,stat,types
from pathlib import Path
from tools import audit_journal_bounded_root_census as census

def test_exact_root_census_is_read_only_and_never_handles_credentials():
    src=Path(census.__file__).read_text()
    tree=ast.parse(src)
    banned={"system","remove","unlink","rename","rmtree","write_text",
            "write_bytes","chown","chmod","kill","start","exec","eval"}
    dangerous=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            call=node.func
            name=call.attr if isinstance(call,ast.Attribute) else (
                call.id if isinstance(call,ast.Name) else "")
            if name in banned:dangerous.append(name)
    assert not dangerous
    assert "O_NOFOLLOW" in src
    assert "O_RDONLY" in src
    assert "owner_challenge\":False" in src
    assert "production_mutations\":False" in src
    assert "subprocess" not in src
    assert "sudo" not in src
    assert "token" not in src.lower()

def test_root_census_returns_sanitized_schema_metadata_without_owner_challenge(
        monkeypatch,tmp_path,capsys):
    safe_scope={
        "rollback_container_capacity_before":{
            "existing_count":7,"existing_names":["old1","old2"]},
        "desired_state_after_sha256":census.sha({"final":True}),
        "desired_state_initial_sha256":census.sha({"intended":"initial"}),
        "rollback_desired_state_sha256":census.sha({"rollback":True}),
        "source_sha256":{"trusted1":"fake-raw-secret-unavailable"},
    }
    expected=census.sha(safe_scope)
    plan={
        "scope":safe_scope,"scope_sha256":expected,
        "candidate_sha":census.EXPECTED_CANDIDATE,
        "owner_oid":census.EXPECTED_OWNER,
        "independently_verified_entra_owner":True,
        "producer_before_sha256":census.sha({"core":{"old":True}}),
    }
    dest=tmp_path/"desired.json"
    dest.write_text('{"intended":"initial"}')
    dataset=tmp_path/"existing.db"
    dataset.write_bytes(b"readonly-fixture")
    monkeypatch.setattr(census,"EXPECTED_SCOPE",expected)
    monkeypatch.setattr(census,"DB",dataset)
    monkeypatch.setattr(census,"ARCHIVE",tmp_path)
    monkeypatch.setattr(census,"DESIRED",dest)
    monkeypatch.setattr(census,"os",types.SimpleNamespace(geteuid=lambda:0))
    monkeypatch.setattr(census,"sys",types.SimpleNamespace(flags=types.SimpleNamespace(isolated=1)))
    record={
        census.PLAN:plan,census.JOURNAL:{"scope_sha256":expected,"steps":{}},
        census.BEFORE:{"core":{"old":True}},
        census.ADOPTION:{"scope_sha256":expected},
        census.POLICY:{"candidate_sha":census.EXPECTED_CANDIDATE,
                       "trusted_source_sha256":safe_scope["source_sha256"]},
        census.CATALOG:{"mode":"legacy","generation":0,"epoch":None,"segments":[]},
        census.BASE/"private/desired-final.json":{"final":True},
        census.BASE/"private/desired-rollback.json":{"rollback":True},
        dest:{"intended":"initial"},
        census.STATE/"production-control-state.json":{
            "circuit_breaker":{"state":"open",
                               "reason":"continuous_production_drift_detected"}},
        census.STATE/"production-drift.json":{
            "status":"drift_detected",
            "observed_at":"2026-11-24T14:00:00+00:00",
            "problems":[{"kind":"failed_system_unit",
                         "unit":"jason-audit-journal-release.service",
                         "state":"failed"}]},
    }
    monkeypatch.setattr(census,"read_json",
                        lambda path,mode:record[Path(path)])
    census.check()
    stdout=capsys.readouterr().out.splitlines()
    assert len(stdout)==2
    assert stdout[1]=="READONLY_PROTECTED_SCOPE_CENSUS=PASS"
    output=json.loads(stdout[0])
    assert output["owner_challenge"] is False
    assert output["production_mutations"] is False
    assert output["scope_field_presence"]["rollback_container_capacity_before"]
    assert not output["scope_field_presence"]["rollback_container_limit_before"]
    assert not output["scope_field_presence"]["rollback_container_reserve"]
    assert output["historical_retention_snapshot_summary"]["reserved_slots"] is None
    assert output["desired_proofs"]["desired-final.json_matches_approved_scope"]
    assert output["desired_proofs"]["live_desired_matches_canonical_initial_or_rollback"]
    assert output["exact_plan_sha256_matches_current_scope"] is True
    assert "fake-raw-secret-unavailable" not in stdout[0]
    assert census.EXPECTED_OWNER not in stdout[0]

def test_root_census_refuses_owner_mismatch_without_disclosing_identity(monkeypatch,tmp_path):
    test_source=Path(census.__file__).read_text()
    assert 'assert result["licensed_owner_recorded"]' in test_source
    assert 'assert result["plan_scope_content_matches_sha256"]' in test_source
    assert 'assert result["old_exact_candidate_matches"]' in test_source
