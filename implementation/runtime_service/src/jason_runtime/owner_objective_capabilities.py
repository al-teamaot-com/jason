"""Registered privileged actions, still subject to canonical and native gates."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from kernel.capabilities import CapabilityApproval, CapabilityLifecycle, CapabilityRisk
from kernel.execution_providers import ProviderApproval, ProviderHealth, ProviderLifecycle
from orchestrator.execution_plan import ExecutionPlan, PreparedExecutionPlan
from orchestrator.service import InvocationResult, ProviderOutcomeIndeterminate
from .owner_objective_root_client import ObjectiveRootRequestDenied
from .autonomous_repair_deployment import _apply_capability, _provider

RESTORE = "release.documentation.publisher.restore"
VERIFY = "release.documentation.publisher.verify"
CAPABILITIES = (RESTORE, VERIFY)
PROVIDER = "jason_owner_objective_root"


def register_objective_actions(*, capabilities, providers, now):
    prototype = _apply_capability(now)
    for name in CAPABILITIES:
        capabilities.register(replace(prototype,
            capability_name=name, version="1.0.0",
            display_name=("Restore reviewed documentation publisher" if name == RESTORE
                          else "Verify scheduled documentation publisher"),
            lifecycle_status=CapabilityLifecycle.ACTIVE,
            business_purpose="Complete an exact signed Owner objective through the installed bounded Root executor.",
            risk_level=CapabilityRisk.CRITICAL,
            approval=CapabilityApproval(required=True, approver_classes=("owner",)),
            timeout_seconds=300, maximum_attempts=1,
            metadata={"provider_neutral": "true", "read_only": "false",
                      "write_capability": "true", "resource_types": "documentation_publisher",
                      "operation": name.rsplit(".", 1)[1], "mcp_action_enabled": "false"}))
    provider = _provider(now)
    providers.register(replace(provider, provider_id=PROVIDER,
        display_name="Jason governed objective Root executor",
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY, approval_status=ProviderApproval.APPROVED,
        capabilities=frozenset(CAPABILITIES),
        limits=replace(provider.limits, maximum_execution_seconds=300)))


@dataclass(frozen=True)
class ObjectiveRootInvoker:
    handler: Callable
    root_client: object
    execution_ledger: object

    def _context(self, request):
        h = self.handler()
        evidence = self.execution_ledger.evidence(request.approval_id or "")
        if (evidence is None or not evidence.get("parent_approval_id")
                or not request.authority_context_id or not request.authority_allowed):
            raise PermissionError("original plan reservation and current JKD authority are required")
        parent_id = evidence["parent_approval_id"]
        proposal = h.proposals.require(parent_id)
        h.requests.verify_proposal(proposal)
        if evidence.get("approved_plan_fingerprint") != proposal.plan_fingerprint:
            raise PermissionError("execution reservation does not bind the original reviewed plan")
        steps = h.requests.steps(parent_id)
        indices = [i for i, step in enumerate(steps) if step.execution_id == request.execution_id]
        if len(indices) != 1:
            raise PermissionError("execution is not exactly one retained plan step")
        index = indices[0]
        original = steps[index]
        if (request.capability_name not in CAPABILITIES
                or request.capability_name != original.capability_name
                or request.principal_id != original.principal_id
                or request.organization_id != original.organization_id
                or request.client_id != original.client_id
                or dict(request.arguments) != dict(original.arguments)):
            raise PermissionError("Root invocation changed the reviewed request")
        accepted = h.service.teams_flow.approval_service.repository.accepted_decision(parent_id)
        if accepted is None or accepted.status != "approved":
            raise PermissionError("no canonical authenticated parent decision")
        signed = h.requests.transport_evidence(accepted.authentication_evidence_hash)
        return parent_id, index, signed

    def prepare_execution_plan(self, *, request, resolution):
        parent, index, _ = self._context(request)
        if resolution.selected_provider_id != PROVIDER:
            raise PermissionError("Root step resolved to an unregistered provider")
        return PreparedExecutionPlan(ExecutionPlan(
            principal_id=request.principal_id, organization_id=request.organization_id,
            client_id=request.client_id, canonical_capability=request.capability_name,
            selected_provider_id=PROVIDER, provider_capability=request.capability_name,
            action_method="LOCAL_ROOT_QUEUE", resource_type="documentation_publisher",
            resource_identifier=request.arguments["component_id"],
            normalized_path="/owner-objectives/" + parent + "/steps/" + str(index),
            normalized_payload=dict(request.arguments)))

    def invoke_execution_plan(self, *, request, resolution, prepared):
        expected = self.prepare_execution_plan(request=request, resolution=resolution)
        if prepared.plan.fingerprint != expected.plan.fingerprint:
            raise PermissionError("prepared Root execution material changed")
        parent, index, signed = self._context(request)
        try:
            result = self.root_client.call("execute", approval_id=parent,
                                         step_index=index, signed_envelope=signed)
        except (TimeoutError, ObjectiveRootRequestDenied) as exc:
            if isinstance(exc, ObjectiveRootRequestDenied) and exc.execution_state == "not_started":
                raise
            try:
                result = self.root_client.call("readback", approval_id=parent,
                                             step_index=index, signed_envelope=signed)
            except (TimeoutError, PermissionError, OSError) as readback_error:
                raise ProviderOutcomeIndeterminate("native Root readback is required") from readback_error
        if (result.get("status") != "verified" or result.get("approval_id") != parent
                or result.get("step_index") != index
                or result.get("candidate_sha") != request.arguments["candidate_sha"]
                or result.get("scope_sha256") != request.arguments["scope_sha256"]):
            raise PermissionError("native Root outcome is not verified for this exact step")
        return InvocationResult(output=result, attempts=1)

    def readback(self, request):
        parent, index, signed = self._context(request)
        result = self.root_client.call("readback", approval_id=parent,
                                     step_index=index, signed_envelope=signed)
        proposal = self.handler().proposals.require(parent)
        args = request.arguments
        if (result.get("status") != "verified" or result.get("approval_id") != parent
                or result.get("plan_fingerprint") != proposal.plan_fingerprint
                or result.get("step_index") != index
                or any(result.get(key) != args[key] for key in
                       ("candidate_sha", "scope_sha256", "manifest_sha256"))):
            raise ProviderOutcomeIndeterminate("exact native Root readback is unavailable")
        return result

    def invoke(self, **kwargs):
        raise PermissionError("a prepared canonical execution plan is required")


TEST_CAPABILITY = "interaction.owner.acceptance.record"
TEST_PROVIDER = "jason_owner_objective_nonexecuting_test"


def register_nonexecuting_acceptance(*, capabilities, providers, now):
    prototype = _apply_capability(now)
    capabilities.register(replace(prototype,
        capability_name=TEST_CAPABILITY, version="1.0.0",
        display_name="Record nonexecuting Owner acceptance test",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose="Verify a real Owner Deny decision without any possible production action.",
        risk_level=CapabilityRisk.LOW, approval=CapabilityApproval(required=True, approver_classes=("owner",)),
        timeout_seconds=5, maximum_attempts=1,
        metadata={"provider_neutral": "true", "read_only": "false",
                  "write_capability": "true", "resource_types": "owner_acceptance_test",
                  "operation": "record", "test_only": "true", "execution_permitted": "false"}))
    provider = _provider(now)
    providers.register(replace(provider, provider_id=TEST_PROVIDER,
        display_name="Jason nonexecuting acceptance recorder",
        lifecycle_status=ProviderLifecycle.AVAILABLE, health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED, capabilities=frozenset({TEST_CAPABILITY})))


class NonexecutingAcceptanceInvoker:
    def prepare_execution_plan(self, *, request, resolution):
        if (request.capability_name != TEST_CAPABILITY
                or resolution.selected_provider_id != TEST_PROVIDER
                or dict(request.arguments) != {"test_only": True, "execution_permitted": False}):
            raise PermissionError("only the exact nonexecuting acceptance case is permitted")
        return PreparedExecutionPlan(ExecutionPlan(
            principal_id=request.principal_id, organization_id=request.organization_id,
            client_id=request.client_id, canonical_capability=TEST_CAPABILITY,
            selected_provider_id=TEST_PROVIDER, provider_capability=TEST_CAPABILITY,
            action_method="RECORD_TEST_ONLY", resource_type="owner_acceptance_test",
            resource_identifier="nonexecuting", normalized_path="/acceptance/nonexecuting",
            normalized_payload=dict(request.arguments)))

    def invoke_execution_plan(self, *, request, resolution, prepared):
        if prepared.plan.fingerprint != self.prepare_execution_plan(
                request=request, resolution=resolution).plan.fingerprint:
            raise PermissionError("nonexecuting test material changed")
        return InvocationResult(output={"test_only": True, "execution_permitted": False,
                                        "production_mutations": False}, attempts=1)

    def invoke(self, **kwargs):
        raise PermissionError("canonical execution preparation is required")
