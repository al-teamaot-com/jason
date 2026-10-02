from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from kernel.capabilities import CapabilityRegistryService
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    IdentityAuthorityService,
    IdentityRecord,
    PermissionMode,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.provider_mutation_capability_catalog import SERVICE_TICKET_CHARGE_CREATE
from orchestrator.provider_read_capability_catalog import (
    SERVICE_BILLING_ITEM_SEARCH,
    SERVICE_INVOICE_READ,
    SERVICE_RESOURCE_READ,
    SERVICE_TICKET_CHARGE_SEARCH,
    SERVICE_TICKET_READ,
)

from .teams_gateway_transport import TeamsGatewayTransport
from .procurement_inventory_billing import (
    BillingAuditState,
    BillingExpectation,
    SQLiteBillingLeakageStore,
    lori_escalation_text,
    reconcile_hardware_billing,
    technician_disposition_card,
)


AUDIT_WORKER_ID = "jason-procurement-billing-audit"
AUDIT_READ_POLICY_ID = "aot-procurement-billing-audit-read-v1"
LORI_EMAIL = "lori@teamaot.com"
AUDIT_READ_CAPABILITIES = (
    SERVICE_TICKET_READ,
    SERVICE_RESOURCE_READ,
    SERVICE_TICKET_CHARGE_SEARCH,
    SERVICE_BILLING_ITEM_SEARCH,
    SERVICE_INVOICE_READ,
)


def ensure_billing_audit_read_authority(
    authority: IdentityAuthorityService, *, enabled: bool
) -> tuple[str, ...]:
    if not enabled:
        return ()
    identity = IdentityRecord(
        identity_id=AUDIT_WORKER_ID,
        identity_type="service",
        organization_id="aot",
        status="active",
    )
    current = authority.identities.get(AUDIT_WORKER_ID)
    if current is None:
        authority.identities.put(identity)
    elif current != identity:
        raise RuntimeError("procurement billing audit identity conflicts with JKD-001")

    created: list[str] = []
    for capability in AUDIT_READ_CAPABILITIES:
        grant = AuthorityGrant(
            grant_id="grant-procurement-billing-audit-" + capability.replace(".", "-"),
            subject_id=AUDIT_WORKER_ID,
            capability=capability,
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.OBSERVE,
            approval_required=False,
            status="active",
        )
        existing = authority.grants.get(grant.grant_id)
        if existing is None:
            authority.grants.put(grant)
            created.append(grant.grant_id)
        elif existing != grant:
            raise RuntimeError(
                f"procurement billing audit grant conflicts: {grant.grant_id}"
            )
    return tuple(created)


@dataclass
class GovernedBillingAuditReadPort:
    authority: IdentityAuthorityService
    capabilities: CapabilityRegistryService
    orchestrator: Any

    def execute(
        self, capability_name: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        capability = self.capabilities.get_current(
            capability_name=capability_name, allow_pilot=False
        )
        execution_id = "exec_billing_audit_" + uuid4().hex
        correlation_id = "corr_billing_audit_" + uuid4().hex
        decision = self.authority.evaluate(
            AuthorityRequest(
                request_id=execution_id,
                correlation_id=correlation_id,
                principal_id=AUDIT_WORKER_ID,
                organization_id="aot",
                client_id=None,
                capability=capability_name,
                requested_mode=PermissionMode.OBSERVE,
                authentication_assurance="workload_identity",
            )
        )
        if decision.outcome is not AuthorityOutcome.ALLOWED:
            raise PermissionError(
                "billing audit read authority denied: "
                + ",".join(decision.reason_codes)
            )
        if decision.execution_context is None:
            raise PermissionError("billing audit read authority context missing")
        request = OrchestrationRequest(
            execution_id=execution_id,
            correlation_id=correlation_id,
            principal_id=AUDIT_WORKER_ID,
            organization_id="aot",
            client_id=None,
            capability_name=capability_name,
            capability_version=capability.version,
            requested_mode="deterministic",
            permission_mode="observe",
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
            arguments=dict(arguments),
            requester_kind="service",
            principal_attributes={"workload": AUDIT_WORKER_ID},
            policy_ids=(AUDIT_READ_POLICY_ID,),
            authority_context_id=decision.execution_context.context_id,
        )
        result = self.orchestrator.execute(request)
        if result.status.value != "succeeded":
            raise RuntimeError(
                f"billing audit read failed: {capability_name}: {result.error_code}"
            )
        return dict(result.output or {})


@dataclass
class TeamsGatewayBillingAuditSender:
    gateway_url: str
    token_file: Path
    bindings: Any
    lori_email: str = LORI_EMAIL

    def _send(self, *, binding: Any, text: str, card: Mapping[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "aadObjectId": str(binding.microsoft_object_id),
            "tenantId": str(binding.microsoft_tenant_id),
            "text": str(text),
        }
        if card is not None:
            payload["card"] = dict(card)
        transport = TeamsGatewayTransport(
            gateway_url=self.gateway_url,
            token_file=self.token_file,
        )
        result = transport.send(transport.prepare(payload))
        if result.get("status") != "succeeded" or not result.get("message_id"):
            raise RuntimeError("Teams hardware billing notification delivery failed")
        return str(result["message_id"])

    def technician(self, *, jason_identity_id: str, text: str, card: Mapping[str, Any]) -> str:
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=jason_identity_id
        )
        if binding is None:
            raise LookupError("technician Teams binding unavailable")
        return self._send(binding=binding, text=text, card=card)

    def lori(self, *, text: str) -> str:
        binding = self.bindings.find_active_by_email(email_address=self.lori_email)
        if binding is None:
            raise LookupError("Lori Teams binding unavailable")
        return self._send(binding=binding, text=text)


def _data(output: Mapping[str, Any]) -> Mapping[str, Any]:
    value = output.get("data")
    return value if isinstance(value, Mapping) else output


def _items(output: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = _data(output).get("items")
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, Mapping))


def _item(output: Mapping[str, Any]) -> Mapping[str, Any] | None:
    data = _data(output)
    raw = data.get("item")
    if isinstance(raw, Mapping):
        return raw
    items = data.get("items")
    if isinstance(items, list) and len(items) == 1 and isinstance(items[0], Mapping):
        return items[0]
    if "id" in data:
        return data
    return None


class HardwareBillingAuditMaintenance:
    """Reconcile received customer hardware to ticket charge and invoice evidence."""

    def __init__(
        self,
        *,
        submissions: Any,
        cases: SQLiteBillingLeakageStore,
        reads: GovernedBillingAuditReadPort,
        notifications: TeamsGatewayBillingAuditSender,
        actions: Any | None = None,
        interval: timedelta = timedelta(minutes=5),
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        if interval < timedelta(minutes=1):
            raise ValueError("hardware billing audit interval must be at least one minute")
        self.submissions = submissions
        self.cases = cases
        self.reads = reads
        self.notifications = notifications
        self.actions = actions
        self.interval = interval
        self.now = now
        self._next_due: datetime | None = None

    def tick(self) -> bool:
        current = self.now()
        if self._next_due is not None and current < self._next_due:
            return False
        self._next_due = current + self.interval
        self.run_once(now=current)
        return True

    def run_once(self, *, now: datetime | None = None) -> Mapping[str, int]:
        current = now or self.now()
        summary = {
            "eligible": 0,
            "reconciled": 0,
            "unbilled": 0,
            "technician_pending": 0,
            "invoice_exception": 0,
            "billing_exception": 0,
            "technician_notified": 0,
            "charge_created": 0,
            "lori_escalated": 0,
        }
        for submission in self.submissions.list_all():
            customer_quantity = int(submission.get("customer_quantity") or 0)
            received_quantity = int(submission.get("received_quantity") or 0)
            if customer_quantity < 1 or received_quantity < customer_quantity:
                continue
            if str(submission.get("release_state") or "") not in {
                "received_pending_disposition",
                "ready_for_release",
                "released",
            }:
                continue
            ticket_id = submission.get("ticket_id")
            ticket_number = str(submission.get("ticket_number") or "").strip()
            product_id = (submission.get("result") or {}).get("product_id")
            if not ticket_id or not ticket_number or not product_id:
                continue
            summary["eligible"] += 1

            charges = _items(
                self.reads.execute(
                    SERVICE_TICKET_CHARGE_SEARCH,
                    {
                        "ticket_id": int(ticket_id),
                        "product_id": int(product_id),
                        "page_size": 50,
                    },
                )
            )
            billing_items: tuple[Mapping[str, Any], ...] = ()
            exact_charge = next(
                (
                    charge
                    for charge in charges
                    if int(charge.get("ticketID") or 0) == int(ticket_id)
                    and int(charge.get("productID") or 0) == int(product_id)
                ),
                None,
            )
            if exact_charge is not None and bool(exact_charge.get("isBilled")):
                billing_items = _items(
                    self.reads.execute(
                        SERVICE_BILLING_ITEM_SEARCH,
                        {
                            "ticket_charge_id": int(exact_charge["id"]),
                            "page_size": 20,
                        },
                    )
                )

            expected = BillingExpectation(
                ticket_id=int(ticket_id),
                ticket_number=ticket_number,
                product_id=int(product_id),
                quantity=Decimal(str(customer_quantity)),
                unit_price=Decimal(str(submission["retail_price"])),
            )
            reconciliation = reconcile_hardware_billing(
                expected,
                ticket_charges=charges,
                billing_items=billing_items,
            )
            evidence: dict[str, Any] = {
                "ticket_id": int(ticket_id),
                "ticket_number": ticket_number,
                "product_id": int(product_id),
                "expected_quantity": customer_quantity,
                "expected_unit_price": str(submission["retail_price"]),
                "charge_ids": [int(x["id"]) for x in charges if x.get("id")],
                "billing_item_ids": [
                    int(x["id"]) for x in billing_items if x.get("id")
                ],
                "reconciliation_reason": reconciliation.reason,
            }

            if reconciliation.invoice_id is not None:
                invoice = _item(
                    self.reads.execute(
                        SERVICE_INVOICE_READ,
                        {"resource_id": reconciliation.invoice_id},
                    )
                )
                evidence["invoice"] = (
                    {
                        "id": invoice.get("id"),
                        "companyID": invoice.get("companyID"),
                        "invoiceNumber": invoice.get("invoiceNumber"),
                        "invoiceDateTime": invoice.get("invoiceDateTime"),
                        "status": invoice.get("status"),
                    }
                    if invoice
                    else None
                )
                expected_company = submission.get("ticket_company_id")
                if (
                    invoice is None
                    or not expected_company
                    or int(invoice.get("companyID") or 0) != int(expected_company)
                ):
                    reconciliation = type(reconciliation)(
                        state=BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION,
                        charge_id=reconciliation.charge_id,
                        invoice_id=reconciliation.invoice_id,
                        billing_item_id=reconciliation.billing_item_id,
                        reason="customer invoice company does not match ticket company",
                    )
                    evidence["reconciliation_reason"] = reconciliation.reason

            technician_identity_id = self._technician_identity(int(ticket_id))
            case_key = (
                f"submission:{submission['submission_id']}:"
                f"ticket:{ticket_id}:product:{product_id}"
            )
            case = self.cases.upsert_observation(
                case_key=case_key,
                state=reconciliation.state,
                ticket_id=int(ticket_id),
                ticket_number=ticket_number,
                product_id=int(product_id),
                expected_quantity=Decimal(str(customer_quantity)),
                expected_unit_price=Decimal(str(submission["retail_price"])),
                charge_id=reconciliation.charge_id,
                invoice_id=reconciliation.invoice_id,
                billing_item_id=reconciliation.billing_item_id,
                evidence=evidence,
                observed_at=current,
                technician_identity_id=technician_identity_id,
                procurement_submission_id=str(submission["submission_id"]),
            )

            if reconciliation.state is BillingAuditState.RECONCILED:
                summary["reconciled"] += 1
                self._record_release_billing(
                    submission, disposition="charge_created"
                )
            elif reconciliation.state is BillingAuditState.EXISTING_UNBILLED_CHARGE:
                summary["unbilled"] += 1
                self._record_release_billing(
                    submission, disposition="existing_unbilled_charge"
                )
            elif reconciliation.state is BillingAuditState.TECHNICIAN_DISPOSITION_PENDING:
                summary["technician_pending"] += 1
                if (
                    case.get("technician_disposition") == "charge_needed"
                    and self.actions is not None
                ):
                    self._create_missing_charge(
                        submission=submission,
                        current=current,
                    )
                    summary["charge_created"] += 1
                    self._record_release_billing(
                        submission, disposition="charge_created"
                    )
                elif (
                    technician_identity_id
                    and not case.get("technician_disposition")
                    and self.cases.notification_needed(case)
                ):
                    self.notifications.technician(
                        jason_identity_id=technician_identity_id,
                        text=(
                            f"Hardware billing check for {ticket_number}: "
                            f"{customer_quantity} customer item(s) need disposition."
                        ),
                        card=technician_disposition_card(case),
                    )
                    self.cases.mark_notified(case_key, notified_at=current)
                    summary["technician_notified"] += 1
            elif reconciliation.state is BillingAuditState.INVOICE_RECONCILIATION_EXCEPTION:
                summary["invoice_exception"] += 1
            else:
                summary["billing_exception"] += 1

        due = self.cases.due_for_lori_escalation(today=current.date())
        if due:
            self.notifications.lori(text=lori_escalation_text(due))
            for case in due:
                self.cases.mark_escalated(str(case["case_key"]), at=current)
                summary["lori_escalated"] += 1
        return summary

    def _record_release_billing(
        self, submission: Mapping[str, Any], *, disposition: str
    ) -> None:
        current = self.submissions.get(str(submission["submission_id"]))
        if current is None:
            return
        if current.get("billing_disposition") == disposition:
            return
        self.submissions.record_billing_disposition(
            str(submission["submission_id"]), disposition=disposition
        )

    def _technician_identity(self, ticket_id: int) -> str | None:
        ticket = _item(
            self.reads.execute(SERVICE_TICKET_READ, {"ticket_id": ticket_id})
        )
        if ticket is None or not ticket.get("assignedResourceID"):
            return None
        resource = _item(
            self.reads.execute(
                SERVICE_RESOURCE_READ,
                {"resource_id": int(ticket["assignedResourceID"])},
            )
        )
        if resource is None:
            return None
        email = str(resource.get("email") or resource.get("emailAddress") or "").strip()
        if not email:
            return None
        binding = self.notifications.bindings.find_active_by_email(
            email_address=email
        )
        return None if binding is None else str(binding.jason_identity_id)

    def _create_missing_charge(
        self, *, submission: Mapping[str, Any], current: datetime
    ) -> None:
        if self.actions is None:
            raise RuntimeError("charge action executor is not configured")
        product_id = int((submission.get("result") or {})["product_id"])
        self.actions.execute(
            capability_name=SERVICE_TICKET_CHARGE_CREATE,
            payload={
                "ticketID": int(submission["ticket_id"]),
                "productID": product_id,
                "costType": 1,
                "datePurchased": current.astimezone(timezone.utc).isoformat(),
                "name": str(submission["product"]["name"])[:100],
                "unitQuantity": int(submission["customer_quantity"]),
                "unitCost": float(Decimal(str(submission["product"]["cost"]))),
                "unitPrice": float(Decimal(str(submission["retail_price"]))),
                "isBillableToCompany": True,
                "description": (
                    "Jason procurement billing disposition "
                    + str(submission["submission_id"])
                )[:2000],
            },
            submission=submission,
            correlation_id="corr_billing_charge_" + uuid4().hex,
        )
