"""Produce source-bound, fail-closed JSON *drafts* for unconverted legacy flows.

These are NON-EXECUTABLE migration design candidates; they are not parity
migrations. Reuse the real v1 schema/validator and existing registry, never
instantiate a second runbook engine or mint execution authority. Unknown
provider argument shape and custom workflow logic remain explicit gaps.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from implementation.autonomous_remediation.playbook_document import (
    validate_playbook_document,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "implementation/autonomous_remediation/playbook_registry.json"
AUDIT = ROOT / "docs/playbooks/json/migration/source-audit-20261119.json"
SNAPSHOT = ROOT / "docs/playbooks/json/migration/live-capability-snapshot-20261119.json"
OUTPUT = ROOT / "docs/playbooks/json/migration/drafts"
ALREADY_DETAILED = frozenset({
    "unsupported_readonly_triage_note",
    "unsupported_triage_human_review",
    "drmm_recent_alert_reconciliation",
    "windows_time_source",
    "offline_ticket_context_augmentation",
    "jason_activity_log",
    "gpt_insights_tech_assist",
    "unexpected_shutdown",
    "client_information_request",
})


# One explicit initial governed-read, diagnostic read, and authoritative
# verification read per legacy playbook. All names must be active in the
# independently recorded live Jason capability catalog.
#
# First-stage structured drafts keep branches/procedures available for
# conversion review but intentionally do not implement complex fanout,
# provider-output normalization, exact approval policy, or all remediation.
WORKFLOWS = {
    "backupiq_endpoint_backup": {
        "entry": "service.ticket.search", "diagnose": "backup.endpoint.asset.search",
        "verify": "backup.endpoint.backup.search", "action": "automation.component.execute",
        "clean": "new_backup_verified", "repair": "agent_reinstall_authorized",
        "wait": "waiting_for_new_successful_backup",
        "missing": ["exact cross-provider BackupIQ asset identity", "24h/2h recheck and provider backup outcome correlation", "one-time approved installer job with exact idempotency", "ticket lifecycle and release-slot persistence"],
    },
    "datto_edr_av": {
        "entry": "service.ticket.search", "diagnose": "endpoint.security.status.read",
        "verify": "endpoint.security.status.read", "action": "automation.component.execute",
        "clean": "verified_product_and_security_healthy", "repair": "approved_bounded_health_repair",
        "wait": "reboot_approval_or_device_wait",
        "missing": ["Python security classifier and cross-provider threat posture", "bounded job continuation and exact approved component arguments", "per-run reboot authorization and 03:30 recheck", "security-incident independent verification and closure"],
    },
    "disk_bad_block_event_7": {
        "entry": "service.ticket.search", "diagnose": "endpoint.alert.history.search",
        "verify": "endpoint.alert.history.search", "action": None,
        "clean": "removable_classification_verified_no_open_alert",
        "repair": "exact_removable_media_alert_resolution_approved",
        "wait": "waiting_approved_storage_diagnostic",
        "missing": ["authoritative HarddiskX physical-model bus map and SMART evidence", "read-only component-control diagnostics and job persistence", "internal-disk note/escalation and approved client notification", "exact Autotask notes/ticket closing and post-write readback"],
    },
    "dns_agent_diagnostic": {
        "entry": "service.ticket.search", "diagnose": "endpoint.software.search",
        "verify": "endpoint.alert.search", "action": "automation.component.execute",
        "clean": "dnsfilter_health_verified", "repair": "approved_bounded_dnsfilter_install_or_reinstall",
        "wait": "waiting_endpoint_or_job",
        "missing": ["native DNSFilter site/agent corroboration and policy-specific exclusions", "approved diagnostic-vs-remediation component selection", "bounded execution and job-output state", "DNS and service stability interval before exact alert/ticket closure"],
    },
    "idle_log_off": {
        "entry": "service.ticket.search", "diagnose": "endpoint.alert.search",
        "verify": "endpoint.alert.search", "action": "automation.component.execute",
        "clean": "policy_compliance_proven", "repair": "approved_setter_component_required",
        "wait": "waiting_idletime_monitor_recheck",
        "missing": ["workstation/site policy scope and approved setter fingerprint", "component terminal job/StdErr bound verification", "post-job monitor propagation and stable observation", "exact alert/ticket completion and output provenance"],
    },
    "low_disk_space": {
        "entry": "service.ticket.search", "diagnose": "endpoint.audit.read",
        "verify": "endpoint.audit.read", "action": "automation.component.execute",
        "clean": "free_space_and_alert_recovered",
        "repair": "approved_bounded_cleanup_warranted",
        "wait": "waiting_monitor_propagation_or_device",
        "missing": ["protected server/workstation role and volume eligibility", "safe file/object allowlist and dry-run candidate collection", "bounded cleanup component arguments and job state", "independent post-cleanup disk/monitor and ticket readback"],
    },
    "post_error_investigation": {
        "entry": "service.ticket.search", "diagnose": "endpoint.alert.history.search",
        "verify": "endpoint.alert.history.search", "action": None,
        "clean": "isolated_healthy_post_alert_already_resolved",
        "repair": "isolated_workstation_exact_post_alert_resolution",
        "wait": "waiting_current_health_evidence",
        "missing": ["WHEA/storage/BSOD recurrence and protected hypervisor detection", "exact alert resolution evidence and negative hardware-risk classification", "follow-up Autotask internal-note and ticket closure", "role-specific protected human-review escalation"],
    },
    "security_log_self_heal": {
        "entry": "service.ticket.search", "diagnose": "endpoint.alert.search",
        "verify": "endpoint.alert.history.search", "action": "automation.component.execute",
        "clean": "security_event_log_healthy",
        "repair": "approved_security_log_self_heal_needed",
        "wait": "waiting_healthy_quick_test_or_job",
        "missing": ["read-only Quick Test component and job-output parser", "one time sensitive event-log mutation with SOC authorization", "independent repeated Quick Test and exact alert closure", "same-device/time/technique side-effect ticket correlation"],
    },
    "vulscan_missing_patch": {
        "entry": "service.ticket.search", "diagnose": "endpoint.patch.search",
        "verify": "endpoint.patch.search", "action": None,
        "clean": "exact_kb_installed_or_superseded",
        "repair": "approved_patch_stack_repair_warranted",
        "wait": "waiting_normal_patch_window_or_approval",
        "missing": ["exact KB approval/window and device-patch identity", "multi-device ticket split prerequisite", "user impact/reboot approval and bounded WU repair flags", "exact KB/build/supersedence and ticket verification"],
    },
    "vulscan_multi_device_split": {
        "entry": "service.ticket.search", "diagnose": "service.configuration.search",
        "verify": "service.ticket.search", "action": "service.ticket.create",
        "clean": "all_exact_child_tickets_already_exist",
        "repair": "all_nodes_same_company_resolved_and_split_approved",
        "wait": "waiting_source_split_reconciliation",
        "missing": ["bounded Affected Nodes parser and exact CI/DRMM lookup", "multi-child fanout and idempotent create receipts", "one-device child lineage and source completion", "source work ownership and post-write readback"],
    },
}


def _fact(name: str) -> dict[str, str]:
    return {"$fact": name}


def _read(step_id: str, capability: str, args: dict, next_step: str) -> dict:
    return {"id": step_id, "type": "diagnostic", "capability": capability,
            "arguments": args, "next": next_step}


def _decision(step_id: str, fact: str, alternatives: list[tuple[object, str]],
              default: str) -> dict:
    return {
        "id": step_id, "type": "decision",
        "branches": [{"when": {"fact": fact, "operator": "eq", "value": value},
                      "next": target} for value, target in alternatives],
        "default": default,
    }


def _verification(step_id: str, capability: str, next_step: str) -> dict:
    return {
        "id": step_id, "type": "verification", "capability": capability,
        "arguments": _fact("server_verified_post_action_read_arguments"),
        "next": next_step,
    }


def build_one(row: dict, audit: dict, snapshot: set[str]) -> dict:
    identifier = row["id"]
    item = WORKFLOWS[identifier]
    caps = [item[k] for k in ("entry", "diagnose", "verify", "action") if item[k]]
    unavailable = sorted(set(caps) - snapshot)
    if unavailable:
        raise ValueError(f"{identifier}:UNREGISTERED_CAPABILITIES:{unavailable}")
    entry_args = (
        {"status": "open"} if item["entry"] == "management.alert.search" else
        {"ticket_id": _fact("ticket_id")} if item["entry"] == "service.ticket.read" else
        {"resource_id": _fact("ticket_id"), "page_size": 2}
    )
    steps = [
        _read("read_target", item["entry"], entry_args, "scope_gate"),
        _decision("scope_gate", "authoritative_same_client_scope_proven",
                  [(True, "read_diagnostic")], "human_review"),
        _read("read_diagnostic", item["diagnose"],
              _fact("server_verified_diagnostic_read_arguments"), "classification_gate"),
        _decision("classification_gate", "verified_legacy_disposition", [
            (item["clean"], "verified_no_action_gate"),
            (item["repair"], "exact_authority_gate" if item["action"] else "human_review"),
            (item["wait"], "wait_for_source"),
        ], "human_review"),
        _decision("verified_no_action_gate", "authoritative_healthy_state_proven",
                  [(True, "read_only_complete")], "human_review"),
        _decision("exact_authority_gate", "exact_owner_promotion_verified",
                  [(True, "approved_action_args_gate")], "human_review"),
        _decision("approved_action_args_gate", "server_action_arguments_exact_and_authorized",
                  [(True, "propose_approved_action")], "human_review"),
        {
            "id": "propose_approved_action",
            "type": "remediation" if item["action"] else "human_review",
            **({"capability": item["action"],
                "arguments": _fact("server_verified_exact_action_arguments"),
                "approval_classification": "modifying",
                "approval_required": True,
                "retry": {"max_attempts": 1},
                "verification_step": "read_independent_verification"}
               if item["action"] else {}),
        },
        _verification("read_independent_verification", item["verify"],
                      "independent_verification_gate"),
        _decision("independent_verification_gate",
                  "authoritative_post_action_health_and_readback_proven",
                  [(True, "remediation_verified")], "human_review"),
        {"id": "read_only_complete", "type": "complete"},
        {"id": "remediation_verified", "type": "complete"},
        {"id": "wait_for_source", "type": "wait", "seconds": 3600,
         "resume": "bounded_wait_terminal"},
        {"id": "bounded_wait_terminal", "type": "human_review"},
        {"id": "human_review", "type": "human_review"},
    ]
    if item["action"] is None:
        # Original authoritative registry denies the requested mutation.
        # Remove the entire unreachable action chain (rather than leaving
        # phantom executable capabilities in an inactive JSON artifact).
        blocked_action_steps = {
            "exact_authority_gate", "approved_action_args_gate",
            "propose_approved_action", "read_independent_verification",
            "independent_verification_gate", "remediation_verified",
        }
        steps = [step for step in steps
                 if step["id"] not in blocked_action_steps]
    version = str(row["version"]) + "-migration.1"
    # The legacy registry does not carry target_type. Preserve an explicit
    # declaration from the source; where absent, use a narrowly reviewed
    # fallback and mark it as an unresolved source mapping in metadata.
    source_content = (ROOT / row["source"]).read_text()
    declared = re.search(
        r"(?m)^\s*target_type:\s*(ticket|endpoint|user|site|service|provider_object)\s*$",
        source_content[:1800],
    )
    fallback = (
        "provider_object" if identifier == "windows_time_source" else
        "endpoint" if identifier in {
            "backupiq_endpoint_backup", "datto_edr_av",
            "disk_bad_block_event_7", "dns_agent_diagnostic",
            "idle_log_off", "security_log_self_heal",
        } else "ticket"
    )
    target_type = declared.group(1) if declared else fallback
    doc = {
        "schema_version": 1,
        "playbook": {
            "id": identifier, "name": str(row["name"]),
            "version": version, "lifecycle": "pilot",
            "target_type": target_type,
            "owner": row.get("owner", "AOT"),
            "source": row["source"],
        },
        "trigger": {
            "legacy_registry_entry": identifier,
            "source_version": row["version"],
            "runtime_filter_integration": "NOT_COMPLETE",
        },
        "scope": {
            "direct_provider_access": False,
            "source_only": True,
            "no_production_activation": True,
            "any_unsupported_branch": "human_review",
        },
        "expected_state": {
            "documented_section": "legacy source section 5",
            "actual_health_requires_authoritative_provider_readback": True,
        },
        "state_model": {
            "entry_step": "read_target",
            "legacy_wait_retry_semantics": "UNMAPPED_BLOCKING",
            "must_resume_without_mutation_replay": True,
        },
        "steps": steps,
        "verification": {
            "authoritative_source": item["verify"],
            "success_condition": "exact same-client healthy state independently proven; all writes separately authorized and read back",
        },
        "completion": {
            "terminal_disposition": "source-only candidate; unsupported or unverified branches remain human review, not ticket closure",
        },
        "autonomy": {
            "activation": "shadow",
            "allowed_capabilities": sorted(set(caps)),
            "disruptive_branches": [],
            "approval_bound_branches": (["propose_approved_action"] if item["action"] else []),
        },
        "migration": {
            "source_conversion": "structural_partial_not_accepted",
            "accepted_for_execution": False,
            "legacy_source_blob_sha": audit["source_git_blob_sha"],
            "legacy_source_sha256": audit["source_sha256"],
            "legacy_registry_version": row["version"],
            "source_map": f"docs/playbooks/json/migration/source_maps/{identifier}.source-map.json",
            "behavior_branches_mapped": {
                "healthy": item["clean"],
                "one_approved_action": item["repair"],
                "waiting": item["wait"],
                "all_else": "human_review",
            },
            "missing_or_unimplemented_parity": item["missing"] + (
                ["Legacy registry does not authorize the requested mutation; this action is blocked pending separately governed source correction and authority."]
                if item["action"] is None else []
            ),
            "additional_required_compatibility": [
                "trusted provider result-to-fact normalizer for each step",
                "exact capability argument schema and approved source identity",
                "all original documented state transitions, dedup/retries, job polls and provider readbacks",
                "per-playbook legacy-vs-JSON positive/negative/approval/recovery parity",
                "isolated shadow acceptance with actual governed read-port binding",
            ],
            "production_activation_authorized": False,
        },
    }
    known = set(snapshot)
    validate_playbook_document(doc, known_capabilities=known)
    return doc


def build() -> dict[str, dict]:
    registry = json.loads(REGISTRY.read_text())
    audits = {x["id"]: x for x in json.loads(AUDIT.read_text())["entries"]}
    catalog = json.loads(SNAPSHOT.read_text())
    snapshot = {x["name"] for x in catalog["items"] if x["lifecycle"] == "active"}
    expected = {p["id"] for p in registry["playbooks"] if p["enabled"]} - ALREADY_DETAILED
    if set(WORKFLOWS) != expected:
        raise ValueError(f"INVENTORY_SCOPE_MISMATCH missing={expected - set(WORKFLOWS)} extras={set(WORKFLOWS) - expected}")
    return {
        identifier: build_one(next(x for x in registry["playbooks"] if x["id"] == identifier),
                              audits[identifier], snapshot)
        for identifier in sorted(WORKFLOWS)
    }


def publish() -> dict[str, dict]:
    docs = build()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for identifier, doc in docs.items():
        path = OUTPUT / f"{identifier}.v1.json"
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return docs


if __name__ == "__main__":
    documents = publish()
    print(f"partial_declarative_drafts={len(documents)} status=NOT_ACCEPTED")
    print("No provider calls, registry staging, playbook activation or release.")
