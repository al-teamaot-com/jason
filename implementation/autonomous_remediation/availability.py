"""Provider-neutral endpoint availability assessment for Jason playbooks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Mapping


class AvailabilityState(str, Enum):
    ONLINE = "online"
    RECENTLY_OFFLINE = "recently_offline"
    PEER_VERIFICATION_DUE = "peer_verification_due"
    PEER_UNAVAILABLE = "peer_unavailable"
    REACHABLE_OUTSIDE_DRMM = "reachable_outside_drmm"
    OFFLINE_LIKELY = "offline_likely"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class OfflineVerificationPolicy:
    peer_verify_after: timedelta = timedelta(hours=2)
    retry_after: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        if self.peer_verify_after <= timedelta(0):
            raise ValueError("peer_verify_after must be greater than zero")
        if self.retry_after <= timedelta(0):
            raise ValueError("retry_after must be greater than zero")


@dataclass(frozen=True)
class PeerProbeResult:
    peer_device_id: str
    attempted_at: datetime
    hostname_resolved: bool | None = None
    resolved_ip: str | None = None
    hostname_ping_succeeded: bool | None = None
    ip_ping_succeeded: bool | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        _aware(self.attempted_at, "attempted_at")
        if not self.peer_device_id.strip():
            raise ValueError("peer_device_id must be non-empty")

    @property
    def reachable(self) -> bool:
        return bool(self.hostname_ping_succeeded or self.ip_ping_succeeded)

    @property
    def attempted_without_success(self) -> bool:
        attempted = (
            self.hostname_ping_succeeded is not None
            or self.ip_ping_succeeded is not None
        )
        return attempted and not self.reachable


@dataclass(frozen=True)
class AvailabilityObservation:
    device_id: str
    observed_at: datetime
    drmm_online: bool
    last_seen_at: datetime | None
    hostname: str | None = None
    last_known_ip: str | None = None
    same_site_peer_available: bool | None = None
    peer_probe: PeerProbeResult | None = None

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at")
        if not self.device_id.strip():
            raise ValueError("device_id must be non-empty")
        if self.last_seen_at is not None:
            _aware(self.last_seen_at, "last_seen_at")
            if self.last_seen_at > self.observed_at:
                raise ValueError("last_seen_at cannot be after observed_at")
        if self.peer_probe is not None and self.same_site_peer_available is False:
            raise ValueError("peer_probe cannot exist when no same-site peer is available")


@dataclass(frozen=True)
class AvailabilityAssessment:
    device_id: str
    state: AvailabilityState
    observed_at: datetime
    offline_age: timedelta | None
    peer_verification_required: bool
    recheck_required: bool
    next_recheck_at: datetime | None
    drmm_agent_issue_suspected: bool
    summary: str
    evidence: Mapping[str, Any]

    def persisted_payload(self) -> Mapping[str, Any]:
        return {
            "device_id": self.device_id,
            "state": self.state.value,
            "observed_at": self.observed_at.isoformat(),
            "offline_age_seconds": (
                None if self.offline_age is None
                else int(self.offline_age.total_seconds())
            ),
            "peer_verification_required": self.peer_verification_required,
            "recheck_required": self.recheck_required,
            "next_recheck_at": (
                None if self.next_recheck_at is None
                else self.next_recheck_at.isoformat()
            ),
            "drmm_agent_issue_suspected": self.drmm_agent_issue_suspected,
            "summary": self.summary,
            "evidence": dict(self.evidence),
        }


def assess_endpoint_availability(
    observation: AvailabilityObservation,
    policy: OfflineVerificationPolicy = OfflineVerificationPolicy(),
) -> AvailabilityAssessment:
    """Return deterministic availability/recheck state without performing provider actions."""

    def result(
        state: AvailabilityState,
        *,
        offline_age: timedelta | None,
        peer_required: bool,
        recheck: bool,
        next_at: datetime | None,
        agent_suspected: bool,
        summary: str,
    ) -> AvailabilityAssessment:
        probe = observation.peer_probe
        evidence = {
            "drmm_online": observation.drmm_online,
            "last_seen_at": (
                None if observation.last_seen_at is None
                else observation.last_seen_at.isoformat()
            ),
            "hostname": observation.hostname,
            "last_known_ip": observation.last_known_ip,
            "same_site_peer_available": observation.same_site_peer_available,
            "peer_device_id": None if probe is None else probe.peer_device_id,
            "hostname_resolved": None if probe is None else probe.hostname_resolved,
            "resolved_ip": None if probe is None else probe.resolved_ip,
            "hostname_ping_succeeded": (
                None if probe is None else probe.hostname_ping_succeeded
            ),
            "ip_ping_succeeded": None if probe is None else probe.ip_ping_succeeded,
            "peer_probe_detail": None if probe is None else probe.detail,
        }
        return AvailabilityAssessment(
            device_id=observation.device_id,
            state=state,
            observed_at=observation.observed_at,
            offline_age=offline_age,
            peer_verification_required=peer_required,
            recheck_required=recheck,
            next_recheck_at=next_at,
            drmm_agent_issue_suspected=agent_suspected,
            summary=summary,
            evidence=evidence,
        )

    if observation.drmm_online:
        return result(
            AvailabilityState.ONLINE,
            offline_age=None,
            peer_required=False,
            recheck=False,
            next_at=None,
            agent_suspected=False,
            summary="DRMM reports the endpoint online.",
        )

    age = (
        None
        if observation.last_seen_at is None
        else observation.observed_at - observation.last_seen_at
    )

    if age is not None and age < policy.peer_verify_after:
        return result(
            AvailabilityState.RECENTLY_OFFLINE,
            offline_age=age,
            peer_required=False,
            recheck=True,
            next_at=observation.last_seen_at + policy.peer_verify_after,
            agent_suspected=False,
            summary="Offline threshold not reached; persist a recheck.",
        )

    if observation.peer_probe is not None:
        if observation.peer_probe.reachable:
            return result(
                AvailabilityState.REACHABLE_OUTSIDE_DRMM,
                offline_age=age,
                peer_required=False,
                recheck=False,
                next_at=None,
                agent_suspected=True,
                summary=(
                    "A same-site peer reached the endpoint while DRMM reports it offline; "
                    "continue with DRMM agent/service/path diagnostics."
                ),
            )
        if observation.peer_probe.attempted_without_success:
            return result(
                AvailabilityState.OFFLINE_LIKELY,
                offline_age=age,
                peer_required=False,
                recheck=True,
                next_at=observation.observed_at + policy.retry_after,
                agent_suspected=False,
                summary=(
                    "Peer probe could not reach the endpoint. Offline is more likely, "
                    "but ping failure is not definitive; keep a persisted recheck."
                ),
            )
        return result(
            AvailabilityState.INCONCLUSIVE,
            offline_age=age,
            peer_required=False,
            recheck=True,
            next_at=observation.observed_at + policy.retry_after,
            agent_suspected=False,
            summary="Peer verification was incomplete or inconclusive; recheck.",
        )

    if observation.same_site_peer_available is False:
        return result(
            AvailabilityState.PEER_UNAVAILABLE,
            offline_age=age,
            peer_required=False,
            recheck=True,
            next_at=observation.observed_at + policy.retry_after,
            agent_suspected=False,
            summary=(
                "Peer verification is due but no suitable same-site peer is available; "
                "do not block or close the workflow."
            ),
        )

    return result(
        AvailabilityState.PEER_VERIFICATION_DUE,
        offline_age=age,
        peer_required=True,
        recheck=True,
        next_at=observation.observed_at + policy.retry_after,
        agent_suspected=False,
        summary=(
            "Offline threshold exceeded; attempt read-only same-site reachability "
            "verification by hostname and last-known IP."
        ),
    )


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
