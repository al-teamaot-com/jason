"""Pure DEB pre-activation checks. No provider calls, grants or mutations.

Inputs are receipts from existing governed reads, bound by the calling
orchestrator to one company/device/asset. This module does not establish that
authority from caller-provided booleans and must not be exposed as an action.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


class DebRecoveryEvidenceError(ValueError):
    pass


def _company(value: Any) -> str:
    if isinstance(value, bool) or not str(value).isdigit():
        raise DebRecoveryEvidenceError("DEB_EXACT_COMPANY_REQUIRED")
    return str(int(value))


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DebRecoveryEvidenceError("DEB_AWARE_BASELINE_REQUIRED")
    return value.astimezone(timezone.utc)


def backupiq_read_arguments(*, company_id: Any, hostname: str,
                            asset_id: str) -> dict[str, dict[str, Any]]:
    """Server-owned scoped selectors; never accept provider customer UUIDs."""
    company = _company(company_id)
    if not isinstance(hostname, str) or not hostname.strip() or not isinstance(asset_id, str) or not asset_id.strip():
        raise DebRecoveryEvidenceError("DEB_EXACT_ASSET_REQUIRED")
    return {
        "asset_search": {"company_id": company, "name": hostname, "page_size": 100},
        "asset_read": {"company_id": company, "resource_id": asset_id},
        "alerts": {"company_id": company, "asset_name": hostname, "page_size": 100},
    }


def _items(receipt: Mapping[str, Any], capability: str, *, maximum: int) -> list:
    if (not isinstance(receipt, Mapping) or receipt.get("status") != "succeeded"
            or receipt.get("capability") != capability or not receipt.get("correlation_id")):
        raise DebRecoveryEvidenceError("DEB_GOVERNED_READ_FAILED_OR_WRONG_CAPABILITY")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, Mapping) or evidence.get("provider") != "backup_net":
        raise DebRecoveryEvidenceError("DEB_PROVIDER_RECEIPT_MISMATCH")
    data = evidence.get("data")
    items = data.get("items") if isinstance(data, Mapping) else None
    if not isinstance(items, list) or len(items) > maximum or any(not isinstance(x, Mapping) for x in items):
        raise DebRecoveryEvidenceError("DEB_READ_MALFORMED_OR_UNBOUNDED")
    if evidence.get("warnings"):
        raise DebRecoveryEvidenceError("DEB_READ_WARNINGS_REQUIRE_REVIEW")
    return items


@dataclass(frozen=True)
class DebRecoveryObservation:
    asset_id: str
    disposition: str
    last_success: datetime | None
    fresh_backup_verified: bool
    next_recheck_at: datetime | None
    provider_mutation_allowed: bool = False


def verify_deb_recovery(*, company_id: Any, hostname: str, asset_id: str,
                        asset_read_arguments: Mapping[str, Any],
                        alert_read_arguments: Mapping[str, Any],
                        expected_customer_id: str,
                        asset_receipt: Mapping[str, Any],
                        alert_receipt: Mapping[str, Any],
                        remediation_baseline: datetime, observed_at: datetime,
                        deadline: datetime) -> DebRecoveryObservation:
    """Verify post-repair provider health, not command success or ticket closure.

The caller must match these selectors to actual governed invocation receipts;
passing an unrelated receipt alongside invented selectors is not authority.
Only whitelist-derived observations leave this function; no raw logs persist.
"""
    expected = backupiq_read_arguments(company_id=company_id, hostname=hostname, asset_id=asset_id)
    if (dict(asset_read_arguments) != expected["asset_read"]
            or dict(alert_read_arguments) != expected["alerts"]):
        raise DebRecoveryEvidenceError("DEB_READ_SELECTORS_CHANGED")
    baseline, now, end = map(_aware, (remediation_baseline, observed_at, deadline))
    if not baseline <= now or not baseline < end <= baseline + timedelta(hours=3):
        raise DebRecoveryEvidenceError("DEB_VERIFICATION_WINDOW_INVALID")
    assets = _items(asset_receipt, "backup.endpoint.asset.read", maximum=1)
    alerts = _items(alert_receipt, "backup.backupiq.alert.search", maximum=100)
    if len(assets) != 1:
        raise DebRecoveryEvidenceError("DEB_EXACT_ASSET_NOT_UNIQUE")
    asset = assets[0]
    if not expected_customer_id or asset.get("customerId") != expected_customer_id:
        raise DebRecoveryEvidenceError("DEB_CUSTOMER_BOUNDARY_CHANGED")
    if str(asset.get("id")) != asset_id or str(asset.get("name", "")).casefold() != hostname.casefold():
        raise DebRecoveryEvidenceError("DEB_ASSET_IDENTITY_CHANGED")
    raw = asset.get("lastSuccessfulBackupTimestamp")
    stamp = None
    if raw:
        try:
            stamp = _aware(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
        except (ValueError, TypeError) as exc:
            raise DebRecoveryEvidenceError("DEB_SUCCESS_TIMESTAMP_INVALID") from exc
        if stamp > now:
            raise DebRecoveryEvidenceError("DEB_FUTURE_SUCCESS_REJECTED")
    status = str(asset.get("status", "")).casefold()
    fresh = bool(asset.get("backupEnabled") is True and status == "online"
                 and stamp is not None and stamp > baseline and not alerts)
    if fresh:
        disposition, due = "provider_recovery_verified", None
    elif now >= end:
        disposition, due = "verification_deadline_human_review", None
    elif asset.get("backupEnabled") is not True:
        disposition, due = "backup_configuration_human_review", None
    elif status in {"online", "inprogress", "running"}:
        disposition, due = "waiting_backup", min(now + timedelta(minutes=15), end)
    else:
        disposition, due = "provider_state_human_review", None
    return DebRecoveryObservation(asset_id, disposition, stamp, fresh, due)
