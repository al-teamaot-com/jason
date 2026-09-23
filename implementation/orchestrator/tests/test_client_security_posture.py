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

def test_healthy_subset_cannot_prove_client_good():
 rule=next(x for x in AOT_BASELINE if x.control_id=="ENDPOINT-AV")
 assert assess_control(rule,[ev(managed_av_healthy=True)]).state is PostureState.UNKNOWN
 assert assess_control(rule,[ev(managed_av_healthy=True)],coverage_complete=True).state is PostureState.CONFIRMED_GOOD
def test_client_binding_requires_exact_autotask_identity():
 import pytest
 with pytest.raises(ValueError): ClientEvidenceBinding("", "XYZ")
def test_unmapped_providers_fail_to_evidence_unavailable():
 b=ClientEvidenceBinding("1158","XYZ Test Company")
 unavailable=set(unavailable_controls_for_binding(b))
 assert "ENDPOINT-AV" in unavailable and "DOCUMENTATION" in unavailable
 assert "BACKUP-SUCCESS" in unavailable and "IDENTITY-MFA" in unavailable
def test_mapped_provider_does_not_claim_control_good_without_observation():
 b=ClientEvidenceBinding("1158","XYZ Test Company",drmm_site_uid="site-1",it_glue_organization_id="org-1")
 r=build_review(client_id=b.autotask_company_id,evidence_by_control={},unavailable_controls=unavailable_controls_for_binding(b))
 by={x.control_id:x for x in r["assessments"]}
 assert by["ENDPOINT-AV"].state is PostureState.UNKNOWN
 assert by["DOCUMENTATION"].state is PostureState.UNKNOWN
 assert by["BACKUP-SUCCESS"].state is PostureState.EVIDENCE_UNAVAILABLE
