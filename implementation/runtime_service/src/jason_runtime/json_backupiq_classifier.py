"""Read-only BackupIQ/DEB classification with existing exact-asset resolution.

No provider customer ID is accepted as authority from the caller. The caller
must first validate its own same-company-to-backup_net boundary with an exact
governed Observe proof, captured separately from the asset payload.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from autonomous_remediation.deb_availability import (
    DebAvailabilityState, parse_deb_timestamp, select_deb_asset,
)


class JsonBackupIQBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonBackupIQAssessment:
    classification: str
    asset_id: str | None
    last_success: datetime | None
    evidence_sha256: str
    provider_matches: int
    reinstall_candidate: bool
    provider_mutation_allowed: bool = False


def classify_backupiq_readonly(
    *,
    exact_autotask_company_id: str,
    verified_provider_customer_boundary: bool,
    exact_device_uid: str,
    exact_hostname: str,
    endpoint: Mapping[str, Any],
    provider_assets: Sequence[Mapping[str, Any]],
    current_provider_alerts: Sequence[Mapping[str, Any]],
    ticket_created_at: datetime,
    observed_at: datetime,
) -> JsonBackupIQAssessment:
    if (not exact_autotask_company_id or
        not exact_device_uid or not exact_hostname or
        verified_provider_customer_boundary is not True):
        raise JsonBackupIQBoundaryError("BACKUPIQ_EXACT_PROVIDER_CUSTOMER_SCOPE_UNVERIFIED")
    # The AOT self-company can validly have Autotask company ID 0.
    if (str(endpoint.get("resource_id") or "") != exact_device_uid or
        str(endpoint.get("companyID") if endpoint.get("companyID") is not None else "") != exact_autotask_company_id or
        str(endpoint.get("hostname") or "").casefold()
        != exact_hostname.casefold()):
        raise JsonBackupIQBoundaryError("BACKUPIQ_ENDPOINT_CLIENT_UID_CHANGED")
    if (observed_at.tzinfo is None or ticket_created_at.tzinfo is None or
        not isinstance(provider_assets, Sequence) or
        not isinstance(current_provider_alerts, Sequence) or
        len(provider_assets)>200 or len(current_provider_alerts)>100):
        raise JsonBackupIQBoundaryError("BACKUPIQ_OBSERVATION_INCOMPLETE_OR_UNBOUNDED")
    selection=select_deb_asset(
        provider_assets,hostname=exact_hostname,observed_at=observed_at)
    asset=selection.asset
    last_success=None
    provider_online=False
    backup_enabled=False
    last_online=None
    endpoint_online=endpoint.get("online") is True
    if asset is None:
        classification={
            DebAvailabilityState.NOT_FOUND:"asset_identity_or_lifecycle_issue",
            DebAvailabilityState.AMBIGUOUS:"duplicate_or_ambiguous_provider_asset",
        }.get(selection.state,"provider_asset_evidence_unavailable")
    else:
        provider_online=str(asset.get("status") or "").strip().casefold()=="online"
        backup_enabled=asset.get("backupEnabled") is True
        last_success=parse_deb_timestamp(asset.get("lastSuccessfulBackupTimestamp"))
        last_online=parse_deb_timestamp(asset.get("lastOnlineTimestamp"))
        recovered=(last_success is not None and last_success>=ticket_created_at)
        if not backup_enabled:
            classification="backup_configuration_issue"
        elif not endpoint_online and not provider_online:
            classification="true_offline_both_sources"
        elif not endpoint_online and provider_online:
            classification="drmm_only_offline_conflict"
        elif endpoint_online and not provider_online:
            classification="backup_agent_connectivity_failure"
        elif recovered and not current_provider_alerts:
            classification="stale_or_recovered_alert"
        elif recovered:
            classification="persistent_backupiq_condition_after_success"
        elif endpoint_online and provider_online:
            classification="backup_failure_or_stale_success"
        else:
            classification="provider_endpoint_state_conflict"
    evidence={
        "classification":classification,
        "endpoint_online":endpoint_online,
        "provider_online":provider_online,
        "backup_enabled":backup_enabled,
        "last_success":last_success.isoformat() if last_success else None,
        "last_online":last_online.isoformat() if last_online else None,
        "current_alert_count":len(current_provider_alerts),
    }
    digest=sha256(json.dumps(
        evidence,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return JsonBackupIQAssessment(
        classification,
        selection.selected_asset_id if asset else None,
        last_success,digest,selection.exact_match_count,
        classification in {
            "backup_agent_connectivity_failure",
            "persistent_backupiq_condition_after_success",
            "backup_failure_or_stale_success",
        },
    )
