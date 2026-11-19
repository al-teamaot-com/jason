from copy import deepcopy
import pytest
from tools.scoped_backport_unit_drift_evidence import validate, DriftEvidenceDenied, UNITS, ROOT_HANDLER_SHA, SOURCE_SHA, REVIEWED_SHA


def fixture():
 a={'profile':'governed-scoped-backport-v1','trusted_source_sha':SOURCE_SHA,'reviewed_ci_sha':REVIEWED_SHA,'root_handler_sha256':ROOT_HANDLER_SHA,'exact_signed_owner_approval_required':True,'native_root_control_supported':True}
 h={**UNITS,'root_handler':ROOT_HANDLER_SHA}
 d={'status':'drift_detected','problems':[{'kind':'undeclared_installed_system_unit','unit':u} for u in UNITS]}
 p={'schema_version':'1.0','allowed_system_units':list(UNITS)}
 return a,h,d,p

def test_exact_four_unit_root_installed_source_attestation_only():
 report=validate(*fixture())
 assert report['unit_count']==4 and report['production_mutations'] is False
 assert report['root_protected_policy_readback_verified'] is False
 assert report['signed_owner_action_consumed'] is False
 assert report['native_breaker_revalidated'] is False

@pytest.mark.parametrize('which,field,value',[
 (0,'trusted_source_sha','unapproved'),(0,'root_handler_sha256','unapproved'),(0,'exact_signed_owner_approval_required',False),
 (1,'jason-scoped-backport-recovery.timer','tampered'),
 (1,'root_handler','tampered'),
 (2,'status','pass'),(3,'allowed_system_units',[]),
])
def test_tamper_or_missing_declaration_denied(which,field,value):
 args=list(deepcopy(fixture()));args[which][field]=value
 with pytest.raises(DriftEvidenceDenied):validate(*args)

def test_unrelated_fifth_unit_denied():
 a,h,d,p=deepcopy(fixture())
 d['problems'].append({'kind':'undeclared_installed_system_unit','unit':'jason-other.service'})
 with pytest.raises(DriftEvidenceDenied,match='UNRELATED_DRIFT'):validate(a,h,d,p)

def test_wrong_reason_even_for_one_matching_unit_denied():
 a,h,d,p=deepcopy(fixture());d['problems'][0]['kind']='failed_system_unit'
 with pytest.raises(DriftEvidenceDenied,match='UNRELATED_DRIFT'):validate(a,h,d,p)
