from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from connectors.autotask.live_read import (
    AutotaskLiveReadRequest,
    GovernedAutotaskLiveRead,
)
from orchestrator import ArtifactReference, InvocationResult, OrchestrationRequest
from kernel.resolution import CapabilityResolutionResult

from .local_llm import OllamaTicketAnalyzer, TicketBriefing


class TicketIntelligenceError(RuntimeError):
    """Safe failure for CAP-002 ticket intelligence."""


@dataclass(frozen=True, slots=True)
class TicketIntelligenceEvidence:
    schema_version: str
    evidence_type: str
    capability: str
    execution_id: str
    correlation_id: str
    principal_id: str
    organization_id: str
    ticket_number: str
    discovered_company_id: str
    autotask_evidence_reference: str
    autotask_evidence_sha256: str
    briefing_sha256: str
    local_model: str
    local_processing_only: bool
    provider_side_change: bool
    raw_ticket_content_persisted: bool
    created_at: str
    status: str
    evidence_sha256: str


class TicketIntelligenceInvoker:
    """Compose canonical Autotask read and local analysis under orchestration."""

    capability_name = "support.ticket.analyze"

    def __init__(
        self,
        *,
        autotask: GovernedAutotaskLiveRead,
        analyzer: OllamaTicketAnalyzer,
        repository_root: Path,
    ) -> None:
        self._autotask = autotask
        self._analyzer = analyzer
        self._repository_root = repository_root.resolve()

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if resolution.capability_name != self.capability_name:
            raise TicketIntelligenceError(
                "Resolved capability does not match ticket intelligence."
            )
        ticket_number = self._required_argument(request, "ticket_number")
        scope = self._required_argument(request, "scope")
        allowed_scope = self._required_argument(request, "allowed_scope")
        if scope != allowed_scope:
            raise PermissionError(
                "Requested scope does not match the authorized scope."
            )
        evidence_directory = Path(
            self._required_argument(request, "evidence_directory")
        ).expanduser().resolve()
        self._require_outside_repository(evidence_directory)
        evidence_directory.mkdir(parents=True, exist_ok=True)
        os.chmod(evidence_directory, 0o700)

        autotask_evidence_path = (
            evidence_directory
            / f"autotask-live-read-{ticket_number}-{request.execution_id}.json"
        )
        briefing_path = (
            evidence_directory
            / f"ticket-briefing-{ticket_number}-{request.execution_id}.json"
        )
        evidence_path = (
            evidence_directory
            / f"ticket-intelligence-{ticket_number}-{request.execution_id}.json"
        )
        for path in (autotask_evidence_path, briefing_path, evidence_path):
            if path.exists():
                raise FileExistsError(
                    f"CAP-002 artifact already exists; overwrite denied: {path.name}"
                )

        snapshot, autotask_evidence = self._autotask.read_ticket(
            AutotaskLiveReadRequest(
                ticket_number=ticket_number,
                scope_name=scope,
                allowed_scope=allowed_scope,
                principal_id=request.principal_id,
                organization_id=request.organization_id,
                correlation_id=request.correlation_id,
                live_read_acknowledged=True,
            ),
            output_path=autotask_evidence_path,
            repository_root=self._repository_root,
        )
        briefing = self._analyzer.analyze(snapshot)
        self._write_json(briefing_path, briefing.as_dict())

        evidence = self._build_evidence(
            request=request,
            ticket_number=ticket_number,
            discovered_company_id=snapshot.company_id,
            autotask_evidence_path=autotask_evidence_path,
            autotask_evidence_sha256=autotask_evidence.evidence_sha256,
            briefing_path=briefing_path,
            briefing=briefing,
        )
        self._write_json(evidence_path, asdict(evidence))

        return InvocationResult(
            output={
                "ticket_number": ticket_number,
                "company_id": snapshot.company_id,
                "summary": briefing.summary,
                "likely_causes": list(briefing.likely_causes),
                "recommended_steps": list(briefing.recommended_steps),
                "escalation_flags": list(briefing.escalation_flags),
                "confidence": briefing.confidence,
                "model": briefing.model,
                "provider_side_change": False,
            },
            artifact_references=(
                self._artifact(autotask_evidence_path),
                self._artifact(briefing_path),
                self._artifact(evidence_path),
            ),
            attempts=1,
        )

    def _build_evidence(
        self,
        *,
        request: OrchestrationRequest,
        ticket_number: str,
        discovered_company_id: str,
        autotask_evidence_path: Path,
        autotask_evidence_sha256: str,
        briefing_path: Path,
        briefing: TicketBriefing,
    ) -> TicketIntelligenceEvidence:
        core: dict[str, Any] = {
            "schema_version": "1.0",
            "evidence_type": "ticket-intelligence",
            "capability": self.capability_name,
            "execution_id": request.execution_id,
            "correlation_id": request.correlation_id,
            "principal_id": request.principal_id,
            "organization_id": request.organization_id,
            "ticket_number": ticket_number,
            "discovered_company_id": discovered_company_id,
            "autotask_evidence_reference": str(autotask_evidence_path),
            "autotask_evidence_sha256": autotask_evidence_sha256,
            "briefing_sha256": self._sha256(briefing_path),
            "local_model": briefing.model,
            "local_processing_only": True,
            "provider_side_change": False,
            "raw_ticket_content_persisted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "approved",
        }
        digest = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return TicketIntelligenceEvidence(**core, evidence_sha256=digest)

    def _require_outside_repository(self, path: Path) -> None:
        try:
            path.relative_to(self._repository_root)
        except ValueError:
            return
        raise TicketIntelligenceError(
            "Ticket-intelligence artifacts must be outside the repository."
        )

    @staticmethod
    def _required_argument(request: OrchestrationRequest, name: str) -> str:
        value = request.arguments.get(name)
        if value is None or not str(value).strip():
            raise TicketIntelligenceError(
                f"Required ticket-intelligence argument is missing: {name}"
            )
        return str(value).strip()

    @classmethod
    def _artifact(cls, path: Path) -> ArtifactReference:
        return ArtifactReference(
            reference=str(path),
            media_type="application/json",
            sha256=cls._sha256(path),
        )

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
