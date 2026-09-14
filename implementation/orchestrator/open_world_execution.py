"""Execute open-world query plans through Jason's normal governed boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .governed_query import (
    DeterministicGovernedQueryEngine,
    GovernedQueryResult,
)
from .open_world_evidence_materialization import OpenWorldEvidenceMaterializer
from .open_world_query_planning import OpenWorldQueryPlan
from .open_world_schema import DiscoveredResourceSchema, OpenWorldResourceCatalog
from .teams_conversation_flow import ConversationIntent


class OpenWorldExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenWorldExecutionResult:
    query_result: GovernedQueryResult
    orchestrations: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class OpenWorldExecutionCoordinator:
    materializer: OpenWorldEvidenceMaterializer
    query_engine: DeterministicGovernedQueryEngine

    def execute(
        self,
        *,
        plan: OpenWorldQueryPlan,
        catalog: OpenWorldResourceCatalog,
        executor,
    ) -> OpenWorldExecutionResult:
        resources = {resource.resource_handle: resource for resource in catalog.resources}
        datasets = []
        orchestrations = []

        for source in plan.sources:
            resource = resources.get(source.resource_handle)
            if resource is None:
                raise OpenWorldExecutionError(
                    "query references an unavailable governed resource"
                )

            intent = self._intent(
                resource=resource,
                selector_reference=source.selector_reference,
                field_paths=source.field_paths,
            )

            if resource.provider_resource_handle is None:
                result = executor.execute(intent)
            else:
                result = self._execute_provider_bound_intent(
                    executor=executor,
                    intent=intent,
                    required_provider_id=resource.provider_id,
                )

            orchestrations.append(result)
            datasets.append(
                self.materializer.materialize(
                    source=source,
                    resource=resource,
                    results=(result,),
                )
            )

        result = self.query_engine.execute(
            plan=plan.relational_plan,
            datasets=tuple(datasets),
        )
        return OpenWorldExecutionResult(
            query_result=result,
            orchestrations=tuple(orchestrations),
        )

    @staticmethod
    def _execute_provider_bound_intent(
        *,
        executor,
        intent: ConversationIntent,
        required_provider_id: str,
    ):
        """Carry trusted catalog provider affinity through the normal governed path.

        ``required_provider_id`` originates in the provider-discovered catalog, not in
        model output.  The normal bound request factory still performs Jason authority
        evaluation and creates the execution context; only then is provider affinity
        attached before Central Orchestrator resolution.
        """

        provider_id = str(required_provider_id).strip()
        if not provider_id:
            raise OpenWorldExecutionError(
                "provider-discovered resource is missing provider affinity"
            )

        required_attributes = (
            "request_factory",
            "orchestrator",
            "principal",
            "identity",
            "correlation_id",
        )
        if any(not hasattr(executor, name) for name in required_attributes):
            raise OpenWorldExecutionError(
                "provider-discovered execution requires the bound governed intent executor"
            )

        request = executor.request_factory.build(
            principal=executor.principal,
            intent=intent,
            identity=executor.identity,
            correlation_id=executor.correlation_id,
        )
        if request.required_provider_id not in {None, provider_id}:
            raise OpenWorldExecutionError(
                "request factory produced conflicting provider affinity"
            )
        request = replace(request, required_provider_id=provider_id)

        validator = getattr(executor, "_validate", None)
        if callable(validator):
            validator(request=request, intent=intent)
        else:
            if request.correlation_id != executor.correlation_id:
                raise PermissionError(
                    "request factory changed the governed turn correlation identity"
                )
            if request.capability_name != intent.capability_name:
                raise PermissionError(
                    "request factory changed the governed capability intent"
                )

        result = executor.orchestrator.execute(request)
        if result.correlation_id != executor.correlation_id:
            raise PermissionError(
                "Central Orchestrator result changed the governed turn correlation identity"
            )
        if result.capability_name != intent.capability_name:
            raise PermissionError(
                "Central Orchestrator result does not match the governed conversation intent"
            )

        results = getattr(executor, "results", None)
        if isinstance(results, list):
            results.append(result)
        return result

    def _intent(
        self,
        *,
        resource: DiscoveredResourceSchema,
        selector_reference: str | None,
        field_paths: tuple[str, ...] = (),
    ) -> ConversationIntent:
        arguments: dict[str, Any] = {}
        reference = (selector_reference or "").strip()

        if resource.collection_supported:
            if reference:
                arguments["selector"] = reference
        else:
            if not reference:
                raise OpenWorldExecutionError(
                    "selector-only resource requires a grounded selector"
                )
            arguments["selector"] = reference

        if resource.provider_resource_handle is not None:
            if not field_paths:
                raise OpenWorldExecutionError(
                    "provider-discovered resource requires a bounded field projection"
                )
            available_fields = {field.path for field in resource.fields}
            invalid_fields = tuple(path for path in field_paths if path not in available_fields)
            if invalid_fields:
                raise OpenWorldExecutionError(
                    "provider-discovered execution references fields outside the governed schema"
                )
            arguments["provider_resource_handle"] = resource.provider_resource_handle
            arguments["field_paths"] = tuple(dict.fromkeys(field_paths))

        return ConversationIntent(
            capability_name=resource.capability_name,
            arguments=arguments,
            execution_mode="deterministic",
            permission_mode="observe",
            risk="low",
        )
