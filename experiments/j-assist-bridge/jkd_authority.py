"""J-Assist adapter to Jason's JKD-001 identity/authority service.

No grants are created here. Invocation requires pre-authenticated server-side
VerifiedTechnician and independent native Datto device permission checks.
"""
from __future__ import annotations

from typing import Callable
from uuid import uuid4

from kernel.identity_authority import (
    AuthorityOutcome,
    AuthorityRequest,
    PermissionMode,
)

from session_gate import VerifiedTechnician

J_ASSIST_OBSERVE_CAPABILITY = "j_assist.session.observe"


def make_jkd_datto_authorizer(
    *,
    identity_authority: object,
    native_datto_device_access: Callable[[VerifiedTechnician, str], bool],
) -> Callable[[VerifiedTechnician, str], bool]:
    """Require BOTH JKD observe grant AND source-side Datto access.

    Existing AOT operational-read grants are not silently widened to screen
    sharing. The distinct capability must be explicitly governed/granted.
    """

    def allowed(principal: VerifiedTechnician, device_uid: str) -> bool:
        request = AuthorityRequest(
            request_id="jassist-" + uuid4().hex,
            correlation_id="jassist-" + uuid4().hex,
            principal_id=principal.subject,
            organization_id=principal.tenant_id,
            client_id=None,
            capability=J_ASSIST_OBSERVE_CAPABILITY,
            requested_mode=PermissionMode.OBSERVE,
            authentication_assurance="trusted-identity-adapter",
        )
        decision = identity_authority.evaluate(request)
        if decision.outcome is not AuthorityOutcome.ALLOWED:
            return False
        # Native Datto permission verification must also succeed. An error is
        # denial, never a fallback to a Jason-only standing grant.
        try:
            return native_datto_device_access(principal, device_uid) is True
        except Exception:
            return False

    return allowed
