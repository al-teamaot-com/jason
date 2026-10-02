from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import uuid4

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision,
    ApprovalPresentation,
    ApprovalRequest,
    ApprovalRequestService,
    ApprovalResponse,
)
from kernel.capabilities import CapabilityRegistryService
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    ApprovalRecord,
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    IdentityAuthorityService,
    IdentityRecord,
    PermissionMode,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.governed_execution_ledger import SQLiteGovernedExecutionLedger
from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_VENDOR_CREATE,
    SERVICE_PRODUCT_CREATE,
    SERVICE_PRODUCT_VENDOR_CREATE,
    SERVICE_OPPORTUNITY_CREATE,
    SERVICE_QUOTE_LOCATION_CREATE,
    SERVICE_QUOTE_CREATE,
    SERVICE_QUOTE_ITEM_CREATE,
    SERVICE_PURCHASE_ORDER_CREATE,
    SERVICE_PURCHASE_ORDER_ITEM_CREATE,
    SERVICE_PURCHASE_ORDER_UPDATE,
    SERVICE_TICKET_CHARGE_CREATE,
)
from orchestrator.provider_read_capability_catalog import (
    SERVICE_COMPANY_SEARCH,
    SERVICE_COMPANY_READ,
    SERVICE_CONTACT_SEARCH,
    SERVICE_PRODUCT_SEARCH,
    SERVICE_RESOURCE_SEARCH,
    SERVICE_TICKET_SEARCH,
)
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    TeamsConversationPrincipalEvidence,
)
from orchestrator.teams_request_factory import GovernedTeamsOrchestrationRequestFactory
from .procurement_web_read import CAPABILITY as PROCUREMENT_WEB_PRODUCT_READ
from .procurement_inventory_billing import AllocationPlan

PROCUREMENT_APPROVAL_CAPABILITY = "procurement.submission.execute"
PROCUREMENT_WORKER_ID = "jason-procurement-worker"
PROCUREMENT_POLICY_ID = "aot-procurement-delegated-spend-v1"
DEFAULT_DB = Path("/var/lib/jason/procurement/submissions.sqlite3")


class ProcurementFlowError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SQLiteProcurementSubmissionStore:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path))
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS procurement_submissions (
                    submission_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()
        os.chmod(self.path, 0o600)

    def put_new(self, submission_id: str, payload: Mapping[str, Any]) -> None:
        body = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute(
                "INSERT INTO procurement_submissions(submission_id,payload,status,updated_at) "
                "VALUES(?,?,?,?)",
                (
                    submission_id,
                    body,
                    str(payload.get("status") or "draft"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get(self, submission_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(str(self.path)) as connection:
            row = connection.execute(
                "SELECT payload FROM procurement_submissions WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
        return None if row is None else dict(json.loads(str(row[0])))

    def update(self, submission_id: str, payload: Mapping[str, Any]) -> None:
        body = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(str(self.path)) as connection:
            cursor = connection.execute(
                "UPDATE procurement_submissions SET payload=?,status=?,updated_at=? "
                "WHERE submission_id=?",
                (
                    body,
                    str(payload.get("status") or "unknown"),
                    datetime.now(timezone.utc).isoformat(),
                    submission_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ProcurementFlowError("procurement submission no longer exists")

    def list_all(self) -> tuple[dict[str, Any], ...]:
        with sqlite3.connect(str(self.path)) as connection:
            rows = connection.execute(
                "SELECT payload FROM procurement_submissions ORDER BY updated_at, submission_id"
            ).fetchall()
        return tuple(dict(json.loads(str(row[0]))) for row in rows)

    def record_receipt(self, submission_id: str, *, received_quantity: int) -> dict[str, Any]:
        payload = self.get(submission_id)
        if payload is None:
            raise ProcurementFlowError("procurement submission no longer exists")
        if received_quantity < 1:
            raise ProcurementFlowError("received quantity must be positive")
        ordered = int(payload.get("quantity") or 0)
        already = int(payload.get("received_quantity") or 0)
        if already + received_quantity > ordered:
            raise ProcurementFlowError("received quantity exceeds outstanding quantity")
        updated_received = already + received_quantity
        customer = int(payload.get("customer_quantity") or 0)
        release_state = (
            "received_pending_disposition"
            if customer > 0
            else "ready_for_release"
        )
        updated = {
            **payload,
            "received_quantity": updated_received,
            "release_state": release_state,
            "status": (
                "received_pending_disposition"
                if customer > 0
                else "received"
            ),
        }
        self.update(submission_id, updated)
        return updated

    def record_billing_disposition(
        self, submission_id: str, *, disposition: str
    ) -> dict[str, Any]:
        payload = self.get(submission_id)
        if payload is None:
            raise ProcurementFlowError("procurement submission no longer exists")
        customer = int(payload.get("customer_quantity") or 0)
        if customer < 1:
            raise ProcurementFlowError("billing disposition is not applicable to AOT-stock-only allocation")
        if not payload.get("ticket_id") or not payload.get("ticket_number"):
            raise ProcurementFlowError("customer billing disposition requires exact ticket")
        allowed = {
            "charge_created",
            "existing_unbilled_charge",
            "no_charge_contract",
            "no_charge_warranty",
            "no_charge_internal",
        }
        if disposition not in allowed:
            raise ProcurementFlowError("billing disposition is not release-authorizing")
        received = int(payload.get("received_quantity") or 0)
        release_state = (
            "ready_for_release"
            if received >= customer
            else str(payload.get("release_state") or "ordered")
        )
        updated = {
            **payload,
            "billing_disposition": disposition,
            "billing_state": disposition,
            "release_state": release_state,
            "status": (
                "ready_for_release"
                if release_state == "ready_for_release"
                else str(payload.get("status") or "ordered")
            ),
        }
        self.update(submission_id, updated)
        return updated

    def release_stock(self, submission_id: str, *, release_quantity: int) -> dict[str, Any]:
        from .procurement_inventory_billing import ReleaseGate

        payload = self.get(submission_id)
        if payload is None:
            raise ProcurementFlowError("procurement submission no longer exists")
        customer = int(payload.get("customer_quantity") or 0)
        already_released = int(payload.get("released_quantity") or 0)
        if release_quantity < 1 or already_released + release_quantity > customer:
            raise ProcurementFlowError("release quantity exceeds customer allocation")
        try:
            ReleaseGate(
                received_quantity=int(payload.get("received_quantity") or 0),
                release_quantity=already_released + release_quantity,
                customer_quantity=customer,
                ticket_id=int(payload["ticket_id"]) if payload.get("ticket_id") else None,
                billing_disposition=payload.get("billing_disposition"),
            ).validate()
        except ValueError as exc:
            raise ProcurementFlowError(str(exc)) from exc
        released = already_released + release_quantity
        updated = {
            **payload,
            "released_quantity": released,
            "release_state": "released" if released == customer else "ready_for_release",
            "status": "released" if released == customer else "ready_for_release",
        }
        self.update(submission_id, updated)
        return updated


def _decimal(value: Any, *, field: str, allow_zero: bool = True) -> Decimal:
    try:
        result = Decimal(str(value).strip())
    except Exception as exc:
        raise ProcurementFlowError(f"{field} is not a valid amount") from exc
    if result < 0 or (not allow_zero and result == 0):
        raise ProcurementFlowError(f"{field} is outside the allowed range")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _bounded_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ProcurementFlowError(f"{field} is invalid")
    try:
        result = int(str(value).strip())
    except Exception as exc:
        raise ProcurementFlowError(f"{field} is invalid") from exc
    if not 1 <= result <= 1000:
        raise ProcurementFlowError(f"{field} is outside the allowed range")
    return result


def _items(output: Mapping[str, Any]) -> list[dict[str, Any]]:
    data = output.get("data")
    source = data if isinstance(data, Mapping) else output
    raw = source.get("items") if isinstance(source, Mapping) else None
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _resource_id(output: Mapping[str, Any]) -> int:
    data = output.get("data")
    source = data if isinstance(data, Mapping) else output
    if isinstance(source, Mapping):
        verification = source.get("jasonVerification")
        if isinstance(verification, Mapping):
            raw = verification.get("resourceId")
            if str(raw or "").isdigit() and int(raw) > 0:
                return int(raw)
        for key in ("itemId", "itemID", "id"):
            raw = source.get(key)
            if str(raw or "").isdigit() and int(raw) > 0:
                return int(raw)
    raise ProcurementFlowError("Autotask write did not return a durable resource id")


def _submission_digest(payload: Mapping[str, Any]) -> str:
    material = {
        key: value
        for key, value in dict(payload).items()
        if key not in {"status", "approval_id", "result"}
    }
    return sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _domain(url: Any) -> str | None:
    value = str(url or "").strip()
    if not value:
        return None
    parsed = urlsplit(value if "://" in value else "https://" + value)
    return (parsed.hostname or "").casefold() or None


def _norm(value: Any) -> str | None:
    text = " ".join(str(value or "").casefold().split())
    return text or None


def _pricing_choices(cost: Decimal) -> tuple[dict[str, str], ...]:
    choices: list[dict[str, str]] = []
    for multiplier in (Decimal("1.18"), Decimal("1.27"), Decimal("1.36")):
        price = (cost * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        gross = price - cost
        margin = (gross / price * Decimal("100")) if price else Decimal("0")
        choices.append(
            {
                "title": (
                    "$" + f"{price:.0f}" + " — $" + f"{gross:.2f}"
                    + " GP / " + f"{margin.quantize(Decimal('0.1'))}% margin"
                ),
                "value": f"{price:.2f}",
            }
        )
    return tuple(choices)


def _vendor_checks(
    source: Mapping[str, Any], vendor: Mapping[str, Any]
) -> tuple[list[dict[str, str]], list[str]]:
    checks: list[dict[str, str]] = []
    mismatches: list[str] = []
    source_address = (
        source.get("address")
        if isinstance(source.get("address"), Mapping)
        else {}
    )
    candidates = (
        ("website", _domain(source.get("url")), _domain(vendor.get("webAddress"))),
        ("phone", _norm(source.get("phone")), _norm(vendor.get("phone"))),
        ("street", _norm(source_address.get("street")), _norm(vendor.get("address1"))),
        ("city", _norm(source_address.get("city")), _norm(vendor.get("city"))),
        ("state", _norm(source_address.get("state")), _norm(vendor.get("state"))),
        (
            "postal_code",
            _norm(source_address.get("postal_code")),
            _norm(vendor.get("postalCode")),
        ),
    )
    for field, observed, stored in candidates:
        if observed and stored:
            status = "match" if observed == stored else "mismatch"
        elif observed and not stored:
            status = "autotask_missing"
        elif not observed and stored:
            status = "source_missing"
        else:
            continue
        checks.append(
            {
                "field": field,
                "source_value": observed or "",
                "autotask_value": stored or "",
                "status": status,
            }
        )
        if status == "mismatch":
            mismatches.append(field)
    return checks, mismatches


def _card(payload: Mapping[str, Any]) -> dict[str, Any]:
    product = dict(payload["product"])
    vendor = dict(payload["vendor"])
    cost = Decimal(str(product["cost"]))
    prices = _pricing_choices(cost)
    part_default = str(
        product.get("existing_sku")
        or product.get("mpn")
        or product.get("sku")
        or ""
    ).strip()
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": "Procurement",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Vendor", "value": vendor["name"]},
                    {"title": "Item", "value": product["name"]},
                    {"title": "Cost", "value": "$" + f"{cost:.2f}"},
                ],
            },
            {
                "type": "Input.Toggle",
                "id": "create_po",
                "title": "Create purchase order",
                "value": "false",
                "valueOn": "true",
                "valueOff": "false",
            },
            {
                "type": "Input.Toggle",
                "id": "create_client_quote",
                "title": "Create client quote",
                "value": "false",
                "valueOn": "true",
                "valueOff": "false",
            },
            {
                "type": "Input.Text",
                "id": "at_part_number",
                "label": "AT Part #",
                "value": part_default,
                "isRequired": True,
            },
            {
                "type": "Input.ChoiceSet",
                "id": "item_class",
                "label": "Class",
                "style": "compact",
                "value": "it",
                "choices": [
                    {"title": "IT", "value": "it"},
                    {"title": "Copy / Print", "value": "copy_print"},
                    {"title": "Other", "value": "other"},
                ],
            },
            {
                "type": "Input.ChoiceSet",
                "id": "retail_price",
                "label": "Retail",
                "style": "compact",
                "value": prices[1]["value"],
                "choices": [
                    {"title": item["title"], "value": item["value"]}
                    for item in prices
                ],
            },
            {
                "type": "Input.Number",
                "id": "quantity",
                "label": "Ordered Qty",
                "value": 1,
                "min": 1,
                "max": 1000,
            },
            {
                "type": "Input.Number",
                "id": "customer_quantity",
                "label": "Customer Qty",
                "value": 0,
                "min": 0,
                "max": 1000,
            },
            {
                "type": "Input.Number",
                "id": "aot_stock_quantity",
                "label": "AOT Stock Qty",
                "value": 1,
                "min": 0,
                "max": 1000,
            },
            {
                "type": "Input.Text",
                "id": "ticket_number",
                "label": "Ticket # (required for customer qty or client quote)",
                "placeholder": "T20261001.0001",
            },
            {
                "type": "Input.ChoiceSet",
                "id": "billing_treatment",
                "label": "Customer billing",
                "style": "compact",
                "value": "charge_ticket",
                "choices": [
                    {"title": "Charge Ticket", "value": "charge_ticket"},
                    {"title": "No Charge — Contract", "value": "no_charge_contract"},
                    {"title": "No Charge — Warranty", "value": "no_charge_warranty"},
                    {"title": "No Charge — Internal", "value": "no_charge_internal"},
                ],
            },
            {
                "type": "Input.Number",
                "id": "freight",
                "label": "Freight",
                "value": 0,
                "min": 0,
            },
            {
                "type": "Input.Number",
                "id": "tax",
                "label": "Tax",
                "value": 0,
                "min": 0,
            },
            {
                "type": "Input.Number",
                "id": "fees",
                "label": "Other Fees",
                "value": 0,
                "min": 0,
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Submit",
                "data": {
                    "kind": "procurement.submit",
                    "submission_id": str(payload["submission_id"]),
                },
            }
        ],
    }


def _exact_udf(contact: Mapping[str, Any], name: str) -> str | None:
    values = contact.get("userDefinedFields")
    if not isinstance(values, list):
        return None
    matches = [
        str(item.get("value") or "").strip()
        for item in values
        if isinstance(item, Mapping)
        and str(item.get("name") or "").strip().casefold() == name.casefold()
    ]
    return matches[0] if len(matches) == 1 else None


PROCUREMENT_WRITE_CAPABILITIES = (
    SERVICE_PRODUCT_CREATE,
    SERVICE_PRODUCT_VENDOR_CREATE,
    SERVICE_OPPORTUNITY_CREATE,
    SERVICE_QUOTE_LOCATION_CREATE,
    SERVICE_QUOTE_CREATE,
    SERVICE_QUOTE_ITEM_CREATE,
    SERVICE_PURCHASE_ORDER_CREATE,
    SERVICE_PURCHASE_ORDER_ITEM_CREATE,
    SERVICE_PURCHASE_ORDER_UPDATE,
    SERVICE_TICKET_CHARGE_CREATE,
)


def ensure_procurement_worker_authority(
    authority: IdentityAuthorityService, *, enabled: bool
) -> tuple[str, ...]:
    if not enabled:
        return ()
    identity = IdentityRecord(
        identity_id=PROCUREMENT_WORKER_ID,
        identity_type="service",
        organization_id="aot",
        status="active",
    )
    existing_identity = authority.identities.get(PROCUREMENT_WORKER_ID)
    if existing_identity is None:
        authority.identities.put(identity)
    elif existing_identity != identity:
        raise RuntimeError("procurement worker identity conflicts with JKD-001")
    created: list[str] = []
    for capability in PROCUREMENT_WRITE_CAPABILITIES:
        grant = AuthorityGrant(
            grant_id="grant-procurement-worker-" + capability.replace(".", "-"),
            subject_id=PROCUREMENT_WORKER_ID,
            capability=capability,
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.EXECUTE,
            approval_required=True,
            status="active",
        )
        existing = authority.grants.get(grant.grant_id)
        if existing is None:
            authority.grants.put(grant)
            created.append(grant.grant_id)
        elif existing != grant:
            raise RuntimeError(f"procurement worker grant conflicts: {grant.grant_id}")
    return tuple(created)


def ensure_procurement_read_authority(
    authority: IdentityAuthorityService, *, enabled: bool
) -> tuple[str, ...]:
    if not enabled:
        return ()
    grant = AuthorityGrant(
        grant_id="grant-aot-procurement-web-read-v1",
        subject_id="organization:aot",
        capability=PROCUREMENT_WEB_PRODUCT_READ,
        organization_id="aot",
        client_id=None,
        permission=PermissionMode.OBSERVE,
        approval_required=False,
        status="active",
    )
    existing = authority.grants.get(grant.grant_id)
    if existing is None:
        authority.grants.put(grant)
        return (grant.grant_id,)
    if existing != grant:
        raise RuntimeError("procurement web read authority grant conflicts")
    return ()


@dataclass
class ProcurementWorkerExecutor:
    authority: IdentityAuthorityService
    capabilities: CapabilityRegistryService
    approvals: Any
    execution_ledger: SQLiteGovernedExecutionLedger
    orchestrator: Any

    def execute(
        self,
        *,
        capability_name: str,
        payload: Mapping[str, Any],
        submission: Mapping[str, Any],
        correlation_id: str,
        route_arguments: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        capability = self.capabilities.get_current(capability_name=capability_name, allow_pilot=False)
        execution_id = f"exec_proc_{uuid4().hex}"
        arguments = {"payload": dict(payload), **dict(route_arguments or {})}
        reservation = self.execution_ledger.reserve_approval(
            principal_id=PROCUREMENT_WORKER_ID,
            organization_id="aot",
            client_id=None,
            capability_name=capability_name,
            arguments=arguments,
            request_id=execution_id,
            ttl_seconds=300,
        )
        if reservation.created:
            self.approvals.put(
                ApprovalRecord(
                    approval_id=reservation.approval_id,
                    request_id=reservation.request_id,
                    capability=capability_name,
                    organization_id="aot",
                    client_id=None,
                    requested_by=PROCUREMENT_WORKER_ID,
                    status="approved",
                    decided_by=f"policy:{PROCUREMENT_POLICY_ID}:{submission['submission_id']}",
                    decided_at=datetime.now(timezone.utc),
                    expires_at=reservation.expires_at,
                )
            )
        decision = self.authority.evaluate(
            AuthorityRequest(
                request_id=reservation.request_id,
                correlation_id=correlation_id,
                principal_id=PROCUREMENT_WORKER_ID,
                organization_id="aot",
                client_id=None,
                capability=capability_name,
                requested_mode=PermissionMode.EXECUTE,
                authentication_assurance="workload_identity",
                approval_id=reservation.approval_id,
            )
        )
        if decision.outcome is not AuthorityOutcome.ALLOWED or decision.execution_context is None:
            raise PermissionError("procurement worker authority denied: " + ",".join(decision.reason_codes))
        request = OrchestrationRequest(
            execution_id=reservation.request_id,
            correlation_id=correlation_id,
            principal_id=PROCUREMENT_WORKER_ID,
            organization_id="aot",
            client_id=None,
            capability_name=capability_name,
            capability_version=capability.version,
            requested_mode="deterministic",
            permission_mode="execute",
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=True,
            approval_present=True,
            risk=capability.risk_level.value,
            data_handling=DataHandlingPolicy(classification="internal", hosted_processing_allowed=False, retention_allowed=False),
            budget=ExecutionBudget(maximum_estimated_cost=Decimal("1.00"), maximum_attempts=1),
            arguments=arguments,
            requester_kind="service",
            principal_attributes={
                "workload": PROCUREMENT_WORKER_ID,
                "procurement_submission_id": str(submission["submission_id"]),
                "procurement_digest": str(submission["digest"]),
                "submitted_by": str(submission["requester_principal_id"]),
            },
            policy_ids=(PROCUREMENT_POLICY_ID,),
            authority_context_id=decision.execution_context.context_id,
            idempotency_key=reservation.idempotency_key,
        )
        result = self.orchestrator.execute(request)
        if result.status.value != "succeeded":
            raise ProcurementFlowError(f"procurement action failed: {capability_name}")
        return dict(result.output or {})


@dataclass(frozen=True, slots=True)
class OwnerOnlyProcurementAuthority:
    owner_ids: frozenset[str]

    def can_approve(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
    ) -> bool:
        return (
            organization_id == "aot"
            and client_id is None
            and capability == PROCUREMENT_APPROVAL_CAPABILITY
            and requested_mode == "purchase"
            and approver_identity_id in self.owner_ids
        )


@dataclass
class ProcurementTeamsFlow:
    identity_binder: Any
    request_factory: GovernedTeamsOrchestrationRequestFactory
    orchestrator: Any
    store: SQLiteProcurementSubmissionStore
    worker: ProcurementWorkerExecutor
    approval_service: ApprovalRequestService
    approval_sender: Any
    owner_ids: tuple[str, ...]
    inventory_location_id: int = 1
    ship_to_name: str = "Atlantic Office Technologies"
    ship_to_address1: str = "1202 W Little Creek Rd"
    ship_to_city: str = "Norfolk"
    ship_to_state: str = "VA"
    ship_to_postal_code: str = "23505"

    def _principal(
        self,
        *,
        tenant: str,
        object_id: str,
        conversation_id: str,
        message_id: str,
    ) -> tuple[BoundConversationPrincipal, TeamsConversationPrincipalEvidence]:
        evidence = TeamsConversationPrincipalEvidence(
            microsoft_tenant_id=tenant,
            microsoft_object_id=object_id,
            authentication_assurance="botframework-authenticated",
            conversation_id=conversation_id,
            message_id=message_id,
        )
        principal = self.identity_binder.bind(evidence)
        if principal is None or principal.organization_id != "aot":
            raise PermissionError("procurement intake is restricted to AOT staff")
        return principal, evidence

    def _read(
        self,
        *,
        principal: BoundConversationPrincipal,
        evidence: TeamsConversationPrincipalEvidence,
        capability: str,
        arguments: Mapping[str, Any],
        correlation_id: str,
    ) -> Mapping[str, Any]:
        intent = ConversationIntent(
            capability_name=capability,
            arguments=dict(arguments),
            permission_mode="observe",
            execution_mode="deterministic",
            risk="low",
        )
        request = self.request_factory.build(
            principal=principal,
            intent=intent,
            identity=evidence,
            correlation_id=correlation_id,
        )
        result = self.orchestrator.execute(request)
        if result.status.value != "succeeded":
            raise ProcurementFlowError(f"read failed: {capability}")
        return dict(result.output or {})

    def _draft_from_normalized_source(
        self,
        *,
        principal: BoundConversationPrincipal,
        evidence: TeamsConversationPrincipalEvidence,
        microsoft_object_id: str,
        occurred_at: datetime,
        source_kind: str,
        source_reference: str,
        source_capture_sha256: str,
        source_captured_at: str,
        source_org: Mapping[str, Any],
        product: Mapping[str, Any],
        correlation_id: str,
    ) -> Mapping[str, Any]:
        normalized_kind = str(source_kind or "").strip().casefold()
        if normalized_kind not in {"website_url", "vendor_quote", "vendor_invoice"}:
            raise ProcurementFlowError("Unsupported procurement source kind.")
        source_reference = str(source_reference or "").strip()
        if not source_reference:
            raise ProcurementFlowError("Procurement source reference is required.")
        product = dict(product)
        raw_cost = product.get("unit_cost")
        if raw_cost is None:
            raw_cost = product.get("price")
        if raw_cost is None:
            raise ProcurementFlowError("The source did not expose a verified unit cost.")
        cost = _decimal(raw_cost, field="source unit cost", allow_zero=False)
        source_org = dict(source_org or {})
        vendor_name = str(
            source_org.get("name") or product.get("seller") or product.get("vendor") or ""
        ).strip()
        if not vendor_name:
            raise ProcurementFlowError("The source did not identify a vendor.")

        vendor_search = self._read(
            principal=principal,
            evidence=evidence,
            capability=SERVICE_COMPANY_SEARCH,
            arguments={"name": vendor_name, "page_size": 20},
            correlation_id=correlation_id,
        )
        vendors = [
            item
            for item in _items(vendor_search)
            if _norm(item.get("companyName")) == _norm(vendor_name)
        ]
        if len(vendors) > 1:
            raise ProcurementFlowError(
                "Vendor could not be resolved to exactly one Autotask company."
            )
        vendor = vendors[0] if vendors else None
        checks: list[dict[str, str]] = []
        mismatches: list[str] = []
        if vendor is not None:
            checks, mismatches = _vendor_checks(source_org, vendor)
            if mismatches:
                raise ProcurementFlowError(
                    "Vendor Review required before procurement: "
                    + ", ".join(sorted(mismatches))
                )

        product_match: dict[str, Any] | None = None
        selectors: list[tuple[str, str]] = []
        if product.get("sku"):
            selectors.append(("sku", str(product["sku"])))
        if product.get("mpn") and product.get("mpn") != product.get("sku"):
            selectors.append(("sku", str(product["mpn"])))
        selectors.append(("name", str(product.get("name") or "").strip()))
        for selector, value in selectors:
            if not value:
                continue
            observed = self._read(
                principal=principal,
                evidence=evidence,
                capability=SERVICE_PRODUCT_SEARCH,
                arguments={selector: value, "page_size": 20},
                correlation_id=correlation_id,
            )
            matches = _items(observed)
            if len(matches) == 1:
                product_match = matches[0]
                break
            if len(matches) > 1:
                raise ProcurementFlowError(
                    "Multiple Autotask products match this source item; review is required."
                )

        verification: list[str] = []
        for check in checks:
            if check["status"] == "match":
                verification.append(check["field"] + " verified")
            elif check["status"] == "autotask_missing":
                verification.append(check["field"] + " missing in Autotask")

        submission_id = f"procsub-{uuid4().hex}"
        payload: dict[str, Any] = {
            "submission_id": submission_id,
            "status": "draft",
            "created_at": occurred_at.astimezone(timezone.utc).isoformat(),
            "requester_principal_id": principal.principal_id,
            "requester_email": principal.email_address,
            "requester_microsoft_object_id": microsoft_object_id,
            "source_kind": normalized_kind,
            "source_reference": source_reference,
            "source_url": source_reference,
            "source_capture_sha256": str(source_capture_sha256 or ""),
            "source_captured_at": str(source_captured_at or ""),
            "vendor": {
                "id": int(vendor["id"]) if vendor is not None else None,
                "name": str(
                    vendor.get("companyName") if vendor is not None else vendor_name
                ),
                "needs_create": vendor is None,
                "source": dict(source_org),
                "field_checks": checks,
                "verification_summary": (
                    "; ".join(verification)
                    if vendor is not None
                    else "Vendor not present in Autotask; creation proposed on submit."
                ),
            },
            "product": {
                "name": str(product.get("name") or "").strip(),
                "description": str(product.get("description") or "").strip(),
                "sku": str(product.get("sku") or "").strip(),
                "mpn": str(product.get("mpn") or "").strip(),
                "brand": str(product.get("brand") or "").strip(),
                "cost": f"{cost:.2f}",
                "existing_product_id": (
                    int(product_match["id"]) if product_match else None
                ),
                "existing_sku": (
                    str(product_match.get("sku") or "") if product_match else ""
                ),
            },
        }
        if not payload["product"]["name"]:
            raise ProcurementFlowError("The source did not identify a product/service line.")
        payload["digest"] = _submission_digest(payload)
        self.store.put_new(submission_id, payload)
        return {
            "status": "completed",
            "submission_id": submission_id,
            "reply": {
                "text": (
                    (
                        "I normalized the source. The vendor is not in Autotask, so "
                        "submission will create the Vendor record first. "
                    )
                    if payload["vendor"].get("needs_create")
                    else "I normalized the source and matched the vendor in Autotask. "
                )
                + "Review the selections below and submit when ready.",
                "card": _card(payload),
            },
        }

    def handle_url(
        self,
        *,
        url: str,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
        conversation_id: str,
        message_id: str,
        occurred_at: datetime,
    ) -> Mapping[str, Any]:
        principal, evidence = self._principal(
            tenant=microsoft_tenant_id,
            object_id=microsoft_object_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        correlation = self.request_factory.new_correlation_id()
        web = self._read(
            principal=principal,
            evidence=evidence,
            capability=PROCUREMENT_WEB_PRODUCT_READ,
            arguments={"url": url},
            correlation_id=correlation,
        )
        products = web.get("products")
        if not isinstance(products, list) or not products:
            raise ProcurementFlowError(
                "The page did not expose enough structured product data to build a safe quote."
            )
        product = dict(products[0])
        organizations = web.get("organizations")
        source_org = (
            dict(organizations[0])
            if isinstance(organizations, list)
            and organizations
            and isinstance(organizations[0], Mapping)
            else {}
        )
        if not source_org.get("name") and not product.get("seller"):
            host = str(web.get("source_host") or "").strip().casefold()
            fallback = host.split(".")[-2].title() if "." in host else host.title()
            source_org["name"] = fallback
        if not product.get("name"):
            product["name"] = str(web.get("page_title") or "").strip()
        return self._draft_from_normalized_source(
            principal=principal,
            evidence=evidence,
            microsoft_object_id=microsoft_object_id,
            occurred_at=occurred_at,
            source_kind="website_url",
            source_reference=str(web.get("final_url") or url),
            source_capture_sha256=str(web.get("content_sha256") or ""),
            source_captured_at=str(web.get("captured_at") or ""),
            source_org=source_org,
            product=product,
            correlation_id=correlation,
        )

    def handle_vendor_document(
        self,
        *,
        normalized: Mapping[str, Any],
        microsoft_tenant_id: str,
        microsoft_object_id: str,
        conversation_id: str,
        message_id: str,
        occurred_at: datetime,
    ) -> Mapping[str, Any]:
        """Accept bounded, already-extracted vendor quote/invoice evidence.

        Extraction is intentionally separate from procurement authority. This method
        converges the document branch into the same vendor/product/draft/card path
        used by URL intake; document content cannot expand runtime authority.
        """
        source_kind = str(normalized.get("source_kind") or "").strip().casefold()
        if source_kind not in {"vendor_quote", "vendor_invoice"}:
            raise ProcurementFlowError(
                "Vendor document must be classified as vendor_quote or vendor_invoice."
            )
        vendor = normalized.get("vendor")
        product = normalized.get("product")
        if not isinstance(vendor, Mapping) or not isinstance(product, Mapping):
            raise ProcurementFlowError(
                "Vendor document requires one normalized vendor and one product line."
            )
        principal, evidence = self._principal(
            tenant=microsoft_tenant_id,
            object_id=microsoft_object_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        correlation = self.request_factory.new_correlation_id()
        return self._draft_from_normalized_source(
            principal=principal,
            evidence=evidence,
            microsoft_object_id=microsoft_object_id,
            occurred_at=occurred_at,
            source_kind=source_kind,
            source_reference=str(normalized.get("source_reference") or ""),
            source_capture_sha256=str(normalized.get("source_capture_sha256") or ""),
            source_captured_at=str(normalized.get("source_captured_at") or ""),
            source_org=vendor,
            product=product,
            correlation_id=correlation,
        )

    def _requester_limit(
        self,
        *,
        payload: Mapping[str, Any],
        principal: BoundConversationPrincipal,
        evidence: TeamsConversationPrincipalEvidence,
        correlation_id: str,
    ) -> tuple[int, str, Decimal]:
        email = str(principal.email_address or payload.get("requester_email") or "").strip()
        if not email:
            raise ProcurementFlowError("Requester email could not be resolved.")
        result = self._read(
            principal=principal,
            evidence=evidence,
            capability=SERVICE_CONTACT_SEARCH,
            arguments={"company_id": 0, "email": email, "page_size": 20},
            correlation_id=correlation_id,
        )
        contacts = _items(result)
        if len(contacts) != 1:
            raise ProcurementFlowError("Requester must resolve to exactly one companyID=0 Autotask contact.")
        contact = contacts[0]
        raw_limit = _exact_udf(contact, "Spending limit")
        limit = Decimal("0") if not raw_limit else _decimal(raw_limit, field="Spending limit")
        display_name = " ".join(
            part
            for part in (
                str(contact.get("firstName") or "").strip(),
                str(contact.get("lastName") or "").strip(),
            )
            if part
        ) or email
        return int(contact["id"]), display_name, limit

    def _ticket(
        self,
        *,
        number: str,
        principal: BoundConversationPrincipal,
        evidence: TeamsConversationPrincipalEvidence,
        correlation_id: str,
    ) -> dict[str, Any]:
        result = self._read(
            principal=principal,
            evidence=evidence,
            capability=SERVICE_TICKET_SEARCH,
            arguments={"ticket_number": number, "page_size": 20},
            correlation_id=correlation_id,
        )
        tickets = _items(result)
        if len(tickets) != 1:
            raise ProcurementFlowError("Customer ticket must resolve to exactly one Autotask ticket.")
        return tickets[0]

    def _company(
        self,
        *,
        company_id: int,
        principal: BoundConversationPrincipal,
        evidence: TeamsConversationPrincipalEvidence,
        correlation_id: str,
    ) -> dict[str, Any]:
        result = self._read(
            principal=principal,
            evidence=evidence,
            capability=SERVICE_COMPANY_READ,
            arguments={"resource_id": company_id},
            correlation_id=correlation_id,
        )
        data = result.get("data")
        item = data.get("item") if isinstance(data, Mapping) else None
        source = item if isinstance(item, Mapping) else data
        if not isinstance(source, Mapping):
            raise ProcurementFlowError("Customer company could not be read for client quote.")
        return dict(source)

    def _requester_resource(
        self,
        *,
        email: str,
        principal: BoundConversationPrincipal,
        evidence: TeamsConversationPrincipalEvidence,
        correlation_id: str,
    ) -> dict[str, Any]:
        result = self._read(
            principal=principal,
            evidence=evidence,
            capability=SERVICE_RESOURCE_SEARCH,
            arguments={"email": email, "page_size": 20},
            correlation_id=correlation_id,
        )
        matches = _items(result)
        if len(matches) != 1:
            raise ProcurementFlowError(
                "Client quote requester must resolve to exactly one active Autotask resource."
            )
        return matches[0]

    def handle_submit(
        self,
        *,
        submission_id: str,
        selections: Mapping[str, str],
        microsoft_tenant_id: str,
        microsoft_object_id: str,
        conversation_id: str,
        channel_response_id: str,
        submitted_at: datetime,
    ) -> Mapping[str, Any]:
        payload = self.store.get(submission_id)
        if payload is None:
            raise PermissionError("procurement submission was not found")
        if payload.get("status") != "draft":
            raise PermissionError("procurement submission is no longer pending")
        if str(payload.get("requester_microsoft_object_id")) != microsoft_object_id:
            raise PermissionError("procurement submission belongs to another requester")

        principal, evidence = self._principal(
            tenant=microsoft_tenant_id,
            object_id=microsoft_object_id,
            conversation_id=conversation_id,
            message_id=channel_response_id,
        )
        if principal.principal_id != payload.get("requester_principal_id"):
            raise PermissionError("procurement requester identity changed")

        allowed = {
            "create_po", "create_client_quote", "at_part_number", "item_class",
            "retail_price", "quantity", "customer_quantity", "aot_stock_quantity",
            "ticket_number", "billing_treatment", "freight", "tax", "fees",
        }
        if set(selections) - allowed:
            raise PermissionError("procurement card contained unsupported selections")

        create_po = str(selections.get("create_po") or "false").casefold() == "true"
        create_client_quote = (
            str(selections.get("create_client_quote") or "false").casefold() == "true"
        )
        item_class = str(selections.get("item_class") or "").strip()
        if item_class not in {"it", "copy_print", "other"}:
            raise ProcurementFlowError("Item classification is invalid.")

        billing = str(selections.get("billing_treatment") or "").strip()
        if billing not in {
            "charge_ticket", "no_charge_contract", "no_charge_warranty",
            "no_charge_internal",
        }:
            raise ProcurementFlowError("Billing treatment is invalid.")

        quantity = _bounded_int(selections.get("quantity") or "1", field="quantity")
        customer_quantity = int(str(selections.get("customer_quantity") or "0").strip())
        aot_stock_quantity = int(str(selections.get("aot_stock_quantity") or "0").strip())
        if customer_quantity < 0 or aot_stock_quantity < 0:
            raise ProcurementFlowError("Allocation quantities cannot be negative.")

        ticket_number = str(selections.get("ticket_number") or "").strip()
        correlation = self.request_factory.new_correlation_id()
        ticket = None
        if customer_quantity or create_client_quote:
            if not ticket_number:
                raise ProcurementFlowError(
                    "Customer allocation and client quote creation require an explicit ticket."
                )
            ticket = self._ticket(
                number=ticket_number,
                principal=principal,
                evidence=evidence,
                correlation_id=correlation,
            )

        if create_client_quote and customer_quantity < 1:
            raise ProcurementFlowError(
                "Client quote creation requires at least one customer-allocated item."
            )

        plan = AllocationPlan(
            ordered_quantity=quantity,
            customer_quantity=customer_quantity,
            aot_stock_quantity=aot_stock_quantity,
            ticket_id=int(ticket["id"]) if ticket else None,
            ticket_number=ticket_number or None,
        )
        try:
            plan.validate()
        except ValueError as exc:
            raise ProcurementFlowError(str(exc)) from exc

        if customer_quantity and item_class == "it" and billing != "charge_ticket":
            raise ProcurementFlowError(
                "Customer-bound IT items must use Charge Ticket billing."
            )
        if not customer_quantity and billing == "charge_ticket":
            billing = "no_charge_internal"
        if item_class != "copy_print" and billing in {
            "no_charge_contract", "no_charge_warranty"
        }:
            raise ProcurementFlowError(
                "Contract/Warranty no-charge reasons are Copy / Print only."
            )

        retail = _decimal(
            selections.get("retail_price") or "",
            field="retail price",
            allow_zero=False,
        )
        part_number = str(selections.get("at_part_number") or "").strip()
        if not part_number or len(part_number) > 100:
            raise ProcurementFlowError(
                "AT Part # is required and must be <= 100 characters."
            )

        freight = _decimal(selections.get("freight") or "0", field="freight")
        tax = _decimal(selections.get("tax") or "0", field="tax")
        fees = _decimal(selections.get("fees") or "0", field="fees")
        unit_cost = Decimal(str(payload["product"]["cost"]))
        commitment = unit_cost * quantity + freight + tax + fees

        contact_id, requester_name, spending_limit = self._requester_limit(
            payload=payload,
            principal=principal,
            evidence=evidence,
            correlation_id=correlation,
        )

        quote_context = None
        if create_client_quote:
            company = self._company(
                company_id=int(ticket["companyID"]),
                principal=principal,
                evidence=evidence,
                correlation_id=correlation,
            )
            requester_email = str(
                principal.email_address or payload.get("requester_email") or ""
            ).strip()
            resource = self._requester_resource(
                email=requester_email,
                principal=principal,
                evidence=evidence,
                correlation_id=correlation,
            )
            quote_context = {
                "company": company,
                "owner_resource_id": int(resource["id"]),
            }

        submitted = {
            **payload,
            "status": "submitted",
            "submitted_at": submitted_at.astimezone(timezone.utc).isoformat(),
            "requester_contact_id": contact_id,
            "requester_name": requester_name,
            "spending_limit": f"{spending_limit:.2f}",
            "create_po": create_po,
            "create_client_quote": create_client_quote,
            "at_part_number": part_number,
            "item_class": item_class,
            "retail_price": f"{retail:.2f}",
            "quantity": quantity,
            "customer_quantity": customer_quantity,
            "aot_stock_quantity": aot_stock_quantity,
            "ticket_number": ticket_number or None,
            "ticket_id": int(ticket["id"]) if ticket else None,
            "ticket_title": str(ticket.get("title") or "") if ticket else None,
            "ticket_company_id": (
                int(ticket["companyID"])
                if ticket and ticket.get("companyID") is not None
                else None
            ),
            "billing_treatment": billing,
            "billing_disposition": (
                "pending_receipt" if customer_quantity else "no_customer_allocation"
            ),
            "freight": f"{freight:.2f}",
            "tax": f"{tax:.2f}",
            "fees": f"{fees:.2f}",
            "total_commitment": f"{commitment:.2f}",
            "quote_context": quote_context,
        }
        submitted["digest"] = _submission_digest(submitted)
        self.store.update(submission_id, submitted)

        # Spend authority governs the purchase branch only. Catalog/client quote
        # creation does not itself commit AOT funds.
        if create_po and commitment > spending_limit:
            approval = self._create_owner_approval(submitted)
            self.store.update(
                submission_id,
                {
                    **submitted,
                    "status": "approval_required",
                    "approval_id": approval.approval_id,
                },
            )
            self.approval_sender.send(approval)
            return {
                "status": "completed",
                "submission_id": submission_id,
                "reply": {
                    "text": (
                        "Submitted. Purchase total $"
                        + f"{commitment:.2f}"
                        + " exceeds "
                        + requester_name
                        + "'s Autotask Spending limit of $"
                        + f"{spending_limit:.2f}"
                        + "; owner approval was sent."
                    )
                },
            }

        result = self.execute_submission(submitted, owner_approval_id=None)
        return {
            "status": "completed",
            "submission_id": submission_id,
            "reply": {"text": result["summary"]},
        }

    def _create_owner_approval(self, submission: Mapping[str, Any]) -> ApprovalRequest:
        now = datetime.now(timezone.utc)
        approval = ApprovalRequest(
            approval_id=f"procapproval-{uuid4().hex}",
            request_id=f"procreq-{uuid4().hex}",
            correlation_id=f"corr_procapproval_{uuid4().hex}",
            organization_id="aot",
            client_id=None,
            requested_by=str(submission["requester_principal_id"]),
            capability=PROCUREMENT_APPROVAL_CAPABILITY,
            requested_mode="purchase",
            requested_at=now,
            expires_at=now + timedelta(days=2),
            authorized_approver_ids=tuple(self.owner_ids),
            presentation=ApprovalPresentation(
                title="Procurement Approval",
                summary=str(submission["requester_name"]) + " submitted an AOT purchase above their current spending authority.",
                facts=(
                    ("Submitted by", str(submission["requester_name"])),
                    ("Vendor", str(submission["vendor"]["name"])),
                    ("Product", str(submission["product"]["name"])),
                    ("AT Part #", str(submission["at_part_number"])),
                    ("Quantity", str(submission["quantity"])),
                    ("AOT Cost", "$" + str(submission["product"]["cost"]) + " each"),
                    ("Total Commitment", "$" + str(submission["total_commitment"])),
                    ("Spending Limit", "$" + str(submission["spending_limit"])),
                    ("Allocation", (
                        str(submission.get("customer_quantity", 0)) + " customer / "
                        + str(submission.get("aot_stock_quantity", 0)) + " AOT stock"
                    )),
                    ("Ticket", str(submission.get("ticket_number") or "None")),
                    ("Retail", "$" + str(submission["retail_price"]) + " each"),
                    ("Billing", str(submission["billing_treatment"])),
                    ("Source", str(submission["source_url"])),
                ),
            ),
            metadata={
                "submission_id": str(submission["submission_id"]),
                "submission_digest": str(submission["digest"]),
            },
        )
        return self.approval_service.create(approval, now=now)

    def execute_submission(
        self,
        submission: Mapping[str, Any],
        *,
        owner_approval_id: str | None,
    ) -> dict[str, Any]:
        current = self.store.get(str(submission["submission_id"]))
        if current is None:
            raise ProcurementFlowError("procurement submission disappeared")
        if str(current.get("digest")) != str(submission.get("digest")):
            raise PermissionError("procurement submission changed after authorization")

        correlation = f"corr_proc_exec_{uuid4().hex}"
        existing_result = current.get("result")
        result: dict[str, Any] = (
            dict(existing_result) if isinstance(existing_result, Mapping) else {}
        )

        def checkpoint(**values: Any) -> None:
            result.update(values)
            latest = self.store.get(str(submission["submission_id"]))
            if latest is None:
                raise ProcurementFlowError("procurement submission disappeared")
            self.store.update(
                str(submission["submission_id"]),
                {**latest, "status": "executing", "result": dict(result)},
            )

        vendor_id = result.get("vendor_id") or submission["vendor"].get("id")
        if vendor_id is None:
            source_vendor = dict(submission["vendor"].get("source") or {})
            source_address = dict(source_vendor.get("address") or {})
            vendor_payload: dict[str, Any] = {
                "companyName": str(submission["vendor"]["name"]),
            }
            field_map = {
                "url": "webAddress",
                "phone": "phone",
            }
            for source_field, target_field in field_map.items():
                value = str(source_vendor.get(source_field) or "").strip()
                if value:
                    vendor_payload[target_field] = value
            address_map = {
                "street": "address1",
                "city": "city",
                "state": "state",
                "postal_code": "postalCode",
            }
            for source_field, target_field in address_map.items():
                value = str(source_address.get(source_field) or "").strip()
                if value:
                    vendor_payload[target_field] = value
            vendor_output = self.worker.execute(
                capability_name=SERVICE_VENDOR_CREATE,
                payload=vendor_payload,
                submission=submission,
                correlation_id=correlation,
            )
            vendor_id = _resource_id(vendor_output)
            checkpoint(vendor_id=int(vendor_id), created_vendor=True)
        else:
            result.setdefault("vendor_id", int(vendor_id))
            result.setdefault("created_vendor", False)

        product_id = (
            result.get("product_id")
            or submission["product"].get("existing_product_id")
        )
        created_product = bool(result.get("created_product", False))
        if product_id is None:
            product_output = self.worker.execute(
                capability_name=SERVICE_PRODUCT_CREATE,
                payload={
                    "name": str(submission["product"]["name"]),
                    "description": str(
                        submission["product"].get("description") or ""
                    ),
                    "isActive": True,
                    "isSerialized": False,
                    "sku": str(submission["at_part_number"]),
                    "vendorProductNumber": str(
                        submission["product"].get("mpn")
                        or submission["product"].get("sku")
                        or ""
                    ),
                    "defaultVendorID": int(vendor_id),
                    "unitCost": float(Decimal(str(submission["product"]["cost"]))),
                    "unitPrice": float(Decimal(str(submission["retail_price"]))),
                },
                submission=submission,
                correlation_id=correlation,
            )
            product_id = _resource_id(product_output)
            created_product = True
            checkpoint(product_id=int(product_id), created_product=True)

        if created_product and not result.get("product_vendor_created"):
            self.worker.execute(
                capability_name=SERVICE_PRODUCT_VENDOR_CREATE,
                payload={
                    "productID": int(product_id),
                    "vendorID": int(vendor_id),
                    "isActive": True,
                    "isDefault": True,
                    "vendorCost": float(
                        Decimal(str(submission["product"]["cost"]))
                    ),
                    "vendorPartNumber": str(
                        submission["product"].get("mpn")
                        or submission["product"].get("sku")
                        or ""
                    ),
                },
                submission=submission,
                correlation_id=correlation,
            )
            checkpoint(
                product_id=int(product_id),
                created_product=created_product,
                product_vendor_created=True,
            )

        result.setdefault("product_id", int(product_id))
        result.setdefault("created_product", created_product)
        result.setdefault("purchase_order_id", None)
        result.setdefault("purchase_order_item_id", None)
        result.setdefault("purchase_order_submitted", False)
        result.setdefault("client_quote_id", None)
        result.setdefault("quote_location_id", None)
        result.setdefault("quote_item_id", None)
        result.setdefault("opportunity_id", None)
        result.setdefault("ticket_charge_id", None)
        result["owner_approval_id"] = owner_approval_id
        checkpoint(**result)

        if submission.get("create_client_quote"):
            if not submission.get("ticket_id"):
                raise ProcurementFlowError(
                    "client quote creation requires an exact ticket"
                )
            context = dict(submission.get("quote_context") or {})
            company = dict(context.get("company") or {})
            owner_resource_id = context.get("owner_resource_id")
            if not company or not owner_resource_id:
                raise ProcurementFlowError(
                    "client quote creation is missing verified company/resource context"
                )

            now = datetime.now(timezone.utc)
            sell_total = (
                Decimal(str(submission["retail_price"]))
                * int(submission["customer_quantity"])
            )
            cost_total = (
                Decimal(str(submission["product"]["cost"]))
                * int(submission["customer_quantity"])
            )
            opportunity_id = result.get("opportunity_id")
            if not opportunity_id:
                opportunity_output = self.worker.execute(
                    capability_name=SERVICE_OPPORTUNITY_CREATE,
                    payload={
                        "amount": float(sell_total),
                        "cost": float(cost_total),
                        "companyID": int(submission["ticket_company_id"]),
                        "ownerResourceID": int(owner_resource_id),
                        "probability": 50,
                        "projectedCloseDate": (now + timedelta(days=30)).isoformat(),
                        "stage": 29682772,
                        "startDate": now.isoformat(),
                        "status": 1,
                        "title": (
                            "Jason quote "
                            + str(submission["ticket_number"])
                            + " - "
                            + str(submission["product"]["name"])
                        )[:128],
                        "useQuoteTotals": True,
                        "description": (
                            "Created from exact ticket "
                            + str(submission["ticket_number"])
                            + " by Jason procurement "
                            + str(submission["submission_id"])
                        )[:8000],
                    },
                    submission=submission,
                    correlation_id=correlation,
                )
                opportunity_id = _resource_id(opportunity_output)
                checkpoint(opportunity_id=opportunity_id)
            else:
                opportunity_id = int(opportunity_id)

            address = {
                "address1": str(company.get("address1") or "")[:50],
                "address2": str(company.get("address2") or "")[:50],
                "city": str(company.get("city") or "")[:50],
                "state": str(company.get("state") or "")[:50],
                "postalCode": str(company.get("postalCode") or "")[:20],
            }
            quote_location_id = result.get("quote_location_id")
            if not quote_location_id:
                location_output = self.worker.execute(
                    capability_name=SERVICE_QUOTE_LOCATION_CREATE,
                    payload={key: value for key, value in address.items() if value},
                    submission=submission,
                    correlation_id=correlation,
                )
                quote_location_id = _resource_id(location_output)
                checkpoint(quote_location_id=quote_location_id)
            else:
                quote_location_id = int(quote_location_id)

            quote_id = result.get("client_quote_id")
            if not quote_id:
                quote_output = self.worker.execute(
                    capability_name=SERVICE_QUOTE_CREATE,
                    payload={
                        "billToLocationID": quote_location_id,
                        "companyID": int(submission["ticket_company_id"]),
                        "effectiveDate": now.isoformat(),
                        "expirationDate": (now + timedelta(days=30)).isoformat(),
                        "externalQuoteNumber": str(submission["submission_id"])[:50],
                        "isActive": True,
                        "name": (
                            str(submission["ticket_number"])
                            + " - "
                            + str(submission["product"]["name"])
                        )[:100],
                        "opportunityID": opportunity_id,
                        "primaryQuote": True,
                        "shipToLocationID": quote_location_id,
                        "soldToLocationID": quote_location_id,
                        "description": (
                            "Ticket "
                            + str(submission["ticket_number"])
                            + " | "
                            + str(submission["source_url"])
                        )[:2000],
                    },
                    submission=submission,
                    correlation_id=correlation,
                )
                quote_id = _resource_id(quote_output)
                checkpoint(client_quote_id=quote_id)
            else:
                quote_id = int(quote_id)

            quote_item_id = result.get("quote_item_id")
            if not quote_item_id:
                quote_item_output = self.worker.execute(
                    capability_name=SERVICE_QUOTE_ITEM_CREATE,
                    payload={
                        "productID": int(product_id),
                        "name": str(submission["product"]["name"])[:1000],
                        "description": str(submission["at_part_number"])[:2000],
                        "isOptional": False,
                        "lineDiscount": 0,
                        "percentageDiscount": 0,
                        "periodType": 5,
                        "quantity": int(submission["customer_quantity"]),
                        "quoteItemType": 1,
                        "unitCost": float(
                            Decimal(str(submission["product"]["cost"]))
                        ),
                        "unitDiscount": 0,
                        "unitPrice": float(
                            Decimal(str(submission["retail_price"]))
                        ),
                    },
                    submission=submission,
                    correlation_id=correlation,
                    route_arguments={"quoteID": quote_id},
                )
                quote_item_id = _resource_id(quote_item_output)
                checkpoint(
                    quote_item_id=quote_item_id,
                    client_quote_id=quote_id,
                    opportunity_id=opportunity_id,
                )


        if submission.get("create_po"):
            po_payload: dict[str, Any] = {
                "vendorID": int(vendor_id),
                "freight": float(Decimal(str(submission["freight"]))),
                "generalMemo": (
                    "Jason procurement "
                    + str(submission["submission_id"])
                    + " | source "
                    + str(submission["source_url"])
                    + " | submitted by "
                    + str(submission["requester_name"])
                )[:4000],
                "purchaseOrderTemplateID": 102,
                "shipToName": self.ship_to_name,
                "shipToAddress1": self.ship_to_address1,
                "shipToCity": self.ship_to_city,
                "shipToState": self.ship_to_state,
                "shipToPostalCode": self.ship_to_postal_code,
                "taxRegionID": 1,
                "useItemDescriptionsFrom": 1,
            }
            if submission.get("ticket_company_id"):
                po_payload["purchaseForCompanyID"] = int(
                    submission["ticket_company_id"]
                )
            po_id = result.get("purchase_order_id")
            if not po_id:
                po_output = self.worker.execute(
                    capability_name=SERVICE_PURCHASE_ORDER_CREATE,
                    payload=po_payload,
                    submission=submission,
                    correlation_id=correlation,
                )
                po_id = _resource_id(po_output)
                checkpoint(purchase_order_id=po_id)
            else:
                po_id = int(po_id)

            po_item_id = result.get("purchase_order_item_id")
            if not po_item_id:
                po_item_output = self.worker.execute(
                    capability_name=SERVICE_PURCHASE_ORDER_ITEM_CREATE,
                    payload={
                        "orderID": po_id,
                        "productID": int(product_id),
                        "inventoryLocationID": int(self.inventory_location_id),
                        "quantity": int(submission["quantity"]),
                        "unitCost": float(
                            Decimal(str(submission["product"]["cost"]))
                        ),
                        "memo": (
                            str(submission["source_url"])
                            + " | customer="
                            + str(submission["customer_quantity"])
                            + " | AOT stock="
                            + str(submission["aot_stock_quantity"])
                        )[:4000],
                    },
                    submission=submission,
                    correlation_id=correlation,
                )
                po_item_id = _resource_id(po_item_output)
                checkpoint(purchase_order_item_id=po_item_id)
            else:
                po_item_id = int(po_item_id)

            if not result.get("purchase_order_submitted"):
                self.worker.execute(
                    capability_name=SERVICE_PURCHASE_ORDER_UPDATE,
                    payload={"id": po_id, "status": 2},
                    submission=submission,
                    correlation_id=correlation,
                )
                checkpoint(
                    purchase_order_id=po_id,
                    purchase_order_item_id=po_item_id,
                    purchase_order_submitted=True,
                )

        # Receiving, billing disposition, stock release, and invoice verification
        # are intentionally subsequent lifecycle gates. No ticket charge is created here.
        if submission.get("create_po"):
            state = "ordered"
        elif submission.get("create_client_quote"):
            state = "client_quote_created"
        else:
            state = "catalog_ready"

        final = {
            **current,
            "status": state,
            "result": result,
            "release_state": (
                "ordered" if submission.get("create_po") else "not_applicable"
            ),
            "billing_state": (
                "pending_receipt"
                if int(submission.get("customer_quantity") or 0) > 0
                else "not_applicable"
            ),
        }
        self.store.update(str(submission["submission_id"]), final)

        parts = ["Catalog product " + str(product_id)]
        if result.get("client_quote_id"):
            parts.append("client quote " + str(result["client_quote_id"]))
        if result.get("purchase_order_id"):
            parts.append("PO " + str(result["purchase_order_id"]))
        if result.get("purchase_order_id") and int(
            submission.get("customer_quantity") or 0
        ):
            parts.append("customer stock held pending receipt + billing disposition")
        parts.append("readback verified")
        return {"summary": "; ".join(parts) + "."}


@dataclass
class ProcurementApprovalInteractionFlow:
    bindings: Any
    approval_service: ApprovalRequestService
    submissions: SQLiteProcurementSubmissionStore
    processor: ProcurementTeamsFlow

    def handle(
        self,
        *,
        approval_id: str,
        decision: str,
        selections: Mapping[str, str] | None = None,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
        conversation_id: str,
        channel_response_id: str,
        decided_at: datetime,
    ) -> Mapping[str, object]:
        if selections:
            raise PermissionError("owner procurement approval does not accept mutable selections")
        binding = self.bindings.find(
            microsoft_tenant_id=microsoft_tenant_id,
            microsoft_object_id=microsoft_object_id,
        )
        if binding is None or binding.status != "active":
            raise PermissionError("approver Microsoft identity is not bound")
        request = self.approval_service.repository.get(approval_id)
        if request is None or request.capability != PROCUREMENT_APPROVAL_CAPABILITY:
            raise LookupError("procurement approval request not found")
        try:
            parsed = ApprovalDecision(decision)
        except ValueError as exc:
            raise PermissionError("invalid procurement approval decision") from exc
        accepted = self.approval_service.accept_response(
            ApprovalResponse(
                approval_id=approval_id,
                organization_id=request.organization_id,
                approver_identity_id=binding.jason_identity_id,
                decision=parsed,
                decided_at=decided_at,
                channel="microsoft_teams",
                channel_response_id=channel_response_id,
            ),
            now=decided_at,
        )
        submission_id = request.metadata["submission_id"]
        submission = self.submissions.get(submission_id)
        if submission is None:
            raise ProcurementFlowError("approved procurement submission is missing")
        if request.metadata.get("submission_digest") != submission.get("digest"):
            raise PermissionError("procurement approval scope changed")
        if accepted.status != "approved":
            self.submissions.update(submission_id, {**submission, "status": accepted.status})
            label = "Declined" if accepted.status == "denied" else "Changes requested"
            return {
                "status": "completed",
                "approval_id": approval_id,
                "reply": {"text": label + ". No procurement write was performed."},
            }
        result = self.processor.execute_submission(submission, owner_approval_id=approval_id)
        return {
            "status": "completed",
            "approval_id": approval_id,
            "reply": {"text": result["summary"]},
        }


@dataclass(frozen=True, slots=True)
class ApprovalInteractionDispatcher:
    procurement: ProcurementApprovalInteractionFlow | None
    fallback: Any | None

    def handle(self, *, approval_id: str, **kwargs):
        if approval_id.startswith("procapproval-"):
            if self.procurement is None:
                raise PermissionError("procurement approval flow is not configured")
            return self.procurement.handle(approval_id=approval_id, **kwargs)
        if self.fallback is None:
            raise PermissionError("approval flow is not configured")
        return self.fallback.handle(approval_id=approval_id, **kwargs)
