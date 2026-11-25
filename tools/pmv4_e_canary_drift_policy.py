#!/usr/bin/env python3
"""Pure exact canary drift-policy plan; zero installed root policy mutations.

One approved canary name is added only to allowed_running_containers,
preserving all other protected keys. Full byte-exact rollback is required
after removing the canary. No breaker, watchdog or freeze bypass.
"""
from __future__ import annotations

import copy
from hashlib import sha256
import json
from typing import Any

from tools import pmv4_e_canary_contract as canary


class CanaryDriftPolicyDenied(PermissionError):
    pass


def need(ok:bool,code:str)->None:
    if not ok:
        raise CanaryDriftPolicyDenied("PMV4_E_CANARY_POLICY_"+code)


def canonical(doc:dict[str,Any])->bytes:
    return json.dumps(doc,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def candidate(*,root_policy_bytes:bytes,expected_before_sha256:str)->dict[str,Any]:
    """Build exact old/new bytes; deploy only after separately approved root action."""
    need(type(root_policy_bytes) is bytes
         and 0<len(root_policy_bytes)<100_000,
         "SOURCE_NOT_TRUSTED_BYTES")
    prior_hash=sha256(root_policy_bytes).hexdigest()
    need(type(expected_before_sha256) is str
         and prior_hash==expected_before_sha256,
         "ROOT_POLICY_BASELINE_SHA_CHANGED")
    try:
        original=json.loads(root_policy_bytes)
    except (ValueError,UnicodeError) as exc:
        raise CanaryDriftPolicyDenied(
            "PMV4_E_CANARY_POLICY_INVALID_JSON") from exc
    need(isinstance(original,dict) and original.get("schema_version")=="1.0",
         "ROOT_POLICY_SCHEMA_UNTRUSTED")
    names=original.get("allowed_running_containers")
    need(isinstance(names,list)
         and all(isinstance(n,str) and n for n in names)
         and len(set(names))==len(names),
         "ALLOWED_CONTAINERS_NOT_EXACT_LIST")
    need(canary.CANARY_CONTAINER_NAME not in names,
         "CANARY_ALREADY_DECLARED")
    required=original.get("required_containers") or []
    need(isinstance(required,list)
         and "jason-runtime" in required and "jason-mcp-pilot" in required,
         "PROTECTED_CORE_NOT_REQUIRED")
    need("jason-runtime" in names and "jason-mcp-pilot" in names,
         "PROTECTED_CORE_NOT_ALLOWED")
    need("jason-pmv4-ticket-core" in names
         and "jason-pmv4-shadow-gateway" in names,
         "ACCEPTED_PMV4_BASELINE_NOT_PINNED")
    updated=copy.deepcopy(original)
    updated["allowed_running_containers"]=[
        *names,canary.CANARY_CONTAINER_NAME]
    new=canonical(updated)+b"\n"
    need(set(updated)==set(original)
         and all(updated[k]==original[k]
                 for k in original if k!="allowed_running_containers")
         and set(updated["allowed_running_containers"])-
                 set(original["allowed_running_containers"])==
                    {canary.CANARY_CONTAINER_NAME},
         "PROTECTED_POLICY_SCOPE_ESCALATION")
    return {
        "status":"source_only_no_root_mutation",
        "canary_container_name":canary.CANARY_CONTAINER_NAME,
        "original_policy_sha256":prior_hash,
        "candidate_policy_sha256":sha256(new).hexdigest(),
        "new_policy_bytes":new,
        "rollback_policy_bytes":root_policy_bytes,
        "revert_only_after_canary_absent":True,
        "production_mutations":False,
        "breaker_overridden":False,
        "watchdog_disabled":False,
        "source_deployment_authorized":False,
    }


def rollback(*,candidate_policy_bytes:bytes,
             expected_candidate_sha256:str,
             original_policy_bytes:bytes,
             expected_original_sha256:str,
             verified_canary_absent:bool)->bytes:
    """Policy rollback is denied while the canary is still running or unknown."""
    need(verified_canary_absent is True,
         "CANNOT_REMOVE_ALLOWANCE_WITH_RUNNING_CANARY")
    verified=candidate(
        root_policy_bytes=original_policy_bytes,
        expected_before_sha256=expected_original_sha256,
    )
    need(verified["candidate_policy_sha256"]==expected_candidate_sha256
         and candidate_policy_bytes==verified["new_policy_bytes"],
         "PROTECTED_POSTINSTALL_POLICY_CHANGED")
    return verified["rollback_policy_bytes"]
