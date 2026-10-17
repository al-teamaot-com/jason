"""Real gateway Ed25519 signature plus independently verified human claims.

No provider, Teams service, tenant credential, or production approval is touched.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import base64
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from connectors.microsoft_graph.microsoft_token_verification import (
    MicrosoftTokenPolicy, MicrosoftTokenVerifier,
)
from jason_openclaw.signed_transport import (
    Ed25519TransportAuthenticator, canonical_signed_payload,
)
from jason_runtime.universal_teams_approval import SignedTeamsApprovalEvidenceVerifier
from jason_runtime.teams_human_token_binding import VerifiedTeamsHumanTokenBinding

NOW = datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc)
TENANT = "11111111-2222-4333-8444-555555555555"
ACTOR = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
CLIENT = "12345678-aaaa-4444-8888-1234567890ab"
AUDIENCE = "api://jason-teams-approvals"
TOKEN = "opaque-human-token-only-in-request-memory"


class ClaimsVerifier:
    def __init__(self, claims=None, error=None):
        self.claims = claims
        self.error = error

    def verify_signature(self, token):
        assert token == TOKEN
        if self.error:
            raise self.error
        return dict(self.claims)


def claims(**changes):
    data = dict(
        tid=TENANT, oid=ACTOR, sub="user-subject",
        iss=f"https://login.microsoftonline.com/{TENANT}/v2.0",
        aud=AUDIENCE,
        iat=int(NOW.timestamp()) - 30,
        nbf=int(NOW.timestamp()) - 30,
        exp=int(NOW.timestamp()) + 180,
        amr=["pwd", "mfa"], scp="user_impersonation",
        azp=CLIENT,
    )
    data.update(changes)
    return data


def setup(token_claims=None, *, crypto_error=None, require_mfa=True):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    transport = SignedTeamsApprovalEvidenceVerifier(
        authenticator=Ed25519TransportAuthenticator(
            {"gateway-key": public}, {"gateway-key": "registered-gateway"}
        ),
        allowed_machine_identities=frozenset({"registered-gateway"}),
        clock=lambda: NOW,
    )
    microsoft = MicrosoftTokenVerifier(
        crypto=ClaimsVerifier(token_claims or claims(), crypto_error),
        policy=MicrosoftTokenPolicy(audience=AUDIENCE, allowed_tenant_ids=(TENANT,)),
        clock=lambda: NOW,
    )
    boundary = VerifiedTeamsHumanTokenBinding(
        transport, microsoft, frozenset({CLIENT}),
        frozenset({"user_impersonation"}), require_mfa=require_mfa,
    )
    return boundary, private


def signed(private, **changes):
    envelope = dict(
        kind="conversation.turn",
        request_id="transport-uta-test",
        correlation_id="test-correlation",
        issued_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(seconds=90)).isoformat(),
        nonce="single-use-unique-test-nonce",
        channel="msteams",
        text="Jason approval response",
        transport_identity={
            "microsoft_tenant_id": TENANT,
            "microsoft_object_id": ACTOR,
            "authentication_assurance": "botframework-authenticated",
        },
        conversation_id="teams-personal-thread-1",
        message_id="teams-callback-message-1",
        interaction=dict(
            kind="approval.submit",
            approval_id="planapproval-controlled-aot-test",
            decision="approve",
            channel_response_id="teams-callback-message-1",
            selections={},
        ),
        key_id="gateway-key",
    )
    envelope.update(changes)
    envelope["signature"] = base64.b64encode(
        private.sign(canonical_signed_payload(envelope))
    ).decode()
    return envelope


def verify(boundary, envelope):
    return boundary.verify(signed_envelope=envelope, user_token=TOKEN)


def test_verified_delegated_human_and_callback_produce_only_nonbearer_digest():
    boundary, private = setup()
    principal = verify(boundary, signed(private))
    assert (principal.tenant_id, principal.object_id) == (TENANT, ACTOR)
    assert principal.authentication_assurance == "mfa"
    assert len(principal.authentication_evidence_hash) == 64
    assert TOKEN not in repr(principal)


@pytest.mark.parametrize("mutated", [
    dict(scp=""), dict(scp="Application.Read.All"),
    dict(idtyp="app"), dict(azp="unknown-client"), dict(azp=None, appid=None),
    dict(tid="wrong-tenant"), dict(oid="wrong-human"),
    dict(aud="https://graph.microsoft.com"), dict(exp=int(NOW.timestamp()) - 200),
    dict(amr=["pwd"]),
])
def test_untrusted_human_proof_fails_closed(mutated):
    boundary, private = setup(claims(**mutated))
    with pytest.raises(PermissionError):
        verify(boundary, signed(private))


def test_crypto_failure_cannot_create_human_proof():
    boundary, private = setup(crypto_error=ValueError("signature failed"))
    with pytest.raises(PermissionError, match="token invalid"):
        verify(boundary, signed(private))


@pytest.mark.parametrize("change", [
    dict(channel="webchat"),
    dict(message_id="a-different-response"),
    dict(transport_identity={
        "microsoft_tenant_id": TENANT,
        "microsoft_object_id": ACTOR,
        "authentication_assurance": "asserted-only",
    }),
    dict(issued_at=(NOW-timedelta(minutes=4)).isoformat(),
         expires_at=(NOW-timedelta(minutes=2)).isoformat()),
])
def test_callback_channel_receipt_assurance_and_expiry_checked(change):
    boundary, private = setup()
    with pytest.raises(PermissionError):
        verify(boundary, signed(private, **change))


def test_gateway_tamper_is_denied_even_with_genuine_user_token():
    boundary, private = setup()
    envelope = signed(private)
    envelope["interaction"]["decision"] = "deny"
    with pytest.raises(PermissionError):
        verify(boundary, envelope)


def test_missing_user_token_fails_without_decoding_signed_envelope():
    boundary, private = setup()
    with pytest.raises(PermissionError, match="token missing"):
        boundary.verify(signed_envelope=signed(private), user_token="")


def test_exact_distinct_teams_decisions_have_distinct_commitments():
    boundary, private = setup()
    approve = verify(boundary, signed(private))
    deny = verify(boundary, signed(private, interaction=dict(
        kind="approval.submit", approval_id="planapproval-controlled-aot-test",
        decision="deny", channel_response_id="teams-callback-message-1",
        selections={},
    )))
    assert approve.authentication_evidence_hash != deny.authentication_evidence_hash


def test_every_required_delegated_scope_must_be_present():
    boundary, private = setup()
    boundary = replace(boundary, required_delegated_scopes=frozenset({
        "user_impersonation", "second_delegated_scope",
    }))
    with pytest.raises(PermissionError, match="not approved delegated"):
        verify(boundary, signed(private))


def test_verifier_must_have_explicit_scopes_and_client_allowlist():
    boundary, private = setup()
    empty = replace(boundary, required_delegated_scopes=frozenset())
    with pytest.raises(PermissionError, match="not configured"):
        verify(empty, signed(private))
