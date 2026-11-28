"""Bind J-Assist identity to Jason's existing authenticated MCP principal.

Integration point: jason_mcp.server._authenticated_identity() resolves the
server-validated Microsoft access token via Entra tenant/object ID, active
Microsoft binding and an active Jason identity. This adapter consumes ONLY
that trusted return value, never browser/model-supplied identity claims.

No HTTP or MCP endpoint is enabled by importing this module.
"""
from __future__ import annotations

from typing import Callable
from session_gate import Denied, VerifiedTechnician

_JASON_MCP_AUTH_ASSURANCE = "entra-oauth-bearer"


class JasonMcpTechnicianIdentity:
    """Trusted callback-based boundary for ChatGPT MCP session requests."""

    def __init__(self, resolve_authenticated_identity: Callable[[], tuple]):
        self._resolver = resolve_authenticated_identity

    def current(self) -> VerifiedTechnician:
        try:
            principal = self._resolver()
        except Exception as exc:
            raise Denied("verified MCP technician identity unavailable") from exc
        if not isinstance(principal, tuple) or len(principal) != 4:
            raise Denied("invalid MCP principal contract")
        subject, organization, assurance, client_id = principal
        if not all(
            isinstance(v, str) and 0 < len(v.strip()) <= 256
            for v in (subject, organization)
        ):
            raise Denied("incomplete MCP principal")
        if assurance != _JASON_MCP_AUTH_ASSURANCE:
            raise Denied("unsupported MCP authentication assurance")
        if client_id is not None and (
            not isinstance(client_id, str) or not client_id.strip()
        ):
            raise Denied("invalid client binding")
        return VerifiedTechnician(subject=subject, tenant_id=organization)

    def read_synthetic_status(
        self, *, tool: object, session_id: str, device_uid: str,
    ) -> dict:
        """Produce one safe synthetic receipt for an authenticated caller.

        The model must not specify the principal, bearer token or server-held
        session credential. All authorization remains with SessionGate.
        """
        principal = self.current()
        return tool.read_synthetic_status(
            authenticated_technician=principal,
            session_id=session_id,
            device_uid=device_uid,
        )
