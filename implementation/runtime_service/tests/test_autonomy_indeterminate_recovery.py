from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from jason_runtime.autonomy_worker_runtime import (
    GovernedAutonomyActionPort,
    OperationalAutonomyError,
)


class _Ledger:
    def __init__(self, observed_match: bool = True):
        self.observed_match = observed_match
        self.reconciled = []

    def evidence(self, approval_id):
        assert approval_id == "approval-1"
        return {
            "state": "consumed",
            "execution_plan_json": json.dumps({
                "canonical_capability": "service.ticket.update",
                "normalized_payload": {
                    "id": 143589,
                    "queueID": 29683489,
                    "status": 8,
                    "billingCodeID": 29682801,
                },
            }),
        }

    def reconcile_consumed_success(self, request, *, output, reason_code):
        self.reconciled.append((request, output, reason_code))


class _Factory:
    def __init__(self, ledger):
        self.execution_ledger = ledger

    def build(self, **kwargs):
        return SimpleNamespace(
            approval_id="approval-1",
            correlation_id="corr-1",
            client_id=None,
        )

    def build_observe(self, **kwargs):
        assert kwargs["capability_name"] == "service.ticket.read"
        assert kwargs["arguments"] == {"ticket_id": 143589}
        return SimpleNamespace(kind="read")


class _PromotionStore:
    def find_scope_approved(self, **kwargs):
        return SimpleNamespace(
            approval_id="owner-promotion",
            allowed_capabilities=("service.ticket.update",),
        )


class _Orchestrator:
    def __init__(self, *, observed_match=True):
        self.observed_match = observed_match
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        if getattr(request, "kind", "") == "read":
            status = 8 if self.observed_match else 1
            return SimpleNamespace(
                status=SimpleNamespace(value="succeeded"),
                output={
                    "data": {
                        "items": [{
                            "id": 143589,
                            "queueID": 29683489,
                            "status": status,
                            "billingCodeID": 29682801,
                        }]
                    }
                },
            )
        return SimpleNamespace(
            status=SimpleNamespace(value="denied"),
            error_code="APPROVAL_CONSUMPTION_REJECTED",
            reason_codes=("approval_consumption_rejected",),
        )


_SCOPE = SimpleNamespace(
    playbook_id="backupiq_endpoint_backup",
    playbook_version="1",
    policy_id="policy-1",
    required_action_capabilities=("service.ticket.update",),
)


def test_consumed_ticket_update_reconciles_from_exact_provider_readback():
    ledger = _Ledger()
    port = GovernedAutonomyActionPort(
        request_factory=_Factory(ledger),
        orchestrator=_Orchestrator(observed_match=True),
        promotion_store=_PromotionStore(),
    )

    output = port.execute(
        _SCOPE,
        "service.ticket.update",
        {
            "payload": {
                "id": 143589,
                "queueID": "Jason",
                "status": "In Progress",
                "billingCodeID": "Remote Support",
            }
        },
    )

    verification = output["data"]["jasonVerification"]
    assert verification["readbackVerified"] is True
    assert verification["recoveryDisposition"] == "confirmed_completed"
    assert verification["verifiedFields"] == ["billingCodeID", "queueID", "status"]
    assert len(ledger.reconciled) == 1
    assert ledger.reconciled[0][2] == "indeterminate_provider_readback_confirmed"


def test_consumed_ticket_update_mismatch_remains_failed_closed():
    ledger = _Ledger()
    port = GovernedAutonomyActionPort(
        request_factory=_Factory(ledger),
        orchestrator=_Orchestrator(observed_match=False),
        promotion_store=_PromotionStore(),
    )

    with pytest.raises(OperationalAutonomyError, match="APPROVAL_CONSUMPTION_REJECTED"):
        port.execute(
            _SCOPE,
            "service.ticket.update",
            {
                "payload": {
                    "id": 143589,
                    "queueID": "Jason",
                    "status": "In Progress",
                    "billingCodeID": "Remote Support",
                }
            },
        )

    assert ledger.reconciled == []
