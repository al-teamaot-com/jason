"""Source-only exact client question intent derived from the deployed catalog.

Pure proposal only: no external notification, no new sender, no approval,
no ledger reservation, and no second runbook engine. Persisted delivery/reply
state remains the existing client_information_requests.ClientQuestionWorkflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .client_information_requests import (
    CLIENT_QUESTION_WORKFLOW_ID, ClientQuestionError,
    ClientQuestionCatalog, load_round1_catalog,
    render_question, select_question_from_diagnostic, TICKET_NUMBER_PATTERN,
)


class JsonClientQuestionBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonClientQuestionIntent:
    disposition: str
    ticket_id: int
    question_id: str
    template_id: str
    body_sha256: str
    evidence_sha256: str
    baseline_notification_id: int
    capability: str | None
    arguments: Mapping[str, Any] | None


def _items(response: Mapping[str, Any], *, name: str) -> list[Mapping[str, Any]]:
    if not isinstance(response, Mapping) or response.get("status") != "succeeded":
        raise JsonClientQuestionBoundaryError(name + "_GOVERNED_READ_FAILED")
    evidence = response.get("evidence")
    data = evidence.get("data") if isinstance(evidence, Mapping) else None
    if not isinstance(data, Mapping):
        raise JsonClientQuestionBoundaryError(name + "_EVIDENCE_MISSING")
    items = data.get("items")
    if not isinstance(items, list) or any(not isinstance(item, Mapping) for item in items):
        raise JsonClientQuestionBoundaryError(name + "_LIST_INCOMPLETE")
    if any(data.get(key) for key in ("has_more", "next_cursor", "nextCursor")):
        raise JsonClientQuestionBoundaryError(name + "_LIST_INCOMPLETE")
    if data.get("total_count") is not None:
        try:
            if int(data["total_count"]) > len(items):
                raise JsonClientQuestionBoundaryError(name + "_LIST_INCOMPLETE")
        except (ValueError, TypeError) as exc:
            raise JsonClientQuestionBoundaryError(name + "_LIST_COUNT_INVALID") from exc
    return items


def plan_client_question(
    *,
    ticket_id: int,
    exact_ticket: Mapping[str, Any],
    exact_contact: Mapping[str, Any],
    question_id: str | None,
    missing_fact_code: str,
    missing_fact_corroborated: bool,
    evidence_sha256: str,
    note_read: Mapping[str, Any],
    notification_history_read: Mapping[str, Any],
    catalog: ClientQuestionCatalog | None = None,
) -> JsonClientQuestionIntent:
    source = catalog or load_round1_catalog()
    try:
        question = select_question_from_diagnostic(
            question_id=question_id,
            missing_fact_code=missing_fact_code,
            corroborated=missing_fact_corroborated,
            catalog=source,
        )
    except ClientQuestionError as exc:
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_DIAGNOSTIC_SELECTION_INVALID") from exc
    if question.review_class != "routine":
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_EXACT_TECHNICIAN_REVIEW_REQUIRED")
    if (not isinstance(ticket_id, int) or ticket_id < 1 or
        str(exact_ticket.get("id")) != str(ticket_id)):
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_TICKET_ID_CHANGED")
    company_id = str(exact_ticket.get("companyID") or "")
    contact_id = str(exact_ticket.get("contactID") or "")
    ticket_number = str(exact_ticket.get("ticketNumber") or "")
    if (not company_id or company_id == "0" or
        not contact_id or contact_id == "0" or
        not TICKET_NUMBER_PATTERN.fullmatch(ticket_number)):
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_TICKET_IDENTITY_INCOMPLETE")
    if str(exact_ticket.get("status") or "").casefold() in {"complete", "closed"}:
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_TICKET_CLOSED")
    if (str(exact_contact.get("id")) != contact_id or
        str(exact_contact.get("companyID")) != company_id or
        exact_contact.get("receivesEmailNotifications") is not True):
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_CONTACT_COMPANY_OR_NOTIFY_CHANGED")
    email = str(exact_contact.get("emailAddress") or "").strip().casefold()
    if email.count("@") != 1 or not all(email.split("@")):
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_CONTACT_EMAIL_INVALID")
    if (not isinstance(evidence_sha256, str) or
        len(evidence_sha256) != 64 or
        any(ch not in "0123456789abcdef" for ch in evidence_sha256)):
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_EVIDENCE_HASH_INVALID")
    notes = _items(note_read, name="TICKET_NOTES")
    history = _items(notification_history_read, name="NOTIFICATION_HISTORY")
    try:
        body = render_question(question, ticket_number, catalog=source)
    except ClientQuestionError as exc:
        raise JsonClientQuestionBoundaryError("CLIENT_QUESTION_CATALOG_TEXT_INVALID") from exc
    digest = sha256(body.encode("utf-8")).hexdigest()
    baseline = max((int(item["id"]) for item in history
                    if str(item.get("id") or "").isdigit()), default=0)
    if question.question_id == "JQ-001":
        if str(exact_ticket.get("description") or "").strip():
            disposition = "information_already_available"
        elif any(
            str(note.get("createdByContactID") or "") == contact_id and
            str(note.get("description") or "").strip()
            for note in notes
        ):
            disposition = "information_already_available"
        else:
            disposition = ""
    else:
        disposition = ""
    if not disposition and any(
        str(note.get("title") or "") == question.title and
        str(note.get("description") or "") == body
        for note in notes
    ):
        disposition = "already_present"
    if disposition:
        return JsonClientQuestionIntent(
            disposition, ticket_id, question.question_id,
            question.template_id, digest, evidence_sha256, baseline, None, None,
        )
    return JsonClientQuestionIntent(
        "proposed_not_authorized", ticket_id, question.question_id,
        question.template_id, digest, evidence_sha256, baseline,
        "service.ticket.client.notification.create",
        {
            "workflow_id": CLIENT_QUESTION_WORKFLOW_ID,
            "template_id": question.template_id,
            "ticket_number": ticket_number,
            "payload": {"ticketID": ticket_id},
        },
    )
