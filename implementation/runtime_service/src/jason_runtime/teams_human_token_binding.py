"""Bind a real Microsoft delegated-user token to one signed Teams approval turn.

This verification port is deliberately NOT wired into production issuance or
approval continuation. It cannot grant authority, store bearer credentials,
or replace the existing JKD/plan policy checks. The caller must obtain the
token from the Microsoft 365 Agents SDK's authenticated user authorization
route during the SAME Teams activity and discard it immediately.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any, Mapping
import json


@dataclass(frozen=True, slots=True)
class VerifiedTeamsHumanTokenBinding:
    signed_evidence_verifier: Any
    microsoft_token_verifier: Any
    allowed_client_ids: frozenset[str]
    required_delegated_scopes: frozenset[str]
    require_mfa: bool = True

    def verify(self, *, signed_envelope: Mapping[str, Any], user_token: str):
        """Verify a human token AND the exact machine-signed callback.

        Return a verified principal with a non-bearer correlated evidence hash.
        No bearer token or token claims are retained or sent to audit stores.
        """
        if not self.allowed_client_ids or not self.required_delegated_scopes:
            raise PermissionError("human approval verifier is not configured")
        if not isinstance(user_token, str) or not user_token.strip():
            raise PermissionError("human user token missing")
        try:
            envelope = json.dumps(dict(signed_envelope), ensure_ascii=False, separators=(",", ":"))
            _, activity = self.signed_evidence_verifier.parse(envelope)
        except Exception as exc:
            raise PermissionError("signed Teams approval activity invalid") from exc

        interaction = activity.approval_submit
        # The signed transport parser already enforces channel=msteams.
        if (interaction is None
                or not interaction.approval_id.startswith("planapproval-")
                or interaction.channel_response_id != activity.message_id
                or activity.authentication_assurance != "botframework-authenticated"):
            raise PermissionError("signed Teams approval response binding invalid")

        # The token verifier must establish Microsoft JWKS signature, issuer,
        # tenant, audience, expiry and assurance before claims can be inspected.
        try:
            principal, verified_claims = self.microsoft_token_verifier.verify_with_claims(user_token)
        except Exception as exc:
            raise PermissionError("Microsoft human user token invalid") from exc

        # An app-only token, id-token, or a Graph token lacking an approved
        # delegated scope is NEVER sufficient to authorize a Teams user click.
        raw_scopes = verified_claims.get("scp")
        scopes = set(raw_scopes.split()) if isinstance(raw_scopes, str) else set()
        client_id = verified_claims.get("azp") or verified_claims.get("appid")
        if (verified_claims.get("idtyp") == "app"
                or not self.required_delegated_scopes.issubset(scopes)
                or not isinstance(client_id, str)
                or client_id not in self.allowed_client_ids):
            raise PermissionError("Microsoft user token is not approved delegated evidence")

        if (principal.tenant_id.casefold() != activity.microsoft_tenant_id.casefold()
                or principal.object_id.casefold() != activity.microsoft_object_id.casefold()):
            raise PermissionError("human token and Teams approval actor mismatch")
        if self.require_mfa and principal.authentication_assurance != "mfa":
            raise PermissionError("human approval token lacks required MFA evidence")

        # This is a commitment to both cryptographically validated inputs,
        # NOT a token or grant. Signed original callback still controls receipt.
        envelope_digest = sha256(envelope.encode("utf-8")).digest()
        token_digest = sha256(user_token.encode("utf-8")).digest()
        commitment = sha256(b"jason-human-teams-approval-v1" + envelope_digest + token_digest).hexdigest()
        return replace(principal, authentication_evidence_hash=commitment)


@dataclass(frozen=True, slots=True)
class BoundTeamsHumanProof:
    """Require an ephemeral independently verified token for one exact callback.

    A token source must only expose same-turn, single-use user bearer evidence
    captured from an authenticated SDK authorization route. No implementation
    is registered in production yet; installing only this class grants nothing.
    """
    binding: VerifiedTeamsHumanTokenBinding
    token_source: Any

    def verify_callback(self, *, signed_envelope: Mapping[str, Any],
            approval_id: str, tenant_id: str, object_id: str,
            channel_response_id: str):
        if not callable(getattr(self.token_source, "require", None)):
            raise PermissionError("verified human token source is not configured")
        try:
            user_token = self.token_source.require(
                approval_id, tenant_id=tenant_id, object_id=object_id,
                channel_response_id=channel_response_id,
            )
        except Exception as exc:
            raise PermissionError("verified human user token not available") from exc
        principal = self.binding.verify(
            signed_envelope=signed_envelope, user_token=user_token,
        )
        if (principal.tenant_id.casefold() != tenant_id.casefold()
                or principal.object_id.casefold() != object_id.casefold()
                or not principal.authentication_evidence_hash):
            raise PermissionError("human user token does not bind to Teams callback")
        return principal
