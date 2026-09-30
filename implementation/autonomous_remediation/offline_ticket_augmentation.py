"""Deterministic site-context assessment for offline-ticket augmentation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class SiteContextState(str, Enum):
    CONFIRMED_UP = "site_confirmed_up"
    LIKELY_UP = "site_likely_up"
    LIKELY_DOWN = "site_likely_down"
    PARTIAL_OR_SEGMENT = "partial_or_segment_outage_suspected"
    UNKNOWN = "site_status_unknown"


@dataclass(frozen=True, slots=True)
class SiteWitness:
    device_uid: str
    hostname: str
    role: str
    online: bool | None
    fixed: bool
    mobile: bool = False
    site_presence_confirmed: bool = False
    live_read_succeeded: bool = False

    def __post_init__(self) -> None:
        if not self.device_uid.strip():
            raise ValueError("device_uid must be non-empty")
        if not self.hostname.strip():
            raise ValueError("hostname must be non-empty")
        if self.mobile and self.fixed:
            raise ValueError("a witness cannot be both mobile and fixed")
        if self.live_read_succeeded and not self.site_presence_confirmed:
            raise ValueError(
                "live_read_succeeded requires confirmed site presence"
            )


@dataclass(frozen=True, slots=True)
class SiteContextEvidence:
    target_hostname: str
    target_drmm_online: bool | None
    target_deb_online: bool | None
    site_name: str | None
    witnesses: tuple[SiteWitness, ...] = ()

    def __post_init__(self) -> None:
        if not self.target_hostname.strip():
            raise ValueError("target_hostname must be non-empty")


@dataclass(frozen=True, slots=True)
class SiteContextAssessment:
    state: SiteContextState
    target_hostname: str
    target_online_outside_drmm: bool
    confirmed_live_witnesses: tuple[str, ...]
    online_fixed_witnesses: tuple[str, ...]
    offline_fixed_witnesses: tuple[str, ...]
    excluded_mobile_online: tuple[str, ...]
    summary: str

    def fingerprint(self) -> str:
        payload = {
            "state": self.state.value,
            "target_hostname": self.target_hostname,
            "target_online_outside_drmm": self.target_online_outside_drmm,
            "confirmed_live_witnesses": self.confirmed_live_witnesses,
            "online_fixed_witnesses": self.online_fixed_witnesses,
            "offline_fixed_witnesses": self.offline_fixed_witnesses,
            "excluded_mobile_online": self.excluded_mobile_online,
            "summary": self.summary,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()


_OFFLINE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:device|server|host|endpoint|workstation|computer|pc)\s+(?:is\s+)?offline\b",
        r"\b(?:device|server|host|endpoint|workstation|computer|pc)\s+(?:is\s+)?down\b",
        r"\b(?:device|server|host|endpoint|workstation|computer|pc)\s+(?:is\s+)?unreachable\b",
        r"\b(?:device|server|host|endpoint|workstation|computer|pc)\s+(?:is\s+)?not responding\b",
        r"\blost\s+(?:contact|connection)\b",
    )
)


def is_offline_ticket(
    *,
    title: str,
    description: str = "",
    has_device_context: bool = False,
) -> bool:
    """Return True only for bounded device/offline language."""

    material = f"{title} {description}".strip()
    if any(pattern.search(material) for pattern in _OFFLINE_PATTERNS):
        return True

    folded_title = str(title or "").casefold()
    return has_device_context and any(
        token in folded_title
        for token in (" offline", "offline ", "[offline]", "- offline")
    )


def classify_site_context(
    evidence: SiteContextEvidence,
) -> SiteContextAssessment:
    witnesses = tuple(evidence.witnesses)

    confirmed_live = tuple(
        sorted(
            witness.hostname
            for witness in witnesses
            if (
                witness.fixed
                and not witness.mobile
                and witness.online is True
                and witness.site_presence_confirmed
                and witness.live_read_succeeded
            )
        )
    )
    online_fixed = tuple(
        sorted(
            witness.hostname
            for witness in witnesses
            if (
                witness.fixed
                and not witness.mobile
                and witness.online is True
                and witness.site_presence_confirmed
            )
        )
    )
    offline_fixed = tuple(
        sorted(
            witness.hostname
            for witness in witnesses
            if (
                witness.fixed
                and not witness.mobile
                and witness.online is False
                and witness.site_presence_confirmed
            )
        )
    )
    excluded_mobile_online = tuple(
        sorted(
            witness.hostname
            for witness in witnesses
            if witness.mobile and witness.online is True
        )
    )

    target_online_outside_drmm = (
        evidence.target_drmm_online is False
        and evidence.target_deb_online is True
    )

    if confirmed_live:
        if len(offline_fixed) >= 2:
            state = SiteContextState.PARTIAL_OR_SEGMENT
            summary = (
                "A confirmed on-site fixed server returned fresh governed output, "
                "so the site is not broadly down; multiple fixed peers are offline, "
                "which suggests a partial/segment issue."
            )
        else:
            state = SiteContextState.CONFIRMED_UP
            summary = (
                "A confirmed on-site fixed server returned fresh governed output; "
                "the broad site-down branch is rejected."
            )
    elif len(online_fixed) >= 2:
        state = SiteContextState.LIKELY_UP
        summary = (
            "Multiple fixed same-site witnesses are currently online; the site is "
            "likely up, although no active server witness was proven."
        )
    elif len(offline_fixed) >= 2 and not online_fixed:
        state = SiteContextState.LIKELY_DOWN
        summary = (
            "Multiple fixed same-site witnesses are offline and no fixed online "
            "site witness is available; a site outage is likely."
        )
    else:
        state = SiteContextState.UNKNOWN
        summary = (
            "Available evidence is insufficient to classify the site as up or down."
        )

    return SiteContextAssessment(
        state=state,
        target_hostname=evidence.target_hostname,
        target_online_outside_drmm=target_online_outside_drmm,
        confirmed_live_witnesses=confirmed_live,
        online_fixed_witnesses=online_fixed,
        offline_fixed_witnesses=offline_fixed,
        excluded_mobile_online=excluded_mobile_online,
        summary=summary,
    )


def render_site_context_note(
    assessment: SiteContextAssessment,
    *,
    target_drmm_online: bool | None,
    target_deb_online: bool | None,
    site_name: str | None,
) -> str:
    labels = {
        SiteContextState.CONFIRMED_UP: "Site confirmed up",
        SiteContextState.LIKELY_UP: "Site likely up",
        SiteContextState.LIKELY_DOWN: "Site likely down",
        SiteContextState.PARTIAL_OR_SEGMENT: "Partial/segment outage suspected",
        SiteContextState.UNKNOWN: "Site status unknown",
    }

    def yn(value: bool | None) -> str:
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        return "Unknown"

    evidence_parts: list[str] = [
        f"Target={assessment.target_hostname}",
        f"DRMMOnline={yn(target_drmm_online)}",
        f"DEBOnline={yn(target_deb_online)}",
    ]
    if site_name:
        evidence_parts.append(f"Site={site_name}")
    if assessment.confirmed_live_witnesses:
        evidence_parts.append(
            "LiveOnSiteWitness=" + ",".join(assessment.confirmed_live_witnesses[:3])
        )
    if assessment.online_fixed_witnesses:
        evidence_parts.append(
            "OnlineFixedPeers=" + ",".join(assessment.online_fixed_witnesses[:5])
        )
    if assessment.offline_fixed_witnesses:
        evidence_parts.append(
            "OfflineFixedPeers=" + ",".join(assessment.offline_fixed_witnesses[:5])
        )
    if assessment.excluded_mobile_online:
        evidence_parts.append(
            "Remote/MobileOnlineExcluded="
            + ",".join(assessment.excluded_mobile_online[:5])
        )

    interpretation = assessment.summary
    if assessment.target_online_outside_drmm:
        interpretation += (
            " DEB reports the target online while DRMM reports it offline, so the "
            "target may have an RMM/monitoring-path issue rather than a true outage."
        )

    return (
        f"STATUS: {labels[assessment.state]}.\n"
        "NEXT STEP: Use this site context to prioritize endpoint versus site/network "
        "troubleshooting; Jason has not taken ownership of the ticket.\n"
        "KEY EVIDENCE: " + "; ".join(evidence_parts) + ".\n"
        "INTERPRETATION: " + interpretation + "\n"
        "CHANGES MADE: None. Read-only ticket augmentation only."
    )
