from __future__ import annotations

from collections import Counter

from .models import (
    AudienceType,
    CommunicationDraft,
    CommunicationReview,
    ReviewDecision,
    ReviewFinding,
)
from .policy import (
    DEFAULT_AUDIENCE_PROFILES,
    INTERNAL_ONLY_MARKERS,
    PURPOSE_APPROVAL_ROLES,
    RAW_LOG_MARKERS,
    SENSITIVE_PATTERNS,
)


class AudiencePolicyEngine:
    """Deterministic communication gate. AI rewriting is optional and subordinate."""

    def review(self, draft: CommunicationDraft) -> CommunicationReview:
        findings: list[ReviewFinding] = []
        approver_roles = set(PURPOSE_APPROVAL_ROLES[draft.purpose])
        body_lower = draft.body.lower()

        if not draft.recipients:
            findings.append(ReviewFinding("recipient.missing", "At least one recipient is required.", "block"))

        audiences = tuple(dict.fromkeys(r.audience_type for r in draft.recipients))
        if len(audiences) > 1:
            findings.append(
                ReviewFinding(
                    "audience.mixed",
                    "Recipients have different audience types; separate messages are recommended.",
                    "revision",
                )
            )

        for recipient in draft.recipients:
            profile = DEFAULT_AUDIENCE_PROFILES[recipient.audience_type]
            if recipient.organization_id != draft.organization_id:
                findings.append(
                    ReviewFinding(
                        "scope.organization_mismatch",
                        "Recipient belongs to a different organization.",
                        "block",
                        recipient.recipient_id,
                    )
                )
            if recipient.client_id != draft.client_id:
                findings.append(
                    ReviewFinding(
                        "scope.client_mismatch",
                        "Recipient does not match the communication client scope.",
                        "block",
                        recipient.recipient_id,
                    )
                )
            if draft.channel not in profile.allowed_channels:
                findings.append(
                    ReviewFinding(
                        "channel.not_allowed",
                        f"Channel {draft.channel!r} is not allowed for this audience.",
                        "block",
                        recipient.recipient_id,
                    )
                )
            for term in profile.prohibited_terms:
                if term in body_lower:
                    findings.append(
                        ReviewFinding(
                            "tone.prohibited_term",
                            f"Message contains audience-inappropriate wording: {term!r}.",
                            "revision",
                            recipient.recipient_id,
                        )
                    )
            if not profile.allow_internal_notes and any(marker in body_lower for marker in INTERNAL_ONLY_MARKERS):
                findings.append(
                    ReviewFinding(
                        "disclosure.internal_note",
                        "Message appears to contain internal-only content.",
                        "block",
                        recipient.recipient_id,
                    )
                )
            if not profile.allow_raw_logs and any(marker in body_lower for marker in RAW_LOG_MARKERS):
                findings.append(
                    ReviewFinding(
                        "disclosure.raw_log",
                        "Raw technical diagnostic content is not appropriate for this audience.",
                        "revision",
                        recipient.recipient_id,
                    )
                )

        for text, code in SENSITIVE_PATTERNS:
            if text in body_lower:
                findings.append(
                    ReviewFinding(
                        f"sensitive.{code}",
                        "Message may contain sensitive information and requires review.",
                        "approval",
                    )
                )
                approver_roles.add("security_approver")

        if draft.attachment_refs and any(
            r.audience_type not in {AudienceType.INTERNAL_TECHNICIAN, AudienceType.VENDOR}
            for r in draft.recipients
        ):
            findings.append(
                ReviewFinding(
                    "attachment.external_review",
                    "Attachments to external or nontechnical audiences require content review.",
                    "approval",
                )
            )
            approver_roles.add("communication_approver")

        decision = self._decision(findings, approver_roles)
        return CommunicationReview(
            decision=decision,
            findings=tuple(findings),
            required_approver_roles=tuple(sorted(approver_roles)),
            normalized_audiences=audiences,
        )

    @staticmethod
    def _decision(findings: list[ReviewFinding], approver_roles: set[str]) -> ReviewDecision:
        counts = Counter(f.severity for f in findings)
        if counts["block"]:
            return ReviewDecision.BLOCK
        if counts["revision"]:
            return ReviewDecision.REQUIRE_REVISION
        if counts["approval"] or approver_roles:
            return ReviewDecision.REQUIRE_APPROVAL
        return ReviewDecision.ALLOW
