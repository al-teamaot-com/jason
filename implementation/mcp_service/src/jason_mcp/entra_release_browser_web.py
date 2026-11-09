"""Guarded V5 Microsoft Entra browser login -> existing Jason release approval.

Off by default. A real web route is not authority: every handler validates
the root 0600 V5 policy, pending release, CA/MFA evidence and fixed AOT OIDs.
No Teams approval, user-selected recipient, direct deployment or bypass.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, PlainTextResponse, Response

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService, ApprovalRequestStatus, SQLiteApprovalRequestRepository,
)
from jason_runtime.mobile_release_approval import (
    MobileReleaseOwnerAuthority, MobileReleaseSignedEvidenceStore,
    read_mobile_release_policy, read_eligible_release,
    read_release_approval_containment,
)
from jason_runtime.release_v5_ca_attestation import verify_root_ca_enforcement_receipt
from jason_runtime.release_v5_aot_policy import (
    CHANNEL,
)
from jason_runtime.release_v5_signed_evidence import public_key_fingerprint
from jason_runtime.release_v5_browser_flow import GovernedV5BrowserReleaseDecision

from .entra_release_stepup import (
    ExactRelease, ReleaseIdentityRoute, EntraStepUpDenied,
    login_authorization_url,
)
from .entra_release_browser_sessions import OneTimeBrowserLoginStore
from .entra_release_decision_sessions import OneTimeAdminDecisionStore
from .entra_release_code_exchange import redeem_admin_browser_code


APPROVAL = re.compile(r"^relapproval-[0-9a-f]{32}$")
LOGIN_COOKIE = "__Host-jason-v5-login"
DECISION_COOKIE = "__Host-jason-v5-decision"


def _sensitive_headers(resp: Response) -> Response:
    resp.headers.update({
        "Cache-Control":"no-store, max-age=0",
        "Pragma":"no-cache",
        "Referrer-Policy":"no-referrer",
        "X-Content-Type-Options":"nosniff",
        "X-Frame-Options":"DENY",
        "Content-Security-Policy": (
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; style-src 'none'; script-src 'none'"
        ),
    })
    return resp


def _failure() -> Response:
    # Do not disclose whether an approval exists or an admin is in scope.
    return _sensitive_headers(PlainTextResponse(
        "Administrator authorization could not be verified. Start the "
        "review again from the Jason Teams notification.",
        status_code=403,
    ))


def _secret(path: Path, *, binary_size: int | None = None) -> bytes:
    path=Path(path)
    try:
        info=path.lstat()
        raw=path.read_bytes()
    except OSError as exc:
        raise EntraStepUpDenied("V5_REVIEWED_BROWSER_SECRET_UNAVAILABLE") from exc
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode)!=0o600
            or info.st_uid not in {0,os.geteuid()}
            or info.st_gid not in {0,os.getegid()}
            or not (32<=len(raw)<=8192)
            or binary_size is not None and len(raw)!=binary_size):
        raise EntraStepUpDenied("V5_REVIEWED_BROWSER_SECRET_NOT_PRIVATE")
    return raw


@dataclass
class AdminReleaseBrowserWeb:
    """V5-only HTTP adapter around one Jason release and approval ledger."""
    policy_path: Path
    state_root: Path
    approval_db: Path
    session_db: Path
    ca_attestation_path: Path
    oauth_secret_file: Path
    browser_signer_file: Path
    enabled: bool = False
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    token_redeemer: Callable[..., Any] = redeem_admin_browser_code

    def _policy(self):
        if not self.enabled:
            raise EntraStepUpDenied("V5_BROWSER_SOURCE_ONLY_NOT_ACTIVATED")
        policy=read_mobile_release_policy(self.policy_path)
        if (policy.schema_version!="5.0" or policy.browser_policy is None
                or policy.admin_approver_binding!=(policy.browser_policy.tenant_id,policy.browser_policy.admin_approver_oid)
                or policy.regular_requester_binding!=(policy.browser_policy.tenant_id,policy.browser_policy.requester_oid)):
            raise EntraStepUpDenied("V5_ROOT_BROWSER_POLICY_NOT_ACTIVATED")
        return policy

    def _host_ok(self, request: Request, *, post: bool = False) -> bool:
        try:
            reviewed=self._policy().browser_policy.notice_uri
            origin=reviewed.removesuffix("/admin/release-approval")
            host=urlsplit(origin).netloc.lower()
        except (PermissionError,ValueError,OSError,TypeError,KeyError):
            return False
        observed=request.headers.get("host","").lower()
        if observed!=host:
            return False
        # Never use an attacker-selected forwarded-proto header as HTTPS proof.
        if request.url.scheme!="https":
            return False
        if post:
            if request.headers.get("origin")!=origin:
                return False
            if request.headers.get("sec-fetch-site","same-origin")!="same-origin":
                return False
        return True

    def _context(self, approval_id: str, now: datetime):
        if not isinstance(approval_id,str) or not APPROVAL.fullmatch(approval_id):
            raise EntraStepUpDenied("V5_PENDING_RELEASE_REQUEST_ID_INVALID")
        policy=self._policy()
        read_release_approval_containment(self.state_root).require_request_eligible(now)
        repo=SQLiteApprovalRequestRepository(self.approval_db)
        req=repo.get(approval_id)
        if (req is None or req.status is not ApprovalRequestStatus.PENDING
                or req.capability!="release.production.approve"
                or req.organization_id!=policy.organization_id
                or req.authorized_approver_ids!=policy.owner_identity_ids
                or req.metadata.get("approval_channel")!=CHANNEL
                or req.metadata.get("admin_approver_entra_oid")!=policy.browser_policy.admin_approver_oid
                or req.metadata.get("notice_to_entra_oid")!=policy.browser_policy.requester_oid
                or not req.requested_at<=now<req.expires_at):
            raise EntraStepUpDenied("V5_PENDING_RELEASE_REQUEST_NOT_AUTHORIZED")
        evidence=read_eligible_release(
            self.state_root,req.metadata["release_id"],policy,
        )
        if (evidence.candidate_sha!=req.metadata.get("candidate_sha")
                or evidence.rollback_sha!=req.metadata.get("rollback_sha")
                or evidence.reviewed_scope_sha256!=req.metadata.get("scope_sha256")
                or evidence.manifest_sha256!=req.metadata.get("manifest_sha256")):
            raise EntraStepUpDenied("V5_PENDING_RELEASE_SCOPE_CHANGED")
        exact=ExactRelease(
            approval_id=req.approval_id,
            candidate_sha=evidence.candidate_sha,
            rollback_sha=evidence.rollback_sha,
            scope_sha256=evidence.reviewed_scope_sha256,
            manifest_sha256=evidence.manifest_sha256,
            expires_at=req.expires_at,
        )
        verify_root_ca_enforcement_receipt(
            self.ca_attestation_path,
            browser_policy=policy.browser_policy,
            now=now,
        )
        route=ReleaseIdentityRoute(
            tenant_id=policy.browser_policy.tenant_id,
            regular_teams_oid=policy.browser_policy.requester_oid,
            admin_approver_oid=policy.browser_policy.admin_approver_oid,
            owner_subject_id=policy.browser_policy.owner_identity_id,
            registered_redirect_uri=policy.browser_policy.callback_uri,
            notice_uri=policy.browser_policy.notice_uri,
        )
        return policy,repo,req,exact,route

    def _route(self) -> ReleaseIdentityRoute:
        bp=self._policy().browser_policy
        return ReleaseIdentityRoute(
            tenant_id=bp.tenant_id, regular_teams_oid=bp.requester_oid,
            admin_approver_oid=bp.admin_approver_oid,
            owner_subject_id=bp.owner_identity_id,
            registered_redirect_uri=bp.callback_uri,
            notice_uri=bp.notice_uri,
        )

    async def begin(self, request: Request) -> Response:
        if not self._host_ok(request):
            return _failure()
        try:
            now=self.clock()
            approval_id=request.query_params.get("request","")
            if len(request.query_params)!=1:
                raise EntraStepUpDenied("V5_BROWSER_UNTRUSTED_QUERY")
            policy,repo,req,exact,route=self._context(approval_id,now)
            store=OneTimeBrowserLoginStore(self.session_db)
            session=store.issue(approval=exact,now=now)
            url=login_authorization_url(
                route=route,login=session.login,
                client_id=policy.browser_policy.browser_client_id,
                redirect_uri=policy.browser_policy.callback_uri,
                required_auth_context=policy.browser_policy.auth_context_id,
            )
            response=RedirectResponse(url,status_code=303)
            response.set_cookie(
                LOGIN_COOKIE,session.cookie_value,
                max_age=300,path="/",secure=True,httponly=True,samesite="lax",
            )
            return _sensitive_headers(response)
        except (PermissionError,ValueError,OSError,TypeError,KeyError):
            return _failure()

    async def callback(self, request: Request) -> Response:
        if not self._host_ok(request):
            return _failure()
        try:
            now=self.clock()
            if (len(request.query_params)!=2
                    or request.query_params.get("error") is not None):
                raise EntraStepUpDenied("V5_BROWSER_CALLBACK_FIELDS_INVALID")
            code=request.query_params.get("code","")
            state=request.query_params.get("state","")
            cookie=request.cookies.get(LOGIN_COOKIE,"")
            login_store=OneTimeBrowserLoginStore(self.session_db)
            approval_id=login_store.peek_approval_id(cookie_value=cookie)
            policy,repo,req,exact,route=self._context(approval_id,now)
            login=login_store.consume(
                cookie_value=cookie,returned_state=state,
                approval=exact,now=now,
            )
            client_secret=_secret(self.oauth_secret_file).decode("utf-8").strip()
            proof=self.token_redeemer(
                code=code,login=login,returned_state=state,approval=exact,
                route=route,
                app_client_id=policy.browser_policy.browser_client_id,
                client_secret=client_secret,
                required_auth_context=policy.browser_policy.auth_context_id,
                now=now,
            )
            decision_store=OneTimeAdminDecisionStore(self.session_db,route=self._route())
            session=decision_store.issue(
                approval=exact,verified_admin_proof=dict(proof),now=now,
            )
            html=self._review_html(req,exact,session.csrf_value)
            response=HTMLResponse(html,status_code=200)
            response.delete_cookie(LOGIN_COOKIE,path="/")
            response.set_cookie(
                DECISION_COOKIE,session.cookie_value,
                max_age=300,path="/",secure=True,httponly=True,samesite="strict",
            )
            return _sensitive_headers(response)
        except (PermissionError,ValueError,OSError,TypeError,KeyError,UnicodeError):
            return _failure()

    @staticmethod
    def _review_html(req, exact: ExactRelease, csrf_value: str) -> str:
        esc=escape
        return (
            "<!doctype html><html lang='en'><head>"
            "<meta charset='utf-8'><title>Jason - Administrator Release Approval</title>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "</head><body><main>"
            "<h1>Administrator release decision</h1>"
            "<p>Authenticated separately as the privileged administrator."
            " This is one exact release and does not grant standing authority.</p>"
            f"<p>Release: <strong>{esc(req.metadata['release_id'])}</strong></p>"
            f"<p>Candidate SHA: <code>{esc(exact.candidate_sha)}</code></p>"
            f"<p>Rollback SHA: <code>{esc(exact.rollback_sha)}</code></p>"
            f"<p>Reviewed scope: <code>{esc(exact.scope_sha256)}</code></p>"
            f"<p>Manifest SHA256: <code>{esc(exact.manifest_sha256)}</code></p>"
            f"<p>Expires: {esc(exact.expires_at.isoformat())}</p>"
            "<form method='post' action='/admin/release-approval/decision'>"
            f"<input type='hidden' name='csrf' value='{esc(csrf_value,quote=True)}'>"
            "<p><button name='decision' value='approve' type='submit'>"
            "Approve exact release</button> "
            "<button name='decision' value='deny' type='submit'>Deny</button></p>"
            "</form></main></body></html>"
        )

    async def decide(self, request: Request) -> Response:
        if not self._host_ok(request,post=True):
            return _failure()
        try:
            if not request.headers.get("content-type","").startswith(
                "application/x-www-form-urlencoded"
            ):
                raise EntraStepUpDenied("V5_FORM_CONTENT_TYPE_INVALID")
            chunks=[]
            total=0
            async for chunk in request.stream():
                total+=len(chunk)
                if total>4096:
                    raise EntraStepUpDenied("V5_FORM_TOO_LARGE")
                chunks.append(chunk)
            form=parse_qs(
                b"".join(chunks).decode("utf-8"),
                keep_blank_values=True,strict_parsing=True,
                max_num_fields=2,
            )
            if (set(form)!={"csrf","decision"}
                    or len(form["csrf"])!=1 or len(form["decision"])!=1
                    or form["decision"][0] not in ("approve","deny")):
                raise EntraStepUpDenied("V5_BROWSER_EXPLICIT_FORM_DECISION_INVALID")
            now=self.clock()
            cookie=request.cookies.get(DECISION_COOKIE,"")
            decision_store=OneTimeAdminDecisionStore(self.session_db,route=self._route())
            approval_id=decision_store.peek_approval_id(cookie_value=cookie)
            policy,repo,req,exact,route=self._context(approval_id,now)
            proof=decision_store.consume(
                cookie_value=cookie,csrf_value=form["csrf"][0],
                approval=exact,now=now,
            )
            raw=_secret(self.browser_signer_file,binary_size=32)
            key=Ed25519PrivateKey.from_private_bytes(raw)
            if public_key_fingerprint(key.public_key())!=(
                    policy.browser_policy.signer_public_key_sha256):
                raise EntraStepUpDenied("V5_BROWSER_REVIEWED_SIGNER_INVALID")
            service=ApprovalRequestService(
                repo,MobileReleaseOwnerAuthority(self.policy_path),
            )
            flow=GovernedV5BrowserReleaseDecision(
                policy_path=self.policy_path,
                release_state_root=self.state_root,
                ca_attestation_path=self.ca_attestation_path,
                requests=repo,approvals=service,
                signed_evidence=MobileReleaseSignedEvidenceStore(
                    self.approval_db,
                ),
                signing_key=key,
            )
            result=flow.handle(
                approval_id=approval_id,
                decision=form["decision"][0],
                authenticated_admin_proof=proof,
                when=now,
            )
            response=HTMLResponse(
                "<!doctype html><html><head>"
                "<meta charset='utf-8'><title>Jason - Decision recorded</title>"
                "</head><body><h1>Administrator decision recorded</h1>"
                "<p>The protected Jason Release Manager must independently "
                "verify this signed decision before any production change.</p>"
                "</body></html>",
                status_code=200,
            )
            response.delete_cookie(DECISION_COOKIE,path="/")
            return _sensitive_headers(response)
        except (PermissionError,ValueError,OSError,TypeError,KeyError,UnicodeError):
            return _failure()
