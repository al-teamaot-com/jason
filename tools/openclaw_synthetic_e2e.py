#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO / "implementation"
OPENCLAW_SRC = IMPLEMENTATION / "connectors" / "openclaw" / "src"
for path in (IMPLEMENTATION, OPENCLAW_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from jason_openclaw.connector import OpenClawConnector  # noqa: E402
from jason_openclaw.ingress import GovernedOpenClawIngress  # noqa: E402
from jason_openclaw.key_registry import FileBackedTrustedKeyRegistry  # noqa: E402
from jason_openclaw.runtime import (  # noqa: E402
    GateChainPolicyEvaluator,
    JasonAuthorityEvaluator,
    OpenClawOrchestratorDispatcher,
    SQLiteReplayStore,
)
from jason_openclaw.security_audit import SQLiteIngressSecurityAudit  # noqa: E402
from kernel.identity_authority import (  # noqa: E402
    ExecutionContextValidator,
    IdentityAuthorityService,
    SQLiteApprovalRepository,
    SQLiteAuthorityGrantRepository,
    SQLiteIdentityAuthorityStore,
    SQLiteIdentityRepository,
)
from kernel.resolution import (  # noqa: E402
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator import (  # noqa: E402
    CentralOrchestrator,
    InvocationResult,
    SQLiteOrchestrationEventStore,
)
from orchestrator.authority import JKD001OrchestrationContextEnforcer  # noqa: E402
from orchestrator.gates import (  # noqa: E402
    CANONICAL_GOVERNANCE_GATES,
    GateDecision,
    GateOutcome,
    GovernanceGateChain,
)

SYNTHETIC_CAPABILITY = "jason.synthetic.health"
SYNTHETIC_VERSION = "1.0.0"
SYNTHETIC_PROVIDER = "jason.synthetic.local"


@dataclass(frozen=True)
class AllowGate:
    name: str

    def evaluate(self, context) -> GateDecision:
        return GateDecision(
            gate=self.name,
            outcome=GateOutcome.ALLOW,
            reason_code="synthetic_gate_allow",
            evidence={"synthetic": True},
        )


class SyntheticResolution:
    def resolve(self, request):
        if request.capability_name != SYNTHETIC_CAPABILITY:
            return CapabilityResolutionResult(
                execution_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability_name=request.capability_name,
                capability_version=request.capability_version,
                outcome=ResolutionOutcome.UNRESOLVED,
                capability_status=CapabilityResolutionStatus.NOT_FOUND,
                reason_codes=("synthetic_capability_not_registered",),
            )
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version=SYNTHETIC_VERSION,
            outcome=ResolutionOutcome.RESOLVED,
            capability_status=CapabilityResolutionStatus.RESOLVED_EXACT,
            reason_codes=("synthetic_capability_resolved",),
            eligible_provider_ids=(SYNTHETIC_PROVIDER,),
            selected_provider_id=SYNTHETIC_PROVIDER,
        )


class SyntheticInvoker:
    def invoke(self, *, request, resolution) -> InvocationResult:
        if resolution.selected_provider_id != SYNTHETIC_PROVIDER:
            raise RuntimeError("synthetic provider mismatch")
        return InvocationResult(
            output={
                "ok": True,
                "synthetic": True,
                "capability": request.capability_name,
                "organization_id": request.organization_id,
                "principal_id": request.principal_id,
            },
            attempts=1,
        )


def build_runtime(args):
    authority_store = SQLiteIdentityAuthorityStore(args.authority_database)
    authority_service = IdentityAuthorityService(
        identities=SQLiteIdentityRepository(authority_store),
        grants=SQLiteAuthorityGrantRepository(authority_store),
        approvals=SQLiteApprovalRepository(authority_store),
        contexts=authority_store,
        audit=authority_store,
    )
    authority = JasonAuthorityEvaluator(authority_service)
    validator = ExecutionContextValidator(authority_store)
    orchestrator_audit = SQLiteOrchestrationEventStore(args.orchestration_audit)
    orchestrator = CentralOrchestrator(
        resolution=SyntheticResolution(),
        invoker=SyntheticInvoker(),
        audit=orchestrator_audit,
        authority_context=JKD001OrchestrationContextEnforcer(validator),
        require_authority_context=True,
    )
    dispatcher = OpenClawOrchestratorDispatcher(
        orchestrator=orchestrator,
        capability_versions={SYNTHETIC_CAPABILITY: SYNTHETIC_VERSION},
        authority_contexts=authority,
        policy_ids=("openclaw-ingress", "synthetic-e2e"),
    )
    gates = GovernanceGateChain([AllowGate(name) for name in CANONICAL_GOVERNANCE_GATES])
    ingress_audit = SQLiteIngressSecurityAudit(args.security_audit)
    connector = OpenClawConnector(
        dispatcher=dispatcher,
        authority=authority,
        audit=ingress_audit,
        replay=SQLiteReplayStore(args.replay_database),
        policy=GateChainPolicyEvaluator(gates),
    )
    authenticator = FileBackedTrustedKeyRegistry(args.key_registry).build_authenticator()
    ingress = GovernedOpenClawIngress(
        connector=connector,
        authenticator=authenticator,
        audit=ingress_audit,
        machine_principal_bindings={args.machine_identity: args.principal_id},
        require_machine_principal_binding=True,
    )
    return ingress, authority_store, ingress_audit, orchestrator_audit


def run(args) -> int:
    envelope = json.loads(args.signed_envelope.read_text(encoding="utf-8"))
    if envelope.get("capability") != SYNTHETIC_CAPABILITY:
        raise ValueError(f"signed envelope must request {SYNTHETIC_CAPABILITY}")
    if envelope.get("principal", {}).get("principal_id") != args.principal_id:
        raise ValueError("signed envelope principal does not match expected principal")

    ingress, authority_store, ingress_audit, orchestrator_audit = build_runtime(args)
    try:
        first = ingress.handle(envelope)
        second = ingress.handle(envelope)
        correlation_id = str(envelope["correlation_id"])
        authority_events = authority_store.connection.execute(
            "SELECT COUNT(*) FROM authority_audit WHERE correlation_id=?",
            (correlation_id,),
        ).fetchone()[0]
        ingress_events = len(ingress_audit.list_by_correlation(correlation_id))
        orchestration_events = len(orchestrator_audit.list_by_correlation(correlation_id))

        passed = (
            first.get("status") == "completed"
            and first.get("result", {}).get("status") == "succeeded"
            and second.get("error_code") == "replay_detected"
            and authority_events >= 1
            and ingress_events >= 2
            and orchestration_events >= 1
        )
        report: Mapping[str, Any] = {
            "status": "pass" if passed else "fail",
            "machine_identity": args.machine_identity,
            "principal_id": args.principal_id,
            "capability": SYNTHETIC_CAPABILITY,
            "correlation_id": correlation_id,
            "first_request_status": first.get("status"),
            "orchestration_status": first.get("result", {}).get("status"),
            "replay_status": second.get("status"),
            "replay_error_code": second.get("error_code"),
            "authority_audit_events": authority_events,
            "ingress_audit_events": ingress_events,
            "orchestration_audit_events": orchestration_events,
            "provider_contacted": False,
            "provider_credentials_used": False,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if passed else 2
    finally:
        authority_store.close()
        ingress_audit.close()
        orchestrator_audit.close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run signed OpenClaw -> JKD-001 -> governance -> orchestrator synthetic proof")
    p.add_argument("--signed-envelope", type=Path, required=True)
    p.add_argument("--authority-database", type=Path, default=Path("/var/lib/jason/authority/authority.sqlite3"))
    p.add_argument("--replay-database", type=Path, default=Path("/var/lib/jason/openclaw/replay.sqlite3"))
    p.add_argument("--security-audit", type=Path, default=Path("/var/lib/jason/openclaw/security-audit.sqlite3"))
    p.add_argument("--orchestration-audit", type=Path, default=Path("/var/lib/jason/openclaw/orchestration-events.sqlite3"))
    p.add_argument("--key-registry", type=Path, default=Path("/var/lib/jason/openclaw/trusted-keys/registry.json"))
    p.add_argument("--machine-identity", default="svc-openclaw-gateway")
    p.add_argument("--principal-id", default="svc-openclaw-gateway")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "fail", "error_type": type(exc).__name__, "message": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
