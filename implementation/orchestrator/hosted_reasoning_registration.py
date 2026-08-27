"""Canonical runtime registration for hosted conversation reasoning."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_policy import (
    ExecutionMode,
    InMemoryPricingRegistry,
    PriceConfidence,
    PricingEntry,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)


OPENAI_CONVERSATION_PROVIDER_ID = "openai-conversation-kernel"
OPENAI_CONVERSATION_CAPABILITY = "conversation.intent.interpret"
OPENAI_CONVERSATION_EVIDENCE_CAPABILITY = "conversation.evidence.assess"
OPENAI_CONVERSATION_PRICING_PROFILE = "pricing-openai-gpt-5.4-nano-2026-08"


def register_openai_conversation_provider(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    pricing: InMemoryPricingRegistry,
    now: datetime,
    model: str,
) -> None:
    """Register the governed hosted Conversation Kernel capability, provider and pricing."""

    model = model.strip()
    if not model:
        raise ValueError("hosted conversation model is required")

    capabilities.register(
        CapabilityDefinition(
            capability_name=OPENAI_CONVERSATION_CAPABILITY,
            version="0.1",
            display_name="Interpret Human Conversation Intent",
            lifecycle_status=CapabilityLifecycle.PILOT,
            business_purpose=(
                "Produce a bounded provider-independent interpretation of a human "
                "conversation turn for deterministic Jason validation."
            ),
            owner_service="Jason Conversation Kernel",
            architectural_capability_ids=frozenset({"JAC-005"}),
            risk_level=CapabilityRisk.LOW,
            data_classifications=frozenset({"internal"}),
            permitted_execution_modes=frozenset({"hosted_ai"}),
            input_schema_reference=(
                "schema://jason/conversation-interpretation-request/0.1"
            ),
            output_schema_reference=(
                "schema://jason/conversation-kernel-decision/0.1"
            ),
            invoking_roles=frozenset({"conversation-kernel"}),
            approval=CapabilityApproval(required=False),
            evidence=CapabilityEvidence(
                required=True,
                requirements=(
                    "local hosted-processing eligibility decision",
                    "minimum-necessary context projection",
                    "deterministic structured-output validation",
                    "append-only hosted reasoning audit evidence",
                    "model usage ledger entry for every provider attempt",
                ),
                verification_requirements=(
                    "hosted provider has no operational execution authority",
                    "restricted content cannot reach hosted transport",
                    "prompt and response bodies are excluded from durable audit",
                ),
            ),
            dependencies=frozenset(),
            idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
            idempotency_key_required=False,
            timeout_seconds=120,
            maximum_attempts=2,
            failure_behavior=(
                "Fail closed for hosted processing and permit only separately "
                "configured governed local reasoning fallback."
            ),
            tenant_isolation_required=True,
            client_isolation_required=False,
            stewardship=CapabilityStewardship(
                steward="technology-steward",
                business_justification=(
                    "Use a low-cost hosted model only for bounded human-language "
                    "interpretation when local policy explicitly permits egress."
                ),
                review_interval_days=90,
                retirement_criteria=(
                    "A local model satisfies required interpretation reliability and latency.",
                    "Hosted conversation processing is prohibited by governance.",
                    "A replacement governed reasoning capability supersedes this capability.",
                ),
                authoritative_change_sources=(
                    "Jason Conversation Kernel governance",
                    "OpenAI provider lifecycle",
                ),
                operational_owner="AOT IT Operations",
                approval_owner="Jason Architecture Authority",
            ),
            created_at=now,
            metadata={
                "provider_neutral": "true",
                "read_only": "true",
                "advisory_only": "true",
                "execution_authority": "none",
                "hosted_egress_requires_policy": "true",
            },
        )
    )


    capabilities.register(
        CapabilityDefinition(
            capability_name=OPENAI_CONVERSATION_EVIDENCE_CAPABILITY,
            version="0.1",
            display_name="Assess Bounded Conversation Evidence",
            lifecycle_status=CapabilityLifecycle.PILOT,
            business_purpose=(
                "Navigate and independently assess a bounded sanitized evidence "
                "view for a provider-independent information need while deterministic "
                "Jason validation retains authority over selected evidence."
            ),
            owner_service="Jason Conversation Evidence",
            architectural_capability_ids=frozenset({"JAC-005"}),
            risk_level=CapabilityRisk.LOW,
            data_classifications=frozenset({"internal"}),
            permitted_execution_modes=frozenset({"hosted_ai"}),
            input_schema_reference=(
                "schema://jason/conversation-evidence-reasoning-request/0.1"
            ),
            output_schema_reference=(
                "schema://jason/conversation-evidence-reasoning-decision/0.1"
            ),
            invoking_roles=frozenset({"conversation-evidence"}),
            approval=CapabilityApproval(required=False),
            evidence=CapabilityEvidence(
                required=True,
                requirements=(
                    "local hosted-processing eligibility decision",
                    "minimum-necessary sanitized evidence projection",
                    "deterministic offered-path validation",
                    "independent bounded evidence review",
                    "append-only hosted reasoning audit evidence",
                    "model usage ledger entry for every provider attempt",
                ),
                verification_requirements=(
                    "hosted provider has no operational execution authority",
                    "identity and transport scope remain local",
                    "restricted content cannot reach hosted transport",
                    "selected pointers are validated locally against offered evidence",
                    "operational values are dereferenced locally after approval",
                    "prompt and response bodies are excluded from durable audit",
                ),
            ),
            dependencies=frozenset(),
            idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
            idempotency_key_required=False,
            timeout_seconds=120,
            maximum_attempts=2,
            failure_behavior=(
                "Fail closed when hosted evidence reasoning is not authorized "
                "or cannot satisfy deterministic validation."
            ),
            tenant_isolation_required=True,
            client_isolation_required=False,
            stewardship=CapabilityStewardship(
                steward="technology-steward",
                business_justification=(
                    "Use a governed low-cost hosted model for bounded semantic "
                    "evidence navigation when the approved local model does not "
                    "meet required reliability."
                ),
                review_interval_days=90,
                retirement_criteria=(
                    "An approved local model satisfies evidence reasoning reliability and latency.",
                    "Hosted evidence processing is prohibited by governance.",
                    "A replacement governed reasoning capability supersedes this capability.",
                ),
                authoritative_change_sources=(
                    "Jason Conversation Evidence governance",
                    "OpenAI provider lifecycle",
                ),
                operational_owner="AOT IT Operations",
                approval_owner="Jason Architecture Authority",
            ),
            created_at=now,
            metadata={
                "provider_neutral": "true",
                "read_only": "true",
                "advisory_only": "true",
                "execution_authority": "none",
                "hosted_egress_requires_policy": "true",
                "deterministic_pointer_validation": "required",
            },
        )
    )

    pricing.add(
        PricingEntry(
            provider_id=OPENAI_CONVERSATION_PROVIDER_ID,
            model_id=model,
            execution_mode=ExecutionMode.HOSTED_AI,
            input_cost_per_million_tokens=Decimal("0.20"),
            output_cost_per_million_tokens=Decimal("1.25"),
            request_cost=Decimal("0"),
            pricing_version="openai-gpt-5.4-nano-2026-08",
            confidence=PriceConfidence.HIGH,
        )
    )

    providers.register(
        ExecutionProvider(
            provider_id=OPENAI_CONVERSATION_PROVIDER_ID,
            display_name="OpenAI Hosted Conversation Kernel",
            provider_type=ProviderType.HOSTED_AI,
            lifecycle_status=ProviderLifecycle.AVAILABLE,
            health_status=ProviderHealth.HEALTHY,
            approval_status=ProviderApproval.PILOT,
            execution_modes=frozenset({"hosted_ai"}),
            capabilities=frozenset(
                {
                    OPENAI_CONVERSATION_CAPABILITY,
                    OPENAI_CONVERSATION_EVIDENCE_CAPABILITY,
                }
            ),
            supported_classifications=frozenset({"internal"}),
            regions=frozenset(),
            limits=ProviderLimits(
                maximum_output_tokens=768,
                maximum_execution_seconds=120,
            ),
            features=ProviderFeatures(
                structured_output=True,
            ),
            pricing_profile_id=OPENAI_CONVERSATION_PRICING_PROFILE,
            stewardship=ProviderStewardship(
                technology_steward="technology-steward",
                business_justification=(
                    "Low-cost bounded human-language interpretation for Jason's "
                    "Conversation Kernel when local policy permits hosted processing."
                ),
                review_interval_days=90,
                last_reviewed_at=now,
                retirement_criteria=(
                    "A lower-cost approved provider meets or exceeds required reliability.",
                    "A local model meets required reliability and latency.",
                    "Hosted conversation processing is prohibited by governance.",
                ),
                vendor_change_sources=("OpenAI API documentation and pricing",),
                operational_owner="technology-steward",
                approval_owner="architecture-authority",
            ),
            created_at=now,
            metadata={
                "model_id": model,
                "role": "conversation-kernel-proposer",
                "minimum_context": "required",
                "retention_requested": "false",
            },
        )
    )
