from __future__ import annotations

from datetime import datetime, timezone

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

from .service import CAPABILITY_NAME, SES_PROVIDER_ID

REGISTERED_AT = datetime(2026, 8, 10, tzinfo=timezone.utc)
CAPABILITY_VERSION = "0.1"


def email_send_capability() -> CapabilityDefinition:
    """Return the conservative pilot definition for governed email sending.

    JAC-007 is the communication/service-delivery architectural mapping for this
    vertical slice; the stable operational identity remains communication.email.send.
    """
    return CapabilityDefinition(
        capability_name=CAPABILITY_NAME,
        version=CAPABILITY_VERSION,
        display_name="Governed Email Send",
        lifecycle_status=CapabilityLifecycle.PILOT,
        business_purpose="Send authorized, auditable operational email through a governed provider.",
        owner_service="Jason Communication Service",
        architectural_capability_ids=frozenset({"JAC-007"}),
        risk_level=CapabilityRisk.HIGH,
        data_classifications=frozenset({"internal", "confidential"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="cap-007://communication.email.send/input/0.1",
        output_schema_reference="cap-007://communication.email.send/output/0.1",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(
            required=True,
            approver_classes=("service-manager", "architecture-authority"),
        ),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester context",
                "approved sender policy",
                "recipient scope",
                "governed provider resolution",
            ),
            verification_requirements=(
                "provider message identifier on accepted send",
                "audit-safe attempted/completed/failed event trail",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="Fail closed; do not retry automatically or fall back to another transport.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="architecture-authority",
            business_justification="Jason requires one reusable governed communication primitive instead of workflow-specific send scripts.",
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by an approved provider-neutral communication capability with equal or stronger controls.",
                "No longer required by a real TeamAOT workflow.",
            ),
            operational_owner="TeamAOT Operations",
            approval_owner="TeamAOT Service Management",
            authoritative_change_sources=("AWS SES", "Jason Constitution", "JKD-003", "JKD-004"),
        ),
        created_at=REGISTERED_AT,
        metadata={
            "roadmap_id": "CAP-007",
            "architectural_domain": "communication-and-service-delivery",
            "initial_provider": SES_PROVIDER_ID,
            "secret_name": "aws_ses.sendmail",
            "pilot_scope": "explicit-approval-only",
            "conversation_action_enabled": "true",
            "conversation_argument_keys": "to,subject,text_body,html_body,cc,bcc,reply_to,from_address",
            "conversation_self_target_field": "to",
            "conversation_default_subject": "Message from Jason",
            "conversation_default_text_body": "You asked Jason to send you an email.",
            "conversation_authenticated_imperative_is_approval": "true",
        },
    )


def aws_ses_provider() -> ExecutionProvider:
    """Return the pilot provider record for AWS SES.

    HEALTHY here means the provider is eligible for the controlled pilot record;
    live activation still requires the separate readiness and check-only gates.
    """
    return ExecutionProvider(
        provider_id=SES_PROVIDER_ID,
        display_name="AWS Simple Email Service",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({CAPABILITY_NAME}),
        supported_classifications=frozenset({"internal", "confidential"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=5,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="aws-ses-pilot-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="AWS SES is the initial replaceable transport for governed outbound email.",
            review_interval_days=90,
            last_reviewed_at=REGISTERED_AT,
            retirement_criteria=(
                "A lower-risk approved provider satisfies the same capability.",
                "AWS SES no longer meets TeamAOT operational or security requirements.",
            ),
            vendor_change_sources=("AWS SES service documentation",),
            operational_owner="TeamAOT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=REGISTERED_AT,
        metadata={
            "secret_name": "aws_ses.sendmail",
            "credentials": "JKD-003-only",
            "automatic_fallback": "prohibited",
            "activation_gate": "controlled-pilot-readiness-required",
        },
    )


def register_email_send(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> None:
    """Register the CAP-007 pilot records through canonical Kernel services."""
    capabilities.register(email_send_capability())
    providers.register(aws_ses_provider())
