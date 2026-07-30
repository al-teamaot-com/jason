from __future__ import annotations

from .models import AudienceProfile, AudienceType, MessagePurpose


DEFAULT_AUDIENCE_PROFILES: dict[AudienceType, AudienceProfile] = {
    AudienceType.INTERNAL_TECHNICIAN: AudienceProfile(
        audience_type=AudienceType.INTERNAL_TECHNICIAN,
        max_technical_depth=5,
        formality="professional_direct",
        target_reading_level="technical",
        allow_raw_logs=True,
        allow_internal_notes=True,
        allowed_channels=frozenset({"email", "teams", "telegram", "portal"}),
    ),
    AudienceType.SERVICE_MANAGER: AudienceProfile(
        audience_type=AudienceType.SERVICE_MANAGER,
        max_technical_depth=4,
        formality="professional_summary",
        target_reading_level="business_technical",
        allow_raw_logs=False,
        allow_internal_notes=True,
        allowed_channels=frozenset({"email", "teams", "portal"}),
        required_elements=("impact", "next_step"),
    ),
    AudienceType.EXECUTIVE: AudienceProfile(
        audience_type=AudienceType.EXECUTIVE,
        max_technical_depth=2,
        formality="executive",
        target_reading_level="business",
        allow_raw_logs=False,
        allow_internal_notes=False,
        allowed_channels=frozenset({"email", "teams", "portal", "sms", "voice"}),
        required_elements=("business_impact", "recommended_action"),
    ),
    AudienceType.CLIENT_END_USER: AudienceProfile(
        audience_type=AudienceType.CLIENT_END_USER,
        max_technical_depth=1,
        formality="clear_reassuring",
        target_reading_level="plain_language",
        allow_raw_logs=False,
        allow_internal_notes=False,
        allowed_channels=frozenset({"email", "sms", "portal", "voice"}),
        prohibited_terms=("user error", "obviously", "simply"),
        required_elements=("plain_language_summary", "next_step"),
    ),
    AudienceType.CLIENT_DECISION_MAKER: AudienceProfile(
        audience_type=AudienceType.CLIENT_DECISION_MAKER,
        max_technical_depth=2,
        formality="professional_business",
        target_reading_level="business",
        allow_raw_logs=False,
        allow_internal_notes=False,
        allowed_channels=frozenset({"email", "sms", "portal", "voice"}),
        required_elements=("impact", "options", "recommended_action"),
    ),
    AudienceType.VENDOR: AudienceProfile(
        audience_type=AudienceType.VENDOR,
        max_technical_depth=4,
        formality="professional_factual",
        target_reading_level="technical_business",
        allow_raw_logs=True,
        allow_internal_notes=False,
        allowed_channels=frozenset({"email", "portal"}),
        required_elements=("observed_behavior", "requested_action"),
    ),
    AudienceType.LEGAL_COMPLIANCE: AudienceProfile(
        audience_type=AudienceType.LEGAL_COMPLIANCE,
        max_technical_depth=3,
        formality="formal_precise",
        target_reading_level="professional",
        allow_raw_logs=False,
        allow_internal_notes=False,
        allowed_channels=frozenset({"email", "portal"}),
        required_elements=("facts", "scope", "evidence_reference"),
    ),
    AudienceType.PUBLIC_MARKETING: AudienceProfile(
        audience_type=AudienceType.PUBLIC_MARKETING,
        max_technical_depth=1,
        formality="brand_approved",
        target_reading_level="plain_language",
        allow_raw_logs=False,
        allow_internal_notes=False,
        allowed_channels=frozenset({"email", "sms", "web", "social"}),
        required_elements=("approved_brand_voice",),
    ),
}


PURPOSE_APPROVAL_ROLES: dict[MessagePurpose, tuple[str, ...]] = {
    MessagePurpose.OPERATIONAL: (),
    MessagePurpose.TICKET_UPDATE: (),
    MessagePurpose.APPROVAL_REQUEST: (),
    MessagePurpose.SECURITY_INCIDENT: ("security_approver",),
    MessagePurpose.LEGAL_COMPLIANCE: ("compliance_approver",),
    MessagePurpose.FINANCIAL: ("financial_approver",),
    MessagePurpose.EMERGENCY: ("incident_commander",),
    MessagePurpose.MARKETING: ("marketing_approver",),
}


SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("password", "credential_reference"),
    ("api key", "credential_reference"),
    ("secret key", "credential_reference"),
    ("recovery code", "credential_reference"),
    ("credit card", "payment_card_reference"),
    ("social security", "government_identifier_reference"),
)


INTERNAL_ONLY_MARKERS: tuple[str, ...] = (
    "internal only",
    "do not send to client",
    "technician note",
    "private note",
)


RAW_LOG_MARKERS: tuple[str, ...] = (
    "<-start diagnostic->",
    "stack trace",
    "exception:",
    "event id:",
    "0x800",
)
