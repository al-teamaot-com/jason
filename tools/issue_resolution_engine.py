#!/usr/bin/env python3
"""Outcome-oriented issue correlation and repair governance for Jason self-heal.

This module turns detector symptoms into a small set of operational incidents.
It deliberately separates four questions:
1. Which invariant is actually violated?
2. Which symptoms belong to the same root incident?
3. How much autonomous repair authority is safe?
4. What must be re-verified before the incident can close?
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"

FAMILY_TITLES = {
    "production_convergence": "Production convergence incomplete",
    "runtime_health": "Jason runtime health degraded",
    "provider_health": "Provider health degraded",
    "ticket_admission": "Ticket admission outcome degraded",
    "operational_outcome": "Operational outcome contract incomplete",
    "service_health": "Jason service health degraded",
    "unknown": "Jason operational invariant degraded",
}

ROOT_INVARIANTS = {
    "production_convergence": (
        "runtime SHA = MCP SHA = active host release SHA = installed scheduled-artifact SHA "
        "and all production timers/watchers required by that release are active"
    ),
    "runtime_health": "Jason runtime and MCP are reachable, healthy, and internally functional",
    "provider_health": (
        "enabled provider canaries are fresh and healthy, or expose a specific governed blocker"
    ),
    "ticket_admission": (
        "eligible support work is reviewed/admitted or has a durable, explicit reason it was not selected"
    ),
    "operational_outcome": (
        "every promised operational outcome reaches verified, failed-with-evidence, or a real external blocker by its deadline"
    ),
    "service_health": "required Jason services and scheduled workers are not failed or silently stale",
    "unknown": "the affected already-approved Jason function is restored and independently re-verified",
}

RELATED_FAMILIES = {
    "production_convergence": ["production_convergence", "runtime_health", "service_health"],
    "runtime_health": ["runtime_health", "production_convergence"],
    "provider_health": ["provider_health"],
    "ticket_admission": ["ticket_admission"],
    "operational_outcome": ["operational_outcome"],
    "service_health": ["service_health", "production_convergence"],
    "unknown": ["unknown"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def failure_family(failure: str) -> str:
    value = str(failure or "").strip().casefold()
    if value.startswith("production_convergence_"):
        return "production_convergence"
    if value.startswith("container_down:") or value.startswith("mcp_status_"):
        return "runtime_health"
    if value.startswith("provider_canary_"):
        return "provider_health"
    if value.startswith("production_health_"):
        return "production_convergence"
    if value.startswith("health_metric:jason_provider_canary_health"):
        return "provider_health"
    if value.startswith("autonomy_"):
        return "ticket_admission"
    if value.startswith("outcome_contract_") or value.startswith("workflow_outcome_stale:"):
        return "operational_outcome"
    if (
        value.startswith("failed_user_unit:")
        or value.startswith("failed_system_unit:")
        or value.startswith("systemd_unit_failed:")
    ):
        return "service_health"
    if value.startswith("health_metric:jason_production_"):
        return "production_convergence"
    if value.startswith("health_metric:jason_mcp_"):
        return "runtime_health"
    return "unknown"


def _authority_markers(failures: list[str]) -> tuple[bool, bool]:
    """Return (disruptive_approval_required, external_authority_required)."""
    material = " ".join(str(value).casefold() for value in failures)
    disruptive = any(
        marker in material
        for marker in (
            "reboot_required",
            "shutdown_required",
            "forced_logoff_required",
            "disruptive_approval_required",
            "owner_approval_required",
        )
    )
    external = any(
        marker in material
        for marker in (
            "admin_consent_required",
            "credential_missing",
            "provider_authority_required",
            "external_authority_required",
            "security_boundary_blocked",
            "sudo_required",
        )
    )
    return disruptive, external


def repair_level(family: str, failures: list[str]) -> dict[str, Any]:
    disruptive, external = _authority_markers(failures)
    if external:
        return {
            "level": 4,
            "name": "external_or_authority_blocker",
            "automatic_execution": False,
            "requires_owner_action": True,
        }
    if disruptive:
        return {
            "level": 3,
            "name": "approval_required_disruptive_repair",
            "automatic_execution": False,
            "requires_owner_action": True,
        }
    if family == "runtime_health" and all(
        value.startswith(("container_down:", "mcp_status_")) for value in failures
    ):
        return {
            "level": 1,
            "name": "deterministic_safe_repair",
            "automatic_execution": True,
            "requires_owner_action": False,
        }
    return {
        "level": 2,
        "name": "bounded_autonomous_repair",
        "automatic_execution": True,
        "requires_owner_action": False,
    }


def verification_contract(family: str, failures: list[str]) -> dict[str, Any]:
    checks: dict[str, list[str]] = {
        "production_convergence": [
            "rerun production convergence detector",
            "prove runtime/MCP/host/scheduled artifacts resolve to one production SHA",
            "prove required timers/watchers are active",
            "prove no related production/runtime/service-health failure was introduced",
        ],
        "runtime_health": [
            "rerun runtime and MCP functional probes",
            "prove original runtime symptom is absent",
            "prove production convergence remains intact",
        ],
        "provider_health": [
            "rerun provider canary",
            "prove the canary is fresh and healthy or exposes a specific governed external blocker",
        ],
        "ticket_admission": [
            "rerun admission scan",
            "prove eligible work is selected or durably explained",
            "prove no new unreviewed work is silently skipped by the same admission path",
        ],
        "operational_outcome": [
            "rerun the original outcome verifier",
            "prove the promised outcome is verified or has a real external blocker with evidence",
        ],
        "service_health": [
            "rerun service/unit health checks",
            "prove scheduled implementation matches the active production release",
        ],
        "unknown": [
            "rerun the original detector",
            "prove the original symptom is absent",
            "prove no related regression was introduced",
        ],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "family": family,
        "must_clear_family": family,
        "related_families_must_be_healthy": RELATED_FAMILIES.get(family, [family]),
        "original_failures": sorted(set(failures)),
        "required_checks": checks.get(family, checks["unknown"]),
        "closure_requires_detector_recheck": True,
    }


def incident_fingerprint(family: str, failures: list[str]) -> str:
    # Durable Support identity follows the violated root invariant, not symptom details.
    material = json.dumps({"schema": "root-invariant-v1", "family": family}, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def correlate_failures(failures: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for failure in sorted(set(str(value) for value in failures if str(value).strip())):
        grouped[failure_family(failure)].append(failure)

    # Production convergence is the upstream invariant for runtime/service symptoms
    # when both are present. Keep one incident instead of alerting each symptom.
    if "production_convergence" in grouped:
        for related in ("runtime_health", "service_health"):
            if related in grouped:
                grouped["production_convergence"].extend(grouped.pop(related))

    incidents: list[dict[str, Any]] = []
    for family, symptoms in sorted(grouped.items()):
        symptoms = sorted(set(symptoms))
        level = repair_level(family, symptoms)
        fp = incident_fingerprint(family, symptoms)
        incidents.append(
            {
                "schema_version": SCHEMA_VERSION,
                "fingerprint": fp,
                "family": family,
                "title": FAMILY_TITLES.get(family, FAMILY_TITLES["unknown"]),
                "root_invariant": ROOT_INVARIANTS.get(family, ROOT_INVARIANTS["unknown"]),
                "symptoms": symptoms,
                "repair": level,
                "verification_contract": verification_contract(family, symptoms),
            }
        )
    return incidents


def update_recurrence_memory(
    path: Path,
    incidents: list[dict[str, Any]],
    *,
    observed_at: str | None = None,
) -> list[dict[str, Any]]:
    observed_at = observed_at or now()
    memory = _read_json(path)
    families = memory.get("families") if isinstance(memory.get("families"), Mapping) else {}
    families = {str(key): dict(value) for key, value in families.items() if isinstance(value, Mapping)}
    active_now = {str(item.get("family") or "unknown") for item in incidents}

    for family, record in list(families.items()):
        if family not in active_now:
            record["active"] = False
            record["last_cleared_at"] = observed_at
            families[family] = record

    enriched: list[dict[str, Any]] = []
    for incident in incidents:
        family = str(incident.get("family") or "unknown")
        previous = dict(families.get(family) or {})
        was_active = bool(previous.get("active"))
        occurrence_count = int(previous.get("occurrence_count") or 0)
        if not was_active:
            occurrence_count += 1
        first_seen = str(previous.get("first_seen_at") or observed_at)
        record = {
            "active": True,
            "first_seen_at": first_seen,
            "last_seen_at": observed_at,
            "occurrence_count": occurrence_count,
            "last_fingerprint": incident.get("fingerprint"),
        }
        families[family] = record

        item = dict(incident)
        item["occurrence_count"] = occurrence_count
        item["recurring"] = occurrence_count >= 2
        item["architectural_correction_required"] = occurrence_count >= 2
        item["priority"] = "P0" if occurrence_count >= 2 else "P1"
        enriched.append(item)

    _atomic_json(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "updated_at": observed_at,
            "families": families,
        },
    )
    return enriched


def acceptance_text(incident: Mapping[str, Any]) -> str:
    family = str(incident.get("family") or "unknown")
    invariant = str(incident.get("root_invariant") or ROOT_INVARIANTS["unknown"])
    occurrence_count = int(incident.get("occurrence_count") or 1)
    contract = incident.get("verification_contract") if isinstance(incident.get("verification_contract"), Mapping) else {}
    checks = contract.get("required_checks") if isinstance(contract.get("required_checks"), list) else []
    prefix = (
        f"Restore and prove the root invariant: {invariant}. "
        "Do not close on command success alone; rerun the original detector and verify the symptom family clears. "
    )
    if occurrence_count >= 2:
        prefix += (
            "This is a recurring defect: implement an architectural correction and regression coverage, not another one-off repair. "
        )
    if checks:
        prefix += "Required verification: " + "; ".join(str(value) for value in checks[:5]) + "."
    return prefix[:1600]
