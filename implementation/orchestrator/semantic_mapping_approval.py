from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .provider_semantic_mapping_proposal import SemanticMappingProposal
from .semantic_mapping_registry import ApprovedSemanticMapping


@dataclass(frozen=True, slots=True)
class SemanticMappingApprovalDecision:
    decision: str
    approver: str
    authority_role: str
    decision_basis: str

    def __post_init__(self) -> None:
        if self.decision not in {"approve", "reject"}:
            raise ValueError("semantic mapping decision must be approve or reject")
        if not self.approver.strip():
            raise ValueError("semantic mapping approver is required")
        if not self.authority_role.strip():
            raise ValueError("semantic mapping authority role is required")
        if not self.decision_basis.strip():
            raise ValueError("semantic mapping decision basis is required")


@dataclass(frozen=True, slots=True)
class GovernedSemanticMappingApprover:
    required_authority_role: str = "technology-steward"

    def approve(
        self,
        *,
        proposal: SemanticMappingProposal,
        decision: SemanticMappingApprovalDecision,
        mapping_id: str,
        version: int,
        resource_authority: str,
    ) -> ApprovedSemanticMapping:
        if decision.authority_role != self.required_authority_role:
            raise PermissionError(
                "semantic mapping approval requires Technology Steward authority"
            )

        if decision.decision != "approve":
            raise PermissionError(
                "rejected semantic mapping proposal cannot be activated"
            )

        if proposal.approved or proposal.active:
            raise PermissionError(
                "semantic mapping proposal must enter approval unactivated"
            )

        return ApprovedSemanticMapping(
            mapping_id=mapping_id,
            version=version,
            provider_id=proposal.provider_id,
            canonical_fact=proposal.canonical_fact,
            provider_schema=proposal.provider_schema,
            provider_field=proposal.provider_field,
            resource_authority=resource_authority,
            approval_status="approved",
            approved_by=decision.approver,
            approval_basis=decision.decision_basis,
            openapi_source_reference=proposal.openapi_source_reference,
            semantic_source_reference=proposal.semantic_source_reference,
            active=True,
        )
