from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from tools.ticket_continuity_evidence_review import evaluate, REQUIRED_SURFACES

NOW = datetime(2026,11,4,15,0,tzinfo=timezone.utc)
D='sha256:'+'d'*64

def good():
    base=NOW-timedelta(minutes=15)
    return {
      'schema_version':'1.0','candidate_sha':'a'*40,'rollback_sha':'b'*40,
      'controlled_test_ticket':{'ticket_id':123,'company_id':222,'test_company':True},
      'baseline':{'observed_at':base.isoformat(),'ticket_id':123,'company_id':222,
                  'queue_id':3,'status_id':2,'notes_count':4,'runtime_healthy':True,'mcp_read_available':True},
      'governed_test_action':{'ticket_id':123,'company_id':222,'candidate_sha':'a'*40,
          'provider':'autotask','status':'readback_verified','field':'status',
          'before_value':2,'requested_value':3,'readback_value':3,
          'owner_approval_evidence_sha256':D,'governed_write_receipt_sha256':D,
          'governed_readback_receipt_sha256':D,'write_correlation_id':'test-trace-123'},
      'postchange_observations':[
        {'observed_at':(NOW-timedelta(minutes=n)).isoformat(),
         'ticket_id':123,'company_id':222,'notes_count':4,
         'runtime_healthy':True,'mcp_read_available':True,'duplicate_claims':0,
         'lost_intake_items':0,'governed_readback_verified':True,
         'verified_surfaces':{key:True for key in REQUIRED_SURFACES},'evidence_sha256':D}
         for n in [8,3]],
      'source_mutation_performed_by_shadow_services':False}

def test_structurally_complete_receipts_only_request_native_review():
    result=evaluate(good(),now=NOW)
    assert result['status']=='evidence_review_required'
    assert result['advisory_only'] and not result['production_authority']
    assert result['native_provider_reverification_required'] is True
    assert result['cycle_count']==2

def test_missing_mutation_or_approval_does_not_certify():
    data=good();data['governed_test_action'].pop('owner_approval_evidence_sha256')
    result=evaluate(data,now=NOW)
    assert result['status']=='blocked'
    assert 'action_owner_approval_evidence_sha256_invalid' in result['reason_codes']

def test_missing_ticket_surface_blocks_cutover():
    data=good();data['postchange_observations'][1]['verified_surfaces']['alert_ticket_routing']=False
    assert evaluate(data,now=NOW)['status']=='blocked'

def test_duplicate_claim_or_lost_ticket_blocks_cutover():
    for field in ('duplicate_claims','lost_intake_items'):
        data=good();data['postchange_observations'][0][field]=1
        assert evaluate(data,now=NOW)['status']=='blocked'

def test_unverified_notes_and_runtime_are_no_go():
    for field in ('notes_count','runtime_healthy','governed_readback_verified'):
        data=good()
        data['postchange_observations'][0][field]= 0 if field=='notes_count' else False
        assert evaluate(data,now=NOW)['status']=='blocked'

def test_two_distinct_cycles_required():
    data=good();data['postchange_observations'][1]['observed_at']=data['postchange_observations'][0]['observed_at']
    assert 'observation_cycles_not_independent' in evaluate(data,now=NOW)['reason_codes']

def test_ticket_identity_mismatch_blocks():
    data=good();data['postchange_observations'][0]['ticket_id']=124
    assert evaluate(data,now=NOW)['status']=='blocked'

def test_expired_and_future_evidence_blocks():
    data=good();data['baseline']['observed_at']=(NOW-timedelta(hours=5)).isoformat()
    assert evaluate(data,now=NOW)['status']=='blocked'
    data=good();data['postchange_observations'][0]['observed_at']=(NOW+timedelta(minutes=4)).isoformat()
    assert evaluate(data,now=NOW)['status']=='blocked'

def test_shadow_mutation_never_allowed():
    data=good();data['source_mutation_performed_by_shadow_services']=True
    assert evaluate(data,now=NOW)['status']=='blocked'


def test_malformed_baseline_and_boolean_ticket_ids_fail_closed():
    data=good();data['baseline']['notes_count']='unexpected'
    assert evaluate(data,now=NOW)['status']=='blocked'
    data=good();data['controlled_test_ticket']['ticket_id']=True
    assert evaluate(data,now=NOW)['status']=='blocked'
