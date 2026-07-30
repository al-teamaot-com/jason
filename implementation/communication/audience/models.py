from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class AudienceType(str, Enum):
    INTERNAL_TECHNICIAN = "internal_technician"
    SERVICE_MANAGER = "service_manager"
    EXECUTIVE = "executive"
    CLIENT_END_USER = "client_end_user"
    CLIENT_DECISION_MAKER = "client_decision_maker"
    VENDOR = "vendor"
    LEGAL_COMPLIANCE = "legal_compliance"
    PUBLIC_MARKETING = "public_marketing"


class MessagePurpose(str, Enum):
    OPERATIONAL = "operational"
    TICKET_UPDATE = "ticket_update"
    APPROVAL_REQUEST = "approval_request"
    SECURITY_INCIDENT = "security_incident"
    LEGAL_COMPLIANCE = "legal_compliance"
    FINANCIAL = "financial"
    EMERGENCY = "emergency"
    MARKETING = "marketing"


class ReviewDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_REVISION = "require_revision"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


@dataclass(frozen=True)
class Recipient:
    recipient_id: str
    organization_id: str
    client_id: str | None
    audience_type: AudienceType
    channel_address: str
    preferred_name: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CommunicationDraft:
    communication_id: str
    correlation_id: str
    organization_id: str
    client_id: str | None
    sender_identity: str
    channel: str
    purpose: MessagePurpose
    subject: str | None
    body: str
    recipients: Sequence[Recipient]
    attachment_refs: Sequence[str] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AudienceProfile:
    audience_type: AudienceType
    max_technical_depth: int
    formality: str
    target_reading_level: str
    allow_raw_logs: bool
    allow_internal_notes: bool
    allowed_channels: frozenset[str]
    prohibited_terms: tuple[str, ...] = ()
    required_elements: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewFinding:
    code: str
    message: str
    severity: str
    recipient_id: str | None = None


@dataclass(frozen=True)
class CommunicationReview:
    decision: ReviewDecision
    findings: tuple[ReviewFinding, ...]
    required_approver_roles: tuple[str, ...] = ()
    normalized_audiences: tuple[AudienceType, ...] = ()
