"""Read-only proposal for 30-day retention in segmented historical archives.

NEVER deletes or edits a SQLite database, catalog, grant or prod service.
Verified per-file SQLite row counts/hashes must later come from a separately
trusted Root evidence producer; untrusted developer inputs never authorize a
cutover or deletion. Canonical governance exception remains pending.
"""
from __future__ import annotations

from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
import re

ACTION="PURGE-EXACT-ORCHESTRATION-EVENTS-OLDER-THAN-30D"
READER_ACTION="RELEASE-EXACT-AUDIT-READER-HANDLE-CLOSURE"


def need(ok,code):
    if not ok:raise ValueError("AUDIT_30DAY_SEALED_"+code)


def canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def cutoff(now):
    need(isinstance(now,datetime) and now.tzinfo is not None
         and now.utcoffset() is not None,"AWARE_CUTOFF_REQUIRED")
    return (now.astimezone(timezone.utc)-timedelta(days=30)).isoformat()


def draft_segment_plan(*,catalog,statistics,now,source_main_sha,prior_catalog_sha256):
    need(re.fullmatch("[0-9a-f]{40}",source_main_sha or "") is not None,
         "PROTECTED_CANDIDATE_SHA")
    need(re.fullmatch("[0-9a-f]{64}",prior_catalog_sha256 or "") is not None,
         "CATALOG_BEFORE_SHA")
    need(isinstance(catalog,dict) and catalog.get("mode")=="segmented"
         and type(catalog.get("generation")) is int and catalog["generation"]>=1,
         "SEGMENTED_CATALOG_REQUIRED")
    segments=catalog.get("segments")
    need(isinstance(segments,list) and
         all(isinstance(x,dict) and x.get("state")=="sealed" for x in segments),
         "NO_PENDING_SEGMENTS_IN_PURGE")
    need(isinstance(statistics,dict) and len(statistics)==len(segments),
         "EXACT_SEGMENT_STATS_REQUIRED")
    rows=[]
    seen=set()
    for rec in segments:
        name=rec.get("id")
        proof=rec.get("proof",{})
        expected=proof.get("events")
        digest=proof.get("file_sha256")
        need(isinstance(name,str) and re.fullmatch("[0-9a-f]{32}",name)
             and type(expected) is int and expected>=0
             and isinstance(digest,str) and re.fullmatch("[0-9a-f]{64}",digest),
             "SEALED_SEGMENT_PROOF")
        need(name not in seen,"DUPLICATE_SEGMENT_ID")
        seen.add(name)
        actual=statistics.get(name)
        need(isinstance(actual,dict) and
             set(actual)=={"retained","expired","file_sha256"}
             and actual["file_sha256"]==digest
             and type(actual["retained"]) is int and type(actual["expired"]) is int
             and actual["retained"]>=0 and actual["expired"]>=0
             and actual["retained"]+actual["expired"]==expected,
             "UNTRUSTED_EVENT_COUNT_OR_HASH")
        rows.append({
            "segment_id":name,"original_file_sha256":digest,
            "catalog_events":expected,"estimated_expired":actual["expired"],
            "estimated_retained":actual["retained"],
            "required_action":(
                "stage_verified_recent_only_copy_then_root_seal_swap"
                if actual["retained"]>0 and actual["expired"]>0
                else "root_remove_only_after_exact_accepted_proof"
                if actual["expired"]>0
                else "retain_original_unchanged"
            ),
        })
    need(seen==set(statistics),"EXACT_SEGMENT_STATS_REQUIRED")
    proposal={
        "stage":"engineering_proposal_not_authorized",
        "schema_version":"1.0",
        "action":ACTION,
        "not_combined_with":READER_ACTION,
        "source_main_sha":source_main_sha,
        "catalog_before_sha256":prior_catalog_sha256,
        "catalog_generation":catalog["generation"],
        "cutoff_utc":cutoff(now),
        "retention_days":30,
        "target_table":"orchestration_events",
        "source_statistics_are_untrusted_until_independently_verified_by_Root":True,
        "archives":rows,
        "pre_reclaim_gates":[
            "new_governance_retention_exception_ratified",
            "new_exact_independently_authenticated_licensed_Owner_signature",
            "verified_production_freeze_and_breaker_and_drift",
            "exact_hash_and_count_readback_from_each_sealed_archive",
            "all_recent_rows_preserved_with_proven_event_id_parity",
            "no_any_open_archive_handles_or_uncommitted_writes",
            "atomic_catalog_generation_and_recovery_receipt",
            "independent_native_health_and_actual_free_blocks",
        ],
        "out_of_scope":["other_databases","root_approval_ledgers","provider_actions",
                        "unrelated_security_audit_records","network_or_reboot"],
        "approved":False,"production_changed":False,
        "expired_records_deleted":False,
    }
    return {"proposal":proposal,"proposal_sha256":sha256(canonical(proposal)).hexdigest()}


def verify_draft(result):
    p=result["proposal"]
    need(sha256(canonical(p)).hexdigest()==result["proposal_sha256"],
         "PROPOSAL_CHANGED")
    need(p["action"]==ACTION and p["not_combined_with"]==READER_ACTION
         and p["approved"] is False and p["production_changed"] is False
         and p["expired_records_deleted"] is False
         and p["source_statistics_are_untrusted_until_independently_verified_by_Root"] is True,
         "PROPOSAL_CANNOT_APPROVE_DELETION")
    return True
