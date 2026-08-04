from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol


class ContextValidationError(PermissionError):
    """Raised when an execution context cannot authorize the requested work."""


class AuthorityResolver(Protocol):
    def may_investigate(self, requester_id: str, *, client_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ContextDecision:
    allowed: bool
    reason: str
    context_id: str
    requester_id: str
    client_id: str


class ExecutionContextValidator:
    """Validates the bounded CAP-001 execution context before evidence collection.

    Cryptographic issuance and signature verification belong to JKD-001. This pilot
    validator enforces the contract, expiry, capability, mode, and authority scope so
    provider adapters never receive an unvalidated caller-supplied context.
    """

    def __init__(
        self,
        resolver: AuthorityResolver,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._resolver = resolver
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def validate(self, request: dict[str, Any]) -> ContextDecision:
        context = request["execution_context"]
        ticket = request["ticket"]

        if context["capability"] != "operations.ticket.investigate":
            raise ContextValidationError("Execution context does not authorize CAP-001.")
        if context["maximum_mode"] not in {"observe", "recommend"}:
            raise ContextValidationError("Execution context exceeds CAP-001 Version 0.1 authority.")
        if context["execution_mode"] not in {
            "deterministic",
            "local_ai",
            "hosted_ai",
            "human",
        }:
            raise ContextValidationError(
                "Execution context contains an unsupported execution mode."
            )
        if context["client_id"] != ticket["client_id"]:
            raise ContextValidationError("Ticket and execution context client scopes differ.")

        expires_at = datetime.fromisoformat(context["expires_at"].replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            raise ContextValidationError("Execution context expiry must include a timezone.")
        if expires_at.astimezone(timezone.utc) <= self._clock().astimezone(timezone.utc):
            raise ContextValidationError("Execution context has expired.")

        requester_id = context["requester_id"]
        client_id = context["client_id"]
        if not self._resolver.may_investigate(requester_id, client_id=client_id):
            raise ContextValidationError("Requester is not authorized for this client scope.")

        return ContextDecision(
            allowed=True,
            reason="Execution context is valid for read-only ticket investigation.",
            context_id=context["context_id"],
            requester_id=requester_id,
            client_id=client_id,
        )


@dataclass(frozen=True, slots=True)
class StaticAuthorityResolver:
    """Small deterministic resolver for tests and the historical-ticket pilot."""

    grants: frozenset[tuple[str, str]]

    def may_investigate(self, requester_id: str, *, client_id: str) -> bool:
        return (requester_id, client_id) in self.grants
