from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from kernel.resolution import CapabilityResolutionResult
from orchestrator import ArtifactReference, InvocationResult, OrchestrationRequest

from .context import AutotaskBusinessContextError, AutotaskBusinessContextReader
from .local_llm import (
    BusinessContextBriefing,
    LocalBusinessContextAnalysisError,
    OllamaBusinessContextAnalyzer,
)


class BusinessContextInvocationError(RuntimeError):
    """Safe failure for CAP-003 business-context execution."""

    def __init__(self, message: str, *, error_code: str = "BUSINESS_CONTEXT_INVOCATION_FAILED") -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class BusinessContextEvidence:
    schema_version: str
    evidence_type: str
    capability: str
    execution_id: str
    correlation_id: str
    principal_id: str
    organization_id: str
    company_name: str
    discovered_company_id: str
    focused_ticket_number: str | None
    contacts_count: int
    configurations_count: int
    tickets_count: int
    contracts_count: int
    projects_count: int
    local_model: str
    local_processing_only: bool
    provider_side_change: bool
    raw_provider_content_persisted: bool
    briefing_sha256: str
    created_at: str
    status: str
    evidence_sha256: str


class AutotaskBusinessContextInvoker:
    """Compose governed Autotask business reads and local analysis."""

    capability_name = "autotask.business.context"

    def __init__(
        self,
        *,
        reader: AutotaskBusinessContextReader,
        analyzer: OllamaBusinessContextAnalyzer,
        repository_root: Path,
    ) -> None:
        self._reader = reader
        self._analyzer = analyzer
        self._repository_root = repository_root.resolve()

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if resolution.capability_name != self.capability_name:
            raise BusinessContextInvocationError(
                "Resolved capability does not match Autotask business context.",
                error_code="CAPABILITY_MISMATCH",
            )
        company_name = self._required_argument(request, "company_name")
        focused_ticket_number = self._optional_argument(request, "ticket_number")
        evidence_directory = Path(
            self._required_argument(request, "evidence_directory")
        ).expanduser().resolve()
        self._require_outside_repository(evidence_directory)
        try:
            evidence_directory.mkdir(parents=True, exist_ok=True)
            os.chmod(evidence_directory, 0o700)
        except OSError as exc:
            raise BusinessContextInvocationError(
                "Unable to prepare CAP-003 evidence directory.",
                error_code="EVIDENCE_DIRECTORY_FAILED",
            ) from exc

        briefing_path = evidence_directory / (
            f"autotask-business-briefing-{request.execution_id}.json"
        )
        evidence_path = evidence_directory / (
            f"autotask-business-context-{request.execution_id}.json"
        )
        for path in (briefing_path, evidence_path):
            if path.exists():
                raise BusinessContextInvocationError(
                    f"CAP-003 artifact already exists; overwrite denied: {path.name}",
                    error_code="ARTIFACT_OVERWRITE_DENIED",
                )

        try:
            context = self._reader.read_company_context(
                company_name=company_name,
                correlation_id=request.correlation_id,
                principal_id=request.principal_id,
                organization_id=request.organization_id,
            )
        except AutotaskBusinessContextError as exc:
            raise BusinessContextInvocationError(
                str(exc),
                error_code=exc.error_code,
            ) from exc

        if focused_ticket_number and not self._ticket_exists(
            context.tickets,
            focused_ticket_number,
        ):
            raise BusinessContextInvocationError(
                "Requested ticket focus was not present in the discovered company context.",
                error_code="TICKET_FOCUS_NOT_FOUND",
            )

        try:
            briefing = self._analyzer.analyze(
                context,
                focus_ticket_number=focused_ticket_number,
            )
        except LocalBusinessContextAnalysisError as exc:
            raise BusinessContextInvocationError(
                str(exc),
                error_code=exc.error_code,
            ) from exc

        try:
            self._write_json(briefing_path, briefing.as_dict())
            evidence = self._build_evidence(
                request=request,
                company_name=company_name,
                focused_ticket_number=focused_ticket_number,
                context=context,
                briefing=briefing,
                briefing_path=briefing_path,
            )
            self._write_json(evidence_path, asdict(evidence))
        except OSError as exc:
            raise BusinessContextInvocationError(
                "Unable to persist CAP-003 evidence artifacts.",
                error_code="ARTIFACT_WRITE_FAILED",
            ) from exc

        return InvocationResult(
            output={
                "company_name": str(context.company.get("companyName", company_name)),
                "company_id": context.company_id,
                "focused_ticket_number": focused_ticket_number,
                "record_counts": {
                    "contacts": len(context.contacts),
                    "configurations": len(context.configurations),
                    "tickets": len(context.tickets),
                    "contracts": len(context.contracts),
                    "projects": len(context.projects),
                },
                "executive_summary": briefing.executive_summary,
                "operational_observations": list(briefing.operational_observations),
                "service_risks": list(briefing.service_risks),
                "recommended_focus": list(briefing.recommended_focus),
                "notable_relationships": list(briefing.notable_relationships),
                "confidence": briefing.confidence,
                "model": briefing.model,
                "provider_side_change": False,
            },
            artifact_references=(
                self._artifact(briefing_path),
                self._artifact(evidence_path),
            ),
            attempts=1,
        )

    def _build_evidence(
        self,
        *,
        request: OrchestrationRequest,
        company_name: str,
        focused_ticket_number: str | None,
        context: Any,
        briefing: BusinessContextBriefing,
        briefing_path: Path,
    ) -> BusinessContextEvidence:
        core: dict[str, Any] = {
            "schema_version": "1.0",
            "evidence_type": "autotask-business-context",
            "capability": self.capability_name,
            "execution_id": request.execution_id,
            "correlation_id": request.correlation_id,
            "principal_id": request.principal_id,
            "organization_id": request.organization_id,
            "company_name": company_name,
            "discovered_company_id": context.company_id,
            "focused_ticket_number": focused_ticket_number,
            "contacts_count": len(context.contacts),
            "configurations_count": len(context.configurations),
            "tickets_count": len(context.tickets),
            "contracts_count": len(context.contracts),
            "projects_count": len(context.projects),
            "local_model": briefing.model,
            "local_processing_only": True,
            "provider_side_change": False,
            "raw_provider_content_persisted": False,
            "briefing_sha256": self._sha256(briefing_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "approved",
        }
        digest = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return BusinessContextEvidence(**core, evidence_sha256=digest)

    def _require_outside_repository(self, path: Path) -> None:
        try:
            path.relative_to(self._repository_root)
        except ValueError:
            return
        raise BusinessContextInvocationError(
            "Business-context artifacts must be outside the repository.",
            error_code="EVIDENCE_PATH_INSIDE_REPOSITORY",
        )

    @staticmethod
    def _required_argument(request: OrchestrationRequest, name: str) -> str:
        value = request.arguments.get(name)
        if value is None or not str(value).strip():
            raise BusinessContextInvocationError(
                f"Required business-context argument is missing: {name}",
                error_code="REQUIRED_ARGUMENT_MISSING",
            )
        return str(value).strip()

    @staticmethod
    def _optional_argument(request: OrchestrationRequest, name: str) -> str | None:
        value = request.arguments.get(name)
        if value is None:
            return None
        canonical = str(value).strip()
        return canonical or None

    @staticmethod
    def _ticket_exists(tickets: Any, ticket_number: str) -> bool:
        canonical = ticket_number.strip().casefold()
        return any(
            str(ticket.get("ticketNumber", "")).strip().casefold() == canonical
            for ticket in tickets
        )

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
