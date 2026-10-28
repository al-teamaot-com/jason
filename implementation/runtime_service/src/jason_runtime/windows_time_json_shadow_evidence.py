"""Read-only evidence binding for the disabled Windows Time JSON shadow pilot.

This module reuses Jason's existing governed read port and Windows Time alert
parsers. It does not create a worker, schedule work, execute arbitrary commands,
modify providers, stage JSON, or grant autonomy. Never use synthetic facts as
operational evidence: this is an isolated *shadow assessment* only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol

from autonomous_remediation.playbook_document import PlaybookDocument
from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter

from .windows_time_source_shadow import (
    RECURRENCE_THRESHOLD,
    RECURRENCE_WINDOW,
    _alert_items,
    _provider_time,
    is_time_source_alert,
    parse_sources,
)

MAX_OPEN_ALERT_AGE = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)
_READ_CAPABILITIES = frozenset(
    {"management.alert.search", "endpoint.device.read", "endpoint.alert.history.search"}
)
_TERMINAL_PREFIX = "review_"


class GovernedReadPort(Protocol):
    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class JsonTimeShadowAssessment:
    """Small evidence-backed outcome; no raw ticket/alert content or secrets."""

    terminal_step: str
    reason_code: str
    alert_uid: str
    device_uid: str
    site_uid: str
    recurrence_count: int | None
    source_fingerprint: str | None
    read_capabilities: tuple[str, ...]
    correlation_ids: tuple[str, ...]
    side_effects: int = 0
    staged: bool = False
    activated: bool = False


class WindowsTimeJsonShadowEvidence:
    """Bridge existing JKD/Central-Orchestrator reads into disabled JSON facts.

    No independent credential, caller-selected capability, direct provider URL,
    user-supplied decision boolean, write path, or production registration is
    accepted. The code is intentionally NOT wired into the live maintenance
    scheduler while the JSON pilot remains unaccepted.
    """

    def __init__(self, *, reads: GovernedReadPort, document: PlaybookDocument) -> None:
        if document.playbook_id != "windows_time_source":
            raise ValueError("JSON_SHADOW_WRONG_PLAYBOOK")
        payload = document.payload
        scope = payload.get("scope")
        if (
            document.autonomy_activation != "disabled"
            or document.capabilities
            or not isinstance(scope, Mapping)
            or scope.get("direct_provider_access") is not False
            or scope.get("simulation_only") is not True
            or scope.get("never_modify_windows_time") is not True
            or scope.get("never_resolve_live_alert") is not True
            or scope.get("never_close_autotask_ticket") is not True
            or payload.get("migration", {}).get("production_replacement_allowed") is not False
        ):
            raise ValueError("JSON_SHADOW_EXECUTION_AUTHORITY_FORBIDDEN")
        steps = payload.get("steps", ())
        if not steps or any(
            not isinstance(step, Mapping)
            or step.get("type") not in ("decision", "human_review")
            or "capability" in step
            or "arguments" in step
            for step in steps
        ):
            raise ValueError("JSON_SHADOW_EXECUTABLE_STEP_FORBIDDEN")
        self.reads = reads
        self.document = document

    def assess(self, *, alert_uid: str, now: datetime) -> JsonTimeShadowAssessment:
        """Look up one exact open alert and classify only verified read evidence.

        A listing can be paginated. An absent alert on a partial page is
        *unknown*, never proof that the alert has resolved.
        """
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("JSON_SHADOW_AWARE_TIME_REQUIRED")
        now = now.astimezone(timezone.utc)
        alert_uid = str(alert_uid).strip()
        if not alert_uid:
            raise ValueError("JSON_SHADOW_EXACT_ALERT_UID_REQUIRED")

        used: list[str] = []
        correlations: list[str] = []
        device_uid = ""
        site_uid = ""
        recurrence: int | None = None
        fingerprint: str | None = None

        def read(capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any] | None:
            if capability not in _READ_CAPABILITIES:
                raise ValueError("JSON_SHADOW_UNAPPROVED_READ")
            used.append(capability)
            try:
                result = self.reads.execute(capability, arguments)
            except Exception:
                return None  # fail closed without propagating provider internals
            if not isinstance(result, Mapping):
                return None
            if (
                result.get("status") != "succeeded"
                or result.get("stage") != "completed"
                or result.get("capability") != capability
                or result.get("provider") != "datto_rmm"
                or result.get("error_code") is not None
                or not str(result.get("correlation_id") or "").strip()
                or not isinstance(result.get("evidence"), Mapping)
            ):
                return None
            correlations.append(str(result["correlation_id"]))
            return result

        def finish(
            reason: str,
            *,
            facts: Mapping[str, bool] | None = None,
        ) -> JsonTimeShadowAssessment:
            instruction = JsonPlaybookInterpreter(self.document).instruction(facts=facts or {})
            if (
                not instruction.terminal
                or instruction.step_type != "human_review"
                or not instruction.step_id.startswith(_TERMINAL_PREFIX)
                or instruction.capability is not None
                or instruction.arguments
                or instruction.approval_required
            ):
                raise ValueError("JSON_SHADOW_UNSAFE_TERMINAL")
            return JsonTimeShadowAssessment(
                terminal_step=instruction.step_id,
                reason_code=reason,
                alert_uid=alert_uid,
                device_uid=device_uid,
                site_uid=site_uid,
                recurrence_count=recurrence,
                source_fingerprint=fingerprint,
                read_capabilities=tuple(used),
                correlation_ids=tuple(correlations),
            )

        listing = read("management.alert.search", {"status": "open"})
        if listing is None:
            return finish("OPEN_ALERT_READ_UNVERIFIED")
        alerts = _alert_items(listing)
        matching = [a for a in alerts if str(a.get("alertUid") or "").strip() == alert_uid]
        if len(matching) != 1:
            return finish("EXACT_OPEN_ALERT_NOT_PROVEN")
        alert = matching[0]
        if alert.get("resolved") is True or not is_time_source_alert(alert):
            return finish("OPEN_TIME_ALERT_SIGNATURE_NOT_PROVEN")
        observed, monitor_sources = parse_sources(alert)
        source = alert.get("alertSourceInfo")
        if not isinstance(source, Mapping):
            return finish("ALERT_IDENTITY_MISSING")
        device_uid = str(source.get("deviceUid") or "").strip()
        hostname = str(source.get("deviceName") or "").strip()
        site_uid = str(source.get("siteUid") or "").strip()
        site_name = str(source.get("siteName") or "").strip()
        if not all((device_uid, hostname, site_uid, site_name, observed, monitor_sources)):
            return finish("ALERT_IDENTITY_OR_SOURCE_MISSING")

        endpoint = read("endpoint.device.read", {"resource_id": device_uid})
        if endpoint is None:
            return finish("EXACT_DEVICE_READ_UNVERIFIED")
        device_evidence = endpoint["evidence"]
        record = device_evidence.get("record")
        if not isinstance(record, Mapping):
            return finish("EXACT_DEVICE_RECORD_MISSING")
        resolved_uid = str(
            record.get("resource_id") or record.get("uid") or record.get("deviceUid") or ""
        ).strip()
        resolved_host = str(
            record.get("hostname") or record.get("hostName") or record.get("name") or ""
        ).strip()
        resolved_site = str(record.get("site_id") or record.get("siteUid") or "").strip()
        resolved_site_name = str(
            record.get("site") or record.get("siteName") or ""
        ).strip()
        if (
            resolved_uid != device_uid
            or resolved_host.casefold() != hostname.casefold()
            or resolved_site != site_uid
            or (resolved_site_name and resolved_site_name.casefold() != site_name.casefold())
        ):
            return finish("ENDPOINT_CLIENT_OR_DEVICE_MISMATCH")
        if not isinstance(record.get("online"), bool):
            return finish("ENDPOINT_ONLINE_STATE_UNVERIFIED")

        material = {
            "alert_uid": alert_uid,
            "device_uid": device_uid,
            "site_uid": site_uid,
            "hostname": hostname.casefold(),
            "observed_source": observed.casefold(),
            "monitor_approved_sources": [value.casefold() for value in monitor_sources],
        }
        fingerprint = sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        base_facts = {"identity_verified": True}
        timestamp = _provider_time(alert)
        if (
            timestamp is None
            or timestamp > now + MAX_FUTURE_SKEW
            or now - timestamp > MAX_OPEN_ALERT_AGE
        ):
            return finish(
                "ALERT_STALE_OR_TIMESTAMP_UNVERIFIED",
                facts={**base_facts, "evidence_fresh": False},
            )
        base_facts["evidence_fresh"] = True

        if record["online"] is False:
            return finish(
                "ENDPOINT_OFFLINE",
                facts={**base_facts, "endpoint_online": False},
            )
        base_facts["endpoint_online"] = True

        history = read("endpoint.alert.history.search", {"resource_id": device_uid})
        if history is None:
            return finish("RECURRENCE_HISTORY_UNVERIFIED", facts=base_facts)
        details = history["evidence"].get("data")
        details = details if isinstance(details, Mapping) else {}
        page = details.get("pageDetails")
        page = page if isinstance(page, Mapping) else {}
        items = _alert_items(history)
        count = page.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(items):
            return finish("RECURRENCE_HISTORY_PAGINATION_UNVERIFIED", facts=base_facts)
        seen: set[str] = set()
        prior = 0
        cutoff = now - RECURRENCE_WINDOW
        for item in items:
            if not is_time_source_alert(item):
                continue
            other_source = item.get("alertSourceInfo")
            if not isinstance(other_source, Mapping):
                return finish("RECURRENCE_HISTORY_IDENTITY_UNVERIFIED", facts=base_facts)
            if str(other_source.get("deviceUid") or "") != device_uid:
                continue
            if str(other_source.get("siteUid") or "") != site_uid:
                return finish("RECURRENCE_HISTORY_CROSS_CLIENT", facts=base_facts)
            prior_uid = str(item.get("alertUid") or "").strip()
            if not prior_uid:
                return finish("RECURRENCE_HISTORY_UID_UNVERIFIED", facts=base_facts)
            if prior_uid == alert_uid or prior_uid in seen:
                continue
            seen.add(prior_uid)
            prior_at = _provider_time(item)
            if prior_at is None:
                return finish("RECURRENCE_HISTORY_TIME_UNVERIFIED", facts=base_facts)
            if cutoff <= prior_at <= now:
                prior += 1
        recurrence = prior + 1
        fingerprint = sha256(
            (fingerprint + f":{recurrence}").encode("ascii")
        ).hexdigest()

        # Do not translate the alert's "approved list" into an authoritative
        # client/site NTP policy. The dedicated Windows Time diagnostic has
        # not been collected or validated by this read-only bridge.
        return finish(
            "DEDICATED_TIME_DIAGNOSTIC_AND_SITE_POLICY_NOT_VERIFIED",
            facts={
                **base_facts,
                "recurrence_threshold_met": recurrence >= RECURRENCE_THRESHOLD,
                "evidence_complete": False,
                "approved_source_policy_confirmed": False,
            },
        )
