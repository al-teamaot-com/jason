from __future__ import annotations

from dataclasses import replace

from kernel.system_registry.contracts import (
    EntityLifecycle,
    Observation,
    RegistryEntity,
    VerificationOutcome,
    VerificationRecord,
)


class DuplicateRegistryEntityError(ValueError):
    """Raised when a registry ID already exists."""


class RegistryEntityNotFoundError(LookupError):
    """Raised when a registry entity does not exist."""


class InvalidLifecycleTransitionError(ValueError):
    """Raised when lifecycle advancement violates registry governance."""


_ALLOWED_TRANSITIONS: dict[EntityLifecycle, frozenset[EntityLifecycle]] = {
    EntityLifecycle.PROPOSED: frozenset({EntityLifecycle.REGISTERED}),
    EntityLifecycle.REGISTERED: frozenset(
        {EntityLifecycle.CONFIGURED, EntityLifecycle.RETIRED}
    ),
    EntityLifecycle.CONFIGURED: frozenset(
        {EntityLifecycle.VERIFIED, EntityLifecycle.SUSPENDED, EntityLifecycle.RETIRED}
    ),
    EntityLifecycle.VERIFIED: frozenset(
        {EntityLifecycle.ACTIVE, EntityLifecycle.SUSPENDED, EntityLifecycle.RETIRED}
    ),
    EntityLifecycle.ACTIVE: frozenset(
        {EntityLifecycle.DEPRECATED, EntityLifecycle.SUSPENDED}
    ),
    EntityLifecycle.DEPRECATED: frozenset(
        {EntityLifecycle.SUSPENDED, EntityLifecycle.RETIRED}
    ),
    EntityLifecycle.SUSPENDED: frozenset(
        {EntityLifecycle.CONFIGURED, EntityLifecycle.RETIRED}
    ),
    EntityLifecycle.RETIRED: frozenset(),
}


class InMemorySystemRegistry:
    def __init__(self) -> None:
        self._entities: dict[str, RegistryEntity] = {}
        self._observations: dict[str, list[Observation]] = {}
        self._verifications: dict[str, list[VerificationRecord]] = {}

    def register(self, entity: RegistryEntity) -> None:
        if entity.registry_id in self._entities:
            raise DuplicateRegistryEntityError(
                f"Registry entity already exists: {entity.registry_id}"
            )

        missing_dependencies = sorted(
            dependency
            for dependency in entity.dependencies
            if dependency not in self._entities
        )
        if missing_dependencies:
            raise RegistryEntityNotFoundError(
                "Dependencies must be registered first: "
                + ", ".join(missing_dependencies)
            )

        self._entities[entity.registry_id] = entity

    def get(self, registry_id: str) -> RegistryEntity:
        try:
            return self._entities[registry_id]
        except KeyError as error:
            raise RegistryEntityNotFoundError(
                f"Registry entity was not found: {registry_id}"
            ) from error

    def list_all(self) -> tuple[RegistryEntity, ...]:
        return tuple(
            sorted(
                self._entities.values(),
                key=lambda entity: entity.registry_id,
            )
        )

    def dependents_of(self, registry_id: str) -> tuple[RegistryEntity, ...]:
        self.get(registry_id)
        return tuple(
            sorted(
                (
                    entity
                    for entity in self._entities.values()
                    if registry_id in entity.dependencies
                ),
                key=lambda entity: entity.registry_id,
            )
        )

    def record_observation(self, observation: Observation) -> None:
        self.get(observation.registry_id)
        self._observations.setdefault(observation.registry_id, []).append(
            observation
        )

    def latest_observation(self, registry_id: str) -> Observation | None:
        self.get(registry_id)
        observations = self._observations.get(registry_id, [])
        if not observations:
            return None
        return max(observations, key=lambda item: item.observed_at)

    def record_verification(self, record: VerificationRecord) -> None:
        entity = self.get(record.registry_id)
        if record.method not in entity.verification_methods:
            raise ValueError(
                f"Verification method is not registered for {record.registry_id}: "
                f"{record.method}"
            )
        self._verifications.setdefault(record.registry_id, []).append(record)

    def verify_from_latest_observation(
        self,
        *,
        registry_id: str,
        method: str,
        verified_at,
    ) -> VerificationRecord:
        entity = self.get(registry_id)
        if method not in entity.verification_methods:
            raise ValueError(
                f"Verification method is not registered for {registry_id}: {method}"
            )

        observation = self.latest_observation(registry_id)
        if observation is None:
            record = VerificationRecord(
                registry_id=registry_id,
                method=method,
                outcome=VerificationOutcome.UNVERIFIED,
                verified_at=verified_at,
                detail="No observation is available.",
            )
            self.record_verification(record)
            return record

        missing_keys = sorted(
            key
            for key in entity.declared_state
            if key not in observation.observed_state
        )
        mismatched_keys = sorted(
            key
            for key, declared_value in entity.declared_state.items()
            if (
                key in observation.observed_state
                and observation.observed_state[key] != declared_value
            )
        )

        if mismatched_keys:
            outcome = VerificationOutcome.DRIFTED
            detail = "Declared and observed state differ for: " + ", ".join(
                mismatched_keys
            )
        elif missing_keys:
            outcome = VerificationOutcome.UNVERIFIED
            detail = "Observation lacks declared fields: " + ", ".join(
                missing_keys
            )
        else:
            outcome = VerificationOutcome.VERIFIED
            detail = "Observed state satisfies declared state."

        record = VerificationRecord(
            registry_id=registry_id,
            method=method,
            outcome=outcome,
            verified_at=verified_at,
            observation_source=observation.source,
            evidence_references=observation.evidence_references,
            detail=detail,
        )
        self.record_verification(record)
        return record

    def latest_verification(
        self,
        registry_id: str,
    ) -> VerificationRecord | None:
        self.get(registry_id)
        records = self._verifications.get(registry_id, [])
        if not records:
            return None
        return max(records, key=lambda item: item.verified_at)

    def transition_lifecycle(
        self,
        *,
        registry_id: str,
        lifecycle_status: EntityLifecycle,
    ) -> RegistryEntity:
        current = self.get(registry_id)
        if lifecycle_status not in _ALLOWED_TRANSITIONS[current.lifecycle_status]:
            raise InvalidLifecycleTransitionError(
                "Invalid lifecycle transition: "
                f"{current.lifecycle_status.value} -> {lifecycle_status.value}"
            )

        if lifecycle_status in {
            EntityLifecycle.VERIFIED,
            EntityLifecycle.ACTIVE,
        }:
            latest = self.latest_verification(registry_id)
            if latest is None or latest.outcome is not VerificationOutcome.VERIFIED:
                raise InvalidLifecycleTransitionError(
                    "Verified or active lifecycle requires a successful verification."
                )

        updated = replace(current, lifecycle_status=lifecycle_status)
        self._entities[registry_id] = updated
        return updated
