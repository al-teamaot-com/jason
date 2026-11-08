"""Source-only confidential OAuth code redemption for admin browser step-up.

This adapter is not an HTTP route, approval or release operator.
The caller must first consume an exact server-bound, one-time login session.
An Entra-authenticated proof is NOT a signed Owner release decision.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .entra_release_stepup import (
    REDIRECT, EntraStepUpDenied, ExactRelease,
    PendingEntraLogin, ReleaseIdentityRoute,
    verified_admin_signin,
)


def redeem_admin_browser_code(
    *, code: str,
    login: PendingEntraLogin,
    returned_state: str,
    approval: ExactRelease,
    route: ReleaseIdentityRoute,
    app_client_id: str,
    client_secret: str,
    required_auth_context: str,
    now: datetime,
    jwk_client=None,
    request_open=None,
) -> Mapping[str, object]:
    """Return verified identity proof only; never mutate the ApprovalRequest.

    Secure host integration must verify the OAuth app's registered redirect,
    bind callback to HttpOnly session and one-time state, and select secrets
    from OpenBao before invoking this function.
    """
    if (type(code) is not str or not 20 <= len(code) <= 4096
            or any(char.isspace() for char in code)
            or type(client_secret) is not str
            or not 16 <= len(client_secret) <= 8192):
        raise EntraStepUpDenied("ADMIN_OAUTH_CODE_OR_CREDENTIAL_INVALID")
    route.validate()
    login.validate()
    approval.validate()
    # Validate all URL/client/policy controls before contacting the token
    # endpoint, including local browser state and expiry. The OIDC validator
    # repeats these checks after token redemption.
    from .entra_release_stepup import _session_is_valid, UUID
    import hmac
    if (not UUID.fullmatch(app_client_id)
            or not _session_is_valid(approval, login, now)
            or not hmac.compare_digest(login.state, returned_state)
            or not required_auth_context):
        raise EntraStepUpDenied("ADMIN_OAUTH_SESSION_OR_POLICY_INVALID")
    endpoint=(
        "https://login.microsoftonline.com/"
        f"{route.tenant_id}/oauth2/v2.0/token"
    )
    body=urlencode({
        "grant_type":"authorization_code",
        "client_id":app_client_id,
        "client_secret":client_secret,
        "code":code,
        "redirect_uri":REDIRECT,
        "code_verifier":login.code_verifier,
        "scope":"openid profile",
    }).encode("utf-8")
    request=Request(
        endpoint, data=body, method="POST",
        headers={"Content-Type":"application/x-www-form-urlencoded",
                 "Accept":"application/json"},
    )
    caller=request_open if request_open is not None else urlopen
    try:
        with caller(request,timeout=10) as response:
            data=response.read(20001)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise EntraStepUpDenied("ADMIN_OAUTH_TOKEN_EXCHANGE_FAILED") from None
    if len(data)>20000:
        raise EntraStepUpDenied("ADMIN_OAUTH_TOKEN_RESPONSE_TOO_LARGE")
    try:
        result=json.loads(data.decode("utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise EntraStepUpDenied("ADMIN_OAUTH_TOKEN_RESPONSE_INVALID") from exc
    if not isinstance(result,dict):
        raise EntraStepUpDenied("ADMIN_OAUTH_TOKEN_RESPONSE_INVALID")
    token=result.get("id_token")
    if (not isinstance(token,str)
            or "error" in result
            or "error_description" in result):
        raise EntraStepUpDenied("ADMIN_OAUTH_ID_TOKEN_UNAVAILABLE")
    # Deliberately never return access_token, refresh_token, code, secret,
    # original PKCE verifier or raw id_token to the API caller or any logger.
    return verified_admin_signin(
        id_token=token, login=login, returned_state=returned_state,
        approval=approval, route=route, app_client_id=app_client_id,
        required_auth_context=required_auth_context,
        now=now, jwk_client=jwk_client,
    )
