from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping


REGISTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
FORBIDDEN_ATTRIBUTE_KEY_PATTERN = re.compile(
    r"(^|[._-])(password|passwd|secret|token|api[_-]?key|private[_-]?key)([._-]|$)",
    re.IGNORECASE,
)


class EntityType(str, Enum):
    COMPONENT = "component"
    CAPABILITY = "capability"
    PROVIDER = "provider"
    RESOURCE = "resource"
    IDENTITY_BINDING = "identity_binding"
    GOVERNANCE_GATE = "governance_gate"
    CREDENTIAL_REFERENCE = "credential_reference"
    DEPLOYMENT = "deployment"


class EntityLifecycle(str, Enum):
    PROPOSED = "proposed"
    REGISTERED = "registered"
    CONFIGURED = "configured"
    VERIFIED = "verified"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class VerificationOutcome(str, Enum):
    VERIFIED = "verified"
    DRIFTED = "drifted"
    UNVERIFIED = "unverified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CredentialReference:
    provider: str
    reference: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("credential provider must be non-empty.")
        if not self.reference.strip():
            raise ValueError("credential reference must be non-empty.")


@dataclass(frozen=True, slots=True)
class RegistryEntity:
    registry_id: str
    entity_type: EntityType
    display_name: str
    environment: str
    lifecycle_status: EntityLifecycle
    declared_state: Mapping[str, str]
    dependencies: frozenset[str]
    verification_methods: tuple[str, ...]
    steward: str
    authority_references: tuple[str, ...] = ()
    credential_references: tuple[CredentialReference, ...] = ()
    evidence_references: tuple[str, ...] = ()
    source_version: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not REGISTRY_ID_PATTERN.fullmatch(self.registry_id):
            raise ValueError(f"Invalid registry ID: {self.registry_id}")
        if not self.display_name.strip():
            raise ValueError("display_name must be non-empty.")
        if not self.environment.strip():
            raise ValueError("environment must be non-empty.")
        if not self.steward.strip():
            raise ValueError("steward must be non-empty.")
        if self.registry_id in self.dependencies:
            raise ValueError("A registry entity cannot depend on itself.")
        for dependency in self.dependencies:
            if not REGISTRY_ID_PATTERN.fullmatch(dependency):
                raise ValueError(f"Invalid dependency registry ID: {dependency}")
        if self.lifecycle_status in {
            EntityLifecycle.CONFIGURED,
            EntityLifecycle.VERIFIED,
            EntityLifecycle.ACTIVE,
        } and not self.verification_methods:
            raise ValueError(
                "Configured, verified, and active entities require a verification method."
            )
        _assert_no_secret_fields(self.declared_state)
        _assert_no_secret_fields(self.metadata)


@dataclass(frozen=True, slots=True)
class Observation:
    registry_id: str
    source: str
    observed_at: datetime
    observed_state: Mapping[str, str]
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not REGISTRY_ID_PATTERN.fullmatch(self.registry_id):
            raise ValueError(f"Invalid registry ID: {self.registry_id}")
        if not self.source.strip():
            raise ValueError("observation source must be non-empty.")
        _assert_no_secret_fields(self.observed_state)


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    registry_id: str
    method: str
    outcome: VerificationOutcome
    verified_at: datetime
    observation_source: str | None = None
    evidence_references: tuple[str, ...] = ()
    detail: str | None = None

    def __post_init__(self) -> None:
        if not REGISTRY_ID_PATTERN.fullmatch(self.registry_id):
            raise ValueError(f"Invalid registry ID: {self.registry_id}")
        if not self.method.strip():
            raise ValueError("verification method must be non-empty.")


def _assert_no_secret_fields(values: Mapping[str, str]) -> None:
    for key in values:
        if FORBIDDEN_ATTRIBUTE_KEY_PATTERN.search(key):
            raise ValueError(
                "Secret-bearing fields are prohibited in the System Registry; "
                f"use a CredentialReference instead: {key}"
            )
