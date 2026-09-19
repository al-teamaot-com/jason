from orchestrator.client_security_posture import *
def ev(**facts): return EvidenceObservation("governed-test","2026-09-19T09:55:00Z","corr-test",facts)
def test_missing_evidence_never_becomes_good():
 r=build_review(client_id="311",evidence_by_control={})
 assert r["counts"]["confirmed_good"]==0
 assert r["counts"]["unknown"]==len(AOT_BASELINE)
def test_unavailable_is_distinct_from_gap_and_unknown():
 r=build_review(client_id="311",evidence_by_control={},unavailable_controls=["BACKUP-SUCCESS","IDENTITY-MFA"])
 by={x.control_id:x for x in r["assessments"]}
 assert by["BACKUP-SUCCESS"].state is PostureState.EVIDENCE_UNAVAILABLE
 assert by["IDENTITY-MFA"].state is PostureState.EVIDENCE_UNAVAILABLE
def test_confirmed_gap_creates_proposal_not_change():
 r=build_review(client_id="311",evidence_by_control={"ENDPOINT-ENCRYPTION":[ev(bitlocker_enabled=False)]})
 assert r["counts"]["confirmed_gap"]==1
 assert r["improvement_proposals"][0]["control_id"]=="ENDPOINT-ENCRYPTION"
 assert r["automatic_changes_allowed"] is False
def test_all_observed_values_must_match_baseline():
 rule=next(x for x in AOT_BASELINE if x.control_id=="ENDPOINT-AV")
 a=assess_control(rule,[ev(managed_av_healthy=True),ev(managed_av_healthy=False)])
 assert a.state is PostureState.CONFIRMED_GAP
