"""Isolated hosting of Jason's existing canonical Owner-plan approval service.

No Ticket Core, provider credentials, Owner signing key, arbitrary capability
router or second approval ledger is created. Current identities/grants/bindings
are read-only; subordinate execution contexts stay in this component's state.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sqlite3
from pathlib import Path
import stat
import threading
import time

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget, ExecutionPolicyEngine, CostEstimator, InMemoryPricingRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from kernel.identity_authority import (SQLiteIdentityAuthorityStore, SQLiteIdentityRepository,
    SQLiteAuthorityGrantRepository, SQLiteApprovalRepository, IdentityAuthorityService,
    ExecutionContextValidator)
from kernel.resolution import GovernedCapabilityResolutionEngine
from jason_openclaw.key_registry import FileBackedTrustedKeyRegistry
from orchestrator.authority import JKD001OrchestrationContextEnforcer
from orchestrator.contracts import OrchestrationRequest, OrchestrationMode
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.service import CentralOrchestrator
from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore
from autonomous_remediation.autonomous_principal import AutonomousPrincipal
from .owner_objective_capabilities import (
    CAPABILITIES, TEST_CAPABILITY, ObjectiveRootInvoker, NonexecutingAcceptanceInvoker,
    register_objective_actions, register_nonexecuting_acceptance)
from .owner_objective_root_client import ObjectiveRootClient
from .universal_teams_approval import build_universal_teams_approval_runtime, UniversalApprovalPolicyFile
from .universal_plan_issuance import UniversalPlanIssuer, ExistingTeamsApprovalDelivery
from .universal_plan_status import UniversalPlanStatusMaintenance

PREFIX = "planapproval-objective-"


class ComponentAudit:
    def append(self, event_type, payload):
        # Business/provider content and signatures never enter service stdout.
        print(json.dumps({"event": event_type, "execution_id": payload.get("execution_id"),
                          "stage": payload.get("stage")}), flush=True)


@dataclass
class Enrollment:
    client: object

    def stage(self, *, proposal, requests, pending):
        if (len(requests) == 1 and requests[0].capability_name == TEST_CAPABILITY
                and dict(requests[0].arguments) == {"test_only": True, "execution_permitted": False}
                and proposal.scope.production_allowed is False):
            return {"approval_id": proposal.approval_id,
                    "plan_fingerprint": proposal.plan_fingerprint,
                    "card_instance_challenge": pending.metadata["card_instance_challenge"]}
        return self.client.stage(proposal=proposal, requests=requests, pending=pending)

    def record_delivery(self, *, approval_id, receipt):
        # The Root worker has no enrollment for the separate nonexecuting case.
        if approval_id == self.nonexecuting_id:
            return
        return self.client.record_delivery(approval_id=approval_id, receipt=receipt)


@dataclass
class ObjectiveDelivery:
    client: object
    nonexecuting_id: str
    ordinary: object
    clock: object

    def deliver(self, request):
        if request.approval_id == self.nonexecuting_id:
            return self.ordinary.deliver(request)
        # Privileged objectives are displayed and delivered by Root from its
        # retained exact manifest. The UID1000 issuer cannot substitute a benign
        # card for a privileged action or assert an arbitrary delivery witness.
        from orchestrator.approval_delivery import ApprovalDeliveryReceipt
        result = self.client.call("deliver", approval_id=request.approval_id)
        if result.get("approval_id") != request.approval_id:
            raise PermissionError("Root delivery belongs to a different objective")
        return ApprovalDeliveryReceipt("microsoft_teams", result["provider_message_id"], self.clock())


def build(config, *, delivery=None, root_client=None, clock=lambda: datetime.now(timezone.utc)):
    if config.get("schema_version") != "1.0" or config.get("enabled") is not True:
        raise PermissionError("Owner objective component is not activated")
    state = Path(config["state_dir"])
    core = SQLiteIdentityAuthorityStore(config["authority_db"], read_only=True)
    contexts = SQLiteIdentityAuthorityStore(state / "execution-contexts.sqlite3")
    identities, grants = SQLiteIdentityRepository(core), SQLiteAuthorityGrantRepository(core)
    approvals = SQLiteApprovalRepository(contexts)
    authority = IdentityAuthorityService(identities, grants, approvals, contexts=contexts, clock=clock)
    bindings = SQLiteMicrosoftIdentityBindingStore(config["bindings_db"], read_only=True)
    keys = FileBackedTrustedKeyRegistry(config["trusted_keys_registry"])
    auth = keys.build_authenticator()
    registry = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_objective_actions(capabilities=registry, providers=providers, now=clock())
    register_nonexecuting_acceptance(capabilities=registry, providers=providers, now=clock())
    invokers = CapabilityInvokerRegistry()
    execution = SQLiteGovernedExecutionLedger(str(state / "execution-ledger.sqlite3"), clock=clock)
    execution.initialize()
    resolution = GovernedCapabilityResolutionEngine(capabilities=registry, providers=providers,
        policy=ExecutionPolicyEngine(cost_estimator=CostEstimator(InMemoryPricingRegistry())))
    central = CentralOrchestrator(resolution=resolution, invoker=invokers, audit=ComponentAudit(),
        authority_context=JKD001OrchestrationContextEnforcer(ExecutionContextValidator(contexts, clock=clock)),
        require_authority_context=True, governed_execution_ledger=execution)
    handler = build_universal_teams_approval_runtime(mode="enforced",
        database_path=config["plans_db"], policy_path=config["policy_path"],
        bindings=bindings, identities=identities, grants=grants, formal_approvals=approvals,
        authority=authority, authenticator=auth,
        allowed_machine_identities=frozenset(config["allowed_machine_identities"]),
        orchestrator=central, governed_execution_ledger=execution, clock=clock)
    client = root_client or ObjectiveRootClient(Path(config["spool"]))
    invoker = ObjectiveRootInvoker(lambda: handler, client, execution)
    for name in CAPABILITIES:
        invokers.register(name, invoker)
    invokers.register(TEST_CAPABILITY, NonexecutingAcceptanceInvoker())
    handler.plan_runner.indeterminate_readback = invoker.readback
    enrollment = Enrollment(client)
    enrollment.nonexecuting_id = config["campaign"]["deny_approval_id"]
    transport = delivery or ExistingTeamsApprovalDelivery(
        gateway_url=config["teams_gateway_url"], token_file=Path(config["teams_token_file"]),
        bindings=bindings, clock=clock)
    root_delivery = ObjectiveDelivery(client, config["campaign"]["deny_approval_id"], transport, clock)
    issuer = UniversalPlanIssuer(handler, UniversalApprovalPolicyFile(Path(config["policy_path"]), clock=clock),
        authority, registry, bindings, root_delivery, clock=clock, objective_enrollment=enrollment)
    handler = replace(handler, issuer=issuer)
    app = ObjectiveApplication(config, handler, execution, bindings, identities, client, clock)
    if delivery is None:
        from .playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
        app.status_maintenance = UniversalPlanStatusMaintenance(handler, bindings, identities,
            TeamsGatewayPlaybookApprovalSender, config["teams_gateway_url"], Path(config["teams_token_file"]),
            clock=clock, approval_id_prefix=PREFIX)
    return app


@dataclass
class ObjectiveApplication:
    config: dict
    handler: object
    execution: object
    bindings: object
    identities: object
    root_client: object
    clock: object
    status_maintenance: object = None
    issuance_lock: object = field(default_factory=threading.RLock)

    def _canonical_decision(self, approval_id, evidence_hash):
        accepted = self.handler.service.teams_flow.approval_service.repository.accepted_decision(approval_id)
        if accepted is None:
            return False
        if (accepted.status != "approved" or accepted.channel != "microsoft_teams"
                or accepted.authentication_evidence_hash != evidence_hash):
            raise PermissionError("different or nonaffirmative canonical decision")
        return True

    def _callback(self, envelope, parsed):
        submit = parsed.approval_submit
        return self.handler.handle(approval_id=submit.approval_id, decision=submit.decision,
            microsoft_tenant_id=parsed.microsoft_tenant_id,
            microsoft_object_id=parsed.microsoft_object_id,
            conversation_id=parsed.conversation_id, channel_response_id=submit.channel_response_id,
            decided_at=parsed.issued_at, selections=submit.selections, signed_envelope=envelope)

    def _handoff_pending(self, approval_id):
        return {"status": "blocked", "approval_id": approval_id,
                "executed": False, "plan_status": "decision_handoff_pending",
                "reply": {"text": "The signed decision is retained for validation. "
                         "No execution is authorized until both approval checks succeed. "
                         "Do not submit another decision for this plan."}}

    def _recover_recorded_decision(self, approval_id, evidence_hash):
        if not self._canonical_decision(approval_id, evidence_hash):
            return None
        self.handler.requests.finish_objective_handoff(approval_id, evidence_hash,
            state="recorded", now=self.clock())
        # The canonical maintenance worker independently re-verifies original
        # evidence, current authority and native gates. Do not claim execution.
        return {"status": "completed", "approval_id": approval_id,
                "approval_status": "approved", "executed": False,
                "reply": {"text": "The original approval was recorded. "
                         "Jason will verify continuation through the existing worker."}}

    def _run_handoff(self, approval_id, evidence_hash, envelope, parsed):
        existing = self._recover_recorded_decision(approval_id, evidence_hash)
        if existing is not None:
            return existing
        # Existing Root verification is mandatory. No new signing or permission
        # path is introduced and a rejected native decision is not retried.
        try:
            proposal = self.handler.proposals.require(approval_id)
            self.handler.requests.verify_proposal(proposal)
            admitted = self.root_client.call("admit", approval_id=approval_id,
                                             signed_envelope=envelope)
            if (admitted.get("owner_decision_recorded") is not True
                    or admitted.get("approval_id") != approval_id
                    or admitted.get("plan_fingerprint") != proposal.plan_fingerprint):
                raise PermissionError("Root did not retain this exact decision")
            result = self._callback(envelope, parsed)
            if not self._canonical_decision(approval_id, evidence_hash):
                raise PermissionError("canonical approval not recorded")
            self.handler.requests.finish_objective_handoff(approval_id, evidence_hash,
                state="recorded", now=self.clock())
            return result
        except PermissionError:
            # If canonical acceptance was already atomically persisted, a
            # later publication exception cannot turn it into a new decision.
            recovered = self._recover_recorded_decision(approval_id, evidence_hash)
            if recovered is not None:
                return recovered
            self.handler.requests.finish_objective_handoff(approval_id, evidence_hash,
                state="rejected", now=self.clock())
            raise
        except (TimeoutError, OSError, sqlite3.OperationalError):
            # Only transient transport/storage failure may be retried. Both
            # original validators still run with their normal freshness gates.
            recovered = self._recover_recorded_decision(approval_id, evidence_hash)
            return recovered if recovered is not None else self._handoff_pending(approval_id)

    def interaction(self, envelope):
        token = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        _, parsed = self.handler.evidence_verifier.parse(token)
        submit = parsed.approval_submit
        if submit is None or not submit.approval_id.startswith(PREFIX):
            raise PermissionError("approval is outside the isolated objective component")
        if submit.approval_id == self.config["campaign"]["deny_approval_id"] or submit.decision != "approve":
            return self._callback(envelope, parsed)
        with self.issuance_lock:
            principal = self.handler.evidence_verifier.verify(token)
            approval_id, evidence_hash = submit.approval_id, principal.authentication_evidence_hash
            if self._canonical_decision(approval_id, evidence_hash):
                # Do not permit a new callback to consume an old decision.
                raise PermissionError("plan decision was already recorded")
            pending = self.handler.service.teams_flow.approval_service.repository.get(approval_id)
            proposal = self.handler.proposals.require(approval_id)
            self.handler.requests.verify_proposal(proposal)
            if (pending is None or pending.status.value != "pending"
                    or dict(submit.selections) != {"card_challenge": pending.metadata.get("card_instance_challenge")}):
                raise PermissionError("original pending objective card required")
            # Retain only a cryptographically verified, live-bound and currently
            # permitted candidate; Root and the canonical service subsequently
            # reperform all acceptance checks. The pointer itself is not approval.
            flow = self.handler.service.teams_flow
            response = flow.ingress.accept_verified_interaction(principal=principal,
                payload={"approval_id": approval_id, "decision": "approve",
                         "organization_id": proposal.organization_id,
                         "channel_response_id": submit.channel_response_id}, decided_at=self.clock())
            if response.approver_identity_id == proposal.requester_id:
                raise PermissionError("requester cannot approve their own plan")
            for step in self.handler.requests.steps(approval_id):
                self.handler.policy.assert_request_allowed(step, required=step.requester_kind == "service")
                if not flow.approval_service.authority.can_approve(
                        approver_identity_id=response.approver_identity_id,
                        organization_id=step.organization_id, client_id=step.client_id,
                        capability=step.capability_name, requested_mode=step.permission_mode):
                    raise PermissionError("current approver authority required")
            self.handler.requests.retain_objective_handoff(approval_id, evidence_hash,
                                                           envelope, now=self.clock())
            return self._run_handoff(approval_id, evidence_hash, envelope, parsed)

    def _recover_handoffs(self):
        # Reuse the existing maintenance loop, private DB and signed evidence.
        # Never backdate verification or manufacture an accepted decision when
        # an unaccepted original callback has expired.
        with self.issuance_lock:
            for approval_id, evidence_hash in self.handler.requests.pending_objective_handoffs(prefix=PREFIX):
                try:
                    if self._recover_recorded_decision(approval_id, evidence_hash) is not None:
                        continue
                    envelope = self.handler.requests.transport_evidence(evidence_hash)
                    token = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
                    _, parsed = self.handler.evidence_verifier.parse(token)
                    principal = self.handler.evidence_verifier.verify(token)
                    if (principal.authentication_evidence_hash != evidence_hash
                            or parsed.approval_submit.approval_id != approval_id
                            or parsed.approval_submit.decision != "approve"):
                        raise PermissionError("retained objective evidence changed")
                except PermissionError:
                    # Fail closed on changed, invalid or expired material. A
                    # conflicting canonical decision remains intact.
                    self.handler.requests.finish_objective_handoff(approval_id, evidence_hash,
                        state="rejected", now=self.clock())
                    continue
                try:
                    self._run_handoff(approval_id, evidence_hash, envelope, parsed)
                except PermissionError:
                    pass  # Durable terminal rejection; other work may continue.

    def issue(self, case):
        with self.issuance_lock:
            return self._issue(case)

    def _issue(self, case):
        campaign = self.config["campaign"]
        approval_id = campaign[case + "_approval_id"]
        prior = self.handler.service.teams_flow.approval_service.repository.get(approval_id)
        if prior is not None:
            if case == "approve" and prior.status.value == "pending":
                self._recover_root_delivery(prior)
            return False
        if case == "approve":
            denied = self.handler.service.teams_flow.approval_service.repository.accepted_decision(
                campaign["deny_approval_id"])
            if denied is None or denied.status != "denied":
                return False
        return self._issue_plan(approval_id, datetime.fromisoformat(campaign["issued_at"]), test=case == "deny")

    def _issue_plan(self, approval_id, issued_at, *, test=False):
        campaign = self.config["campaign"]
        names = (TEST_CAPABILITY,) if test else CAPABILITIES
        args = ({"test_only": True, "execution_permitted": False}
                if test else campaign["step_arguments"])
        requests = tuple(OrchestrationRequest(
            execution_id=approval_id + "-" + str(index), correlation_id=approval_id,
            principal_id=self.config["requester_identity_id"], organization_id="aot",
            capability_name=name, capability_version="1.0.0",
            requested_mode="deterministic", orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=False, approval_present=False,
            risk="low" if test else "critical",
            data_handling=DataHandlingPolicy("internal", False, retention_allowed=True),
            budget=ExecutionBudget(Decimal("0")), arguments=args,
            permission_mode="execute", requester_kind="service")
            for index, name in enumerate(names))
        issuer = replace(self.handler.issuer, approval_id_factory=lambda: approval_id,
                         clock=lambda: issued_at)
        issuer.submit_service_plan(requests=requests,
            principal=AutonomousPrincipal(self.config["requester_identity_id"], "aot"),
            title=("TEST ONLY: choose Deny" if test
                   else "Complete documentation publisher restoration and scheduled verification"),
            summary=("This separate test cannot execute a production action, even if approved."
                     if test else
                     "One decision covers the reviewed restore and its scheduled readback. Jason executes and verifies both steps."),
            production=not test, ttl_seconds=self.config["objective_ttl_seconds"])
        return True

    def activated(self):
        activation = self.config.get("activation_path")
        if activation is None:
            return True
        ready = read_profile(Path(activation))
        return ready.get("ready") is True and ready.get("source_sha") == self.config["source_sha"]

    def submit_registered(self, *, template_id, request_id):
        """Request one immutable registered plan; never grant human authority."""
        import re
        if template_id != "documentation-publisher" or not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
            raise PermissionError("REGISTERED_OBJECTIVE_REQUEST_REQUIRED")
        approval_id = PREFIX + request_id
        campaign = self.config["campaign"]
        if approval_id in (campaign["deny_approval_id"], campaign["approve_approval_id"]):
            raise PermissionError("ACCEPTANCE_OBJECTIVE_ID_RESERVED")
        with self.issuance_lock:
            denied = self.handler.service.teams_flow.approval_service.repository.accepted_decision(campaign["deny_approval_id"])
            progress = self.handler.requests.progress(campaign["approve_approval_id"])
            if (not self.activated() or denied is None or denied.status != "denied"
                    or progress is None or progress["state"] != "completed"
                    or self.root_client.call("status", approval_id=campaign["approve_approval_id"]).get("state") != "verified_complete"):
                raise PermissionError("LIVE_OWNER_ACCEPTANCE_REQUIRED")
            now = self.clock()
            issued_at = self.handler.requests.objective_submission(
                approval_id=approval_id, template_id=template_id, now=now, prefix=PREFIX,
                maximum_active=2, ttl_seconds=self.config["objective_ttl_seconds"])
            pending = self.handler.service.teams_flow.approval_service.repository.get(approval_id)
            if pending is None:
                if now >= issued_at + timedelta(seconds=self.config["objective_ttl_seconds"]):
                    raise PermissionError("OBJECTIVE_SUBMISSION_EXPIRED")
                self._issue_plan(approval_id, issued_at)
            elif pending.status.value == "pending":
                self._recover_root_delivery(pending)
            return self.submission_status(request_id=request_id)

    def submission_status(self, *, request_id):
        import re
        if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
            raise PermissionError("OBJECTIVE_REQUEST_ID_REQUIRED")
        approval_id = PREFIX + request_id
        if not self.handler.requests.contains(approval_id):
            raise PermissionError("OBJECTIVE_NOT_FOUND")
        proposal = self.handler.proposals.require(approval_id)
        pending = self.handler.service.teams_flow.approval_service.repository.get(approval_id)
        return {"approval_id": approval_id, "template_id": "documentation-publisher",
                "state": (self.handler.requests.progress(approval_id) or {}).get("state", "staging"),
                "decision": pending.status.value if pending else None,
                "expires_at": proposal.scope.expires_at.isoformat(),
                "plan_fingerprint": proposal.plan_fingerprint}

    def _recover_root_delivery(self, pending):
        from orchestrator.approval_audit import ApprovalAuditEventType
        from orchestrator.approval_delivery import ApprovalRequestDeliveryCoordinator
        audit = self.handler.service.teams_flow.audit
        events = audit.sink.list_for_approval(approval_id=pending.approval_id,
                                              organization_id=pending.organization_id)
        from orchestrator.approval_audit import ApprovalAuditRecorder
        if not ApprovalAuditRecorder.verify_chain(events):
            raise PermissionError("existing objective delivery audit is invalid")
        if any(event.event_type is ApprovalAuditEventType.DELIVERY_RECORDED for event in events):
            return
        coordinator = ApprovalRequestDeliveryCoordinator(
            self.handler.service.teams_flow.approval_service, audit, self.handler.issuer.delivery)
        try:
            # Root returns its prior verified send, or performs the first send
            # only when no native delivery claim exists. An unknown send denies.
            receipt = self.handler.issuer.delivery.deliver(pending)
            self.handler.issuer.objective_enrollment.record_delivery(
                approval_id=pending.approval_id, receipt=receipt)
            coordinator._record(event_type=ApprovalAuditEventType.DELIVERY_RECORDED,
                request=pending, occurred_at=receipt.delivered_at, actor_identity_id=None,
                channel=receipt.channel, channel_reference_id=receipt.channel_reference_id,
                metadata={"recovery_source": "root_sealed_delivery"})
            self.handler.requests.record_progress(pending.approval_id, state="awaiting_approval",
                now=self.clock())
        except (TimeoutError, PermissionError, OSError):
            self.handler.requests.record_progress(pending.approval_id, state="blocked",
                now=self.clock(), reason_code="approval_delivery_root_readback_required")

    def maintenance(self):
        activation = self.config.get("activation_path")
        if activation is not None:
            ready = read_profile(Path(activation))
            if ready.get("ready") is not True or ready.get("source_sha") != self.config["source_sha"]:
                return
        self._recover_handoffs()
        self.issue("deny")
        self.issue("approve")
        for approval_id in self.handler.requests.objective_submission_ids(
                prefix=PREFIX, now=self.clock(), ttl_seconds=self.config["objective_ttl_seconds"]):
            try:
                self.submit_registered(template_id="documentation-publisher",
                                       request_id=approval_id.removeprefix(PREFIX))
            except Exception as exc:
                print(json.dumps({"event": "owner_objective_submission_blocked",
                                  "reason": type(exc).__name__}), flush=True)
        for approval_id in self.handler.requests.candidate_ids(limit=32, prefix=PREFIX, include_indeterminate=True):
            if approval_id.startswith(PREFIX):
                self.handler.plan_runner.process(approval_id)
                break
        if self.status_maintenance is not None:
            self.status_maintenance.tick()


def read_profile(path):
    meta = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0
            or meta.st_nlink != 1 or stat.S_IMODE(meta.st_mode) != 0o444
            or not 0 < meta.st_size <= 65536):
        raise PermissionError("Root-owned activation profile required")
    return json.loads(path.read_bytes())


def main():
    config = read_profile(Path("/run/jason/owner-objective/profile.json"))
    app = build(config)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path != "/health":
                self.send_error(404); return
            raw = json.dumps({"status": "healthy", "source_sha": config["source_sha"],
                              "component": "owner-objective"}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(raw)
        def do_POST(self):
            self.connection.settimeout(10)
            if self.path != "/v1/openclaw/teams/conversation":
                self.send_error(404); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("bounded signed request required")
                result = app.interaction(json.loads(self.rfile.read(length)))
                status = 200
            except Exception:
                result = {"status": "denied", "executed": False,
                          "reply": {"text": "Jason could not verify this approval. No action was authorized."}}
                status = 403
            self.send_response(status); self.end_headers()
            self.wfile.write(json.dumps(result).encode())
    server = ThreadingHTTPServer(("0.0.0.0", 8097), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    from .owner_objective_submission import start_issuer
    start_issuer(app, Path(config["state_dir"]) / "issuer.sock")
    while True:
        try:
            app.maintenance()
        except Exception as exc:
            print(json.dumps({"event": "owner_objective_maintenance_blocked",
                              "reason": type(exc).__name__}), flush=True)
        time.sleep(15)


if __name__ == "__main__":
    main()
