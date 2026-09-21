from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorRequest,
    ConnectorResult,
    SecretResolver,
)
from connectors.core.mutations import (
    ApprovalResolver,
    IdempotencyStore,
    MutationPlan,
    MutationPolicy,
    RiskLevel,
    require_mutation_authority,
)
from connectors.kfs.client import KfsApiClient


class KfsMutationExecutor:
    provider_name = "kfs"
    logical_secret = "kfs.runtime"

    def __init__(
        self,
        secrets: SecretResolver,
        *,
        base_url: str,
        api_version: int = 6,
        client_factory=KfsApiClient,
    ) -> None:
        self._secrets = secrets
        self._base_url = base_url
        self._api_version = api_version
        self._client_factory = client_factory

    def execute_mutation(
        self,
        request: ConnectorRequest,
        plan: MutationPlan,
    ) -> ConnectorResult:
        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )
        body = {
            "RequestFrom": credentials["request_from"],
            "RequestTo": credentials["request_to"],
            "BODID": "Global_KFS_Pull_ChangeStatus",
            "deviceIds": list(plan.target["device_ids"]),
            "targetStatus": int(
                plan.proposed_changes["target_status"]
            ),
        }
        payload = self._client_factory(
            credentials,
            base_url=self._base_url,
            api_version=self._api_version,
        ).call(
            "/KFS/ChangeStatus",
            body,
            min_api_version=2,
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=payload,
        )


class KfsMutationConnector:
    """Jason-governed write boundary over the single KFS API access level."""

    provider_name = "kfs"
    policies = {
        "kfs.device.management_status.change": MutationPolicy(
            "kfs.device.management_status.change",
            RiskLevel.HIGH,
        )
    }
    capabilities = frozenset(policies)
    TARGET_STATUS_NAMES = {
        1: "managed",
        2: "unmanaged",
        3: "archived",
        5: "terminated",
    }

    def __init__(
        self,
        *,
        audit: AuditSink,
        approvals: ApprovalResolver | None = None,
        idempotency: IdempotencyStore | None = None,
        executor: KfsMutationExecutor | None = None,
    ) -> None:
        self._audit = audit
        self._approvals = approvals
        self._idempotency = idempotency
        self._executor = executor

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        policy = self.policies.get(request.context.capability)
        if policy is None:
            raise ValueError(
                f"Unsupported capability: {request.context.capability}"
            )

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
            {
                "provider": self.provider_name,
                "risk": policy.risk.value,
                "digest": digest,
            },
        )

        if request.context.mode == "propose":
            return ConnectorResult(
                request.context.capability,
                self.provider_name,
                {
                    "status": "proposed",
                    "argument_digest": digest,
                    "plan": self._plan_data(plan),
                },
                warnings=plan.warnings,
            )

        if self._executor is None or self._idempotency is None:
            raise RuntimeError(
                "KFS mutation execution is not configured."
            )

        key = str(request.arguments["idempotency_key"])
        if not self._idempotency.reserve(key, request.context):
            raise RuntimeError("Duplicate or active idempotency key.")
        try:
            result = self._executor.execute_mutation(request, plan)
            self._idempotency.complete(
                key,
                request.context,
                result.data,
            )
            if (
                grant is not None
                and grant.single_use
                and self._approvals is not None
            ):
                self._approvals.consume(
                    grant.approval_id,
                    request.context,
                )
            self._audit.record(
                "connector.mutation.completed",
                request.context,
                {"provider": self.provider_name},
            )
            return result
        except Exception:
            self._idempotency.release(key, request.context)
            self._audit.record(
                "connector.mutation.failed",
                request.context,
                {"provider": self.provider_name},
            )
            raise

    def _build_plan(
        self,
        request: ConnectorRequest,
    ) -> MutationPlan:
        raw_device_ids = request.arguments.get("device_ids")
        if isinstance(raw_device_ids, str):
            raw_device_ids = [raw_device_ids]
        if not isinstance(raw_device_ids, (list, tuple)):
            raise ValueError(
                "device_ids must be a non-empty list."
            )
        device_ids = tuple(
            str(value).strip()
            for value in raw_device_ids
            if str(value).strip()
        )
        if not device_ids:
            raise ValueError(
                "device_ids must be a non-empty list."
            )

        target_status = int(request.arguments["target_status"])
        if target_status not in self.TARGET_STATUS_NAMES:
            raise ValueError(
                "target_status must be one of 1, 2, 3, or 5."
            )

        warnings = ()
        if target_status == 5:
            warnings = (
                "KFS status 5 terminates/deletes the device from management.",
            )

        return MutationPlan(
            capability=request.context.capability,
            provider=self.provider_name,
            risk=RiskLevel.HIGH,
            target={"device_ids": device_ids},
            proposed_changes={
                "target_status": target_status,
                "target_status_name": self.TARGET_STATUS_NAMES[
                    target_status
                ],
            },
            preconditions=(
                "principal_authorized_for_kfs_write",
                "device_identity_rechecked_before_write",
                "current_management_status_rechecked_before_write",
            ),
            rollback_notes=(
                "Record each device's prior management status before mutation.",
                "Use a compensating ChangeStatus call when the prior state remains valid.",
            ),
            warnings=warnings,
        )

    @staticmethod
    def _plan_data(
        plan: MutationPlan,
    ) -> Mapping[str, Any]:
        return {
            "capability": plan.capability,
            "provider": plan.provider,
            "risk": plan.risk.value,
            "target": {
                "device_ids": list(plan.target["device_ids"])
            },
            "proposed_changes": dict(plan.proposed_changes),
            "preconditions": list(plan.preconditions),
            "rollback_notes": list(plan.rollback_notes),
            "warnings": list(plan.warnings),
        }

    @classmethod
    def _digest(cls, plan: MutationPlan) -> str:
        canonical = json.dumps(
            cls._plan_data(plan),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
