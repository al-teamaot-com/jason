"""Pure protected desired-state pre/post policy, no daemon or root writes."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools import pmv4_e_canary_drift_policy as policy
from tools import pmv4_e_canary_contract as canary

BASE=Path(__file__).resolve().parents[1]/"config/production-desired-state.json"


def trusted_prior():
    source=json.loads(BASE.read_bytes())
    # This is a SYNTHETIC reconstruction for tests, not a purported read
    # of protected root policy. Root execution must independently verify
    # the exact live protected bytes and their expected SHA fingerprint.
    source["allowed_running_containers"]=[
        *source["allowed_running_containers"],
        *[name for name in ("jason-pmv4-ticket-core",
                           "jason-pmv4-shadow-gateway")
          if name not in source["allowed_running_containers"]],
    ]
    raw=json.dumps(source,sort_keys=True,indent=2).encode()+b"\n"
    return raw


def test_canary_allowance_is_exact_and_reversible():
    old=trusted_prior()
    baseline=sha256(old).hexdigest()
    plan=policy.candidate(
        root_policy_bytes=old,expected_before_sha256=baseline)
    assert plan["status"]=="source_only_no_root_mutation"
    assert plan["production_mutations"] is False
    assert plan["breaker_overridden"] is False
    assert plan["watchdog_disabled"] is False
    assert plan["source_deployment_authorized"] is False
    assert plan["rollback_policy_bytes"]==old
    before=json.loads(old)
    after=json.loads(plan["new_policy_bytes"])
    assert set(after)==set(before)
    assert all(after[k]==before[k]
               for k in before if k!="allowed_running_containers")
    assert after["allowed_running_containers"]==[
        *before["allowed_running_containers"],
        canary.CANARY_CONTAINER_NAME,
    ]
    restored=policy.rollback(
        candidate_policy_bytes=plan["new_policy_bytes"],
        expected_candidate_sha256=plan["candidate_policy_sha256"],
        original_policy_bytes=old,
        expected_original_sha256=baseline,
        verified_canary_absent=True)
    assert restored==old


def test_untrusted_base_hash_blocks_policy_staging():
    old=trusted_prior()
    with pytest.raises(policy.CanaryDriftPolicyDenied,
                       match="ROOT_POLICY_BASELINE_SHA_CHANGED"):
        policy.candidate(
            root_policy_bytes=old,expected_before_sha256="a"*64)


def test_already_allowlisted_canary_denied_not_overlaid():
    old=json.loads(trusted_prior())
    old["allowed_running_containers"].append(canary.CANARY_CONTAINER_NAME)
    raw=json.dumps(old).encode()
    with pytest.raises(policy.CanaryDriftPolicyDenied,
                       match="CANARY_ALREADY_DECLARED"):
        policy.candidate(
            root_policy_bytes=raw,
            expected_before_sha256=sha256(raw).hexdigest())


def test_fake_protected_base_missing_stable_ticket_core_denied():
    old=json.loads(trusted_prior())
    old["allowed_running_containers"].remove("jason-pmv4-ticket-core")
    raw=json.dumps(old).encode()
    with pytest.raises(policy.CanaryDriftPolicyDenied,
                       match="ACCEPTED_PMV4_BASELINE_NOT_PINNED"):
        policy.candidate(
            root_policy_bytes=raw,expected_before_sha256=sha256(raw).hexdigest())


def test_removing_approved_allowance_while_canary_running_denied():
    old=trusted_prior()
    plan=policy.candidate(root_policy_bytes=old,
        expected_before_sha256=sha256(old).hexdigest())
    with pytest.raises(policy.CanaryDriftPolicyDenied,
                       match="CANNOT_REMOVE_ALLOWANCE_WITH_RUNNING_CANARY"):
        policy.rollback(
            candidate_policy_bytes=plan["new_policy_bytes"],
            expected_candidate_sha256=plan["candidate_policy_sha256"],
            original_policy_bytes=old,
            expected_original_sha256=sha256(old).hexdigest(),
            verified_canary_absent=False)


def test_unrelated_root_policy_change_blocks_rollback():
    old=trusted_prior()
    plan=policy.candidate(root_policy_bytes=old,
        expected_before_sha256=sha256(old).hexdigest())
    new=json.loads(plan["new_policy_bytes"])
    new["required_system_units"].append("jason-new-unknown.service")
    changed=json.dumps(new).encode()
    with pytest.raises(policy.CanaryDriftPolicyDenied,
                       match="PROTECTED_POSTINSTALL_POLICY_CHANGED"):
        policy.rollback(
            candidate_policy_bytes=changed,
            expected_candidate_sha256=plan["candidate_policy_sha256"],
            original_policy_bytes=old,
            expected_original_sha256=sha256(old).hexdigest(),
            verified_canary_absent=True)


def test_protected_core_must_remain_in_policy():
    old=json.loads(trusted_prior())
    old["required_containers"].remove("jason-runtime")
    raw=json.dumps(old).encode()
    with pytest.raises(policy.CanaryDriftPolicyDenied,
                       match="PROTECTED_CORE_NOT_REQUIRED"):
        policy.candidate(
            root_policy_bytes=raw,
            expected_before_sha256=sha256(raw).hexdigest())


def test_duplicate_or_malformed_allowlist_denied():
    old=json.loads(trusted_prior())
    old["allowed_running_containers"].append("jason-runtime")
    raw=json.dumps(old).encode()
    with pytest.raises(policy.CanaryDriftPolicyDenied,
                       match="ALLOWED_CONTAINERS_NOT_EXACT_LIST"):
        policy.candidate(root_policy_bytes=raw,
            expected_before_sha256=sha256(raw).hexdigest())


def test_canary_drift_policy_source_never_disables_safety_controls():
    text=Path(policy.__file__).read_text()
    for bad in ("systemctl stop", "systemctl disable",
                "breaker_override", "disable_watchdog", "docker run",
                "os.chown", "os.unlink", "subprocess.run"):
        assert bad not in text
    assert "revert_only_after_canary_absent" in text
    assert '"production_mutations":False' in text
