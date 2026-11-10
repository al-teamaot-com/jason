"""Source-only Entra web step-up for the existing PMv3.2 release approval.

This module is deliberately NOT a new endpoint or deployment authority.
The web adapter must use a registered HTTPS confidential-client callback,
redeem the auth code with PKCE and validate a server-side session. The host
release consumer must independently accept a reviewed channel before use.

A Teams notice goes to the regular account; only an independently
authenticated ADMIN Entra object may ever produce approval evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import base64
import json
import hmac
import re
import secrets
from typing import Any, Mapping
from urllib.parse import urlencode, urlsplit
import ipaddress

import jwt
from jwt import PyJWKClient, PyJWTError


UUID = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
APPROVAL = re.compile(r"^relapproval-[0-9a-f]{32}$")
# Hostnames and identities are supplied by a *trusted, reviewed policy*.
# None of these are fixed to an individual AOT account or deployment URL.
_OWNER_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_NOTICE_PATH = "/admin/release-approval"
_CALLBACK_PATH = "/admin/release-approval/callback"


def _https_origin(value: str, *, required_path: str) -> str:
    """Reject insecure, injected, or unreviewable approval destinations."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise EntraStepUpDenied("REVIEWED_APPROVAL_ENDPOINT_REQUIRED")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = (parsed.hostname or "").lower()
        if not host or host in ("localhost",) or host.endswith((".local", ".internal")):
            raise ValueError("not a public HTTPS host")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("IP literal is not an approved FQDN")
    except ValueError as exc:
        raise EntraStepUpDenied("REVIEWED_APPROVAL_ENDPOINT_REQUIRED") from exc
    if (parsed.scheme != "https" or not host or "." not in host
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443)
            or parsed.path != required_path
            or parsed.query or parsed.fragment
            or value != f"https://{parsed.netloc}{required_path}"):
        raise EntraStepUpDenied("REVIEWED_APPROVAL_ENDPOINT_REQUIRED")
    return f"https://{parsed.netloc}"


class EntraStepUpDenied(PermissionError):
    """An exact privileged-browser approval is missing or not verified."""


@dataclass(frozen=True)
class ReleaseIdentityRoute:
    """Trusted, reviewable tenant/authority binding; never an email allowlist.

    The future adapter must populate these from the versioned protected
    approval policy after group/owner role authorization, not caller input.
    The OIDs are exact subjects resolved from Entra and can be rotated in
    governance without a code release.
    """
    tenant_id: str
    regular_teams_oid: str
    admin_approver_oid: str
    owner_subject_id: str
    registered_redirect_uri: str
    notice_uri: str

    def validate(self) -> None:
        if (not all(isinstance(x, str) and UUID.fullmatch(x)
                    for x in (self.tenant_id, self.regular_teams_oid,
                              self.admin_approver_oid))
                or self.regular_teams_oid == self.admin_approver_oid
                or not isinstance(self.owner_subject_id, str)
                or not _OWNER_ID.fullmatch(self.owner_subject_id)):
            raise EntraStepUpDenied("SEPARATE_ENTRA_ADMIN_REQUIRED")
        callback_origin = _https_origin(
            self.registered_redirect_uri, required_path=_CALLBACK_PATH,
        )
        notice_origin = _https_origin(self.notice_uri, required_path=_NOTICE_PATH)
        if callback_origin != notice_origin:
            raise EntraStepUpDenied("APPROVAL_ENDPOINT_ORIGIN_MISMATCH")


@dataclass(frozen=True)
class ExactRelease:
    approval_id: str
    candidate_sha: str
    rollback_sha: str
    scope_sha256: str
    manifest_sha256: str
    expires_at: datetime

    def validate(self) -> None:
        if (not APPROVAL.fullmatch(self.approval_id)
                or not SHA40.fullmatch(self.candidate_sha)
                or not SHA40.fullmatch(self.rollback_sha)
                or not SHA64.fullmatch(self.scope_sha256)
                or not SHA64.fullmatch(self.manifest_sha256)
                or self.candidate_sha == self.rollback_sha
                or self.expires_at.tzinfo is None):
            raise EntraStepUpDenied("RELEASE_EXACT_SCOPE_INVALID")

    def fingerprint(self) -> str:
        self.validate()
        data = {
            "approval_id": self.approval_id,
            "candidate_sha": self.candidate_sha,
            "rollback_sha": self.rollback_sha,
            "scope_sha256": self.scope_sha256,
            "manifest_sha256": self.manifest_sha256,
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
        }
        return sha256(json.dumps(
            data, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PendingEntraLogin:
    """Store in a secure server-side session, never in a Teams URL."""
    approval_id: str
    exact_release_fingerprint: str
    state: str
    nonce: str
    code_verifier: str
    started_at: datetime

    def validate(self) -> None:
        if (not APPROVAL.fullmatch(self.approval_id)
                or not SHA64.fullmatch(self.exact_release_fingerprint)
                or not all(isinstance(x, str) and len(x) >= 40
                           for x in (self.state, self.nonce, self.code_verifier))
                or self.started_at.tzinfo is None):
            raise EntraStepUpDenied("BROWSER_LOGIN_SESSION_INVALID")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def new_login(approval: ExactRelease, *, now: datetime) -> PendingEntraLogin:
    """Mint a one-time PKCE challenge for a specific pending approval."""
    approval.validate()
    if now.tzinfo is None or not now < approval.expires_at:
        raise EntraStepUpDenied("RELEASE_APPROVAL_EXPIRED")
    return PendingEntraLogin(
        approval_id=approval.approval_id,
        exact_release_fingerprint=approval.fingerprint(),
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        code_verifier=secrets.token_urlsafe(48),
        started_at=now,
    )


def login_authorization_url(
    *, route: ReleaseIdentityRoute, login: PendingEntraLogin,
    client_id: str, redirect_uri: str,
    required_auth_context: str,
) -> str:
    """Use Entra OIDC, not Teams or a caller-supplied identity assertion.

    IMPORTANT: An acrs claim alone is not proof that the auth context has a
    protecting Conditional Access policy. Activation must independently
    verify the Entra CA policy and its required step-up control.
    """
    route.validate()
    login.validate()
    if not UUID.fullmatch(client_id) or redirect_uri != route.registered_redirect_uri:
        raise EntraStepUpDenied("REVIEWED_ENTRA_APP_REDIRECT_REQUIRED")
    if (required_auth_context is not None
            and (not isinstance(required_auth_context,str)
                 or not re.fullmatch(r"c[1-9][0-9]?",required_auth_context))):
        raise EntraStepUpDenied("REVIEWED_ADMIN_STEP_UP_POLICY_MISSING")
    challenge = _base64url(sha256(login.code_verifier.encode("ascii")).digest())
    # The root-reviewed existing-role-MFA option requests Microsoft-signed
    # amr/auth_time rather than a tenant auth-context that does not exist.
    # The token validator MUST require an actual MFA claim in this mode.
    id_token_claims=(
        {"acrs":{"essential":True,"value":required_auth_context}}
        if required_auth_context is not None else
        {"amr":{"essential":True},"auth_time":{"essential":True}}
    )
    return (
        f"https://login.microsoftonline.com/{route.tenant_id}/oauth2/v2.0/authorize?"
        + urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": "openid profile",
            "state": login.state,
            "nonce": login.nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "login",
            "max_age": "300",
            "claims": json.dumps(
                {"id_token":id_token_claims},
                separators=(",", ":"), sort_keys=True,
            ),
        })
    )


def regular_teams_notice(
    *, route: ReleaseIdentityRoute, approval: ExactRelease,
) -> dict[str, Any]:
    """Informative only: NO approve/deny card or credential-bearing link."""
    route.validate()
    approval.validate()
    link = f"{route.notice_uri}?{urlencode({'request': approval.approval_id})}"
    return {
        "recipient_entra_oid": route.regular_teams_oid,
        "tenant_id": route.tenant_id,
        "kind": "notification",
        "text": (
            "Jason production release approval is ready for administrator "
            "verification. Open the reviewed request and sign in using your "
            "separate administrator account. This Teams message cannot approve."
        ),
        "view_url": link,
        # Teams is transport only. No Action.Submit nor approval credential.
        "card": None,
        "can_approve_from_teams": False,
    }


def verified_admin_signin(
    *, id_token: str, login: PendingEntraLogin,
    returned_state: str, approval: ExactRelease,
    route: ReleaseIdentityRoute,
    app_client_id: str,
    required_auth_context: str,
    now: datetime,
    jwk_client: PyJWKClient | None = None,
) -> Mapping[str, Any]:
    """Validate an ID token AFTER the confidential client redeems OAuth code.

    The server-side login session must already be bound to a secure HttpOnly
    browser cookie; the callback adapter must verify its CSRF state and PKCE
    code_verifier on Microsoft's token endpoint. This function additionally
    validates the cryptographic ID token and exact privileged identity.

    required_auth_context: a reviewed Entra CA authentication context 'cX'.
    If no context has been configured, browser approval is DENIED.
    """
    route.validate()
    approval.validate()
    login.validate()
    if (not _session_is_valid(approval, login, now)
            or not isinstance(returned_state, str)
            or not hmac.compare_digest(login.state, returned_state)):
        raise EntraStepUpDenied("RELEASE_BROWSER_SESSION_OR_STATE_MISMATCH")
    if not UUID.fullmatch(app_client_id):
        raise EntraStepUpDenied("ENTRA_CLIENT_ID_INVALID")
    if (required_auth_context is not None
            and (not isinstance(required_auth_context,str)
                 or not re.fullmatch(r"c[1-9][0-9]?",required_auth_context))):
        raise EntraStepUpDenied("REVIEWED_ADMIN_STEP_UP_POLICY_MISSING")
    if not isinstance(id_token, str) or not 40 <= len(id_token) <= 16000:
        raise EntraStepUpDenied("ENTRA_ID_TOKEN_INVALID")
    issuer = f"https://login.microsoftonline.com/{route.tenant_id}/v2.0"
    jwks = f"https://login.microsoftonline.com/{route.tenant_id}/discovery/v2.0/keys"
    client = jwk_client if jwk_client is not None else PyJWKClient(jwks)
    try:
        key = client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token, key.key, algorithms=["RS256"],
            audience=app_client_id, issuer=issuer,
            options={"require": [
                "exp", "nbf", "iat", "iss", "aud", "tid", "oid",
                "nonce", "auth_time",
            ]},
            leeway=15,
        )
    except (PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise EntraStepUpDenied("ENTRA_ID_TOKEN_SIGNATURE_OR_CLAIMS_INVALID") from exc
    except Exception as exc:
        raise EntraStepUpDenied("ENTRA_ID_TOKEN_VERIFICATION_UNAVAILABLE") from exc
    auth_time = claims.get("auth_time")
    if (str(claims.get("tid")) != route.tenant_id
            or str(claims.get("oid")) != route.admin_approver_oid
            or not hmac.compare_digest(str(claims.get("nonce") or ""), login.nonce)
            or type(auth_time) is not int
            or not 0 <= int(now.timestamp()) - auth_time <= 300
            or (required_auth_context is not None and
                (not isinstance(claims.get("acrs"),list)
                 or required_auth_context not in claims["acrs"]))
            or (required_auth_context is None and
                (not isinstance(claims.get("amr"),list)
                 or "mfa" not in claims["amr"]))):
        raise EntraStepUpDenied("PRIVILEGED_ADMIN_SESSION_NOT_VERIFIED")
    return {
        "authenticated_admin_oid": route.admin_approver_oid,
        "tenant_id": route.tenant_id,
        "owner_subject_id": route.owner_subject_id,
        "approval_id": approval.approval_id,
        "channel": "microsoft_entra_browser_stepup",
        "candidate_sha": approval.candidate_sha,
        "scope_sha256": approval.scope_sha256,
        "rollback_sha": approval.rollback_sha,
        "manifest_sha256": approval.manifest_sha256,
        "auth_time": auth_time,
        "evidence_sha256": sha256(id_token.encode("ascii")).hexdigest(),
        # Not an approval decision; host consumer still requires a versioned
        # root-trusted proof, same request TTL, challenge and one-time decision.
        "release_authorized": False,
    }


def _session_is_valid(approval: ExactRelease, login: PendingEntraLogin, now: datetime) -> bool:
    return (
        now.tzinfo is not None
        and login.approval_id == approval.approval_id
        and hmac.compare_digest(login.exact_release_fingerprint, approval.fingerprint())
        and login.started_at <= now
        and 0 <= (now - login.started_at).total_seconds() <= 300
        and now < approval.expires_at
    )
