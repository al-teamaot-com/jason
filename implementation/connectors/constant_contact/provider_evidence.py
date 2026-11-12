"""Provider-backed account, list and per-contact evidence for approved imports.

All HTTP calls are GETs against Constant Contact V3 fixed endpoints using a
trusted injected transport. The protected expected account identity and token
come from Jason's secret/session layer, never the workbook or approval card.
This class does not create any contacts or grant execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
import time
from typing import Mapping

from connectors.core.contracts import HttpTransport
from .contact_evidence import (
    ObservedContact, ProviderContactEvidenceError, evaluate_exact_contact_lookup,
    verify_imported_membership,
)
from .import_activity import ImportSpecification
from .import_authorization import ImportAuthorizationError

BASE = "https://api.cc.email/v3"
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# Pilot is intentionally smaller than vendor's 40k maximum: all contacts must
# have fresh exact suppression reads and be covered by one short-lived approval.
MAX_VERIFIED_CONTACTS = 25


@dataclass(frozen=True)
class VerifiedProviderSnapshot:
    account_binding_sha256: str
    suppression_receipt_sha256: str
    contact_count: int


class ConstantContactProviderEvidence:
    def __init__(self, *, transport: HttpTransport, access_token: str,
                 expected_encoded_account_id: str,
                 minimum_interval_seconds: float = 0.30,
                 clock=time.monotonic, sleep=time.sleep):
        if (not isinstance(access_token, str) or not access_token
                or not isinstance(expected_encoded_account_id, str)
                or not re.fullmatch(r"[A-Za-z0-9]{8,64}", expected_encoded_account_id)):
            raise ImportAuthorizationError("Trusted OAuth account binding required")
        self.transport = transport
        self.token = access_token
        self.expected_account = expected_encoded_account_id
        if not 0 <= minimum_interval_seconds <= 1:
            raise ImportAuthorizationError("Invalid Constant Contact rate limit")
        self.minimum_interval = minimum_interval_seconds
        self.clock, self.sleep = clock, sleep
        self._last_read: float | None = None

    def _get(self, path: str, *, params: Mapping[str, object] | None = None) -> Mapping[str, object]:
        if self._last_read is not None and self.minimum_interval:
            remaining = self.minimum_interval - (self.clock() - self._last_read)
            if remaining > 0:
                self.sleep(remaining)
        self._last_read = self.clock()
        try:
            result = self.transport.request(
                method="GET", url=BASE + path,
                headers={"Accept": "application/json",
                         "Authorization": "Bearer " + self.token},
                params=params, timeout_seconds=15.0,
            )
        except Exception:
            # Never leak provider contact or bearer material through errors.
            raise ImportAuthorizationError("Constant Contact evidence read unavailable") from None
        if not isinstance(result, Mapping):
            raise ImportAuthorizationError("Constant Contact evidence response invalid")
        return result

    def require_account(self) -> str:
        account = self._get("/account/summary")
        found = account.get("encoded_account_id")
        if found != self.expected_account:
            raise ImportAuthorizationError("Connected Constant Contact account changed")
        return sha256(self.expected_account.encode("utf-8")).hexdigest()

    def require_lists(self, list_ids: tuple[str, ...]) -> None:
        if not 1 <= len(list_ids) <= 50 or len(set(list_ids)) != len(list_ids):
            raise ImportAuthorizationError("Exact destination lists required")
        for list_id in list_ids:
            if not UUID.fullmatch(list_id):
                raise ImportAuthorizationError("Malformed list identifier")
            found = self._get("/contact_lists/" + list_id)
            if (found.get("list_id") != list_id
                    or not isinstance(found.get("name"), str)
                    or not found["name"].strip()
                    or str(found.get("status", "active")).lower() != "active"):
                raise ImportAuthorizationError("Destination contact list not verified")

    def _exact_response(self, email: str) -> Mapping[str, object]:
        return self._get("/contacts", params={
            "email": email, "status": "all", "include": "list_memberships", "limit": 2,
        })

    @staticmethod
    def _observe_email(email: str, response: Mapping[str, object]) -> ObservedContact:
        try:
            return evaluate_exact_contact_lookup(expected_email=email, response=response)
        except ProviderContactEvidenceError:
            raise ImportAuthorizationError("Exact contact evidence incomplete") from None

    def exact_contact(self, email: str) -> ObservedContact:
        return self._observe_email(email, self._exact_response(email))

    @staticmethod
    def _emails(specification: ImportSpecification) -> list[str]:
        contacts = specification.payload.get("import_data")
        if (not isinstance(contacts, list) or not 1 <= len(contacts) <= MAX_VERIFIED_CONTACTS
                or specification.contact_count != len(contacts)):
            raise ImportAuthorizationError("Import exceeds bounded evidence pilot")
        emails = []
        for item in contacts:
            if not isinstance(item, dict):
                raise ImportAuthorizationError("Import contact shape invalid")
            value = item.get("email")
            if not isinstance(value, str) or not value or len(value) > 50:
                raise ImportAuthorizationError("Import contact identity invalid")
            emails.append(value)
        if len(set(emails)) != len(emails):
            raise ImportAuthorizationError("Duplicate contact identities in import")
        return emails

    def snapshot(self, specification: ImportSpecification) -> VerifiedProviderSnapshot:
        emails = self._emails(specification)
        account_hash = self.require_account()
        self.require_lists(specification.list_ids)
        observed = []
        for email in emails:
            contact = self.exact_contact(email)
            if not contact.safe_for_import:
                raise ImportAuthorizationError("Existing contact is suppressed or not sendable")
            # Constant Contact is authoritative about list-level unsubscribe
            # history. A globally subscribed contact not on the destination
            # list could have opted out of that specific list. Do not silently
            # re-add it without a separately verified list-specific opt-in path.
            if contact.exists and not set(specification.list_ids) <= set(contact.list_memberships):
                raise ImportAuthorizationError(
                    "Existing contact is not subscribed to all destination lists; "
                    "list-specific re-consent is required"
                )
            observed.append({
                "email_sha256": sha256(email.encode("utf-8")).hexdigest(),
                "existing": contact.exists,
                "permission": contact.permission_to_send,
                "lists": list(contact.list_memberships),
            })
        material = {
            "account": account_hash,
            "specification": specification.sha256,
            "lists": list(specification.list_ids),
            "contacts": observed,
        }
        digest = sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return VerifiedProviderSnapshot(account_hash, digest, len(observed))

    def require_current_provider_match(
        self, *, account_binding_sha256: str, specification: ImportSpecification,
        suppression_receipt_sha256: str,
    ) -> None:
        fresh = self.snapshot(specification)
        if (fresh.account_binding_sha256 != account_binding_sha256
                or fresh.suppression_receipt_sha256 != suppression_receipt_sha256):
            raise ImportAuthorizationError("Current provider account, lists or suppression evidence changed")

    def readback_memberships(
        self, specification: ImportSpecification,
    ) -> tuple[dict[str, str], ...]:
        # Re-verify the same account and lists, not just a returned activity ID.
        self.require_account()
        self.require_lists(specification.list_ids)
        results = []
        self._emails(specification)
        for expected in specification.payload["import_data"]:
            email = expected["email"]
            response = self._exact_response(email)
            observed = self._observe_email(email, response)
            confirmed = (observed.exists and observed.safe_for_import
                         and set(specification.list_ids) <= set(observed.list_memberships))
            # A verified import must include the intended field updates, not
            # merely the contact's existence and list membership. Fail closed
            # if the provider omitted an expected field or normalized it
            # incompatibly, without exposing contact PII in readback receipts.
            if confirmed:
                contact = response["contacts"][0]
                for field in ("first_name", "last_name", "company_name", "job_title"):
                    if field in expected and str(contact.get(field, "")).strip() != expected[field].strip():
                        confirmed = False
                        break
            results.append({
                "email_sha256": sha256(email.encode("utf-8")).hexdigest(),
                "status": "verified" if confirmed else "not_verified",
            })
        return tuple(results)
