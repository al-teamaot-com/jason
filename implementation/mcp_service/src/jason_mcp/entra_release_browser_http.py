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
from .entra_release_browser_decision_sessions import OneTimeAdminDecisionStore
from .entra_release_browser_decision import create_browser_decision_envelope
from .entra_release_code_exchange import redeem_admin_browser_code
from .entra_release_stepup import (
    EntraStepUpDenied, ExactRelease, ReleaseIdentityRoute,
    login_authorization_url,
)

_COOKIE = "__Host-jason-admin-release"
_DECISION_COOKIE = "__Host-jason-admin-decision"
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
        decision_store: OneTimeAdminDecisionStore | None = None,
        signing_key_loader=None,
        signing_key_id: str | None = None,
        signed_decision_sink=None,
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
        self.decision_store = decision_store
        self.signing_key_loader = signing_key_loader
        self.signing_key_id = signing_key_id
        self.signed_decision_sink = signed_decision_sink
        self.jwk_client = jwk_client
        self.request_open = request_open

    def _check_request(
        self, request: Request, *, callback: bool = False,
        decision: bool = False,
    ) -> None:
        expected = urlsplit(self.route.notice_uri)
        host = str(request.headers.get("host") or "")
        expected_path = (urlsplit(self.route.registered_redirect_uri).path if callback
                         else expected.path + "/decision" if decision
                         else expected.path)
        if (host.lower() != expected.netloc.lower()
                or request.url.scheme != "https"
                or request.url.path != expected_path):
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
            if self.decision_store is not None:
                issued = self.decision_store.issue(
                    approval=approval, route=self.route,
                    verified_login_proof=proof, now=datetime.now(timezone.utc),
                )
                authorized_view = RedirectResponse(
                    self.route.notice_uri + "/decision", status_code=303,
                    headers=_NO_STORE,
                )
                authorized_view.set_cookie(
                    _DECISION_COOKIE, issued.cookie_value,
                    max_age=300, path="/", secure=True,
                    httponly=True, samesite="strict",
                )
                authorized_view.delete_cookie(
                    _COOKIE, path="/", secure=True, httponly=True, samesite="lax",
                )
                return authorized_view
            success = PlainTextResponse(
                "Administrator identity verified. No release has been approved or deployed.",
                status_code=200, headers=_NO_STORE,
            )
            success.delete_cookie(_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
            return success
        except (EntraStepUpDenied, ValueError, TypeError, OSError, UnicodeError):
            return response


    async def decision_page(self, request: Request):
        """Display exact release after fresh login; no GET can authorize."""
        try:
            self._check_request(request, decision=True)
            self._policy_ready()
            if self.decision_store is None:
                raise EntraStepUpDenied("ADMIN_DECISION_SURFACE_NOT_CONFIGURED")
            cookie = request.cookies.get(_DECISION_COOKIE)
            if not isinstance(cookie, str):
                raise EntraStepUpDenied("ADMIN_DECISION_COOKIE_REQUIRED")
            approval = self._load(
                self.decision_store.lookup_release_id(cookie_value=cookie)
            )
            csrf = self.decision_store.load_consent(
                cookie_value=cookie, approval=approval,
                now=datetime.now(timezone.utc),
            )
            markup = (
                "<!doctype html><html><head><meta charset='utf-8'></head>"
                "<body><h1>Confirm exact administrator decision</h1>"
                "<p>Release candidate SHA: <code>"
                + escape(approval.candidate_sha, quote=True)
                + "</code></p><p>Rollback SHA: <code>"
                + escape(approval.rollback_sha, quote=True)
                + "</code></p>"
                "<p>A decision is separately checked by the governed host. "
                "No deployment starts on this page.</p>"
                "<form action='/admin/release-approval/decision' method='post'>"
                "<input name='csrf' type='hidden' value='"
                + escape(csrf, quote=True)
                + "'><button name='decision' value='approve'>Approve exact release</button>"
                "<button name='decision' value='deny'>Deny</button></form></body></html>"
            )
            return HTMLResponse(markup, headers=_NO_STORE)
        except (EntraStepUpDenied, ValueError, TypeError, OSError):
            return PlainTextResponse(_FAILURE, status_code=403, headers=_NO_STORE)

    async def decision_submit(self, request: Request):
        """One explicit CSRF-bound action, not direct release authorization."""
        response = PlainTextResponse(_FAILURE, status_code=403, headers=_NO_STORE)
        response.delete_cookie(
            _DECISION_COOKIE, path="/", secure=True,
            httponly=True, samesite="strict",
        )
        try:
            self._check_request(request, decision=True)
            self._policy_ready()
            if (self.decision_store is None or self.signing_key_loader is None
                    or self.signing_key_id is None
                    or self.signed_decision_sink is None):
                raise EntraStepUpDenied("SIGNED_ADMIN_DECISION_NOT_CONFIGURED")
            expected_origin = self.route.notice_uri.rsplit(
                "/admin/release-approval", 1,
            )[0]
            if request.headers.get("origin") != expected_origin:
                raise EntraStepUpDenied("ADMIN_DECISION_CSRF_ORIGIN")
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/x-www-form-urlencoded":
                raise EntraStepUpDenied("ADMIN_DECISION_FORM_INVALID")
            length = request.headers.get("content-length")
            if length is not None and (not length.isdecimal() or int(length) > 2048):
                raise EntraStepUpDenied("ADMIN_DECISION_FORM_TOO_LARGE")
            chunks=[]
            total=0
            async for part in request.stream():
                total += len(part)
                if total > 2048:
                    raise EntraStepUpDenied("ADMIN_DECISION_FORM_TOO_LARGE")
                chunks.append(part)
            form = parse_qs(
                b"".join(chunks).decode("ascii"),
                keep_blank_values=True, strict_parsing=True,
            )
            if (set(form) != {"decision", "csrf"}
                    or len(form["decision"]) != 1
                    or len(form["csrf"]) != 1):
                raise EntraStepUpDenied("ADMIN_DECISION_FORM_INVALID")
            cookie = request.cookies.get(_DECISION_COOKIE)
            if not isinstance(cookie, str):
                raise EntraStepUpDenied("ADMIN_DECISION_COOKIE_REQUIRED")
            approval = self._load(
                self.decision_store.lookup_release_id(cookie_value=cookie)
            )
            # Loading the signing key BEFORE consuming prevents taking the
            # user's one-time decision if the signer is unavailable.
            signing_key = self.signing_key_loader()
            now = datetime.now(timezone.utc)
            proof = self.decision_store.preview_explicit_decision(
                cookie_value=cookie, csrf_token=form["csrf"][0],
                decision=form["decision"][0],
                approval=approval, route=self.route, now=now,
            )
            signed = create_browser_decision_envelope(
                approval=approval, route=self.route,
                verified_login_proof=proof, decision=form["decision"][0],
                signing_key=signing_key, key_id=self.signing_key_id, now=now,
            )
            # Consume the consent AND retain its exact signed evidence in one
            # durable SQLite transaction BEFORE communicating with a sink.
            # A failed/ambiguous send is safely replayable with identical
            # evidence by a governed outbox reconciler (no new signature).
            proof_sha = self.decision_store.record_signed_decision(
                cookie_value=cookie, csrf_token=form["csrf"][0],
                decision=form["decision"][0], approval=approval,
                route=self.route, signed_envelope=signed, now=now,
            )
            # This injected consumer must be idempotent by approval ID+digest;
            # it is not a direct Release Manager approval endpoint.
            self.signed_decision_sink(signed)
            self.decision_store.mark_signed_delivered(
                approval_id=approval.approval_id, signed_sha256=proof_sha,
            )
            accepted = PlainTextResponse(
                "Signed decision recorded for independent governed verification. "
                "No release has been deployed.",
                status_code=200, headers=_NO_STORE,
            )
            accepted.delete_cookie(
                _DECISION_COOKIE, path="/", secure=True,
                httponly=True, samesite="strict",
            )
            return accepted
        except (EntraStepUpDenied, ValueError, TypeError, OSError,
                PermissionError, RuntimeError, UnicodeError):
            return response
