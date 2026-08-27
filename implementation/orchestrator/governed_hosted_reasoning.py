"""Governed boundary for external structured reasoning.

Every hosted request crosses local classification, minimum-necessary projection,
canonical provider eligibility, Execution Policy Engine evaluation, append-only audit,
and Usage Ledger accounting before its result can participate in Jason reasoning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping
from uuid import uuid4

from kernel.execution_policy import (
    CostEstimator,
    DecisionOutcome,
    ExecutionBudget,
    ExecutionCandidate,
    ExecutionMode,
    ExecutionPolicyEngine,
    ExecutionRequest,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    ProviderCandidateQuery,
)
from usage_ledger.adapters import from_openai_response
from usage_ledger.contracts import (
    AttemptOutcome,
    CostUsage,
    TokenUsage,
    UsageContext,
    UsageEntry,
    UsageSource,
)

from .hosted_reasoning_egress import HostedReasoningEgressClassifier


class HostedReasoningPolicyDenied(PermissionError):
    """Hosted reasoning was not authorized by Jason's local policy boundary."""


@dataclass(frozen=True, slots=True)
class GovernedHostedReasoningClient:
    client: Any
    policy: ExecutionPolicyEngine
    cost_estimator: CostEstimator
    providers: ExecutionProviderRegistryService
    audit: Any
    usage_ledger: Any
    provider_id: str
    model_id: str
    classifier: HostedReasoningEgressClassifier
    payload_projector: Callable[[str], str] | None = None
    capability: str = "conversation.intent.interpret"
    capability_version: str = "0.1"
    maximum_input_tokens: int = 12000
    maximum_output_tokens: int = 768
    maximum_attempts: int = 2
    maximum_estimated_cost: Decimal = Decimal("0.02")

    @property
    def model(self) -> str:
        return self.model_id

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]:
        organization_id = _organization_id(user)
        principal_id = _principal_id(user)
        correlation_id = _correlation_id(user)

        projector = (
            self.payload_projector
            if self.payload_projector is not None
            else _minimum_kernel_payload
        )
        minimized_user = projector(user)

        # Classify the exact bounded payload eligible to leave Jason.
        # Internal transport, identity, organization, and correlation
        # metadata remain local for authority and audit and must not
        # influence hosted-egress classification after projection.
        egress = self.classifier.classify(
            user_payload=minimized_user
        )

        execution_id = f"reasoning_{uuid4().hex}"
        attempt_id = f"attempt_{uuid4().hex}"

        eligible = self.providers.find_candidates(
            ProviderCandidateQuery(
                capability=self.capability,
                execution_mode="hosted_ai",
                classification=None,
                allow_pilot=True,
            )
        )

        provider = next(
            (item for item in eligible if item.provider_id == self.provider_id),
            None,
        )

        if provider is None:
            self._audit(
                "hosted.reasoning.policy_denied",
                execution_id=execution_id,
                correlation_id=correlation_id,
                organization_id=organization_id,
                principal_id=principal_id,
                details={
                    "classification": egress.classification,
                    "reason_codes": ["provider_ineligible"],
                },
            )
            raise HostedReasoningPolicyDenied(
                "hosted reasoning provider is not eligible"
            )

        registered_model = str(provider.metadata.get("model_id", "")).strip()

        if registered_model != self.model_id:
            self._audit(
                "hosted.reasoning.policy_denied",
                execution_id=execution_id,
                correlation_id=correlation_id,
                organization_id=organization_id,
                principal_id=principal_id,
                details={
                    "classification": egress.classification,
                    "reason_codes": ["registered_model_mismatch"],
                },
            )
            raise HostedReasoningPolicyDenied(
                "hosted reasoning model does not match canonical provider state"
            )

        estimated_input = _estimate_tokens(system, minimized_user)

        request = ExecutionRequest(
            execution_id=execution_id,
            correlation_id=correlation_id,
            capability=self.capability,
            capability_version=self.capability_version,
            tenant_id=organization_id,
            client_id=None,
            requested_mode="hosted_ai",
            authority_allowed=True,
            approval_present=False,
            risk="low",
            data_handling=egress.data_handling,
            budget=ExecutionBudget(
                maximum_estimated_cost=self.maximum_estimated_cost,
                maximum_input_tokens=self.maximum_input_tokens,
                maximum_output_tokens=min(
                    self.maximum_output_tokens,
                    max_output_tokens,
                ),
                maximum_attempts=self.maximum_attempts,
            ),
            candidates=(
                ExecutionCandidate(
                    execution_mode=ExecutionMode.HOSTED_AI,
                    provider_id=self.provider_id,
                    model_id=self.model_id,
                    estimated_input_tokens=estimated_input,
                    estimated_output_tokens=max_output_tokens,
                    estimated_attempts=1,
                    approved=True,
                    healthy=True,
                    supports_classifications=provider.supported_classifications,
                ),
            ),
            policy_ids=(
                "policy-hosted-reasoning-egress",
                "policy-minimum-necessary-context",
            ),
        )

        decision = self.policy.evaluate(request)

        if (
            decision.outcome is not DecisionOutcome.ALLOWED
            or decision.execution_mode is not ExecutionMode.HOSTED_AI
            or decision.plan is None
        ):
            self._audit(
                "hosted.reasoning.policy_denied",
                execution_id=execution_id,
                correlation_id=correlation_id,
                organization_id=organization_id,
                principal_id=principal_id,
                details={
                    "classification": egress.classification,
                    "reason_codes": list(decision.reason_codes),
                    "redaction_profile": egress.redaction_profile,
                    "retention_allowed": False,
                },
            )
            raise HostedReasoningPolicyDenied(
                "hosted reasoning denied by local Jason policy"
            )

        self._audit(
            "hosted.reasoning.policy_allowed",
            execution_id=execution_id,
            correlation_id=correlation_id,
            organization_id=organization_id,
            principal_id=principal_id,
            details={
                "classification": egress.classification,
                "reason_codes": list(decision.reason_codes),
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "redaction_profile": egress.redaction_profile,
                "minimum_context_applied": True,
                "retention_allowed": False,
                "estimated_input_tokens": estimated_input,
                "maximum_output_tokens": max_output_tokens,
                "estimated_cost": str(
                    decision.plan.estimated_cost.total_estimated_cost
                ),
            },
        )

        usage_context = UsageContext(
            workflow_id=correlation_id,
            request_id=execution_id,
            attempt_id=attempt_id,
            organization_id=organization_id,
            client_id=None,
            capability=self.capability,
            routing_profile=self.provider_id,
            metadata={
                "classification": egress.classification,
                "minimum_context_applied": True,
            },
        )

        started_at = datetime.now(timezone.utc)

        self._audit(
            "hosted.reasoning.started",
            execution_id=execution_id,
            correlation_id=correlation_id,
            organization_id=organization_id,
            principal_id=principal_id,
            details={
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "attempt_id": attempt_id,
            },
        )

        try:
            if hasattr(self.client, "complete_with_response"):
                output, raw_response = self.client.complete_with_response(
                    system=system,
                    user=minimized_user,
                    schema=schema,
                    max_output_tokens=max_output_tokens,
                )

                usage_entry = from_openai_response(
                    context=usage_context,
                    model=self.model_id,
                    response=raw_response,
                    outcome=AttemptOutcome.COMPLETED,
                    started_at=started_at,
                )

                if (
                    usage_entry.tokens.input_tokens is not None
                    and usage_entry.tokens.output_tokens is not None
                ):
                    actual_cost = self.cost_estimator.calculate_token_usage_cost(
                        provider_id=self.provider_id,
                        model_id=self.model_id,
                        execution_mode=ExecutionMode.HOSTED_AI,
                        input_tokens=usage_entry.tokens.input_tokens,
                        cached_input_tokens=(
                            usage_entry.tokens.cached_input_tokens or 0
                        ),
                        output_tokens=usage_entry.tokens.output_tokens,
                    )
                    calculated_cost = actual_cost.total_estimated_cost
                    calculated_currency = actual_cost.currency
                    pricing_version = actual_cost.pricing_version
                else:
                    calculated_cost = None
                    calculated_currency = decision.plan.estimated_cost.currency
                    pricing_version = decision.plan.estimated_cost.pricing_version

                usage_entry = replace(
                    usage_entry,
                    cost=CostUsage(
                        calculated_cost=calculated_cost,
                        currency=calculated_currency,
                    ),
                    metadata={
                        **dict(usage_entry.metadata),
                        "classification": egress.classification,
                        "minimum_context_applied": True,
                        "pricing_version": pricing_version,
                        "pre_execution_estimated_cost": str(
                            decision.plan.estimated_cost.total_estimated_cost
                        ),
                    },
                )
            else:
                output = self.client.complete(
                    system=system,
                    user=minimized_user,
                    schema=schema,
                    max_output_tokens=max_output_tokens,
                )

                usage_entry = UsageEntry(
                    entry_id=f"usage_{uuid4().hex}",
                    context=usage_context,
                    provider=self.provider_id,
                    model=self.model_id,
                    outcome=AttemptOutcome.COMPLETED,
                    usage_source=UsageSource.UNKNOWN,
                    tokens=TokenUsage(),
                    cost=CostUsage(
                        calculated_cost=None,
                        currency=decision.plan.estimated_cost.currency,
                    ),
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                    confidence=0.0,
                    metadata={
                        "classification": egress.classification,
                        "minimum_context_applied": True,
                        "pre_execution_estimated_cost": str(
                            decision.plan.estimated_cost.total_estimated_cost
                        ),
                    },
                )

            self.usage_ledger.append(usage_entry)

            self._audit(
                "hosted.reasoning.completed",
                execution_id=execution_id,
                correlation_id=correlation_id,
                organization_id=organization_id,
                principal_id=principal_id,
                details={
                    "provider_id": self.provider_id,
                    "model_id": self.model_id,
                    "attempt_id": attempt_id,
                    "input_tokens": usage_entry.tokens.input_tokens,
                    "cached_input_tokens": usage_entry.tokens.cached_input_tokens,
                    "output_tokens": usage_entry.tokens.output_tokens,
                    "reasoning_tokens": usage_entry.tokens.reasoning_tokens,
                    "total_tokens": usage_entry.tokens.total_tokens,
                    "calculated_cost": (
                        None
                        if usage_entry.cost.calculated_cost is None
                        else str(usage_entry.cost.calculated_cost)
                    ),
                    "provider_request_id": usage_entry.provider_request_id,
                },
            )

            return output

        except Exception as error:
            provider_response = getattr(error, "response", None)

            if isinstance(provider_response, Mapping):
                failure_entry = from_openai_response(
                    context=usage_context,
                    model=self.model_id,
                    response=provider_response,
                    outcome=AttemptOutcome.FAILED,
                    started_at=started_at,
                )

                if (
                    failure_entry.tokens.input_tokens is not None
                    and failure_entry.tokens.output_tokens is not None
                ):
                    actual_failure_cost = (
                        self.cost_estimator.calculate_token_usage_cost(
                            provider_id=self.provider_id,
                            model_id=self.model_id,
                            execution_mode=ExecutionMode.HOSTED_AI,
                            input_tokens=failure_entry.tokens.input_tokens,
                            cached_input_tokens=(
                                failure_entry.tokens.cached_input_tokens or 0
                            ),
                            output_tokens=failure_entry.tokens.output_tokens,
                        )
                    )
                    failure_entry = replace(
                        failure_entry,
                        cost=CostUsage(
                            calculated_cost=(
                                actual_failure_cost.total_estimated_cost
                            ),
                            currency=actual_failure_cost.currency,
                        ),
                        metadata={
                            "classification": egress.classification,
                            "minimum_context_applied": True,
                            "failure_type": type(error).__name__,
                            "pricing_version": (
                                actual_failure_cost.pricing_version
                            ),
                            "pre_execution_estimated_cost": str(
                                decision.plan.estimated_cost.total_estimated_cost
                            ),
                        },
                    )
            else:
                failure_entry = UsageEntry(
                entry_id=f"usage_{uuid4().hex}",
                context=usage_context,
                provider=self.provider_id,
                model=self.model_id,
                outcome=(
                    AttemptOutcome.TIMED_OUT
                    if isinstance(error, TimeoutError)
                    else AttemptOutcome.FAILED
                ),
                usage_source=UsageSource.UNKNOWN,
                tokens=TokenUsage(),
                cost=CostUsage(
                    calculated_cost=decision.plan.estimated_cost.total_estimated_cost,
                    currency=decision.plan.estimated_cost.currency,
                ),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                confidence=0.0,
                    metadata={
                        "classification": egress.classification,
                        "minimum_context_applied": True,
                        "failure_type": type(error).__name__,
                        "pre_execution_estimated_cost": str(
                            decision.plan.estimated_cost.total_estimated_cost
                        ),
                    },
                )

            self.usage_ledger.append(failure_entry)

            self._audit(
                "hosted.reasoning.failed",
                execution_id=execution_id,
                correlation_id=correlation_id,
                organization_id=organization_id,
                principal_id=principal_id,
                details={
                    "provider_id": self.provider_id,
                    "model_id": self.model_id,
                    "attempt_id": attempt_id,
                    "failure_type": type(error).__name__,
                },
            )

            raise

    def _audit(
        self,
        event_type: str,
        *,
        execution_id: str,
        correlation_id: str,
        organization_id: str,
        principal_id: str,
        details: Mapping[str, Any],
    ) -> None:
        self.audit.append(
            event_type,
            {
                "execution_id": execution_id,
                "correlation_id": correlation_id,
                "organization_id": organization_id,
                "principal_id": principal_id,
                "capability_name": self.capability,
                "stage": "hosted_reasoning",
                "details": dict(details),
            },
        )


def _minimum_kernel_payload(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HostedReasoningPolicyDenied(
            "hosted reasoning payload is not valid bounded JSON"
        ) from error

    if not isinstance(payload, Mapping):
        raise HostedReasoningPolicyDenied(
            "hosted reasoning payload must be an object"
        )

    message = payload.get("message")
    context = payload.get("context", {})
    resource_kinds = payload.get(
        "available_resource_kinds",
        [],
    )
    resource_descriptions = payload.get(
        "resource_kind_descriptions",
        {},
    )

    if not isinstance(message, str) or not message.strip():
        raise HostedReasoningPolicyDenied(
            "hosted reasoning message is missing"
        )

    if not isinstance(context, Mapping):
        raise HostedReasoningPolicyDenied(
            "hosted reasoning context is invalid"
        )

    if not isinstance(resource_kinds, list):
        raise HostedReasoningPolicyDenied(
            "hosted reasoning resource vocabulary is invalid"
        )

    normalized_resource_kinds = []
    seen_resource_kinds = set()

    for raw_kind in resource_kinds:
        if not isinstance(raw_kind, str):
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource kind is invalid"
            )

        kind = raw_kind.strip()

        if not kind:
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource kind is empty"
            )

        if len(kind) > 256:
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource kind exceeds safety bound"
            )

        if kind not in seen_resource_kinds:
            normalized_resource_kinds.append(kind)
            seen_resource_kinds.add(kind)

    if len(normalized_resource_kinds) > 256:
        raise HostedReasoningPolicyDenied(
            "hosted reasoning resource vocabulary exceeds safety bound"
        )

    if not isinstance(resource_descriptions, Mapping):
        raise HostedReasoningPolicyDenied(
            "hosted reasoning resource descriptions are invalid"
        )

    normalized_resource_descriptions = {}

    for raw_kind, raw_description in resource_descriptions.items():
        if not isinstance(raw_kind, str):
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource description key is invalid"
            )

        kind = raw_kind.strip()

        if kind not in seen_resource_kinds:
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource description references "
                "an unavailable resource kind"
            )

        if not isinstance(raw_description, str):
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource description is invalid"
            )

        description = " ".join(
            raw_description.split()
        )

        if not description:
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource description is empty"
            )

        if len(description) > 2048:
            raise HostedReasoningPolicyDenied(
                "hosted reasoning resource description exceeds safety bound"
            )

        normalized_resource_descriptions[kind] = description

    minimum = {
        "message": message,
        "context": {
            "active_topic": context.get("active_topic"),
            "active_entity_refs": context.get("active_entity_refs", {}),
            "active_entities": context.get("active_entities", []),
            "entities": [
                {
                    "ref": item.get("ref"),
                    "kind": item.get("kind"),
                    "canonical_id": item.get("canonical_id"),
                    "display_name": item.get("display_name"),
                }
                for item in context.get("entities", [])
                if isinstance(item, Mapping)
            ],
            "recent_resolutions": context.get("recent_resolutions", []),
        },
    }

    if normalized_resource_kinds:
        minimum["available_resource_kinds"] = (
            normalized_resource_kinds
        )

    if normalized_resource_descriptions:
        minimum["resource_kind_descriptions"] = {
            kind: normalized_resource_descriptions[kind]
            for kind in normalized_resource_kinds
            if kind in normalized_resource_descriptions
        }

    return json.dumps(
        minimum,
        ensure_ascii=False,
        separators=(",", ":"),
    )



def minimum_evidence_payload(raw: str) -> str:
    """Return the bounded evidence reasoning payload eligible for hosted egress.

    Authentication, organization and conversation identifiers remain local.
    Only the provider-neutral information need and already-sanitized bounded
    evidence view required for the current reasoning operation may leave Jason.
    """

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HostedReasoningPolicyDenied(
            "hosted evidence reasoning payload is not valid bounded JSON"
        ) from error

    if not isinstance(payload, Mapping):
        raise HostedReasoningPolicyDenied(
            "hosted evidence reasoning payload must be an object"
        )

    information_need = payload.get("information_need")

    if (
        not isinstance(information_need, str)
        or not information_need.strip()
        or len(information_need) > 2048
    ):
        raise HostedReasoningPolicyDenied(
            "hosted evidence information need is invalid"
        )

    minimum: dict[str, Any] = {
        "information_need": information_need.strip(),
    }

    if "evidence_frontier" in payload:
        frontier = payload["evidence_frontier"]

        if not isinstance(frontier, list) or len(frontier) > 48:
            raise HostedReasoningPolicyDenied(
                "hosted evidence frontier exceeds safety bound"
            )

        minimum["evidence_frontier"] = frontier

    if "evidence_catalog" in payload:
        catalog = payload["evidence_catalog"]

        if not isinstance(catalog, list) or len(catalog) > 96:
            raise HostedReasoningPolicyDenied(
                "hosted evidence catalog exceeds safety bound"
            )

        minimum["evidence_catalog"] = catalog

    if "proposed" in payload:
        proposed = payload["proposed"]

        if not isinstance(proposed, Mapping):
            raise HostedReasoningPolicyDenied(
                "hosted evidence review proposal is invalid"
            )

        minimum["proposed"] = dict(proposed)

    if len(minimum) == 1:
        raise HostedReasoningPolicyDenied(
            "hosted evidence payload contains no bounded evidence view"
        )

    encoded = json.dumps(
        minimum,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    if len(encoded) > 20000:
        raise HostedReasoningPolicyDenied(
            "hosted evidence payload exceeds minimum-context safety bound"
        )

    return encoded


def _organization_id(raw: str) -> str:
    payload = _payload(raw)
    context = payload.get("context", {})
    value = str(context.get("organization_id", "")).strip()

    if not value:
        raise HostedReasoningPolicyDenied(
            "organization scope is required for hosted reasoning"
        )

    return value


def _principal_id(raw: str) -> str:
    payload = _payload(raw)
    context = payload.get("context", {})
    value = str(context.get("principal_id", "")).strip()

    if not value:
        raise HostedReasoningPolicyDenied(
            "principal scope is required for hosted reasoning"
        )

    return value


def _correlation_id(raw: str) -> str:
    payload = _payload(raw)
    context = payload.get("context", {})
    value = str(context.get("conversation_id", "")).strip()

    return value or f"conversation_{uuid4().hex}"


def _payload(raw: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(raw)
    except Exception as error:
        raise HostedReasoningPolicyDenied(
            "hosted reasoning scope could not be established locally"
        ) from error

    if not isinstance(payload, Mapping):
        raise HostedReasoningPolicyDenied(
            "hosted reasoning scope payload is invalid"
        )

    return payload


def _estimate_tokens(system: str, user: str) -> int:
    chars = len(system) + len(user)
    return max(1, (chars + 2) // 3)
