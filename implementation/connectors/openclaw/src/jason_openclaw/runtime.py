from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Protocol
from uuid import uuid4

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator import CentralOrchestrator, OrchestrationMode, OrchestrationRequest
from orchestrator.gates import GateContext, GateOutcome, GovernanceGateChain

from .models import CapabilityRequest


class IdentityAuthorityService(Protocol):
    def evaluate(
        self,
        *,
        principal_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
        authentication_assurance: str,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class JasonAuthorityEvaluator:
    service: IdentityAuthorityService

    def evaluate(self, request: CapabilityRequest) -> str:
        decision = self.service.evaluate(
            principal_id=request.principal.principal_id,
            organization_id=request.principal.organization_id,
            client_id=request.principal.client_id,
            capability=request.capability,
            requested_mode=request.requested_mode,
            authentication_assurance=request.principal.authentication_assurance,
        )
        if decision not in {"allowed", "denied", "approval_required"}:
            return "denied"
        return decision


@dataclass(frozen=True, slots=True)
class GateChainPolicyEvaluator:
    gates: GovernanceGateChain

    def evaluate(self, request: CapabilityRequest) -> str:
        result = self.gates.evaluate(
            GateContext(
                correlation_id=request.correlation_id,
                principal_id=request.principal.principal_id,
                organization_id=request.principal.organization_id,
                client_id=request.principal.client_id,
                capability=request.capability,
                requested_mode=request.requested_mode,
                arguments=dict(request.arguments),
            )
        )
        mapping = {
            GateOutcome.ALLOW: "allowed",
            GateOutcome.DENY: "denied",
            GateOutcome.APPROVAL_REQUIRED: "approval_required",
        }
        return mapping[result.outcome]


@dataclass(frozen=True, slots=True)
class OpenClawOrchestratorDispatcher:
    orchestrator: CentralOrchestrator
    capability_versions: Mapping[str, str]
    policy_ids: tuple[str, ...] = ("openclaw-ingress",)

    def dispatch(self, request: CapabilityRequest) -> Mapping[str, Any]:
        version = self.capability_versions.get(request.capability)
        if version is None:
            raise KeyError(request.capability)

        result = self.orchestrator.execute(
            OrchestrationRequest(
                execution_id=f"openclaw-{uuid4()}",
                correlation_id=request.correlation_id,
                principal_id=request.principal.principal_id,
                organization_id=request.principal.organization_id,
                client_id=request.principal.client_id,
                capability_name=request.capability,
                capability_version=version,
                requested_mode=request.requested_mode,
                orchestration_mode=OrchestrationMode.EXECUTE,
                authority_allowed=True,
                approval_present=False,
                risk="low",
                data_handling=DataHandlingPolicy(
                    classification="internal",
                    hosted_processing_allowed=False,
                    retention_allowed=False,
                ),
                budget=ExecutionBudget(
                    maximum_estimated_cost=Decimal("0"),
                    maximum_attempts=1,
                ),
                arguments=dict(request.arguments),
                policy_ids=self.policy_ids,
                requester_kind="service",
            )
        )
        return {
            "execution_id": result.execution_id,
            "status": result.status.value,
            "reason_codes": list(result.reason_codes),
            "provider_id": result.provider_id,
            "output": dict(result.output),
            "artifact_references": [
                {
                    "reference": item.reference,
                    "media_type": item.media_type,
                    "sha256": item.sha256,
                }
                for item in result.artifact_references
            ],
        }


class SQLiteReplayStore:
    """Durable request-id replay protection for one OpenClaw ingress."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS openclaw_replay_claims (
                    claim_key TEXT PRIMARY KEY,
                    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def claim(self, request_id: str) -> bool:
        key = request_id.strip()
        if not key:
            return False
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO openclaw_replay_claims (claim_key) VALUES (?)",
                    (key,),
                )
            except sqlite3.IntegrityError:
                return False
        return True
