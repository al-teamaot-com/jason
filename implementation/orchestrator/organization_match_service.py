"""Governed invocation boundary for the provider-neutral organization matcher.

Not a live MCP capability. Hosting processes must obtain authorized source records
through their existing provider and information-release gates before invoking.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .organization_matching import (
    MatchResult,
    OrganizationRecord,
    VerifiedOrganizationLink,
    match_organizations,
)


class OrganizationMatchAuthorization(Protocol):
    def approved(
        self, *, principal_id: str, process_id: str, scope_id: str,
        left_source: str, right_source: str,
    ) -> bool: ...


class VerifiedOrganizationMappingRegistry(Protocol):
    def verified_links(
        self, *, scope_id: str, left_source: str, right_source: str,
    ) -> Sequence[VerifiedOrganizationLink]: ...


class MatchingAudit(Protocol):
    def record(self, event: str, fields: Mapping[str, object]) -> None: ...


@dataclass(frozen=True)
class OrganizationMatchRequest:
    principal_id: str
    process_id: str
    scope_id: str
    left_source: str
    right_source: str
    left_evidence_id: str
    right_evidence_id: str

    def __post_init__(self) -> None:
        values = (
            self.principal_id, self.process_id, self.scope_id,
            self.left_source, self.right_source,
            self.left_evidence_id, self.right_evidence_id,
        )
        if any(not isinstance(x, str) or not x.strip() for x in values):
            raise ValueError("Validated requester/process/scope/providers and source evidence required")
        if self.left_source == self.right_source:
            raise ValueError("A distinct source pair is required")


@dataclass(frozen=True)
class GovernedOrganizationMatchService:
    authorizer: OrganizationMatchAuthorization
    mapping_registry: VerifiedOrganizationMappingRegistry
    audit: MatchingAudit

    def match(
        self,
        request: OrganizationMatchRequest,
        left: Sequence[OrganizationRecord],
        right: Sequence[OrganizationRecord],
    ) -> tuple[MatchResult, ...]:
        if self.authorizer.approved(
            principal_id=request.principal_id,
            process_id=request.process_id,
            scope_id=request.scope_id,
            left_source=request.left_source,
            right_source=request.right_source,
        ) is not True:
            raise PermissionError("The process is not authorized to correlate these organizations")

        # A caller cannot pass a self-declared 'verified' link; the mapping
        # registry must return separately approved, persisted evidence.
        links = self.mapping_registry.verified_links(
            scope_id=request.scope_id,
            left_source=request.left_source,
            right_source=request.right_source,
        )
        self.audit.record("organization.match.requested", {
            "principal_id": request.principal_id,
            "process_id": request.process_id,
            "scope_id": request.scope_id,
            "left_source": request.left_source,
            "right_source": request.right_source,
            "left_evidence_id": request.left_evidence_id,
            "right_evidence_id": request.right_evidence_id,
        })
        results = match_organizations(
            left, right, scope_id=request.scope_id,
            left_source=request.left_source, right_source=request.right_source,
            verified_links=links,
        )
        counts = Counter(result.status for result in results)
        self.audit.record("organization.match.completed", {
            "process_id": request.process_id,
            "scope_id": request.scope_id,
            "total": len(results),
            "verified": counts["verified"],
            "probable": counts["probable"],
            "possible": counts["possible"],
            "ambiguous": counts["ambiguous"],
            "unmatched": counts["unmatched"],
        })
        return results
