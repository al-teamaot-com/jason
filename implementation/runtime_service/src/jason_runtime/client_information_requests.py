"""Round 1 source-controlled client information requests and durable lifecycle.

Source content approval is not notification authority. The sending engine requires
an exact activation profile, a promoted playbook scope, a proven missing fact, and
authoritative ticket and recipient reads. Uncertain writes are never retried.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

CATALOG_PATH = (
    Path(__file__).resolve().parents[4]
    / "config" / "client_communications" / "information_requests_round1.json"
)
CLIENT_QUESTION_WORKFLOW_ID = "client_information_request"
CLIENT_QUESTION_PROFILE_ENV = "JASON_CLIENT_INFORMATION_REQUEST_PROFILE"
CLIENT_QUESTION_APPROVED_PROFILE = "approved-round1-v1"
TICKET_NUMBER_PATTERN = re.compile(r"\AT[0-9]{8}\.[0-9]{4,5}\Z")
SHA256_PATTERN = re.compile(r"\A[a-f0-9]{64}\Z")

# Deterministic mapping from verified diagnostic gaps to approved questions.
# No free-form inference from ticket prose is permitted.
DIAGNOSTIC_GAP_QUESTIONS = {
    "problem_description_missing": "JQ-001",
    "issue_start_time_missing": "JQ-004",
    "affected_users_unknown": "JQ-009",
    "business_impact_unknown": "JQ-012",
    "error_text_missing": "JQ-017",
    "error_code_missing": "JQ-019",
    "device_identity_missing": "JQ-025",
    "account_identity_missing": "JQ-033",
    "mail_delivery_notice_missing": "JQ-045",
    "attachment_size_missing": "JQ-055",
    "printer_identity_missing": "JQ-057",
    "wireless_or_wired_unknown": "JQ-065",
    "application_identity_missing": "JQ-073",
    "storage_warning_unknown": "JQ-083",
    "missing_file_identity": "JQ-089",
    "suspicious_message_interaction_unknown": "JQ-097",
    "scheduling_availability_missing": "JQ-105",
    "resolution_retest_needed": "JQ-114",
}


class ClientQuestionError(RuntimeError):
    """A message or state transition did not meet the fail-closed contract."""


@dataclass(frozen=True, slots=True)
class ClientQuestion:
    question_id: str
    template_id: str
    category: str
    title: str
    body: str
    review_class: str
    gap_code: str


@dataclass(frozen=True, slots=True)
class ClientQuestionCatalog:
    questions: tuple[ClientQuestion, ...]
    footer: str

    def by_id(self, question_id: str) -> ClientQuestion:
        matches = [q for q in self.questions if q.question_id == question_id]
        if len(matches) != 1:
            raise ClientQuestionError("CLIENT_QUESTION_ID_NOT_APPROVED")
        return matches[0]

    def by_template_id(self, template_id: str) -> ClientQuestion:
        matches = [q for q in self.questions if q.template_id == template_id]
        if len(matches) != 1:
            raise ClientQuestionError("CLIENT_QUESTION_TEMPLATE_NOT_APPROVED")
        return matches[0]


def client_question_profile_enabled() -> bool:
    return os.getenv(CLIENT_QUESTION_PROFILE_ENV, "").strip() == CLIENT_QUESTION_APPROVED_PROFILE


def load_round1_catalog(path: Path | None = None) -> ClientQuestionCatalog:
    try:
        content = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ClientQuestionError("CLIENT_QUESTION_CATALOG_UNREADABLE") from exc
    if not isinstance(content, Mapping):
        raise ClientQuestionError("CLIENT_QUESTION_CATALOG_INVALID")
    if (content.get("schema_version") != 1
            or content.get("catalog_id") != "aot-client-information-requests-round1-v1"
            or content.get("content_approval") != "owner-approved-2026-10-28"
            or content.get("production_activation") is not False
            or content.get("send_authority") != "none-from-catalog"):
        raise ClientQuestionError("CLIENT_QUESTION_CATALOG_AUTHORITY_INVALID")
    entries = content.get("questions")
    footer = content.get("footer")
    if not isinstance(entries, list) or len(entries) != 120 or not isinstance(footer, Mapping):
        raise ClientQuestionError("CLIENT_QUESTION_CATALOG_INCOMPLETE")
    if (footer.get("template_id") != "client-support-footer-v1"
            or footer.get("placeholders") != ["ticket_number"]
            or not isinstance(footer.get("body"), str)
            or footer["body"].count("{{ticket_number}}") != 1
            or "support@teamaot.com" not in footer["body"]
            or "757-466-8862" not in footer["body"]):
        raise ClientQuestionError("CLIENT_QUESTION_FOOTER_INVALID")
    questions: list[ClientQuestion] = []
    categories = set()
    gap_codes = set()
    for idx, raw in enumerate(entries, 1):
        if not isinstance(raw, Mapping):
            raise ClientQuestionError("CLIENT_QUESTION_ENTRY_INVALID")
        expected_id = f"JQ-{idx:03d}"
        expected_template = f"aot-client-question-jq-{idx:03d}-v1"
        if (raw.get("question_id") != expected_id
                or raw.get("template_id") != expected_template
                or raw.get("content_approved") is not True
                or raw.get("autonomous_send_enabled") is not False
                or raw.get("review_class") not in
                    {"routine", "context_controlled", "human_review"}):
            raise ClientQuestionError("CLIENT_QUESTION_ENTRY_AUTHORITY_INVALID")
        for key in ("category", "title", "body"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise ClientQuestionError("CLIENT_QUESTION_TEXT_INVALID")
        if "{{" in raw["body"] or "}}" in raw["body"]:
            raise ClientQuestionError("CLIENT_QUESTION_UNBOUNDED_PLACEHOLDER")
        gap_code = raw.get("gap_code")
        if (not isinstance(gap_code, str)
                or not re.fullmatch(r"[a-z][a-z0-9_]{5,159}", gap_code)
                or gap_code in gap_codes):
            raise ClientQuestionError("CLIENT_QUESTION_GAP_CODE_INVALID")
        gap_codes.add(gap_code)
        categories.add(raw["category"])
        questions.append(ClientQuestion(
            question_id=expected_id,
            template_id=expected_template,
            category=raw["category"],
            title=raw["title"],
            body=raw["body"],
            review_class=raw["review_class"],
            gap_code=gap_code,
        ))
    if len(categories) != 15:
        raise ClientQuestionError("CLIENT_QUESTION_CATEGORIES_INCOMPLETE")
    return ClientQuestionCatalog(tuple(questions), footer["body"])


def render_question(question: ClientQuestion, ticket_number: str, *,
                    catalog: ClientQuestionCatalog | None = None) -> str:
    if not isinstance(ticket_number, str) or not TICKET_NUMBER_PATTERN.fullmatch(ticket_number):
        raise ClientQuestionError("CLIENT_QUESTION_TICKET_NUMBER_INVALID")
    source = catalog or load_round1_catalog()
    authoritative = source.by_id(question.question_id)
    if question != authoritative:
        raise ClientQuestionError("CLIENT_QUESTION_TEXT_CHANGED")
    return question.body + "\n\n" + source.footer.replace(
        "{{ticket_number}}", ticket_number
    )


def select_question_from_diagnostic(
    *, question_id: str | None = None, missing_fact_code: str, corroborated: bool,
    catalog: ClientQuestionCatalog | None = None,
) -> ClientQuestion:
    """Select only when a governed diagnostic supplies an exact missing fact.

    This method deliberately does not infer gaps from untrusted ticket prose.
    Every one of the 120 IDs is selectable; non-routine questions additionally
    require an exact technician review at the execution boundary.
    """
    if not isinstance(missing_fact_code, str) or not re.fullmatch(
        r"[a-z][a-z0-9_]{5,159}", missing_fact_code
    ):
        raise ClientQuestionError("CLIENT_QUESTION_MISSING_FACT_UNVERIFIED")
    if corroborated is not True:
        raise ClientQuestionError("CLIENT_QUESTION_MISSING_FACT_UNVERIFIED")
    source = catalog or load_round1_catalog()
    direct = [q for q in source.questions if q.gap_code == missing_fact_code]
    mapped_id = DIAGNOSTIC_GAP_QUESTIONS.get(missing_fact_code)
    if mapped_id is not None:
        direct.append(source.by_id(mapped_id))
    if len(direct) != 1:
        raise ClientQuestionError("CLIENT_QUESTION_GAP_BINDING_NOT_APPROVED")
    question = direct[0]
    if question_id is not None and question_id != question.question_id:
        raise ClientQuestionError("CLIENT_QUESTION_GAP_BINDING_NOT_APPROVED")
    return question


@dataclass(frozen=True, slots=True)
class ClientQuestionRecord:
    ticket_id: int
    ticket_number: str
    company_id: int
    contact_id: int
    contact_email: str
    question_id: str
    evidence_hash: str
    resume_phase: str
    state: str
    baseline_notification_id: int
    outbound_note_id: int
    reply_note_id: int
    resumed_at: str


class SQLiteClientQuestionLedger:
    """Single-writer transactional reservations prevent repeated client sends."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS client_question_requests (
        ticket_id INTEGER NOT NULL,
        ticket_number TEXT NOT NULL,
        company_id INTEGER NOT NULL,
        contact_id INTEGER NOT NULL,
        contact_email TEXT NOT NULL,
        question_id TEXT NOT NULL,
        evidence_hash TEXT NOT NULL,
        resume_phase TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL,
        baseline_notification_id INTEGER NOT NULL DEFAULT 0,
        outbound_note_id INTEGER NOT NULL DEFAULT 0,
        reply_note_id INTEGER NOT NULL DEFAULT 0,
        resumed_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY (ticket_id, question_id, evidence_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_client_question_wait
    ON client_question_requests(state, ticket_id);
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(self._SCHEMA)
        os.chmod(self.path, 0o600)

    @staticmethod
    def _as_record(row: sqlite3.Row) -> ClientQuestionRecord:
        return ClientQuestionRecord(**{
            key: row[key] for key in ClientQuestionRecord.__dataclass_fields__
        })

    def reserve(self, *, ticket_id: int, ticket_number: str, company_id: int,
                contact_id: int, contact_email: str, question_id: str,
                evidence_hash: str, baseline_notification_id: int,
                resume_phase: str = "") -> bool:
        if not SHA256_PATTERN.fullmatch(evidence_hash):
            raise ClientQuestionError("CLIENT_QUESTION_EVIDENCE_HASH_INVALID")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            active = self.db.execute(
                "SELECT 1 FROM client_question_requests WHERE ticket_id=? "
                "AND question_id=? AND state NOT IN ('resumed','cancelled') LIMIT 1",
                (ticket_id, question_id),
            ).fetchone()
            if active:
                self.db.execute("ROLLBACK")
                return False
            existing = self.db.execute(
                "SELECT 1 FROM client_question_requests WHERE ticket_id=? "
                "AND question_id=? AND evidence_hash=?",
                (ticket_id, question_id, evidence_hash),
            ).fetchone()
            if existing:
                self.db.execute("ROLLBACK")
                return False
            self.db.execute(
                "INSERT INTO client_question_requests "
                "(ticket_id,ticket_number,company_id,contact_id,contact_email,"
                "question_id,evidence_hash,resume_phase,state,baseline_notification_id,"
                "updated_at) VALUES(?,?,?,?,?,?,?,?,'reserved',?,?)",
                (ticket_id, ticket_number, company_id, contact_id,
                 contact_email, question_id, evidence_hash, resume_phase,
                 baseline_notification_id, datetime.now(timezone.utc).isoformat()),
            )
            self.db.execute("COMMIT")
            return True
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def transition(self, record: ClientQuestionRecord, state: str, *,
                   outbound_note_id: int | None = None,
                   reply_note_id: int | None = None) -> None:
        allowed = {
            "reserved": {"send_uncertain"},
            "send_uncertain": {"delivery_pending"},
            "delivery_pending": {"awaiting_reply"},
            "awaiting_reply": {"reply_verified"},
            "reply_verified": {"resumed"},
        }
        if state not in allowed.get(record.state, set()):
            raise ClientQuestionError("CLIENT_QUESTION_STATE_TRANSITION_INVALID")
        changes = {"state": state, "updated_at": datetime.now(timezone.utc).isoformat()}
        if outbound_note_id is not None:
            changes["outbound_note_id"] = int(outbound_note_id)
        if reply_note_id is not None:
            changes["reply_note_id"] = int(reply_note_id)
        if state == "resumed":
            changes["resumed_at"] = datetime.now(timezone.utc).isoformat()
        keys = tuple(changes)
        with self.db:
            cur = self.db.execute(
                "UPDATE client_question_requests SET "
                + ",".join(f"{key}=?" for key in keys)
                + " WHERE ticket_id=? AND question_id=? AND evidence_hash=? "
                  "AND state=?",
                tuple(changes[key] for key in keys)
                + (record.ticket_id, record.question_id, record.evidence_hash,
                   record.state),
            )
            if cur.rowcount != 1:
                raise ClientQuestionError("CLIENT_QUESTION_CONCURRENT_TRANSITION")

    def has_question(self, ticket_id: int, question_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM client_question_requests WHERE ticket_id=? "
            "AND question_id=? LIMIT 1", (int(ticket_id), question_id)
        ).fetchone()
        return row is not None

    def waiting(self) -> tuple[ClientQuestionRecord, ...]:
        rows = self.db.execute(
            "SELECT * FROM client_question_requests WHERE state IN "
            "('send_uncertain','delivery_pending','awaiting_reply','reply_verified') "
            "ORDER BY updated_at,ticket_id"
        ).fetchall()
        return tuple(self._as_record(row) for row in rows)

    def find(self, ticket_id: int, question_id: str, evidence_hash: str) -> ClientQuestionRecord:
        row = self.db.execute(
            "SELECT * FROM client_question_requests "
            "WHERE ticket_id=? AND question_id=? AND evidence_hash=?",
            (ticket_id, question_id, evidence_hash),
        ).fetchone()
        if row is None:
            raise ClientQuestionError("CLIENT_QUESTION_STATE_MISSING")
        return self._as_record(row)


class ClientQuestionWorkflow:
    """Governed, injection-safe handoff around the existing Autotask adapter."""

    def __init__(self, *, reads: Any, actions: Any, ledger: SQLiteClientQuestionLedger,
                 scope: Any, scope_is_promoted: Callable[[], bool],
                 catalog: ClientQuestionCatalog | None = None) -> None:
        self.reads = reads
        self.actions = actions
        self.ledger = ledger
        self.scope = scope
        self.scope_is_promoted = scope_is_promoted
        self.catalog = catalog or load_round1_catalog()

    def _assert_authorized(self) -> None:
        if not client_question_profile_enabled():
            raise ClientQuestionError("CLIENT_QUESTION_PROFILE_DISABLED")
        if self.scope_is_promoted() is not True:
            raise ClientQuestionError("CLIENT_QUESTION_SCOPE_NOT_PROMOTED")

    def _read(self, capability: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = self.reads.execute(capability, arguments)
        if not isinstance(result, Mapping) or result.get("status") != "succeeded":
            raise ClientQuestionError("CLIENT_QUESTION_GOVERNED_READ_FAILED")
        evidence = result.get("evidence")
        data = evidence.get("data") if isinstance(evidence, Mapping) else None
        if not isinstance(data, Mapping):
            raise ClientQuestionError("CLIENT_QUESTION_READ_EVIDENCE_MISSING")
        return dict(data)

    def _ticket(self, ticket_id: int) -> dict[str, Any]:
        data = self._read("service.ticket.read", {"ticket_id": ticket_id})
        item = data.get("item", data.get("record", data))
        if not isinstance(item, Mapping) or int(item.get("id") or 0) != ticket_id:
            raise ClientQuestionError("CLIENT_QUESTION_TICKET_READBACK_MISMATCH")
        return dict(item)

    def _contact(self, contact_id: int, company_id: int) -> dict[str, Any]:
        data = self._read("service.contact.read", {"resource_id": contact_id})
        item = data.get("item", data.get("record", data))
        if not isinstance(item, Mapping):
            raise ClientQuestionError("CLIENT_QUESTION_CONTACT_READ_INVALID")
        if (int(item.get("id") or 0) != contact_id
                or int(item.get("companyID") or 0) != company_id):
            raise ClientQuestionError("CLIENT_QUESTION_CONTACT_COMPANY_MISMATCH")
        email = str(item.get("emailAddress") or "").strip().casefold()
        if not email or "@" not in email or email.count("@") != 1:
            raise ClientQuestionError("CLIENT_QUESTION_CONTACT_EMAIL_INVALID")
        if item.get("receivesEmailNotifications") is not True:
            raise ClientQuestionError("CLIENT_QUESTION_CONTACT_NOTIFICTIONS_DISABLED")
        return dict(item)

    def _notes(self, ticket_id: int) -> list[dict[str, Any]]:
        data = self._read("service.ticket.notes.search",
                          {"ticket_id": ticket_id, "page_size": 100})
        items = data.get("items")
        if not isinstance(items, list) or not all(isinstance(i, Mapping) for i in items):
            raise ClientQuestionError("CLIENT_QUESTION_NOTES_INCOMPLETE")
        if data.get("next_cursor") or data.get("nextCursor") or data.get("has_more"):
            raise ClientQuestionError("CLIENT_QUESTION_NOTES_PAGINATION_UNVERIFIED")
        if data.get("total_count") is not None and int(data["total_count"]) > len(items):
            raise ClientQuestionError("CLIENT_QUESTION_NOTES_PAGINATION_UNVERIFIED")
        return [dict(item) for item in items]

    def _history(self, ticket_id: int) -> list[dict[str, Any]]:
        data = self._read("service.notification.history.search",
                          {"ticket_id": ticket_id, "page_size": 100})
        items = data.get("items")
        if not isinstance(items, list) or not all(isinstance(i, Mapping) for i in items):
            raise ClientQuestionError("CLIENT_QUESTION_HISTORY_INCOMPLETE")
        if data.get("next_cursor") or data.get("nextCursor") or data.get("has_more"):
            raise ClientQuestionError("CLIENT_QUESTION_HISTORY_PAGINATION_UNVERIFIED")
        return [dict(item) for item in items]

    @staticmethod
    def _max_id(items: Sequence[Mapping[str, Any]]) -> int:
        return max((int(item["id"]) for item in items if
                    str(item.get("id") or "").isdigit()), default=0)

    def _assert_ticket_identity(self, ticket: Mapping[str, Any],
                                record: ClientQuestionRecord) -> None:
        if (str(ticket.get("ticketNumber") or "") != record.ticket_number
                or int(ticket.get("companyID") or 0) != record.company_id
                or int(ticket.get("contactID") or 0) != record.contact_id):
            raise ClientQuestionError("CLIENT_QUESTION_TICKET_IDENTITY_CHANGED")

    def request(self, *, ticket_id: int, question_id: str | None = None,
                missing_fact_code: str, evidence_hash: str,
                corroborated: bool, technician_reviewed: bool = False,
                resume_phase: str = "") -> str:
        self._assert_authorized()
        question = select_question_from_diagnostic(
            question_id=question_id, missing_fact_code=missing_fact_code,
            corroborated=corroborated, catalog=self.catalog,
        )
        # Context-controlled and human-review questions require a separately
        # approved exact-argument path. A caller-supplied boolean is not proof.
        if question.review_class != "routine":
            raise ClientQuestionError("CLIENT_QUESTION_HUMAN_REVIEW_REQUIRED")
        if resume_phase and not re.fullmatch(r"[a-z][a-z0-9_]{2,79}", resume_phase):
            raise ClientQuestionError("CLIENT_QUESTION_RESUME_PHASE_INVALID")
        if not SHA256_PATTERN.fullmatch(evidence_hash):
            raise ClientQuestionError("CLIENT_QUESTION_EVIDENCE_HASH_INVALID")
        ticket_id = int(ticket_id)
        ticket = self._ticket(ticket_id)
        ticket_number = str(ticket.get("ticketNumber") or "")
        if not TICKET_NUMBER_PATTERN.fullmatch(ticket_number):
            raise ClientQuestionError("CLIENT_QUESTION_TICKET_NUMBER_INVALID")
        company_id = int(ticket.get("companyID") or 0)
        contact_id = int(ticket.get("contactID") or 0)
        if company_id <= 0 or contact_id <= 0:
            raise ClientQuestionError("CLIENT_QUESTION_CONTACT_REQUIRED")
        if str(ticket.get("status") or "").casefold() in {"complete", "closed"}:
            raise ClientQuestionError("CLIENT_QUESTION_TICKET_ALREADY_CLOSED")
        # The connector independently re-reads the same company/contact and
        # validates the outbound recipient, email notification preference,
        # and exact reconstructed body before it permits provider mutation.
        contact = self._contact(contact_id, company_id)
        contact_email = str(contact["emailAddress"]).strip().casefold()
        notes = self._notes(ticket_id)
        # The narrow automatic intake case is valid only when the exact,
        # authoritative ticket still has no description and contains no
        # already-authored client explanation in its note timeline.
        if question.question_id == "JQ-001":
            if str(ticket.get("description") or "").strip():
                return "information_already_available"
            if any(
                int(note.get("createdByContactID") or 0) == contact_id
                and str(note.get("description") or "").strip()
                for note in notes
            ):
                return "information_already_available"
        expected_body = render_question(question, ticket_number, catalog=self.catalog)
        if any((str(note.get("description") or "") == expected_body
                and str(note.get("title") or "") == question.title)
               for note in notes):
            return "already_present"
        history_id = self._max_id(self._history(ticket_id))
        # Contact email is verified only by the actual connector. This field is
        # intentionally empty until a verified delivery receipt is observed.
        if not self.ledger.reserve(
            ticket_id=ticket_id, ticket_number=ticket_number,
            company_id=company_id, contact_id=contact_id, contact_email=contact_email,
            question_id=question.question_id, evidence_hash=evidence_hash,
            baseline_notification_id=history_id,
            resume_phase=resume_phase,
        ):
            return "already_reserved"
        row = self.ledger.find(ticket_id, question.question_id, evidence_hash)
        # Reservation becomes uncertain before the mutation, including on
        # timeout or readback failure. Never automatically issue the send twice.
        self.ledger.transition(row, "send_uncertain")
        output = self.actions.execute(
            self.scope, "service.ticket.client.notification.create",
            {"workflow_id": CLIENT_QUESTION_WORKFLOW_ID,
             "template_id": question.template_id,
             "ticket_number": ticket_number,
             "payload": {"ticketID": ticket_id}},
        )
        data = output.get("data") if isinstance(output, Mapping) else None
        verification = data.get("jasonVerification") if isinstance(data, Mapping) else None
        if not (isinstance(verification, Mapping)
                and verification.get("readbackVerified") is True):
            raise ClientQuestionError("CLIENT_QUESTION_SEND_READBACK_UNVERIFIED")
        # Resolve actual note ID from the authoritative ticket note timeline,
        # not from an untrusted caller-provided payload.
        matches = [n for n in self._notes(ticket_id)
                   if (n.get("title") == question.title
                       and n.get("description") == expected_body
                       and str(n.get("id") or "").isdigit())]
        if len(matches) != 1:
            raise ClientQuestionError("CLIENT_QUESTION_SENT_NOTE_UNVERIFIED")
        outbound_id = int(matches[0]["id"])
        row = self.ledger.find(ticket_id, question.question_id, evidence_hash)
        self.ledger.transition(row, "delivery_pending", outbound_note_id=outbound_id)
        return "delivery_pending"

    def reconcile(self, *, on_verified_reply: Callable[[ClientQuestionRecord], bool]
                  | None = None) -> tuple[tuple[int, str, str], ...]:
        """Read-only reconciliation; callback is an existing governed resume gate."""
        outcomes = []
        for row in self.ledger.waiting():
            try:
                ticket = self._ticket(row.ticket_id)
                self._assert_ticket_identity(ticket, row)
                contact = self._contact(row.contact_id, row.company_id)
                if str(contact["emailAddress"]).strip().casefold() != row.contact_email:
                    raise ClientQuestionError("CLIENT_QUESTION_CONTACT_EMAIL_CHANGED")
                question = self.catalog.by_id(row.question_id)
                notes = self._notes(row.ticket_id)
                exact_body = render_question(question, row.ticket_number,
                                             catalog=self.catalog)
                outgoing = [n for n in notes
                            if str(n.get("description") or "") == exact_body
                            and str(n.get("title") or "") == question.title
                            and str(n.get("id") or "").isdigit()]
                if row.state == "send_uncertain":
                    if len(outgoing) != 1:
                        outcomes.append((row.ticket_id, row.question_id, "send_uncertain"))
                        continue
                    self.ledger.transition(
                        row, "delivery_pending", outbound_note_id=int(outgoing[0]["id"])
                    )
                    row = self.ledger.find(row.ticket_id, row.question_id, row.evidence_hash)
                if row.state == "delivery_pending":
                    history = self._history(row.ticket_id)
                    matching = [
                        h for h in history
                        if int(h.get("ticketID") or 0) == row.ticket_id
                        and int(h.get("id") or 0) > row.baseline_notification_id
                    ]
                    # History provides the notification's recipient; never
                    # mistake a notification to someone else for client delivery.
                    recipient = [
                        h for h in matching
                        if (str(h.get("recipientEmailAddress") or "").strip().casefold()
                            == row.contact_email)
                    ]
                    if not recipient:
                        outcomes.append((row.ticket_id, row.question_id, "delivery_pending"))
                        continue
                    self.ledger.transition(row, "awaiting_reply")
                    row = self.ledger.find(row.ticket_id, row.question_id, row.evidence_hash)
                if row.state == "awaiting_reply":
                    replies = [
                        n for n in notes
                        if str(n.get("id") or "").isdigit()
                        and int(n["id"]) > row.outbound_note_id
                        and int(n.get("createdByContactID") or 0) == row.contact_id
                        and str(n.get("description") or "").strip()
                    ]
                    if not replies:
                        outcomes.append((row.ticket_id, row.question_id, "awaiting_reply"))
                        continue
                    self.ledger.transition(
                        row, "reply_verified",
                        reply_note_id=min(int(n["id"]) for n in replies)
                    )
                    row = self.ledger.find(row.ticket_id, row.question_id, row.evidence_hash)
                if row.state == "reply_verified":
                    if on_verified_reply is None or on_verified_reply(row) is not True:
                        outcomes.append((row.ticket_id, row.question_id, "resume_pending"))
                        continue
                    self.ledger.transition(row, "resumed")
                    outcomes.append((row.ticket_id, row.question_id, "resumed"))
            except Exception:
                # No guessed recipient, no second send, no unverified resume.
                outcomes.append((row.ticket_id, row.question_id, "reconcile_blocked"))
        return tuple(outcomes)
