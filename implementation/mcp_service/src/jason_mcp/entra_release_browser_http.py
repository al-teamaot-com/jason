"""Non-activated secure HTTP adapter for separate Entra admin browser sign-in.

Only identity proof is produced. NO release approval, decision or side effect.
Mounting in production requires a separately reviewed policy/CA proof, new
host-signed decision consumer and exact Teams-governed release authorization.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Callable, Mapping
from urllib.parse import parse_qs, urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from .entra_release_browser_sessions import OneTimeBrowserLoginStore
from .entra_release_code_exchange import redeem_admin_browser_code
from .entra_release_stepup import (
    EntraStepUpDenied, ExactRelease, ReleaseIdentityRoute,
    login_authorization_url,
)

_COOKIE = "__Host-jason-admin-release"
_FAILURE = "This administrative sign-in could not be verified. No release was authorized."
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}


class AdminReleaseBrowserAdapter:
    """Dependency-injected, fail-closed adapter; source-only, never auto-mounted.

    All callbacks are from protected server state, not untrusted HTTP params.
    Conditional Access effectiveness must be independently attested; a JWT
    acrs claim by itself does NOT satisfy that gate.
    """

    def __init__(
        self, *,
        route: ReleaseIdentityRoute,
        client_id: str,
        load_exact_release: Callable[[str], ExactRelease],
        login_store: OneTimeBrowserLoginStore,
        credential_loader: Callable[[], str],
        verify_ca_enforcement: Callable[[], bool],
        required_auth_context: str,
        proof_sink: Callable[[Mapping[str, object]], None] | None = None,
        jwk_client=None,
        request_open=None,
    ) -> None:
        route.validate()
        self.route = route
        self.client_id = client_id
        self.load_exact_release = load_exact_release
        self.login_store = login_store
        self.credential_loader = credential_loader
        self.verify_ca_enforcement = verify_ca_enforcement
        self.required_auth_context = required_auth_context
        # Not an approval sink: only nonauthorizing identity evidence.
        self.proof_sink = proof_sink
        self.jwk_client = jwk_client
        self.request_open = request_open

    def _check_request(self, request: Request, *, callback: bool = False) -> None:
        expected = urlsplit(self.route.notice_uri)
        host = str(request.headers.get("host") or "")
        if (host.lower() != expected.netloc.lower()
                or request.url.scheme != "https"
                or request.url.path != (
                    urlsplit(self.route.registered_redirect_uri).path
                    if callback else expected.path
                )):
            raise EntraStepUpDenied("ADMIN_BROWSER_UNTRUSTED_ORIGIN")

    def _policy_ready(self) -> None:
        # Strict true only: no env-controlled default, no silent fallback.
        if self.verify_ca_enforcement() is not True:
            raise EntraStepUpDenied("ADMIN_CA_MFA_ENFORCEMENT_NOT_ATTESTED")

    def _load(self, request_id: str) -> ExactRelease:
        release = self.load_exact_release(request_id)
        if not isinstance(release, ExactRelease) or release.approval_id != request_id:
            raise EntraStepUpDenied("ADMIN_RELEASE_NOT_AUTHORIZED")
        release.validate()
        return release

    async def notice(self, request: Request):
        try:
            self._check_request(request)
            self._policy_ready()
            ids = request.query_params.getlist("request")
            if len(ids) != 1:
                raise EntraStepUpDenied("ADMIN_RELEASE_REQUEST_INVALID")
            approval = self._load(ids[0])
            if datetime.now(timezone.utc) >= approval.expires_at:
                raise EntraStepUpDenied("ADMIN_RELEASE_EXPIRED")
            # No bare GET may start Entra login, sign or approve.
            markup = (
                "<!doctype html><html><head><meta charset='utf-8'></head>"
                "<body><h1>Administrator release verification</h1>"
                "<p>This sign-in does not approve or deploy a release.</p>"
                "<form method='post' action='/admin/release-approval'>"
                "<input type='hidden' name='request' value='"
                + escape(approval.approval_id, quote=True) +
                "'><button type='submit'>Verify administrator identity</button>"
                "</form></body></html>"
            )
            return HTMLResponse(markup, headers=_NO_STORE)
        except (EntraStepUpDenied, ValueError, TypeError, OSError):
            return PlainTextResponse(_FAILURE, status_code=403, headers=_NO_STORE)

    async def begin(self, request: Request):
        try:
            self._check_request(request)
            self._policy_ready()
            origin = request.headers.get("origin")
            if origin != self.route.notice_uri.rsplit("/admin/release-approval", 1)[0]:
                raise EntraStepUpDenied("ADMIN_RELEASE_CSRF_ORIGIN")
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/x-www-form-urlencoded":
                raise EntraStepUpDenied("ADMIN_RELEASE_FORM_INVALID")
            content_length = request.headers.get("content-length")
            if content_length is not None:
                if not content_length.isdecimal() or int(content_length) > 2048:
                    raise EntraStepUpDenied("ADMIN_RELEASE_FORM_TOO_LARGE")
            chunks = []
            total = 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > 2048:
                    raise EntraStepUpDenied("ADMIN_RELEASE_FORM_TOO_LARGE")
                chunks.append(chunk)
            raw = b"".join(chunks)
            form = parse_qs(raw.decode("ascii"), keep_blank_values=True, strict_parsing=True)
            ids = form.get("request", [])
            if len(form) != 1 or len(ids) != 1:
                raise EntraStepUpDenied("ADMIN_RELEASE_FORM_INVALID")
            approval = self._load(ids[0])
            issued = self.login_store.issue(approval=approval, now=datetime.now(timezone.utc))
            authorize = login_authorization_url(
                route=self.route, login=issued.login, client_id=self.client_id,
                redirect_uri=self.route.registered_redirect_uri,
                required_auth_context=self.required_auth_context,
            )
            response = RedirectResponse(authorize, status_code=303, headers=_NO_STORE)
            response.set_cookie(
                _COOKIE, issued.cookie_value, max_age=300, path="/",
                secure=True, httponly=True, samesite="lax",
            )
            return response
        except (EntraStepUpDenied, ValueError, TypeError, OSError, UnicodeError):
            return PlainTextResponse(_FAILURE, status_code=403, headers=_NO_STORE)

    async def callback(self, request: Request):
        response = PlainTextResponse(_FAILURE, status_code=403, headers=_NO_STORE)
        response.delete_cookie(_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        try:
            self._check_request(request, callback=True)
            self._policy_ready()
            codes = request.query_params.getlist("code")
            states = request.query_params.getlist("state")
            if (len(codes) != 1 or len(states) != 1
                    or "error" in request.query_params):
                raise EntraStepUpDenied("ADMIN_OAUTH_CALLBACK_INVALID")
            cookie = request.cookies.get(_COOKIE)
            if not isinstance(cookie, str):
                raise EntraStepUpDenied("ADMIN_BROWSER_COOKIE_REQUIRED")
            # Lookup uses a server-side SHA256 of an HttpOnly cookie.
            approval_id = self.login_store.lookup_release_id(cookie_value=cookie)
            approval = self._load(approval_id)
            login = self.login_store.consume(
                cookie_value=cookie, returned_state=states[0],
                approval=approval, now=datetime.now(timezone.utc),
            )
            proof = redeem_admin_browser_code(
                code=codes[0], login=login, returned_state=states[0],
                approval=approval, route=self.route,
                app_client_id=self.client_id,
                client_secret=self.credential_loader(),
                required_auth_context=self.required_auth_context,
                now=datetime.now(timezone.utc),
                jwk_client=self.jwk_client,
                request_open=self.request_open,
            )
            if proof.get("release_authorized") is not False:
                raise EntraStepUpDenied("ADMIN_EVIDENCE_MUST_NOT_AUTHORIZE_RELEASE")
            if self.proof_sink is not None:
                self.proof_sink(proof)
            success = PlainTextResponse(
                "Administrator identity verified. No release has been approved or deployed.",
                status_code=200, headers=_NO_STORE,
            )
            success.delete_cookie(_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
            return success
        except (EntraStepUpDenied, ValueError, TypeError, OSError, UnicodeError):
            return response
