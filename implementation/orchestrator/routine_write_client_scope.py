"""Exact per-client scope selection for two routine MCP write capabilities.

An AOT technician's Entra identity often has no attached *customer* client.
For these two actions the caller must select the exact client; JKD-001 then
requires a matching client-bound execute grant and the provider independently
verifies its durable client/tenant mapping. This never creates authority.
"""
from __future__ import annotations

import re
from typing import Any, Mapping


_SCOPED_WRITE_ACTIONS = frozenset({
    "documentation.configuration.update", "identity.user.create",
})

_CLIENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def resolve_routine_write_client(
    *, capability: str, authenticated_client_id: str | None,
    arguments: Mapping[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    supplied = dict(arguments)
    if capability not in _SCOPED_WRITE_ACTIONS:
        return authenticated_client_id, supplied
    raw_client = supplied.pop("client_id", None)
    if (not isinstance(raw_client, str)
            or raw_client != raw_client.strip()
            or not _CLIENT_ID.fullmatch(raw_client)):
        raise ValueError("ROUTINE_RW_EXACT_CLIENT_ID_REQUIRED")
    if (authenticated_client_id is not None
            and authenticated_client_id != raw_client):
        raise PermissionError("ROUTINE_RW_AUTHENTICATED_CLIENT_SCOPE_MISMATCH")
    return raw_client, supplied
