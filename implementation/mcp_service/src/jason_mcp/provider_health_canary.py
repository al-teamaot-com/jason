from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    AuthorityOutcome,
    AuthorityRequest,
    PermissionMode,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.provider_health_canary_policy import (
    PROVIDER_HEALTH_CANARY_POLICY_ID,
    PROVIDER_HEALTH_CANARY_PRINCIPAL,
    PROVIDER_HEALTH_CANARY_SPECS,
)

from . import server


_ERROR_TOKEN = re.compile(r"[^a-z0-9_]+")


def _error_class(
    *,
    status: str,
    error_code: str | None,
    reason_codes: tuple[str, ...],
) -> str:
    text = " ".join(
        [str(error_code or ""), *[str(item) for item in reason_codes]]
    ).casefold()
    if status == "succeeded":
        return "none"
    if "authority" in text or "no_matching_authority_grant" in text:
        return "authority_denied"
    if "information" in text or "request_access" in text:
        return "information_release_denied"
    if "timeout" in text:
        return "timeout"
    if "unavailable" in text or "credential" in text or "authentication" in text:
        return "provider_unavailable"
    if "provider" in text:
        return "provider_error"
    normalized = _ERROR_TOKEN.sub("_", str(error_code or status).casefold()).strip("_")
    return normalized[:48] or "execution_failed"


def _run_one(spec: Mapping[str, Any]) -> dict[str, Any]:
    app = server._runtime()
    capability_name = str(spec["capability_name"])
    expected_provider = str(spec["provider_id"])
    arguments = dict(spec["arguments"])
    execution_id = f"exec_provider_canary_{uuid4().hex}"
    correlation_id = f"corr_provider_canary_{uuid4().hex}"

    started = time.monotonic()
    decision = app.identity_authority.evaluate(
        AuthorityRequest(
            request_id=execution_id,
            correlation_id=correlation_id,
            principal_id=PROVIDER_HEALTH_CANARY_PRINCIPAL,
            organization_id="aot",
            client_id=None,
            capability=capability_name,
            requested_mode=PermissionMode.OBSERVE,
            authentication_assurance="workload_identity",
        )
    )
    if decision.outcome is not AuthorityOutcome.ALLOWED or decision.execution_context is None:
        elapsed = max(0.0, time.monotonic() - started)
        reasons = tuple(str(item) for item in decision.reason_codes)
        return {
            "provider": expected_provider,
            "capability": capability_name,
            "healthy": False,
            "latency_seconds": round(elapsed, 6),
            "error_class": _error_class(
                status="denied",
                error_code=None,
                reason_codes=reasons,
            ),
            "correlation_id": correlation_id,
        }

    capability = app.capabilities.get_current(
        capability_name=capability_name,
        allow_pilot=False,
    )
    request = OrchestrationRequest(
        execution_id=execution_id,
        correlation_id=correlation_id,
        principal_id=PROVIDER_HEALTH_CANARY_PRINCIPAL,
        organization_id="aot",
        client_id=None,
        capability_name=capability_name,
        capability_version=capability.version,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk=capability.risk_level.value,
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("1.00"),
            maximum_attempts=1,
        ),
        arguments=arguments,
        requester_kind="service",
        principal_attributes={"workload": "provider-health-canary"},
        permission_mode="observe",
        policy_ids=(PROVIDER_HEALTH_CANARY_POLICY_ID,),
        authority_context_id=decision.execution_context.context_id,
    )
    result = app.governed_orchestrator.execute(request)
    elapsed = max(0.0, time.monotonic() - started)
    status = result.status.value
    actual_provider = str(result.provider_id or "")
    reasons = tuple(str(item) for item in result.reason_codes)
    healthy = status == "succeeded" and actual_provider == expected_provider
    error_class = (
        "unexpected_provider"
        if status == "succeeded" and actual_provider != expected_provider
        else _error_class(
            status=status,
            error_code=result.error_code,
            reason_codes=reasons,
        )
    )
    return {
        "provider": expected_provider,
        "capability": capability_name,
        "healthy": healthy,
        "latency_seconds": round(elapsed, 6),
        "error_class": error_class,
        "correlation_id": result.correlation_id or correlation_id,
    }


def run_canaries() -> dict[str, Any]:
    results = []
    for spec in PROVIDER_HEALTH_CANARY_SPECS:
        try:
            results.append(_run_one(spec))
        except Exception:
            results.append(
                {
                    "provider": str(spec["provider_id"]),
                    "capability": str(spec["capability_name"]),
                    "healthy": False,
                    "latency_seconds": 0.0,
                    "error_class": "runner_error",
                    "correlation_id": f"corr_provider_canary_{uuid4().hex}",
                }
            )

    now = datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "generated_at_epoch": now.timestamp(),
        "principal": PROVIDER_HEALTH_CANARY_PRINCIPAL,
        "policy": PROVIDER_HEALTH_CANARY_POLICY_ID,
        "results": results,
    }


def main() -> int:
    print(json.dumps(run_canaries(), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
