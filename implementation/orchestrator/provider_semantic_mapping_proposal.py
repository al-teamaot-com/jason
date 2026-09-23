from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .provider_corroborating_evidence_review import CorroboratingEvidence
from .provider_semantic_statement import AuthoritativeSemanticStatement


@dataclass(frozen=True, slots=True)
class SemanticMappingProposal:
    provider_id: str
    canonical_fact: str
    provider_schema: str
    provider_field: str
    openapi_source_reference: str
    semantic_source_reference: str
    proposal_status: str = "pending_technology_steward_review"
    approved: bool = False
    active: bool = False

    def __post_init__(self) -> None:
        if self.approved or self.active:
            raise PermissionError(
                "proposal creation cannot approve or activate semantic mapping"
            )

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "canonical_fact": self.canonical_fact,
            "provider_schema": self.provider_schema,
            "provider_field": self.provider_field,
            "openapi_source_reference": self.openapi_source_reference,
            "semantic_source_reference": self.semantic_source_reference,
            "proposal_status": self.proposal_status,
            "approved": False,
            "active": False,
        }


@dataclass(frozen=True, slots=True)
class GovernedCrossSourceSemanticMappingProposer:
    def propose(
        self,
        *,
        structural_evidence: CorroboratingEvidence,
        semantic_statement: AuthoritativeSemanticStatement,
    ) -> SemanticMappingProposal:
        if structural_evidence.semantic_proof:
            raise PermissionError("structural evidence may not carry semantic proof")

        if semantic_statement.semantic_mapping_approved:
            raise PermissionError("semantic statement may not pre-approve mapping")

        if structural_evidence.provider_id != semantic_statement.provider_id:
            raise PermissionError("cross-source provider mismatch")

        if (
            structural_evidence.unsupported_fact
            != semantic_statement.canonical_fact
        ):
            raise PermissionError("cross-source canonical fact mismatch")

        if not structural_evidence.read_only_operations:
            raise ValueError(
                "mapping proposal requires documented read-only response path"
            )

        return SemanticMappingProposal(
            provider_id=structural_evidence.provider_id,
            canonical_fact=structural_evidence.unsupported_fact,
            provider_schema=structural_evidence.documented_schema,
            provider_field=structural_evidence.documented_field,
            openapi_source_reference=structural_evidence.source_reference,
            semantic_source_reference=semantic_statement.source_reference,
        )
