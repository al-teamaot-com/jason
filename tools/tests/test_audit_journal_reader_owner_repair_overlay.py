"""Fail-closed immutable adoption of one exact signed reader source repair.

This is a pure fixture; never executes a Root call or edits production files.
"""
import copy
from hashlib import sha256
import json
import pytest
from tools import audit_journal_control as control


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()

def fixture(monkeypatch):
    before={
       'schema_version':'1.0','enabled':True,'maintenance_operations':['rotate','seal','scrub','recover'],
       'trusted_source_sha256':{
           'tools/audit_journal_control.py':'1'*64,
           'implementation/orchestrator/segmented_journal.py':'2'*64,
           'implementation/orchestrator/journal_sql.py':'3'*64},
       'candidate_sha':'a'*40,'old_profile_sha256':'4'*64}
    after=copy.deepcopy(before)
    after['trusted_source_sha256']['tools/audit_journal_control.py']='5'*64
    after['trusted_source_sha256']['implementation/orchestrator/segmented_journal.py']='6'*64
    adoption={'action':control.ACTION,'owner_oid':control.OWNER,
              'independently_verified_entra_owner':True,
              'maintenance_policy_adopted':True,
              'policy_sha256':sha256(canonical(before)).hexdigest()}
    grant={'schema_version':'1.0','action':control.READER_REPAIR_ACTION,
           'owner_oid':control.OWNER,'independently_verified_entra_owner':True,
           'no_legacy_rebuild':True,'provider_calls':0,'root_release_finalized':True,
           'previous_adoption_sha256':sha256(canonical(adoption)).hexdigest(),
           'previous_policy_sha256':sha256(canonical(before)).hexdigest(),
           'new_policy_sha256':sha256(canonical(after)).hexdigest(),
           'source_sha256':{k:after['trusted_source_sha256'][k] for k in sorted(control.READER_REPAIR_FILES)}}
    def mock_read(path,*args):
        if path==control.READER_REPAIR_BEFORE_POLICY:return before
        if path==control.READER_REPAIR_RECEIPT:return grant
        raise AssertionError('unexpected_root_record')
    monkeypatch.setattr(control,'read_control',mock_read)
    return before,after,adoption,grant


def test_exact_immutable_old_adoption_with_one_new_signed_policy(monkeypatch):
    before,after,adoption,grant=fixture(monkeypatch)
    assert control.verified_reader_repair_policy(after,adoption) is None
    assert before['trusted_source_sha256']['tools/audit_journal_control.py']=='1'*64
    assert adoption['policy_sha256']==sha256(canonical(before)).hexdigest()


@pytest.mark.parametrize('field,value',[
    ('owner_oid','other'),('independently_verified_entra_owner',False),
    ('root_release_finalized',False),('no_legacy_rebuild',False),
    ('provider_calls',1),('action','UNREVIEWED'),
    ('new_policy_sha256','0'*64),('previous_adoption_sha256','0'*64),
    ('previous_policy_sha256','0'*64),('source_sha256',{})])
def test_tampered_or_unapproved_root_grant_denied(monkeypatch,field,value):
    before,after,adoption,grant=fixture(monkeypatch)
    grant[field]=value
    with pytest.raises(Exception,match='JOURNAL_READER_REPAIR_EXACT_OWNER_POLICY_REQUIRED'):
        control.verified_reader_repair_policy(after,adoption)


def test_new_policy_cannot_smuggle_additional_changes(monkeypatch):
    before,after,adoption,grant=fixture(monkeypatch)
    for key,value in [('candidate_sha','b'*40),('maintenance_operations',[]),('extra_production_flag',True)]:
        modified=copy.deepcopy(after);modified[key]=value
        grant['new_policy_sha256']=sha256(canonical(modified)).hexdigest()
        with pytest.raises(Exception,match='JOURNAL_READER_REPAIR_EXACT_OWNER_POLICY_REQUIRED'):
            control.verified_reader_repair_policy(modified,adoption)


def test_only_two_exact_predeclared_trusted_sources_may_change(monkeypatch):
    before,after,adoption,grant=fixture(monkeypatch)
    modified=copy.deepcopy(after)
    modified['trusted_source_sha256']['implementation/orchestrator/journal_sql.py']='7'*64
    grant['new_policy_sha256']=sha256(canonical(modified)).hexdigest()
    with pytest.raises(Exception,match='JOURNAL_READER_REPAIR_EXACT_OWNER_POLICY_REQUIRED'):
        control.verified_reader_repair_policy(modified,adoption)
