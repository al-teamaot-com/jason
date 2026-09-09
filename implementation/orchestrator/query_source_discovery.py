"""Discover governed query sources from runtime capability/provider registries.

This module performs implementation discovery after semantic planning.

The semantic planner says WHAT resource types and canonical facts are needed.
This layer discovers WHICH registered governed capabilities and approved execution
providers can contribute those facts.

It contains no:
- human question mappings
- provider ids
- connector ids
- vendor names
- domain-specific routing
- credential access
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
)

from .semantic_query_planning import (
    SemanticQuerySource,
)


class QuerySourceDiscoveryError(LookupError):
    """A semantic source could not be bound to governed runtime capabilities."""


@dataclass(frozen=True, slots=True)
class QuerySourceContribution:
    """One provider/capability able to contribute canonical source facts."""

    provider_id: str
    capability_name: str
    resource_type: str
    canonical_facts: tuple[str, ...]
    operation: str
    selector_keys: tuple[str, ...]
    selector_required: bool
    collection_scope: str | None
    permission_mode: str = "observe"
    risk: str = "low"
    description: str = "Governed resource read"

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError(
                "query source contribution provider_id is required"
            )
        if not self.capability_name.strip():
            raise ValueError(
                "query source contribution capability_name is required"
            )
        if not self.resource_type.strip():
            raise ValueError(
                "query source contribution resource_type is required"
            )
        if not self.canonical_facts:
            raise ValueError(
                "query source contribution requires canonical facts"
            )
        if self.operation not in {
            "search",
            "read",
        }:
            raise ValueError(
                "query source contribution operation is invalid"
            )
        if self.permission_mode != "observe":
            raise ValueError(
                "query source contribution must remain observe-only"
            )
        if not self.risk.strip():
            raise ValueError(
                "query source contribution risk is required"
            )
        if not self.description.strip():
            raise ValueError(
                "query source contribution description is required"
            )


@dataclass(frozen=True, slots=True)
class QuerySourceBinding:
    """Runtime implementation binding for one provider-neutral semantic source."""

    source_alias: str
    resource_type: str
    required_facts: tuple[str, ...]
    contributions: tuple[QuerySourceContribution, ...]

    def __post_init__(self) -> None:
        if not self.source_alias.strip():
            raise ValueError(
                "query source binding alias is required"
            )
        if not self.resource_type.strip():
            raise ValueError(
                "query source binding resource_type is required"
            )
        if not self.required_facts:
            raise ValueError(
                "query source binding requires facts"
            )
        if not self.contributions:
            raise ValueError(
                "query source binding requires contributions"
            )

    @property
    def covered_facts(
        self,
    ) -> tuple[str, ...]:
        available = {
            fact
            for contribution in self.contributions
            for fact in contribution.canonical_facts
        }
        return tuple(
            fact
            for fact in self.required_facts
            if fact in available
        )


@dataclass(frozen=True, slots=True)
class GovernedQuerySourceDiscovery:
    """Bind semantic sources to currently registered governed runtime truth."""

    capabilities: CapabilityRegistryService
    providers: ExecutionProviderRegistryService
    include_pilot: bool = True

    def discover(
        self,
        source: SemanticQuerySource,
    ) -> QuerySourceBinding:
        required = tuple(
            dict.fromkeys(
                fact.strip()
                for fact in source.required_facts
                if fact.strip()
            )
        )

        candidates = self._capabilities_for(
            source=source,
        )

        contributions: list[
            QuerySourceContribution
        ] = []

        for capability in candidates:
            capability_name = (
                capability.capability_name
            )

            canonical_facts = _csv(
                capability.metadata.get(
                    "canonical_facts",
                    "",
                )
            )

            relevant = tuple(
                fact
                for fact in required
                if fact in canonical_facts
            )

            if not relevant:
                continue

            for provider in self.providers.list_all():
                if not _provider_available(
                    provider
                ):
                    continue

                if (
                    capability_name
                    not in provider.capabilities
                ):
                    continue

                contributions.append(
                    QuerySourceContribution(
                        provider_id=(
                            provider.provider_id
                        ),
                        capability_name=(
                            capability_name
                        ),
                        resource_type=(
                            source.resource_type
                        ),
                        canonical_facts=relevant,
                        operation=str(
                            capability.metadata.get(
                                "operation",
                                "",
                            )
                        )
                        .strip()
                        .casefold(),
                        selector_keys=_csv(
                            capability.metadata.get(
                                "selector_keys",
                                "",
                            )
                        ),
                        selector_required=_truthy(
                            capability.metadata.get(
                                "selector_required",
                                "true",
                            )
                        ),
                        collection_scope=(
                            str(
                                capability.metadata.get(
                                    "collection_scope",
                                    "",
                                )
                            ).strip()
                            or None
                        ),
                        permission_mode=str(
                            capability.metadata.get(
                                "conversation_permission_mode",
                                "observe",
                            )
                        ).strip(),
                        risk=capability.risk_level.value,
                        description=" ".join(
                            part
                            for part in (
                                capability.display_name.strip(),
                                capability.business_purpose.strip(),
                            )
                            if part
                        ),
                    )
                )

        contributions.sort(
            key=lambda item: (
                item.capability_name.casefold(),
                item.provider_id.casefold(),
                item.canonical_facts,
            )
        )

        if not contributions:
            raise QuerySourceDiscoveryError(
                "no registered governed capability/provider "
                "combination covers required canonical facts: "
                + ", ".join(required)
            )

        binding = QuerySourceBinding(
            source_alias=source.alias,
            resource_type=(
                source.resource_type
            ),
            required_facts=required,
            contributions=tuple(
                contributions
            ),
        )

        missing = tuple(
            fact
            for fact in required
            if fact not in set(
                binding.covered_facts
            )
        )

        if missing:
            raise QuerySourceDiscoveryError(
                "no registered governed capability/provider "
                "combination covers required canonical facts: "
                + ", ".join(missing)
            )

        return binding

    def discover_all(
        self,
        sources: Sequence[
            SemanticQuerySource
        ],
    ) -> tuple[
        QuerySourceBinding,
        ...,
    ]:
        return tuple(
            self.discover(source)
            for source in sources
        )

    def _capabilities_for(
        self,
        *,
        source: SemanticQuerySource,
    ):
        matches = []

        for capability in (
            self.capabilities.list_all()
        ):
            if (
                capability.lifecycle_status
                is CapabilityLifecycle.ACTIVE
            ):
                pass
            elif (
                self.include_pilot
                and capability.lifecycle_status
                is CapabilityLifecycle.PILOT
            ):
                pass
            else:
                continue

            metadata = capability.metadata

            if not _truthy(
                metadata.get(
                    "provider_neutral",
                    "false",
                )
            ):
                continue

            if not _truthy(
                metadata.get(
                    "read_only",
                    "false",
                )
            ):
                continue

            resource_types = _csv(
                metadata.get(
                    "resource_types",
                    "",
                )
            )

            if (
                source.resource_type
                not in resource_types
            ):
                continue

            operation = str(
                metadata.get(
                    "operation",
                    "",
                )
            ).strip().casefold()

            if operation not in {
                "search",
                "read",
            }:
                continue

            if (
                source.scope == "collection"
                and not (
                    operation == "search"
                    and not _truthy(
                        metadata.get(
                            "selector_required",
                            "true",
                        )
                    )
                    and str(
                        metadata.get(
                            "collection_scope",
                            "",
                        )
                    ).strip()
                )
            ):
                continue

            if (
                source.scope == "single"
                and not _csv(
                    metadata.get(
                        "selector_keys",
                        "",
                    )
                )
            ):
                continue

            matches.append(
                capability
            )

        return tuple(
            matches
        )


def _provider_available(
    provider: ExecutionProvider,
) -> bool:
    lifecycle = str(
        getattr(
            provider.lifecycle_status,
            "value",
            provider.lifecycle_status,
        )
    ).strip().casefold()

    health = str(
        getattr(
            provider.health_status,
            "value",
            provider.health_status,
        )
    ).strip().casefold()

    approval = str(
        getattr(
            provider.approval_status,
            "value",
            provider.approval_status,
        )
    ).strip().casefold()

    if lifecycle != "available":
        return False

    if health != "healthy":
        return False

    if approval != "approved":
        return False

    return True


def _truthy(
    value,
) -> bool:
    return (
        str(value)
        .strip()
        .casefold()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def _csv(
    value,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in str(value).split(",")
            if item.strip()
        )
    )


@dataclass(frozen=True, slots=True)
class RuntimeSemanticQueryUniverseBuilder:
    """Build the planner universe from current governed runtime truth.

    Only read-only, provider-neutral capabilities backed by an available,
    approved, healthy execution provider are exposed to semantic planning.

    Adding another compliant provider/capability therefore expands the semantic
    universe without changing this code.
    """

    capabilities: CapabilityRegistryService
    providers: ExecutionProviderRegistryService
    include_pilot: bool = True

    def build(self):
        from .semantic_query_planning import (
            SemanticQueryFact,
            SemanticQueryResource,
            SemanticQueryUniverse,
        )

        resource_facts: dict[
            str,
            dict[str, str | None],
        ] = {}

        collection_support: dict[
            str,
            bool,
        ] = {}

        selector_support: dict[
            str,
            bool,
        ] = {}

        providers = tuple(
            provider
            for provider in self.providers.list_all()
            if _provider_available(provider)
        )

        for capability in self.capabilities.list_all():
            if (
                capability.lifecycle_status
                is CapabilityLifecycle.ACTIVE
            ):
                pass
            elif (
                self.include_pilot
                and capability.lifecycle_status
                is CapabilityLifecycle.PILOT
            ):
                pass
            else:
                continue

            metadata = capability.metadata

            if not _truthy(
                metadata.get(
                    "provider_neutral",
                    "false",
                )
            ):
                continue

            if not _truthy(
                metadata.get(
                    "read_only",
                    "false",
                )
            ):
                continue

            operation = str(
                metadata.get(
                    "operation",
                    "",
                )
            ).strip().casefold()

            if operation not in {
                "search",
                "read",
            }:
                continue

            if not any(
                capability.capability_name
                in provider.capabilities
                for provider in providers
            ):
                continue

            resources = _csv(
                metadata.get(
                    "resource_types",
                    "",
                )
            )

            facts = _csv(
                metadata.get(
                    "canonical_facts",
                    "",
                )
            )

            if not resources or not facts:
                continue

            expected_shapes = _fact_shapes(
                metadata.get(
                    "canonical_fact_shapes",
                    "",
                )
            )

            supports_collection = (
                operation == "search"
                and not _truthy(
                    metadata.get(
                        "selector_required",
                        "true",
                    )
                )
                and bool(
                    str(
                        metadata.get(
                            "collection_scope",
                            "",
                        )
                    ).strip()
                )
            )

            supports_selector = bool(
                _csv(
                    metadata.get(
                        "selector_keys",
                        "",
                    )
                )
            )

            for resource_type in resources:
                fact_map = (
                    resource_facts.setdefault(
                        resource_type,
                        {},
                    )
                )

                for fact in facts:
                    shape = expected_shapes.get(
                        fact
                    )

                    existing = fact_map.get(
                        fact
                    )

                    if (
                        existing is not None
                        and shape is not None
                        and existing != shape
                    ):
                        raise QuerySourceDiscoveryError(
                            "conflicting canonical fact shape "
                            f"declarations for {resource_type}:{fact}"
                        )

                    if fact not in fact_map:
                        fact_map[
                            fact
                        ] = shape
                    elif fact_map[
                        fact
                    ] is None:
                        fact_map[
                            fact
                        ] = shape

                collection_support[
                    resource_type
                ] = (
                    collection_support.get(
                        resource_type,
                        False,
                    )
                    or supports_collection
                )

                selector_support[
                    resource_type
                ] = (
                    selector_support.get(
                        resource_type,
                        False,
                    )
                    or supports_selector
                )

        resources = tuple(
            SemanticQueryResource(
                resource_type=resource_type,
                facts=tuple(
                    SemanticQueryFact(
                        name=fact,
                        expected_shape=shape,
                    )
                    for fact, shape
                    in sorted(
                        facts.items(),
                        key=lambda item: (
                            item[0].casefold()
                        ),
                    )
                ),
                collection_supported=(
                    collection_support.get(
                        resource_type,
                        False,
                    )
                ),
                selector_supported=(
                    selector_support.get(
                        resource_type,
                        False,
                    )
                ),
            )
            for resource_type, facts
            in sorted(
                resource_facts.items(),
                key=lambda item: (
                    item[0].casefold()
                ),
            )
        )

        if not resources:
            raise QuerySourceDiscoveryError(
                "runtime exposes no governed semantic query resources"
            )

        return SemanticQueryUniverse(
            resources=resources
        )


def _fact_shapes(
    value,
) -> dict[str, str]:
    """Decode optional fact=shape capability metadata.

    Shape metadata is advisory planning information only. The existing evidence
    interpreter remains authoritative for verified operational values.
    """

    output = {}

    for item in _csv(value):
        if "=" not in item:
            continue

        fact, shape = item.split(
            "=",
            1,
        )

        fact = fact.strip()
        shape = shape.strip()

        if fact and shape:
            output[
                fact
            ] = shape

    return output
