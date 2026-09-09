from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .provider_read_capability_catalog import (
    AUTOTASK_CAPABILITIES,
    AUTOTASK_PROVIDER,
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
)


_PROVIDER_CAPABILITIES = {
    IT_GLUE_PROVIDER: IT_GLUE_CAPABILITIES,
    AUTOTASK_PROVIDER: AUTOTASK_CAPABILITIES,
}


@dataclass(frozen=True, slots=True)
class ProviderReadAcceptanceRecord:
    """Sanitized provider-backed evidence presented to the activation gate.

    This record intentionally contains no credential material and no raw provider
    payload. It is an input to a deterministic activation decision, not an action.
    """

    provider_id: str
    observed_at: datetime
    evidence_reference: str
    verified_capabilities: frozenset[str]
    status: str
    provider_backed: bool
    read_only: bool
    credential_boundary_proven: bool
    protected_values_exposed: bool
    raw_provider_payload_persisted: bool
    hosted_model_used: bool


@dataclass(frozen=True, slots=True)
class ProviderReadActivationPlan:
    provider_id: str
    verified_capabilities: tuple[str, ...]
    target_provider_lifecycle: str
    target_provider_health: str
    target_capability_lifecycle: str
    evidence_reference: str
    hosted_model_required: bool


def build_provider_read_activation_plan(
    record: ProviderReadAcceptanceRecord,
) -> ProviderReadActivationPlan:
    """Fail closed unless sanitized live evidence is sufficient for activation.

    The returned plan does not mutate provider/capability registries. A separate,
    explicitly governed deployment step must apply it after review.
    """

    provider_id = record.provider_id.strip()
    allowed = _PROVIDER_CAPABILITIES.get(provider_id)
    if allowed is None:
        raise ValueError(f"Unsupported provider acceptance record: {provider_id or '<blank>'}")

    if record.status.strip().lower() not in {"pass", "approved"}:
        raise PermissionError("Provider-backed acceptance status is not approved.")
    if not record.provider_backed:
        raise PermissionError("Provider activation requires provider-backed evidence.")
    if not record.read_only:
        raise PermissionError("Provider-read acceptance must prove a read-only path.")
    if not record.credential_boundary_proven:
        raise PermissionError("Provider credential boundary has not been proven.")
    if record.protected_values_exposed:
        raise PermissionError("Protected values were exposed during provider acceptance.")
    if record.raw_provider_payload_persisted:
        raise PermissionError("Raw provider payload persistence is not accepted.")
    if record.hosted_model_used:
        raise PermissionError(
            "Provider-read acceptance must use the deterministic connector path without "
            "a separately billed hosted model."
        )
    if record.observed_at.tzinfo is None or record.observed_at.utcoffset() is None:
        raise ValueError("Provider acceptance observed_at must be timezone-aware.")

    evidence_reference = record.evidence_reference.strip()
    if not evidence_reference:
        raise ValueError("Provider acceptance requires a durable evidence reference.")

    verified = frozenset(_nonblank(record.verified_capabilities))
    if not verified:
        raise ValueError("Provider acceptance must verify at least one canonical capability.")
    unknown = sorted(verified - allowed)
    if unknown:
        raise ValueError(
            "Provider acceptance names unsupported canonical capabilities: "
            + ", ".join(unknown)
        )

    return ProviderReadActivationPlan(
        provider_id=provider_id,
        verified_capabilities=tuple(sorted(verified)),
        target_provider_lifecycle="available",
        target_provider_health="healthy",
        target_capability_lifecycle="active",
        evidence_reference=evidence_reference,
        hosted_model_required=False,
    )


def _nonblank(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Verified capability names must be non-empty strings.")
        result.append(value.strip())
    return tuple(result)
