"""Source-only disk-health and safe cleanup candidate classification.

Reuses deployed deterministic low_disk_analysis and existing governed
endpoint evidence; the output is NOT an execution grant.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .low_disk_analysis import (
    storage_health_summary, choose_cleanup, relevant_findings,
    artifact_bytes, recommendation,
)


class JsonLowDiskBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonLowDiskAssessment:
    disposition: str
    storage_risk: bool
    storage_health_text: str
    cleanup_kind: str | None
    cleanup_bytes: float
    recommendation: str
    findings: tuple[str, ...]
    mutation_permitted: bool = False


def classify_low_disk_readonly(
    *,
    exact_client_id: str,
    exact_device_uid: str,
    exact_drive_letter: str,
    endpoint: Mapping[str, Any],
    current_volume: Mapping[str, Any],
    authoritative_low_disk_monitor_open: bool,
    source_grace_elapsed: bool,
    evidence: Mapping[str, Sequence[Mapping[str, Any]]],
    evidence_failures: Sequence[str] = (),
    storage_risk_event_count: int = 0,
) -> JsonLowDiskAssessment:
    if (not exact_client_id or not exact_device_uid or
        not exact_drive_letter or len(exact_drive_letter) > 3):
        raise JsonLowDiskBoundaryError("LOW_DISK_EXACT_CLIENT_DEVICE_DRIVE_REQUIRED")
    if (str(endpoint.get("resource_id") or "") != exact_device_uid or
        str(endpoint.get("companyID") or "") != exact_client_id):
        raise JsonLowDiskBoundaryError("LOW_DISK_ENDPOINT_CLIENT_UID_CHANGED")
    if endpoint.get("online") is not True:
        return JsonLowDiskAssessment(
            "waiting_device_access", False, "Endpoint not online",
            None, 0.0, "Wait for exact device access", ())
    if (str(current_volume.get("DriveLetter") or "").casefold()
        != exact_drive_letter.rstrip(":").casefold()):
        raise JsonLowDiskBoundaryError("LOW_DISK_VOLUME_IDENTITY_CHANGED")
    for key in ("Size", "SizeRemaining"):
        value = current_volume.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            raise JsonLowDiskBoundaryError("LOW_DISK_VOLUME_CAPACITY_INVALID")
    if current_volume["SizeRemaining"] > current_volume["Size"]:
        raise JsonLowDiskBoundaryError("LOW_DISK_VOLUME_FREE_EXCEEDS_SIZE")
    if not isinstance(authoritative_low_disk_monitor_open, bool):
        raise JsonLowDiskBoundaryError("LOW_DISK_MONITOR_NOT_AUTHORITATIVE")
    if not isinstance(source_grace_elapsed, bool):
        raise JsonLowDiskBoundaryError("LOW_DISK_SOURCE_GRACE_UNVERIFIED")
    if not source_grace_elapsed and authoritative_low_disk_monitor_open:
        return JsonLowDiskAssessment(
            "waiting_existing_autotask_cleanup", False, "Grace period active",
            None, 0.0, "Wait for normal 15-minute monitor propagation", ())
    protected = any(
        token in str(endpoint.get("device_type") or "").casefold()
        for token in ("server", "hypervisor", "domain controller", "backup repository")
    )
    required = (
        "physical_disks", "reliability", "sysmon", "sysmon_dependencies",
        "software_distribution", "large_files", "top_folders",
        "vss", "system_files",
    )
    if any(key not in evidence or not isinstance(evidence[key], Sequence)
           for key in required):
        raise JsonLowDiskBoundaryError("LOW_DISK_READONLY_EVIDENCE_INCOMPLETE")
    if any(len(evidence[key]) > 100 for key in required):
        raise JsonLowDiskBoundaryError("LOW_DISK_EVIDENCE_UNBOUNDED")
    risk, health_text = storage_health_summary(
        evidence["physical_disks"], evidence["reliability"],
        storage_risk_event_count,
    )
    failed = set(evidence_failures)
    safe_sysmon = evidence["sysmon"] if "sysmon" not in failed else ()
    safe_deps = (evidence["sysmon_dependencies"]
                 if "sysmon_dependencies" not in failed
                 else ({"Name": "Dependency evidence unavailable"},))
    clean, amount = choose_cleanup(
        sysmon=safe_sysmon,
        sysmon_dependencies=safe_deps,
        software_distribution=(
            evidence["software_distribution"]
            if "software_distribution" not in failed else ()),
        storage_health_risk=risk,
    )
    findings = tuple(relevant_findings(
        top_folders=evidence["top_folders"],
        large_files=evidence["large_files"],
        vss=evidence["vss"], system_files=evidence["system_files"],
        sysmon=evidence["sysmon"],
        software_distribution=evidence["software_distribution"],
    ))
    recommendation_text = recommendation(
        alert_still_open=authoritative_low_disk_monitor_open,
        storage_health_risk=risk,
        cleanup_kind=clean if not protected else None,
        cleanup_bytes=amount,
        artifact_bytes=artifact_bytes(evidence["large_files"]),
    )
    if risk:
        disposition = "storage_health_risk_human_review"
    elif protected:
        disposition = "protected_device_human_review"
    elif failed:
        disposition = "evidence_inconclusive_human_review"
    elif not authoritative_low_disk_monitor_open:
        disposition = "monitor_cleared_verify_ticket"
    elif clean == "sysmon":
        disposition = "one_exact_cleanup_candidate_requires_promotion"
    else:
        disposition = "capacity_review"
    return JsonLowDiskAssessment(
        disposition, risk, health_text, clean, amount,
        recommendation_text, findings, False)
