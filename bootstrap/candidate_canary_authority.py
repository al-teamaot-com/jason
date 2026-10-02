from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Mapping, Sequence

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
    validate_candidate_host_identity,
)
from kernel.identity_authority import AuthorityGrant, IdentityRecord, PermissionMode
from kernel.identity_authority.durable import SQLiteIdentityAuthorityStore
from orchestrator.provider_health_canary_policy import (
    PROVIDER_HEALTH_CANARY_PRINCIPAL,
    PROVIDER_HEALTH_CANARY_SPECS,
)


class CandidateCanaryAuthorityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CanaryAuthorityReceipt:
    schema_version: str
    instance_id: str
    organization_id: str
    principal_id: str
    provider_ids: tuple[str, ...]
    capabilities: tuple[str, ...]
    grant_ids: tuple[str, ...]
    effective_from: str
    effective_until: str
    permission: str
    approval_required: bool


def _specs_by_provider() -> dict[str, Mapping[str, object]]:
    return {
        str(item["provider_id"]): item
        for item in PROVIDER_HEALTH_CANARY_SPECS
    }


def provision_candidate_canary_authority(
    *,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity,
    organization_id: str,
    provider_ids: Sequence[str],
    now: datetime | None = None,
    lifetime_minutes: int = 60,
) -> CanaryAuthorityReceipt:
    validate_candidate_host_identity(candidate_identity)
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="candidate canary authority",
    )

    organization = organization_id.strip()
    if not organization:
        raise CandidateCanaryAuthorityError(
            "acceptance organization_id must be non-empty"
        )
    providers = tuple(sorted(set(str(item).strip() for item in provider_ids if str(item).strip())))
    if not providers:
        raise CandidateCanaryAuthorityError(
            "at least one canary provider must be selected"
        )
    specs = _specs_by_provider()
    unknown = sorted(set(providers) - set(specs))
    if unknown:
        raise CandidateCanaryAuthorityError(
            "unsupported canary providers: " + ",".join(unknown)
        )
    if lifetime_minutes < 1 or lifetime_minutes > 240:
        raise CandidateCanaryAuthorityError(
            "canary authority lifetime must be between 1 and 240 minutes"
        )

    issued = now or datetime.now(timezone.utc)
    if issued.tzinfo is None:
        raise CandidateCanaryAuthorityError("now must be timezone-aware")
    expires = issued + timedelta(minutes=lifetime_minutes)

    store = SQLiteIdentityAuthorityStore(
        root / "var/lib/jason/authority/authority.sqlite3"
    )
    try:
        existing = store.get_identity(PROVIDER_HEALTH_CANARY_PRINCIPAL)
        expected = IdentityRecord(
            PROVIDER_HEALTH_CANARY_PRINCIPAL,
            "service",
            organization,
        )
        if existing is not None and existing != expected:
            raise CandidateCanaryAuthorityError(
                "existing canary identity conflicts with candidate acceptance scope"
            )
        store.put_identity(expected)

        grant_ids: list[str] = []
        capabilities: list[str] = []
        for provider in providers:
            capability = str(specs[provider]["capability_name"])
            material = (
                candidate_identity.instance_id
                + "|"
                + organization
                + "|"
                + provider
                + "|"
                + capability
            )
            grant_id = (
                "acceptance-canary-"
                + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
            )
            expected_grant = AuthorityGrant(
                grant_id=grant_id,
                subject_id=PROVIDER_HEALTH_CANARY_PRINCIPAL,
                capability=capability,
                organization_id=organization,
                client_id=None,
                permission=PermissionMode.OBSERVE,
                approval_required=False,
                effective_from=issued,
                effective_until=expires,
                status="active",
            )
            current = store.get_grant(grant_id)
            if current is not None and current != expected_grant:
                raise CandidateCanaryAuthorityError(
                    f"existing canary grant conflicts with acceptance scope: {grant_id}"
                )
            store.put_grant(expected_grant)
            grant_ids.append(grant_id)
            capabilities.append(capability)
    finally:
        store.close()

    return CanaryAuthorityReceipt(
        schema_version="1.0",
        instance_id=candidate_identity.instance_id,
        organization_id=organization,
        principal_id=PROVIDER_HEALTH_CANARY_PRINCIPAL,
        provider_ids=providers,
        capabilities=tuple(capabilities),
        grant_ids=tuple(grant_ids),
        effective_from=issued.isoformat(),
        effective_until=expires.isoformat(),
        permission=PermissionMode.OBSERVE.value,
        approval_required=False,
    )
