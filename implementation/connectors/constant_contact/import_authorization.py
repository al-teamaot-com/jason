"""Fail-closed governed import protocol; no production provider adapter is wired.

This boundary is source-only. A trusted implementation of ApprovalPort MUST
perform actual authenticated Teams approval-ledger verification. A caller flag,
chat instruction, unsigned token, or string that looks like approval is NEVER
sufficient. The import service must be registered only through Jason's
Central Orchestrator exact-action execution plan.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Protocol

from .import_activity import ImportSpecification, ImportContractError


class ImportAuthorizationError(PermissionError):
    """Protected import authorization rejection."""


@dataclass(frozen=True)
class ExactImportIntent:
    account_binding_sha256: str
    specification_sha256: str
    preview_digest: str
    suppression_receipt_sha256: str
    list_ids: tuple[str, ...]
    contact_count: int

    def digest(self) -> str:
        normalized = json.dumps({
            "account": self.account_binding_sha256,
            "specification": self.specification_sha256,
            "preview": self.preview_digest,
            "suppression": self.suppression_receipt_sha256,
            "lists": list(self.list_ids),
            "count": self.contact_count,
        }, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(normalized).hexdigest()


class TrustedTeamsApprovalPort(Protocol):
    def require_exact_signed_approval(self, *, requester_id: str, intent: ExactImportIntent) -> None:
        """Verify Entra identity and non-replayed, unexpired Teams approval receipt."""


class TrustedProviderEvidencePort(Protocol):
    def require_current_provider_match(self, *,
                                       account_binding_sha256: str,
                                       specification: ImportSpecification,
                                       suppression_receipt_sha256: str) -> None:
        """Recheck OAuth account, target lists and all subscription/suppression evidence."""


class DurableImportClaimPort(Protocol):
    def claim_once(self, *, intent_digest: str) -> None:
        """Atomically create durable one-time claim or reject replay/pending execution."""


@dataclass(frozen=True)
class AuthorizedImportClaim:
    intent_digest: str
    specification: ImportSpecification


def prepare_authorized_claim(
    *,
    requester_id: str,
    account_binding_sha256: str,
    suppression_receipt_sha256: str,
    specification: ImportSpecification,
    approvals: TrustedTeamsApprovalPort,
    provider: TrustedProviderEvidencePort,
    ledger: DurableImportClaimPort,
) -> AuthorizedImportClaim:
    """Authorize immutable intent; a later separately governed provider adapter sends POST.

    Approval must match all material fields, not just a file name or row count.
    Claim is durable before any provider mutation, so ambiguous HTTP results
    cannot cause accidental automatic redispatch.
    """
    if not requester_id.strip():
        raise ImportAuthorizationError("Verified requester identity required")
    if any(len(x) != 64 or any(c not in "0123456789abcdef" for c in x) for x in (
        account_binding_sha256, suppression_receipt_sha256,
        specification.sha256, specification.preview_digest,
    )):
        raise ImportAuthorizationError("Immutable import evidence digests required")
    if not specification.contact_count or not specification.list_ids:
        raise ImportContractError("Empty import is not allowed")
    intent = ExactImportIntent(
        account_binding_sha256=account_binding_sha256,
        specification_sha256=specification.sha256,
        preview_digest=specification.preview_digest,
        suppression_receipt_sha256=suppression_receipt_sha256,
        list_ids=specification.list_ids,
        contact_count=specification.contact_count,
    )
    # Independently revalidate current live provider data before approval and
    # dispatch, never trusting source workbook suppression flags.
    provider.require_current_provider_match(
        account_binding_sha256=account_binding_sha256,
        specification=specification,
        suppression_receipt_sha256=suppression_receipt_sha256,
    )
    approvals.require_exact_signed_approval(requester_id=requester_id, intent=intent)
    ledger.claim_once(intent_digest=intent.digest())
    return AuthorizedImportClaim(intent_digest=intent.digest(), specification=specification)
