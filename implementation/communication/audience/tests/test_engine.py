from communication.audience.engine import AudiencePolicyEngine
from communication.audience.models import (
    AudienceType,
    CommunicationDraft,
    MessagePurpose,
    Recipient,
    ReviewDecision,
)


def _recipient(audience: AudienceType, client_id: str | None = "client-1") -> Recipient:
    return Recipient(
        recipient_id="recipient-1",
        organization_id="aot",
        client_id=client_id,
        audience_type=audience,
        channel_address="person@example.com",
    )


def _draft(body: str, recipient: Recipient, channel: str = "email") -> CommunicationDraft:
    return CommunicationDraft(
        communication_id="comm-1",
        correlation_id="corr-1",
        organization_id="aot",
        client_id="client-1",
        sender_identity="aot.support",
        channel=channel,
        purpose=MessagePurpose.TICKET_UPDATE,
        subject="Ticket update",
        body=body,
        recipients=(recipient,),
    )


def test_plain_client_update_is_allowed() -> None:
    review = AudiencePolicyEngine().review(
        _draft("We identified the issue and will provide another update after testing.", _recipient(AudienceType.CLIENT_END_USER))
    )
    assert review.decision is ReviewDecision.ALLOW


def test_cross_client_recipient_is_blocked() -> None:
    review = AudiencePolicyEngine().review(
        _draft("Status update", _recipient(AudienceType.CLIENT_END_USER, client_id="other-client"))
    )
    assert review.decision is ReviewDecision.BLOCK


def test_raw_log_for_client_requires_revision() -> None:
    review = AudiencePolicyEngine().review(
        _draft("Event ID: 1001 Exception: package failed", _recipient(AudienceType.CLIENT_END_USER))
    )
    assert review.decision is ReviewDecision.REQUIRE_REVISION


def test_sensitive_reference_requires_approval() -> None:
    review = AudiencePolicyEngine().review(
        _draft("The password was reset.", _recipient(AudienceType.CLIENT_DECISION_MAKER))
    )
    assert review.decision is ReviewDecision.REQUIRE_APPROVAL
    assert "security_approver" in review.required_approver_roles


def test_disallowed_channel_is_blocked() -> None:
    review = AudiencePolicyEngine().review(
        _draft("Vendor request", _recipient(AudienceType.VENDOR), channel="sms")
    )
    assert review.decision is ReviewDecision.BLOCK
