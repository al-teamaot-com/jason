"""Source-only governed Constant Contact import and reconciliation connector.

Never register this connector on a live runtime without a reviewed, isolated
release. An actual write can occur only through Central Orchestrator's
prepare/bind/re-prepare/execute path, after verified plan approval, protected
account binding, fresh suppression evidence and an atomic one-time claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Callable, Mapping, Protocol
import hmac
import secrets

from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
    ConnectorResult, HttpTransport,
)
from orchestrator.connector_invoker import ProviderPreparedExecution

from .import_activity import (
    ImportContractError, ImportSpecification, build_specification,
)
from .import_authorization import (
    ExactImportIntent, ImportAuthorizationError, TrustedTeamsApprovalPort,
)
from .import_dispatch import (
    UnwiredConstantContactImportDispatcher, read_provider_activity,
)
from .import_ledger import SQLiteImportActivityLedger
from .import_preflight import ImportPreflight
from .import_work_store import EncryptedImportWorkStore, StoredImportWork
from .provider_evidence import ConstantContactProviderEvidence
from .xlsx_preflight import preview_xlsx

PROVIDER = "constant_contact"
CAPABILITY = "marketing.contact.import"
PATH = "/v3/activities/contacts_json_import"


class CanonicalApprovalFactory(Protocol):
    def __call__(self, work: StoredImportWork) -> TrustedTeamsApprovalPort: ...


class TrustedOAuthSession(Protocol):
    def __call__(self) -> tuple[str, str]:
        """Return current access token and separately protected expected account ID."""


def intent_for_work(work: StoredImportWork) -> ExactImportIntent:
    spec = work.specification
    return ExactImportIntent(
        account_binding_sha256=work.account_binding_sha256,
        specification_sha256=spec.sha256,
        preview_digest=spec.preview_digest,
        suppression_receipt_sha256=work.suppression_receipt_sha256,
        list_ids=spec.list_ids,
        contact_count=spec.contact_count,
    )


def canonical_import_arguments(work: StoredImportWork) -> dict[str, object]:
    intent = intent_for_work(work)
    return {
        "work_id": work.work_id,
        "intent_digest": intent.digest(),
        "account_binding_sha256": intent.account_binding_sha256,
        "specification_sha256": intent.specification_sha256,
        "preview_digest": intent.preview_digest,
        "suppression_receipt_sha256": intent.suppression_receipt_sha256,
        "list_ids": list(intent.list_ids),
        "contact_count": intent.contact_count,
        "source_sha256": work.source_sha256,
    }


@dataclass(frozen=True)
class _AuthorizedOpaqueImport:
    work: StoredImportWork = field(repr=False)
    token: str = field(repr=False)
    expected_account_id: str = field(repr=False)
    preparation_nonce: str = field(repr=False)


@dataclass(frozen=True)
class PreparedImportSummary:
    work_id: str
    account_binding_sha256: str
    suppression_receipt_sha256: str
    preview_digest: str
    contact_count: int
    list_ids: tuple[str, ...]


class GovernedConstantContactImportConnector:
    provider_name = PROVIDER
    capabilities = frozenset({CAPABILITY})

    def __init__(
        self, *, transport: HttpTransport, session: TrustedOAuthSession,
        work_store: EncryptedImportWorkStore,
        claims: SQLiteImportActivityLedger,
        approvals: CanonicalApprovalFactory,
        execute_enabled: bool = False,
        min_read_interval_seconds: float = 0.30,
    ) -> None:
        self.transport = transport
        self.session = session
        self.work_store = work_store
        self.claims = claims
        self.approvals = approvals
        self.execute_enabled = execute_enabled
        self.min_read_interval_seconds = min_read_interval_seconds
        self._preparation_nonce = secrets.token_hex(32)

    def _provider(self, token: str, account: str) -> ConstantContactProviderEvidence:
        return ConstantContactProviderEvidence(
            transport=self.transport, access_token=token,
            expected_encoded_account_id=account,
            minimum_interval_seconds=self.min_read_interval_seconds,
        )

    def create_preview(
        self, *, requester_id: str, workbook: bytes, list_ids: tuple[str, ...],
    ) -> PreparedImportSummary:
        """Read-only preparation with real provider evidence, no approval issued."""
        if not requester_id.strip():
            raise ImportAuthorizationError("Authenticated import requester required")
        preview = preview_xlsx(workbook)
        if preview.rejected:
            raise ImportContractError("Import preview contains rejected rows")
        spec = build_specification(preview, list_ids=list_ids)
        token, account = self.session()
        evidence = self._provider(token, account).snapshot(spec)
        work = self.work_store.create(
            requester_id=requester_id, specification=spec,
            account_binding_sha256=evidence.account_binding_sha256,
            suppression_receipt_sha256=evidence.suppression_receipt_sha256,
            source_sha256=sha256(workbook).hexdigest(),
        )
        return PreparedImportSummary(
            work_id=work.work_id,
            account_binding_sha256=work.account_binding_sha256,
            suppression_receipt_sha256=work.suppression_receipt_sha256,
            preview_digest=spec.preview_digest,
            contact_count=spec.contact_count,
            list_ids=spec.list_ids,
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        # Governed write must never fall back to the read-only connector API.
        raise ConnectorAuthorizationError(
            "Constant Contact import requires canonical prepared execution plan"
        )

    def _require_work(self, request: ConnectorRequest) -> StoredImportWork:
        context = request.context
        if (context.capability != CAPABILITY or context.mode != "execute"
                or context.organization_id.strip().casefold() != "aot"
                or context.client_id is not None or not context.principal_id.strip()):
            raise ImportAuthorizationError("Governed AOT contact import authority required")
        work_id = request.arguments.get("work_id")
        if not isinstance(work_id, str):
            raise ImportAuthorizationError("Server-owned import work reference required")
        work = self.work_store.load_for_requester(
            work_id=work_id, requester_id=context.principal_id,
        )
        if not work.approval_id:
            raise ImportAuthorizationError("Signed exact import approval is not yet bound")
        if dict(request.arguments) != canonical_import_arguments(work):
            raise ImportAuthorizationError("Requested import does not match approved immutable work")
        return work

    def prepare_governed_execution(
        self, request: ConnectorRequest,
    ) -> ProviderPreparedExecution:
        if not self.execute_enabled:
            raise ConnectorAuthorizationError("Constant Contact import is not activated")
        work = self._require_work(request)
        token, account = self.session()
        fresh = self._provider(token, account).snapshot(work.specification)
        if (fresh.account_binding_sha256 != work.account_binding_sha256
                or fresh.suppression_receipt_sha256 != work.suppression_receipt_sha256):
            raise ImportAuthorizationError("Provider evidence has changed since preview")
        self.approvals(work).require_exact_signed_approval(
            requester_id=work.requester_id, intent=intent_for_work(work),
        )
        return ProviderPreparedExecution(
            provider_capability=CAPABILITY,
            action_method="POST",
            resource_type="marketing_contact_import",
            resource_identifier=work.account_binding_sha256,
            normalized_path=PATH,
            payload={
                "specification_sha256": work.specification.sha256,
                "preview_digest": work.specification.preview_digest,
                "suppression_receipt_sha256": work.suppression_receipt_sha256,
                "contact_count": work.specification.contact_count,
                "list_ids": list(work.specification.list_ids),
            },
            parameters={"work_id": work.work_id},
            symbolic_resolutions={},
            opaque=_AuthorizedOpaqueImport(
                work=work, token=token, expected_account_id=account,
                preparation_nonce=self._preparation_nonce,
            ),
        )

    def execute_governed_execution(
        self, prepared: ProviderPreparedExecution,
    ) -> ConnectorResult:
        if not self.execute_enabled:
            raise ConnectorAuthorizationError("Constant Contact import not activated")
        opaque = prepared.opaque
        if (
            not isinstance(opaque, _AuthorizedOpaqueImport)
            or not hmac.compare_digest(opaque.preparation_nonce, self._preparation_nonce)
            or prepared.provider_capability != CAPABILITY
            or prepared.action_method != "POST"
            or prepared.normalized_path != PATH
        ):
            raise ImportAuthorizationError("Canonical prepared import identity changed")
        work = opaque.work
        # Protect against execution after a work record changes or expires.
        persisted = self.work_store.load_for_requester(
            work_id=work.work_id, requester_id=work.requester_id,
        )
        if persisted != work:
            raise ImportAuthorizationError("Stored import work changed before dispatch")
        current_token, account = self.session()
        if account != opaque.expected_account_id:
            raise ImportAuthorizationError("Connected account changed before import")
        provider = self._provider(current_token, account)
        dispatcher = UnwiredConstantContactImportDispatcher(
            approval=self.approvals(work), evidence=provider,
            ledger=self.claims, transport=self.transport,
        )
        receipt = dispatcher.submit_once(
            requester_id=work.requester_id,
            account_binding_sha256=work.account_binding_sha256,
            suppression_receipt_sha256=work.suppression_receipt_sha256,
            specification=work.specification,
            access_token=current_token,
        )
        return ConnectorResult(
            capability=CAPABILITY, provider=PROVIDER,
            data={
                "status": receipt.completion_state,
                "activity_id": receipt.activity_id,
                "intent_digest": receipt.intent_digest,
                "work_id": work.work_id,
                "provider_readback_required": True,
            },
        )

    def reconcile(
        self, *, work_id: str, requester_id: str,
    ) -> dict[str, object]:
        """Read-only completion proof; never redispatch an ambiguous POST."""
        work = self.work_store.load_for_reconciliation(
            work_id=work_id, requester_id=requester_id,
        )
        intent = intent_for_work(work)
        prior = self.claims.read_claim(intent_digest=intent.digest())
        if not prior or prior["state"] != "dispatched" or not prior["activity_id"]:
            return {"status": "pending_or_unknown", "work_id": work_id}
        verified = self.claims.read_verification(intent_digest=intent.digest())
        if verified:
            return {
                "status": "verified", "activity_id": prior["activity_id"],
                "verified_count": len(verified["item_results"]),
                "per_record": verified["item_results"],
            }
        terminal = self.claims.read_provider_failure(intent_digest=intent.digest())
        if terminal is not None:
            return {
                "status": "failed",
                "activity_id": terminal["activity_id"],
                "reason": terminal["reason"],
                "provider_readback_required": False,
            }
        token, account = self.session()
        provider = self._provider(token, account)
        # Fail closed on account switch even for historical activities.
        if provider.require_account() != work.account_binding_sha256:
            raise ImportAuthorizationError("Provider account no longer matches")
        # Expired/rotated approvals do not block read-only reconciliation.
        # This path has no approval issuer and no provider POST capability.
        activity = read_provider_activity(
            transport=self.transport,
            activity_id=str(prior["activity_id"]), access_token=token,
        )
        if activity["state"] != "activity_complete_unverified":
            return {
                "status": str(activity["state"]),
                "activity_id": prior["activity_id"],
                "provider_readback_required": True,
            }
        counts = activity.get("provider_counts")
        if not counts or (
            counts["items_total_count"] != work.specification.contact_count
            or counts["items_completed_count"] != work.specification.contact_count
            or counts["error_count"] != 0
            or counts["cannot_add_to_list_count"] != 0
        ):
            return {
                "status": "provider_counts_unverified",
                "activity_id": prior["activity_id"],
                "provider_readback_required": True,
            }
        per_record = provider.readback_memberships(work.specification)
        if any(row["status"] != "verified" for row in per_record):
            return {
                "status": "incomplete_provider_readback",
                "activity_id": prior["activity_id"],
                "per_record": list(per_record),
            }
        self.claims.record_verified(
            intent_digest=intent.digest(),
            activity_id=str(prior["activity_id"]),
            item_results=per_record,
        )
        return {
            "status": "verified", "activity_id": prior["activity_id"],
            "verified_count": len(per_record), "per_record": list(per_record),
        }
