"""Exact read-only JSON facts from existing offline-context legacy classifier.

This is a partial conversion proof. Active same-site PowerShell witness,
10-minute lifecycle and note write/readback are NOT implemented here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from autonomous_remediation.deb_availability import (
    DebAvailabilityState, select_deb_asset,
)
from autonomous_remediation.json_shadow_integration import JsonShadowBoundaryError
from autonomous_remediation.offline_ticket_augmentation import (
    SiteContextEvidence, SiteWitness, classify_site_context,
    is_offline_ticket, render_site_context_note,
)
from .autonomy_worker_runtime import OperationalAutonomyMaintenance


def _provider_data(result: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = result.get("evidence")
    if not isinstance(evidence, Mapping):
        raise JsonShadowBoundaryError("OFFLINE_GOVERNED_EVIDENCE_MISSING")
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        raise JsonShadowBoundaryError("OFFLINE_GOVERNED_DATA_MISSING")
    return data


def _one_record(result: Mapping[str, Any]) -> Mapping[str, Any]:
    data = _provider_data(result)
    items = data.get("items")
    if items is not None:
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
            raise JsonShadowBoundaryError("OFFLINE_RECORD_NOT_UNIQUE")
        return items[0]
    record = data.get("item", data.get("record"))
    if not isinstance(record, Mapping):
        raise JsonShadowBoundaryError("OFFLINE_RECORD_UNAVAILABLE")
    return record


def _id(value: Any) -> str:
    return str(value or "").strip()


def reduce_offline_context_shadow(
    capability: str,
    result: Mapping[str, Any],
    facts: Mapping[str, Any],
    *,
    at: datetime,
) -> Mapping[str, Any]:
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise JsonShadowBoundaryError("OFFLINE_AWARE_CLOCK_REQUIRED")
    if capability == "service.ticket.read":
        ticket = _one_record(result)
        if _id(ticket.get("id")) != _id(facts.get("target_id")):
            raise JsonShadowBoundaryError("OFFLINE_TICKET_IDENTITY_CHANGED")
        if _id(ticket.get("companyID")) != _id(facts.get("client_id")):
            raise JsonShadowBoundaryError("OFFLINE_TICKET_CLIENT_CHANGED")
        ci_id = ticket.get("configurationItemID")
        try:
            ci_id = int(ci_id)
        except (TypeError, ValueError):
            ci_id = 0
        eligible = (
            ci_id > 0 and is_offline_ticket(
                title=str(ticket.get("title") or ""),
                description=str(ticket.get("description") or ""),
                has_device_context=True,
            )
            and str(ticket.get("status") or "").casefold() not in {"complete", "5"}
        )
        return {
            "exact_same_client_offline_ticket": eligible,
            "company_id": str(ticket.get("companyID")),
            "ticket_number": str(ticket.get("ticketNumber") or ticket["id"]),
            "ticket_title": str(ticket.get("title") or ""),
            "configuration_item_id": ci_id,
        }
    if capability == "service.configuration.read":
        ci = _one_record(result)
        if (_id(ci.get("id")) != _id(facts.get("configuration_item_id")) or
            _id(ci.get("companyID")) != _id(facts.get("company_id")) or
            ci.get("isActive") is not True):
            raise JsonShadowBoundaryError("OFFLINE_CI_COMPANY_OR_STATE_MISMATCH")
        uid = _id(ci.get("referenceNumber"))
        name = _id(ci.get("referenceTitle"))
        if not uid or not name:
            raise JsonShadowBoundaryError("OFFLINE_CI_TARGET_IDENTITY_INCOMPLETE")
        return {
            "exact_active_same_company_ci": True,
            "device_uid": uid, "device_hostname": name,
        }
    if capability == "endpoint.device.read":
        data = result.get("evidence")
        record = data.get("record") if isinstance(data, Mapping) else None
        if not isinstance(record, Mapping):
            raise JsonShadowBoundaryError("OFFLINE_DEVICE_RECORD_MISSING")
        uid = _id(record.get("resource_id") or record.get("uid") or record.get("deviceUid"))
        hostname = _id(record.get("hostname") or record.get("hostName") or record.get("name"))
        if uid != facts.get("device_uid") or hostname.casefold() != str(
            facts.get("device_hostname") or "").casefold():
            raise JsonShadowBoundaryError("OFFLINE_DEVICE_IDENTITY_CONFLICT")
        site = _id(record.get("site"))
        site_uid = _id(record.get("siteUid") or record.get("site_uid"))
        if not site or not site_uid:
            raise JsonShadowBoundaryError("OFFLINE_SITE_IDENTITY_UNVERIFIED")
        state = (
            True if record.get("online") is True else
            False if record.get("online") is False else None
        )
        return {
            "exact_target_device_identity": True,
            "target_drmm_online": state,
            "site_name": site, "site_uid": site_uid,
        }
    if capability == "backup.endpoint.asset.search":
        data = _provider_data(result)
        items = data.get("items")
        if not isinstance(items, list):
            raise JsonShadowBoundaryError("OFFLINE_DEB_LIST_MISSING")
        selected = select_deb_asset(
            items, hostname=str(facts.get("device_hostname") or ""),
            observed_at=at,
        )
        state = (
            True if selected.state is DebAvailabilityState.ONLINE else
            False if selected.state is DebAvailabilityState.OFFLINE else None
        )
        return {"target_deb_online": state}
    if capability == "endpoint.device.search":
        data = _provider_data(result)
        peers = data.get("resource_matches")
        if not isinstance(peers, list) or len(peers) > 20:
            raise JsonShadowBoundaryError("OFFLINE_PEER_INVENTORY_INCOMPLETE")
        site_uid = str(facts.get("site_uid") or "")
        target_uid = str(facts.get("device_uid") or "")
        witnesses = []
        for raw in peers:
            if not isinstance(raw, Mapping):
                raise JsonShadowBoundaryError("OFFLINE_PEER_RECORD_INVALID")
            uid = _id(raw.get("resource_id") or raw.get("uid") or raw.get("deviceUid"))
            if not uid or uid == target_uid:
                continue
            if _id(raw.get("siteUid") or raw.get("site_uid")) != site_uid:
                raise JsonShadowBoundaryError("OFFLINE_PEER_SITE_SCOPE_MISMATCH")
            role, fixed, mobile = OperationalAutonomyMaintenance._offline_augmentation_role(raw)
            hostname = _id(raw.get("hostname") or raw.get("hostName") or raw.get("name"))
            if not hostname:
                raise JsonShadowBoundaryError("OFFLINE_PEER_HOSTNAME_MISSING")
            online = (
                True if raw.get("online") is True else
                False if raw.get("online") is False else None
            )
            witnesses.append(SiteWitness(
                device_uid=uid, hostname=hostname, role=role,
                online=online, fixed=fixed, mobile=mobile,
                site_presence_confirmed=fixed and not mobile,
                live_read_succeeded=False,
            ))
        evidence = SiteContextEvidence(
            target_hostname=str(facts["device_hostname"]),
            target_drmm_online=facts.get("target_drmm_online"),
            target_deb_online=facts.get("target_deb_online"),
            site_name=str(facts.get("site_name") or ""),
            witnesses=tuple(witnesses),
        )
        assessment = classify_site_context(evidence)
        return {
            "peer_inventory_scope_verified": True,
            "classification": assessment.state.value,
            "assessment_fingerprint": assessment.fingerprint(),
            "legacy_readonly_note_preview": render_site_context_note(
                assessment,
                target_drmm_online=evidence.target_drmm_online,
                target_deb_online=evidence.target_deb_online,
                site_name=evidence.site_name,
            ),
            "witness_count": len(witnesses),
            "active_server_witness_attempted": False,
        }
    raise JsonShadowBoundaryError("OFFLINE_UNDECLARED_READ_CAPABILITY")
