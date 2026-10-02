from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from tools.zero_to_operational import (
    PHASES,
    ZeroToOperationalError,
    receipt_to_json,
    run_zero_to_operational,
)


class PassingExecutor:
    def execute_phase(self, phase, context):
        return {
            "status": "PASS",
            "summary": phase + " passed",
            "evidence": phase,
            "context_update": {phase + "_complete": True},
        }


class FailingExecutor:
    def execute_phase(self, phase, context):
        if phase == "verify_ready":
            return {
                "status": "FAIL",
                "summary": "candidate not READY",
                "blocker": "provider_not_ready",
            }
        return {"status": "PASS", "summary": phase + " passed"}


def schema():
    return json.load(
        open(
            "config/schemas/zero-to-operational-receipt.schema.json",
            encoding="utf-8",
        )
    )


def test_synthetic_full_pass_does_not_claim_deployability():
    receipt = run_zero_to_operational(
        scenario_id="synthetic-v1",
        mode="synthetic",
        executor=PassingExecutor(),
    )
    assert receipt.status == "PASS"
    assert receipt.deployability_proven is False
    assert receipt.production_authorized is False
    assert len(receipt.phases) == len(PHASES)
    assert all(item.status == "PASS" for item in receipt.phases)
    Draft202012Validator(schema()).validate(json.loads(receipt_to_json(receipt)))


def test_host_full_pass_is_only_mode_that_can_prove_deployability():
    receipt = run_zero_to_operational(
        scenario_id="host-v1",
        mode="host",
        executor=PassingExecutor(),
    )
    assert receipt.status == "PASS"
    assert receipt.deployability_proven is True
    assert receipt.production_authorized is False


def test_failure_skips_all_later_phases_and_cannot_prove_deployability():
    receipt = run_zero_to_operational(
        scenario_id="host-failure",
        mode="host",
        executor=FailingExecutor(),
    )
    assert receipt.status == "FAIL"
    assert receipt.deployability_proven is False
    ready_index = PHASES.index("verify_ready")
    assert receipt.phases[ready_index].status == "FAIL"
    assert all(
        item.status == "SKIPPED"
        for item in receipt.phases[ready_index + 1 :]
    )


def test_receipt_hash_is_deterministic():
    one = run_zero_to_operational(
        scenario_id="deterministic",
        mode="synthetic",
        executor=PassingExecutor(),
    )
    two = run_zero_to_operational(
        scenario_id="deterministic",
        mode="synthetic",
        executor=PassingExecutor(),
    )
    assert one.receipt_sha256 == two.receipt_sha256


def test_executor_cannot_smuggle_production_authorization():
    class BadExecutor:
        def execute_phase(self, phase, context):
            return {
                "status": "PASS",
                "context_update": {"production_authorized": True},
            }

    receipt = run_zero_to_operational(
        scenario_id="bad",
        mode="host",
        executor=BadExecutor(),
    )
    assert receipt.status == "FAIL"
    assert receipt.production_authorized is False
    assert receipt.deployability_proven is False
    assert "production authorization" in receipt.phases[0].summary


def test_acceptance_evidence_rejects_secret_bearing_keys():
    class LeakyExecutor:
        def execute_phase(self, phase, context):
            return {
                "status": "PASS",
                "root_token": "should-never-enter-receipt",
            }

    receipt = run_zero_to_operational(
        scenario_id="leaky",
        mode="synthetic",
        executor=LeakyExecutor(),
    )
    assert receipt.status == "FAIL"
    assert "ZeroToOperationalError" in receipt.phases[0].summary
    assert receipt.deployability_proven is False
