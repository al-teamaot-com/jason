"""Unwired import activity dispatcher; approval and durable claim required.

No production entrypoint imports this module. A future governed mutation
connector must invoke it *only* after exact signed Teams approval and fresh
provider evidence, via Central Orchestrator's protected execution-plan path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Protocol

from connectors.core.contracts import HttpTransport
from .import_activity import (
    ImportSpecification, ImportContractError, classify_activity,
)
from .import_authorization import (
    DurableImportClaimPort, ExactImportIntent, TrustedProviderEvidencePort,
    TrustedTeamsApprovalPort, prepare_authorized_claim,
)

ENDPOINT = "https://api.cc.email/v3/activities/contacts_json_import"
ACTIVITY_BASE = "https://api.cc.email/v3/activities/"
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class ImportActivityLedger(DurableImportClaimPort, Protocol):
    def record_dispatched(self, *, intent_digest: str, activity_id: str) -> None:
        """Persist provider activity ID and irreversible dispatch checkpoint."""


@dataclass(frozen=True)
class ImportDispatchReceipt:
    intent_digest: str
    activity_id: str
    completion_state: str


class UnwiredConstantContactImportDispatcher:
    """Caller supplies trusted ports; not a public or independently authorized API."""

    def __init__(self, *, approval: TrustedTeamsApprovalPort,
                 evidence: TrustedProviderEvidencePort, ledger: ImportActivityLedger,
                 transport: HttpTransport):
        self._approval, self._evidence = approval, evidence
        self._ledger, self._transport = ledger, transport

    def submit_once(self, *, requester_id: str,
                    account_binding_sha256: str,
                    suppression_receipt_sha256: str,
                    specification: ImportSpecification,
                    access_token: str) -> ImportDispatchReceipt:
        if not access_token:
            raise ImportContractError("Current OAuth session required")
        claim = prepare_authorized_claim(
            requester_id=requester_id,
            account_binding_sha256=account_binding_sha256,
            suppression_receipt_sha256=suppression_receipt_sha256,
            specification=specification,
            approvals=self._approval,
            provider=self._evidence,
            ledger=self._ledger,
        )
        # Never retry ambiguous POST. Claim stays pending until an
        # authenticated provider activity or manual reconciliation proves state.
        response = self._transport.request(
            method="POST", url=ENDPOINT,
            headers={"Accept": "application/json",
                     "Authorization": "Bearer " + access_token},
            json=specification.payload,
            timeout_seconds=30.0,
        )
        if not isinstance(response, Mapping):
            raise ImportContractError("Import activity response invalid; manual reconciliation required")
        activity_id = str(response.get("activity_id") or "")
        if not _UUID.fullmatch(activity_id):
            raise ImportContractError("Import activity identity unavailable; do not redispatch")
        self._ledger.record_dispatched(intent_digest=claim.intent_digest, activity_id=activity_id)
        return ImportDispatchReceipt(claim.intent_digest, activity_id, "pending_unverified")

    def read_activity(self, *, activity_id: str, access_token: str) -> dict[str, object]:
        if not _UUID.fullmatch(activity_id) or not access_token:
            raise ImportContractError("Authenticated activity lookup requires exact activity ID")
        result = self._transport.request(
            method="GET", url=ACTIVITY_BASE + activity_id,
            headers={"Accept": "application/json",
                     "Authorization": "Bearer " + access_token},
            timeout_seconds=30.0,
        )
        if not isinstance(result, Mapping):
            raise ImportContractError("Activity result invalid")
        return classify_activity(result, expected_activity_id=activity_id)
