"""Provider contact evidence normalization for safe import preflight and readback.

The provider client must retrieve GET /contacts with exact email, status=all
and list_memberships included. The caller must additionally verify the
OAuth-bound account and target list IDs; this pure function never grants
execution authority or accesses provider data itself.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class ProviderContactEvidenceError(PermissionError):
    """Incomplete or unsafe provider evidence."""


@dataclass(frozen=True)
class ObservedContact:
    email: str
    exists: bool
    safe_for_import: bool
    list_memberships: tuple[str, ...]
    permission_to_send: str | None


def evaluate_exact_contact_lookup(*, expected_email: str,
                                  response: Mapping[str, object]) -> ObservedContact:
    if not expected_email or "@" not in expected_email:
        raise ProviderContactEvidenceError("Exact contact identity required")
    links = response.get("_links")
    if not isinstance(links, Mapping) or links.get("next"):
        raise ProviderContactEvidenceError("Contact search is incomplete or paginated")
    contacts = response.get("contacts")
    if not isinstance(contacts, list) or len(contacts) > 1:
        raise ProviderContactEvidenceError("Contact search has ambiguous shape")
    email = expected_email.strip().casefold()
    if not contacts:
        return ObservedContact(email, False, True, (), None)
    contact = contacts[0]
    if not isinstance(contact, Mapping):
        raise ProviderContactEvidenceError("Provider contact object invalid")
    address = contact.get("email_address")
    if not isinstance(address, Mapping):
        raise ProviderContactEvidenceError("Provider contact address missing")
    observed_email = address.get("address")
    permission = address.get("permission_to_send")
    if not isinstance(observed_email, str) or observed_email.strip().casefold() != email:
        raise ProviderContactEvidenceError("Provider contact email does not match requested identity")
    if not isinstance(permission, str):
        raise ProviderContactEvidenceError("Provider subscription state missing")
    normalized = permission.strip().casefold()
    # Existing unsubscribed, temporary hold, deleted or unknown states must
    # never be silently reactivated by contact import.
    safe = normalized in {"explicit", "implicit"}
    lists = contact.get("list_memberships")
    if not isinstance(lists, list) or any(not isinstance(x, str) for x in lists):
        raise ProviderContactEvidenceError("Provider list membership readback missing")
    return ObservedContact(
        email=email, exists=True, safe_for_import=safe,
        list_memberships=tuple(sorted(set(lists))),
        permission_to_send=normalized,
    )


def verify_imported_membership(*, expected_email: str,
                               expected_list_ids: Sequence[str],
                               response: Mapping[str, object]) -> bool:
    observed = evaluate_exact_contact_lookup(
        expected_email=expected_email, response=response,
    )
    if not observed.exists or not observed.safe_for_import:
        return False
    return set(expected_list_ids) <= set(observed.list_memberships)
