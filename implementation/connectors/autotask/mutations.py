from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorRequest, ConnectorResult
from connectors.core.mutations import (
    ApprovalResolver,
    IdempotencyStore,
    MutationExecutor,
    MutationPlan,
    MutationPolicy,
    RiskLevel,
    require_mutation_authority,
)


class AutotaskMutationConnector:
    """Governed Autotask mutation planner and execution gate.

    This foundation intentionally does not embed live vendor endpoint mappings.
    A production executor must implement the verified Autotask REST operations.
    """

    provider_name = "autotask"
    policies = {
        "autotask.ticket.note.add_internal": MutationPolicy(
            "autotask.ticket.note.add_internal", RiskLevel.LOW
        ),
        "autotask.ticket.note.add_client": MutationPolicy(
            "autotask.ticket.note.add_client", RiskLevel.MEDIUM
        ),
        "autotask.ticket.status.update": MutationPolicy(
            "autotask.ticket.status.update", RiskLevel.MEDIUM
        ),
        "autotask.ticket.assign": MutationPolicy(
            "autotask.ticket.assign", RiskLevel.MEDIUM
        ),
        "autotask.ticket.create": MutationPolicy(
            "autotask.ticket.create", RiskLevel.MEDIUM
        ),
        "autotask.ticket.udf.update": MutationPolicy(
            "autotask.ticket.udf.update", RiskLevel.MEDIUM
        ),
    }
    capabilities = frozenset(policies)

    def __init__(
        self,
        *,
        audit: AuditSink,
        approvals: ApprovalResolver | None = None,
        idempotency: IdempotencyStore | None = None,
        executor: MutationExecutor | None = None,
    ) -> None:
        self._audit = audit
        self._approvals = approvals
        self._idempotency = idempotency
        self._executor = executor

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        policy = self.policies.get(request.context.capability)
        if policy is None:
            raise ValueError(f"Unsupported capability: {request.context.capability}")

        plan = self._build_plan(request)
        digest = self._digest(plan)
        grant = require_mutation_authority(
            request,
            policy,
            argument_digest=digest,
            approval_resolver=self._approvals,
            audit=self._audit,
        )

        self._audit.record(
            "connector.mutation.planned",
            request.context,
            {"provider": self.provider_name, "risk": policy.risk.value, "digest": digest},
        )
        if request.context.mode == "propose":
            return ConnectorResult(
                request.context.capability,
                self.provider_name,
                {"status": "proposed", "argument_digest": digest, "plan": self._plan_data(plan)},
                warnings=plan.warnings,
            )

        if self._executor is None or self._idempotency is None:
            raise RuntimeError("Autotask mutation execution is not configured.")

        key = str(request.arguments["idempotency_key"])
        if not self._idempotency.reserve(key, request.context):
            raise RuntimeError("Duplicate or active idempotency key.")
        try:
            result = self._executor.execute_mutation(request, plan)
            self._idempotency.complete(key, request.context, result.data)
            if grant is not None and grant.single_use and self._approvals is not None:
                self._approvals.consume(grant.approval_id, request.context)
            self._audit.record("connector.mutation.completed", request.context, {"provider": self.provider_name})
            return result
        except Exception:
            self._idempotency.release(key, request.context)
            self._audit.record("connector.mutation.failed", request.context, {"provider": self.provider_name})
            raise

    def _build_plan(self, request: ConnectorRequest) -> MutationPlan:
        a = request.arguments
        capability = request.context.capability
        ticket_id = a.get("ticket_id")
        target: dict[str, Any] = {"ticket_id": int(ticket_id)} if ticket_id is not None else {}

        if capability in {"autotask.ticket.note.add_internal", "autotask.ticket.note.add_client"}:
            note = a.get("note")
            if not isinstance(note, str) or not note.strip():
                raise ValueError("A non-empty note is required.")
            changes = {"note": note.strip(), "visibility": "internal" if capability.endswith("internal") else "client"}
        elif capability == "autotask.ticket.status.update":
            changes = {"status_id": int(a["status_id"])}
        elif capability == "autotask.ticket.assign":
            changes = {"resource_id": int(a["resource_id"])}
        elif capability == "autotask.ticket.udf.update":
            name = a.get("field_name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("field_name is required.")
            changes = {"field_name": name.strip(), "value": a.get("value")}
        elif capability == "autotask.ticket.create":
            required = ("company_id", "title", "description", "queue_id", "priority")
            missing = [name for name in required if a.get(name) in (None, "")]
            if missing:
                raise ValueError(f"Missing required fields: {', '.join(missing)}")
            target = {"company_id": int(a["company_id"])}
            changes = {name: a[name] for name in required if name != "company_id"}
        else:
            raise ValueError(f"Unsupported capability: {capability}")

        return MutationPlan(
            capability=capability,
            provider=self.provider_name,
            risk=self.policies[capability].risk,
            target=target,
            proposed_changes=changes,
            preconditions=("principal_authorized", "client_scope_valid", "current_record_rechecked_before_write"),
            rollback_notes=("Record the prior values before mutation.", "Use a compensating update when supported."),
        )

    @staticmethod
    def _plan_data(plan: MutationPlan) -> Mapping[str, Any]:
        return {
            "capability": plan.capability,
            "provider": plan.provider,
            "risk": plan.risk.value,
            "target": dict(plan.target),
            "proposed_changes": dict(plan.proposed_changes),
            "preconditions": list(plan.preconditions),
            "rollback_notes": list(plan.rollback_notes),
        }

    @classmethod
    def _digest(cls, plan: MutationPlan) -> str:
        canonical = json.dumps(cls._plan_data(plan), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
