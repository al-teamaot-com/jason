"""Source-only native policy reconciliation invariants; no root host writes."""
import json
import pytest
from tools import scoped_backport_unit_drift_reconcile_root as root
from tools import scoped_backport_unit_drift_evidence as evidence


def baseline():
 return {'schema_version':'1.0','allowed_system_units':['jason-core.service','jason-provider-health-canary.service'],'max_stopped_rollback_containers':20}


def test_exact_four_installed_root_units_are_bound_to_source():
 assert set(root.CANDIDATE_NAMES)==set(evidence.UNITS)
 assert root.EXPECTED_UNITS==evidence.UNITS
 assert root.INSTALL_SOURCE==evidence.SOURCE_SHA
 assert root.ROOT_INSTALLED.as_posix().startswith('/etc/jason-owner-release/')
 assert root.ACTION=='scoped-backport-four-unit-drift-policy-reconcile-v1'


def test_candidate_policy_adds_exactly_four_and_no_wildcards():
 a=baseline();changed=root.expected_policy(json.dumps(a).encode())
 assert changed['allowed_system_units']==sorted(a['allowed_system_units']+list(root.CANDIDATE_NAMES))
 assert changed['schema_version']=='1.0'
 assert changed['max_stopped_rollback_containers']==20
 assert set(changed)==set(a)


def test_idempotent_replay_cannot_extend_already_reconciled_root_policy():
 m=root.expected_policy(json.dumps(baseline()).encode())
 with pytest.raises(root.ScopedBackportDriftDenied):
  root.expected_policy(json.dumps(m).encode())


def test_invalid_baseline_or_rollback_cap_fail_closed():
 for obj in ({'schema_version':'2.0','allowed_system_units':[],'max_stopped_rollback_containers':20},
             {'schema_version':'1.0','allowed_system_units':[],'max_stopped_rollback_containers':100},
             {'schema_version':'1.0','allowed_system_units':['a','a'],'max_stopped_rollback_containers':20}):
  with pytest.raises(root.ScopedBackportDriftDenied):root.expected_policy(json.dumps(obj).encode())


def test_signed_owner_proof_is_restricted_to_the_licensed_jason_owner():
 source=__import__('inspect').getsource(root.verified_owner)
 assert 'bee80bdc-ffb0-4c50-b453-c09d4d411f5f' in source
 assert 'person-entra-bee80bdcffb04c50b453c09d4d411f5f' in source
 assert 'EXACT_LICENSED_JASON_OWNER_SIGNATURE_REQUIRED' in source
