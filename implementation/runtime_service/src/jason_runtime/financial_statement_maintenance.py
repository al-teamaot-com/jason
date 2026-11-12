"""Daily governed SharePoint financial-statement organizer.

The maintenance service is deliberately narrow: one configured Microsoft tenant,
one configured drive and one configured root path. It never deletes a file and never
writes to an accounting provider. Move/rename occurs only after deterministic content
classification and exact duplicate checks, followed by provider readback.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo



CANONICAL_ROOT = "Bank Statements - Organized"
_ACCOUNT_PATTERNS = (
    re.compile(r"(?i)(?:account|acct|card|line of credit)[^\n]{0,45}?(?:ending\s*(?:in)?|x{2,}|\*{2,}|#)?\s*([0-9]{4})(?:\D|$)"),
    re.compile(r"(?i)(?:ending\s+in|last\s+four(?:\s+digits)?(?:\s+are)?)[^0-9]{0,8}([0-9]{4})"),
)
_PERIOD_RANGE_NUMERIC = re.compile(
    r"(?i)(?:statement\s+(?:period|cycle)|billing\s+period)[^\n]{0,20}?"
    r"(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12][0-9]|3[01])[/\-](?:20[0-9]{2})"
    r"\s*(?:-|through|to)\s*(0?[1-9]|1[0-2])[/\-](0?[1-9]|[12][0-9]|3[01])[/\-](20[0-9]{2})"
)
_PERIOD_RANGE_WORD = re.compile(
    r"(?i)(?:statement\s+(?:period|cycle)|billing\s+period)[^\n]{0,20}?"
    r"[A-Z][a-z]+\s+(?:0?[1-9]|[12][0-9]|3[01]),?\s+20[0-9]{2}"
    r"\s*(?:-|through|to)\s*([A-Z][a-z]+)\s+(0?[1-9]|[12][0-9]|3[01]),?\s+(20[0-9]{2})"
)
_PERIOD_PATTERNS = (
    re.compile(r"(?i)(?:statement\s+(?:date|period|ending\s+date)|closing\s+date|period\s+ending|through)\s*[:\-]?\s*(0?[1-9]|1[0-2])[/\-](0?[1-9]|[12][0-9]|3[01])[/\-](20[0-9]{2})"),
    re.compile(r"(?i)(?:statement\s+(?:date|period|ending\s+date)|closing\s+date|period\s+ending|through)\s*[:\-]?\s*([A-Z][a-z]+)\s+(0?[1-9]|[12][0-9]|3[01]),?\s+(20[0-9]{2})"),
)
_MONTHS = {m.lower(): i for i, m in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"), 1)}
_INSTITUTIONS = (
    (re.compile(r"(?i)Atlantic\s+Union\s+Bank"), "Atlantic Union Bank", "AtlanticUnionBank"),
    (re.compile(r"(?i)PNC\s+Bank|\bPNC\b"), "PNC Bank", "PNCBank"),
    (re.compile(r"(?i)\bTruist\b"), "Truist", "Truist"),
    (re.compile(r"(?i)Fulton\s+Bank"), "Fulton Bank", "FultonBank"),
    (re.compile(r"(?i)American\s+Express|\bAMEX\b"), "American Express", "AmericanExpress"),
)
_NON_STATEMENT = re.compile(r"(?i)payroll\s+approval|invoice|receipt|packing\s+slip")
_KNOWN_ACCOUNT_FOLDERS = {
    ("Atlantic Union Bank", "3049"): "Checking 3049",
    ("Atlantic Union Bank", "3545"): "Payroll Checking 3545",
    ("PNC Bank", "5842"): "Checking 5842",
    ("Fulton Bank", "7313"): "Checking 7313",
    ("American Express", "1003"): "Business Gold 41003",
}


@dataclass(frozen=True, slots=True)
class StatementIdentity:
    institution: str
    filename_bank: str
    last4: str
    month: int
    year: int
    account_label: str

    @property
    def filename(self) -> str:
        return f"{self.filename_bank}-{self.last4}-{self.month:02d}{self.year:04d}.pdf"


class SQLiteFinancialStatementState:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS financial_statement_runs (
      run_date TEXT PRIMARY KEY,
      started_at TEXT NOT NULL,
      completed_at TEXT,
      summary_json TEXT
    );
    -- Runs are mutable retry state. This independent chain is append-only.
    CREATE TABLE IF NOT EXISTS financial_statement_events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      recorded_at TEXT NOT NULL,
      run_date TEXT NOT NULL,
      event_type TEXT NOT NULL,
      metadata_json TEXT NOT NULL,
      previous_sha256 TEXT NOT NULL,
      event_sha256 TEXT NOT NULL UNIQUE
    );
    """
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self.db.executescript(self._SCHEMA)

    @staticmethod
    def _canonical_event_bytes(data: Mapping[str, Any]) -> bytes:
        return json.dumps(dict(data), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")

    def _append_event_unlocked(self, run_date: str, when: datetime,
                               event_type: str, metadata: Mapping[str, Any]) -> str:
        if when.tzinfo is None:
            raise ValueError("financial audit event requires an aware timestamp")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", event_type):
            raise ValueError("invalid financial audit event type")
        previous = self.db.execute(
            "SELECT event_sha256 FROM financial_statement_events ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        prior = str(previous[0]) if previous else "0" * 64
        body = {
            "recorded_at": when.astimezone(timezone.utc).isoformat(),
            "run_date": run_date,
            "event_type": event_type,
            "metadata": dict(metadata),
            "previous_sha256": prior,
        }
        signature = hashlib.sha256(self._canonical_event_bytes(body)).hexdigest()
        self.db.execute(
            "INSERT INTO financial_statement_events "
            "(recorded_at,run_date,event_type,metadata_json,previous_sha256,event_sha256) "
            "VALUES(?,?,?,?,?,?)",
            (body["recorded_at"], run_date, event_type,
             self._canonical_event_bytes(body["metadata"]).decode("utf-8"),
             prior, signature),
        )
        return signature

    def event(self, run_date: str, when: datetime, event_type: str,
              metadata: Mapping[str, Any]) -> str:
        """Durably append before a provider mutation; never rewrite old events."""
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            return self._append_event_unlocked(run_date, when, event_type, metadata)

    def verify_event_chain(self) -> bool:
        """Verify the local chain; suffix truncation needs an external anchor."""
        prior = "0" * 64
        for recorded_at, run_date, event_type, metadata_json, previous_sha, signature in self.db.execute(
            "SELECT recorded_at,run_date,event_type,metadata_json,previous_sha256,event_sha256 "
            "FROM financial_statement_events ORDER BY event_id"
        ):
            try:
                metadata = json.loads(metadata_json)
                body = {"recorded_at": recorded_at, "run_date": run_date,
                        "event_type": event_type, "metadata": metadata,
                        "previous_sha256": previous_sha}
            except (TypeError, ValueError, json.JSONDecodeError):
                return False
            if (not isinstance(metadata, dict) or previous_sha != prior
                    or hashlib.sha256(self._canonical_event_bytes(body)).hexdigest() != signature):
                return False
            prior = signature
        return True

    def completed(self, run_date: str) -> bool:
        row = self.db.execute("SELECT completed_at FROM financial_statement_runs WHERE run_date=?", (run_date,)).fetchone()
        return bool(row and row[0])

    def can_attempt(self, run_date: str, when: datetime, retry_minutes: int = 15) -> bool:
        row = self.db.execute(
            "SELECT started_at,completed_at FROM financial_statement_runs WHERE run_date=?",
            (run_date,),
        ).fetchone()
        if row is None:
            return True
        if row[1]:
            return False
        previous = datetime.fromisoformat(str(row[0]))
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        return (when.astimezone(timezone.utc) - previous.astimezone(timezone.utc)).total_seconds() >= retry_minutes * 60

    def start(self, run_date: str, when: datetime) -> None:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._append_event_unlocked(run_date, when, "run_started", {})
            self.db.execute("INSERT INTO financial_statement_runs(run_date,started_at,completed_at,summary_json) VALUES(?,?,NULL,NULL) ON CONFLICT(run_date) DO UPDATE SET started_at=excluded.started_at,completed_at=NULL,summary_json=NULL", (run_date, when.isoformat()))

    def finish(self, run_date: str, when: datetime, summary: Mapping[str, Any], *, success: bool) -> None:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self._append_event_unlocked(run_date, when, "run_finished", {
                "success": success, "summary": dict(summary),
            })
            self.db.execute(
                "UPDATE financial_statement_runs SET completed_at=?,summary_json=? WHERE run_date=?",
                (when.isoformat() if success else None, json.dumps(dict(summary), sort_keys=True), run_date),
            )


def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    chunks = []
    for page in reader.pages[:12]:
        text = page.extract_text() or ""
        if text:
            chunks.append(text)
    return "\n".join(chunks)[:120000]


def classify_statement(text: str) -> StatementIdentity | None:
    if not text.strip() or _NON_STATEMENT.search(text):
        return None
    institution = None
    for pattern, display, slug in _INSTITUTIONS:
        if pattern.search(text):
            institution = (display, slug)
            break
    if institution is None:
        return None
    last4 = None
    for pattern in _ACCOUNT_PATTERNS:
        matches = {m.group(1) for m in pattern.finditer(text)}
        if len(matches) == 1:
            last4 = next(iter(matches))
            break
        if len(matches) > 1:
            return None
    if last4 is None:
        return None
    month = year = None
    range_match = _PERIOD_RANGE_NUMERIC.search(text)
    if range_match:
        month = int(range_match.group(1))
        year = int(range_match.group(3))
    else:
        range_match = _PERIOD_RANGE_WORD.search(text)
        if range_match:
            month = _MONTHS.get(range_match.group(1).lower())
            year = int(range_match.group(3))
    if month is None or year is None:
        for pattern in _PERIOD_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            first, _day, third = match.groups()
            if first.isdigit():
                month = int(first)
            else:
                month = _MONTHS.get(first.lower())
            year = int(third)
            break
    if month is None or year is None:
        return None
    lowered = text.lower()
    label = _KNOWN_ACCOUNT_FOLDERS.get((institution[0], last4))
    if label is None and institution[0] == "Truist" and "line of credit" in lowered:
        label = "Line of Credit"
    elif label is None and institution[0] == "Truist":
        label = "Checking"
    elif label is None and "line of credit" in lowered:
        label = f"Line of Credit {last4}"
    elif label is None and ("credit card" in lowered or institution[0] == "American Express"):
        label = f"Business Card {last4}"
    elif label is None and "payroll" in lowered:
        label = f"Payroll Checking {last4}"
    elif label is None:
        label = f"Checking {last4}"
    return StatementIdentity(institution[0], institution[1], last4, month, year, label)


class FinancialStatementMaintenance:
    def __init__(self, *, client, state: SQLiteFinancialStatementState, tenant_id: str,
                 drive_id: str, root_path: str = "Bank Checking Accounts Register",
                 timezone_name: str = "America/New_York", run_hour: int = 5,
                 now=lambda: datetime.now(timezone.utc), audit=None) -> None:
        self.client = client
        self.state = state
        self.tenant_id = tenant_id.strip()
        self.drive_id = drive_id.strip()
        self.root_path = root_path.strip().strip("/")
        self.timezone = ZoneInfo(timezone_name)
        self.run_hour = int(run_hour)
        self.now = now
        self.audit = audit
        if not self.tenant_id or not self.drive_id or not self.root_path:
            raise ValueError("financial statement tenant, drive and root are required")
        if not 0 <= self.run_hour <= 23:
            raise ValueError("run_hour must be 0-23")

    def tick(self) -> bool:
        current = self.now()
        local = current.astimezone(self.timezone)
        run_date = local.date().isoformat()
        if local.hour < self.run_hour or not self.state.can_attempt(run_date, current):
            return False
        self.run_once(now=current)
        return True

    def _record_event(self, run_date, when, kind, details):
        event_hash = self.state.event(run_date, when, kind, details)
        if self.audit is None:
            if kind == "move_intent":
                raise RuntimeError("financial statement canonical audit unavailable")
            return event_hash
        self.audit.append("financial.statement." + kind, {
            "execution_id": "financial-statement-" + event_hash[:32],
            "correlation_id": "financial-statement-" + run_date,
            "organization_id": "aot",
            "principal_id": "jason-financial-statement-maintenance",
            "capability_name": "documentation.financial_statement.organize",
            "stage": "invoking" if kind == "move_intent" else "completed",
            "event_sha256": event_hash,
            "details": dict(details),
        })
        return event_hash

    def _walk(self, root: Mapping[str, Any]):
        stack = [(root, self.root_path)]
        seen = set()
        while stack:
            folder, path = stack.pop()
            folder_id = str(folder.get("id") or "")
            if not folder_id or folder_id in seen:
                continue
            seen.add(folder_id)
            for item in self.client.list_children(tenant_id=self.tenant_id, drive_id=self.drive_id, item_id=folder_id):
                name = str(item.get("name") or "")
                child_path = f"{path}/{name}"
                if isinstance(item.get("folder"), Mapping):
                    stack.append((item, child_path))
                elif isinstance(item.get("file"), Mapping):
                    yield item, child_path

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _find_child_folder(self, parent_id: str, name: str) -> Mapping[str, Any] | None:
        matches = [x for x in self.client.list_children(tenant_id=self.tenant_id, drive_id=self.drive_id, item_id=parent_id)
                   if isinstance(x.get("folder"), Mapping) and str(x.get("name") or "").casefold() == name.casefold()]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous SharePoint folder: {name}")
        return matches[0] if matches else None

    def _folder(self, parent_id: str, name: str) -> Mapping[str, Any]:
        existing = self._find_child_folder(parent_id, name)
        if existing is not None:
            return existing
        created = self.client.create_folder(tenant_id=self.tenant_id, drive_id=self.drive_id, parent_id=parent_id, name=name)
        verified = self._find_child_folder(parent_id, name)
        if verified is None or str(verified.get("id") or "") != str(created.get("id") or ""):
            raise RuntimeError("SharePoint folder creation readback failed")
        return verified

    def run_once(self, *, now: datetime | None = None) -> Mapping[str, Any]:
        current = now or self.now()
        local = current.astimezone(self.timezone)
        run_date = local.date().isoformat()
        self.state.start(run_date, current)
        summary: dict[str, Any] = {"run_date": run_date, "files_discovered": 0, "classified": 0,
                                  "moved": 0, "already_canonical": 0, "duplicates": 0,
                                  "ambiguous_or_unclassified": 0, "errors": []}
        root = self.client.get_item_by_path(tenant_id=self.tenant_id, drive_id=self.drive_id, path=self.root_path)
        root_id = str(root.get("id") or "")
        if not root_id:
            raise RuntimeError("SharePoint intake root could not be resolved")
        canonical = self._folder(root_id, CANONICAL_ROOT)
        canonical_id = str(canonical.get("id") or "")

        files = list(self._walk(root))
        known_hashes: dict[str, str] = {}
        for item, path in files:
            name = str(item.get("name") or "")
            if not name.lower().endswith(".pdf"):
                continue
            summary["files_discovered"] += 1
            try:
                data = self.client.download_file(tenant_id=self.tenant_id, drive_id=self.drive_id, item_id=str(item.get("id") or ""))
                digest = self._sha256(data)
                prior = known_hashes.get(digest)
                if prior is not None:
                    self._record_event(run_date, current, "duplicate_skipped", {
                        "path": path, "item_id": str(item.get("id") or ""),
                        "sha256": digest, "first_seen_path": prior,
                    })
                    summary["duplicates"] += 1
                    continue
                known_hashes[digest] = path
                identity = classify_statement(extract_pdf_text(data))
                if identity is None:
                    self._record_event(run_date, current, "unclassified_preserved", {
                        "path": path, "item_id": str(item.get("id") or ""),
                        "sha256": digest,
                    })
                    summary["ambiguous_or_unclassified"] += 1
                    continue
                summary["classified"] += 1
                institution = self._folder(canonical_id, identity.institution)
                account = self._folder(str(institution["id"]), identity.account_label)
                year = self._folder(str(account["id"]), str(identity.year))
                destination_id = str(year["id"])
                desired = identity.filename
                parent_ref = item.get("parentReference") if isinstance(item.get("parentReference"), Mapping) else {}
                if str(parent_ref.get("id") or "") == destination_id and name == desired:
                    self._record_event(run_date, current, "already_canonical", {
                        "path": path, "item_id": str(item.get("id") or ""),
                        "sha256": digest, "filename": desired,
                    })
                    summary["already_canonical"] += 1
                    continue
                destinations = [x for x in self.client.list_children(tenant_id=self.tenant_id, drive_id=self.drive_id, item_id=destination_id)
                                if str(x.get("name") or "").casefold() == desired.casefold()]
                if destinations:
                    other = destinations[0]
                    other_data = self.client.download_file(tenant_id=self.tenant_id, drive_id=self.drive_id, item_id=str(other.get("id") or ""))
                    if self._sha256(other_data) == digest:
                        self._record_event(run_date, current, "duplicate_skipped", {
                            "path": path, "item_id": str(item.get("id") or ""),
                            "sha256": digest, "canonical_item_id": str(other.get("id") or ""),
                        })
                        summary["duplicates"] += 1
                        continue
                    raise RuntimeError(f"canonical filename collision: {desired}")
                self._record_event(run_date, current, "move_intent", {
                    "path": path, "item_id": str(item.get("id") or ""),
                    "sha256": digest, "destination_parent_id": destination_id,
                    "filename": desired,
                })
                moved = self.client.move_and_rename(tenant_id=self.tenant_id, drive_id=self.drive_id,
                                                    item_id=str(item.get("id") or ""), destination_parent_id=destination_id,
                                                    new_name=desired)
                verify = self.client.get_item(tenant_id=self.tenant_id, drive_id=self.drive_id, item_id=str(item.get("id") or ""))
                vparent = verify.get("parentReference") if isinstance(verify.get("parentReference"), Mapping) else {}
                if str(verify.get("name") or "") != desired or str(vparent.get("id") or "") != destination_id:
                    raise RuntimeError("SharePoint move/rename readback failed")
                if str(moved.get("id") or "") and str(moved.get("id")) != str(item.get("id") or ""):
                    raise RuntimeError("SharePoint move returned unexpected item identity")
                self._record_event(run_date, current, "move_verified", {
                    "path": path, "item_id": str(item.get("id") or ""),
                    "sha256": digest, "destination_parent_id": destination_id,
                    "filename": desired,
                })
                summary["moved"] += 1
            except Exception as exc:
                error = {"path": path, "error": type(exc).__name__, "message": str(exc)[:240]}
                self._record_event(run_date, current, "file_error", error)
                summary["errors"].append(error)
        completed = self.now()
        summary["success"] = not bool(summary["errors"])
        self.state.finish(run_date, completed, summary, success=bool(summary["success"]))
        return summary
