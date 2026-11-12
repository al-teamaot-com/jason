"""Source-only issuer/workflow for a verified AOT Constant Contact import.

The user-supplied workbook never creates action authority. Preview is a
provider-read workflow, proposal goes through Jason's existing authenticated
universal plan issuer, and later execution uses Central Orchestrator's
protected execution plan after independent exact-action reauthorization.

No new public HTTP route, Teams gateway or approval ledger is introduced.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from kernel.identity_authority import AuthorityOutcome, AuthorityRequest, PermissionMode
from typing import Any
from uuid import uuid4

from connectors.constant_contact.governed_import import (
    CAPABILITY, GovernedConstantContactImportConnector,
    canonical_import_arguments,
)
from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.import_work_store import EncryptedImportWorkStore
from connectors.constant_contact.intake_handoff import verify_excel_handoff
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest


@dataclass(frozen=True)
class ConstantContactImportWorkflow:
    connector: GovernedConstantContactImportConnector
    work_store: EncryptedImportWorkStore
    issuer: Any

    def _requester(self, identity) -> str:
        if getattr(identity, "authentication_assurance", "") not in {
            "botframework-authenticated", "entra-oauth-bearer",
        }:
            raise ImportAuthorizationError("Authenticated AOT requester required")
        binding = self.issuer.bindings.find(
            microsoft_tenant_id=identity.microsoft_tenant_id,
            microsoft_object_id=identity.microsoft_object_id,
        )
        if (binding is None or binding.status != "active"
                or not binding.jason_identity_id):
            raise ImportAuthorizationError("AOT requester identity binding unavailable")
        identity_record = self.issuer.authority.identities.get(binding.jason_identity_id)
        if (identity_record is None or identity_record.status != "active"
                or identity_record.organization_id != "aot"):
            raise ImportAuthorizationError("Requester does not belong to active AOT identity")
        # Preview exposes real contact data. Authentication alone is not a
        # permission to read: require a current read authority grant BEFORE
        # any provider call, independent of later mutation approval.
        decision = self.issuer.authority.evaluate(AuthorityRequest(
            request_id="cc-preview-" + uuid4().hex,
            correlation_id="cc-preview-" + uuid4().hex,
            principal_id=binding.jason_identity_id, organization_id="aot",
            client_id=None, capability="marketing.contact.search",
            requested_mode=PermissionMode.OBSERVE,
            authentication_assurance=identity.authentication_assurance,
        ))
        if decision.outcome is not AuthorityOutcome.ALLOWED:
            raise ImportAuthorizationError("Requester lacks governed contact-read permission")
        return binding.jason_identity_id

    def preview(self, *, identity, workbook: bytes, list_ids: tuple[str, ...]):
        requester_id = self._requester(identity)
        return self.connector.create_preview(
            requester_id=requester_id,
            workbook=workbook,
            list_ids=list_ids,
        )

    def preview_attachment(
        self, *, identity, workbook_base64: str, source_sha256: str,
        source_reference: str, filename: str, list_ids: tuple[str, ...],
    ) -> dict[str, object]:
        # Permission before parsing or contacting the provider; handoff
        # metadata never supplies requester identity or approval.
        self._requester(identity)
        evidence = verify_excel_handoff(
            workbook_base64=workbook_base64, source_sha256=source_sha256,
            source_reference=source_reference, filename=filename,
        )
        summary = self.preview(
            identity=identity, workbook=evidence.workbook, list_ids=list_ids,
        )
        return {
            "status": "preview_unapproved",
            "work_id": summary.work_id,
            "source_sha256": evidence.source_sha256,
            "source_reference": evidence.source_reference,
            "contact_count": summary.contact_count,
            "list_ids": list(summary.list_ids),
            "preview_digest": summary.preview_digest,
            "provider_suppression_verified": True,
            "approval_required": True,
        }

    def submit_approval(self, *, identity, work_id: str) -> dict[str, object]:
        requester_id = self._requester(identity)
        work = self.work_store.load_for_requester(
            work_id=work_id, requester_id=requester_id,
        )
        if work.approval_id:
            raise ImportAuthorizationError("Import proposal has already been issued")
        request = OrchestrationRequest(
            execution_id="constant-contact-import-" + uuid4().hex,
            correlation_id="cc-import-" + uuid4().hex,
            principal_id=requester_id,
            organization_id="aot",
            capability_name=CAPABILITY,
            capability_version="1.0",
            requested_mode="deterministic",
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=False,
            approval_present=False,
            risk="high",
            data_handling=DataHandlingPolicy(
                classification="confidential",
                hosted_processing_allowed=False,
                retention_allowed=True,
            ),
            budget=ExecutionBudget(Decimal("0")),
            arguments=canonical_import_arguments(work),
            permission_mode="execute",
            requester_kind="human",
            idempotency_key="cc-import-" + work.work_id,
        )
        issued = self.issuer.submit_plan(
            requests=(request,), identity=identity,
            title="Approve Constant Contact import",
            summary=(
                f"Add {work.specification.contact_count} consent-reviewed contacts "
                f"to {len(work.specification.list_ids)} exact AOT contact lists. "
                "No email campaign is sent; verify the immutable plan fingerprint."
            ),
            production=True,
            ttl_seconds=1800,
        )
        approval_id = issued.get("approval_id")
        if (not isinstance(approval_id, str)
                or not approval_id.startswith("planapproval-")):
            raise ImportAuthorizationError("Canonical issuer did not return an approval ID")
        self.work_store.attach_approval(
            work_id=work.work_id, requester_id=requester_id,
            approval_id=approval_id,
        )
        return {
            "work_id": work.work_id,
            "approval_id": approval_id,
            "status": str(issued.get("status") or "awaiting_approval"),
            "plan_fingerprint": str(issued.get("plan_fingerprint") or ""),
        }

    def readback(self, *, identity, work_id: str) -> dict[str, object]:
        requester_id = self._requester(identity)
        return self.connector.reconcile(
            work_id=work_id, requester_id=requester_id,
        )
