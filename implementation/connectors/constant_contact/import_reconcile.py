"""Independent read-only Constant Contact import activity reconciler.

May run as an isolated periodic worker AFTER governed deployment. It cannot
create import claims or submit POSTs. One incomplete job cannot stall others.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .import_work_store import EncryptedImportWorkStore
from .import_ledger import SQLiteImportActivityLedger
from .governed_import import intent_for_work


class ImportReadback(Protocol):
    def reconcile(self, *, work_id: str, requester_id: str) -> dict[str, object]: ...


@dataclass(frozen=True)
class ReconcileCycle:
    considered: int
    verified: int
    pending: int
    blocked: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ConstantContactReadbackWorker:
    work_store: EncryptedImportWorkStore
    claims: SQLiteImportActivityLedger
    connector: ImportReadback

    def run_once(self, *, max_items: int = 25) -> ReconcileCycle:
        """Bounded GET-only execution; never redispatch ambiguous provider POST."""
        if type(max_items) is not int or not 1 <= max_items <= 25:
            raise ValueError("Invalid import reconciliation batch limit")
        # Scan past completed/undispatched rows so older records never starve
        # later real activity receipts. Bounded scan; no implicit dispatch.
        # Retain pagination offset across calls for deterministic auditing.
        items = []
        offset = 0
        while len(items) < max_items and offset < 2500:
            page = self.work_store.list_reconcilable(
                limit=min(25, max_items), offset=offset,
            )
            if not page:
                break
            offset += len(page)
            for work in page:
                digest = intent_for_work(work).digest()
                claim = self.claims.read_claim(intent_digest=digest)
                if (work.approval_id and claim is not None and claim.get("state") == "dispatched"
                        and self.claims.read_verification(intent_digest=digest) is None
                        and self.claims.read_provider_failure(intent_digest=digest) is None):
                    items.append(work)
                    if len(items) == max_items:
                        break
        considered = verified = pending = blocked = 0
        reasons = []
        for work in items:
            digest = intent_for_work(work).digest()
            claim = self.claims.read_claim(intent_digest=digest)
            if claim is None or claim.get("state") != "dispatched":
                # No exact provider activity ID: wait for a verified operator
                # reconciliation. Never infer from an ambiguous POST.
                continue
            if self.claims.read_verification(intent_digest=digest) is not None:
                continue
            considered += 1
            try:
                result = self.connector.reconcile(
                    work_id=work.work_id, requester_id=work.requester_id,
                )
                state = str(result.get("status") or "unknown")
                if state == "verified":
                    verified += 1
                elif state in {"pending", "pending_or_unknown",
                               "activity_complete_unverified",
                               "provider_counts_unverified",
                               "incomplete_provider_readback"}:
                    pending += 1
                elif state == "failed":
                    claim = self.claims.read_claim(intent_digest=digest)
                    activity_id = str(claim.get("activity_id") or "") if claim else ""
                    if result.get("activity_id") == activity_id:
                        self.claims.record_provider_failure(
                            intent_digest=digest, activity_id=activity_id,
                        )
                    blocked += 1
                    reasons.append("provider_activity_failed")
                else:
                    blocked += 1
                    reasons.append("provider_import_" + state[:32])
            except Exception:
                # Never return bearer credentials, contact PII or raw provider
                # exception text. Other independent jobs can still progress.
                blocked += 1
                reasons.append("import_readback_failed")
        return ReconcileCycle(
            considered=considered, verified=verified,
            pending=pending, blocked=blocked, reasons=tuple(reasons),
        )
