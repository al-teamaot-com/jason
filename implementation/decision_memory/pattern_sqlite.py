from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import sqlite3

from .pattern_memory import AOTResolutionPattern, PatternStepEvidence
from .resolution_memory import ResolutionSignature


_PATTERN_SCHEMA = """
CREATE TABLE IF NOT EXISTS aot_resolution_patterns (
    pattern_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    signature_json TEXT NOT NULL,
    root_cause_class TEXT NOT NULL,
    support_count INTEGER NOT NULL,
    supporting_client_count INTEGER NOT NULL,
    contradiction_count INTEGER NOT NULL,
    contradiction_rate REAL NOT NULL,
    outcome_quality REAL NOT NULL,
    recency_factor REAL NOT NULL,
    confidence REAL NOT NULL,
    latest_support_at TEXT NOT NULL,
    promotion_mode TEXT NOT NULL,
    steps_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aot_resolution_patterns_org_confidence
ON aot_resolution_patterns(organization_id, confidence DESC);
"""


@dataclass(frozen=True, slots=True)
class SQLiteAOTPatternStore:
    database_path: str

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(_PATTERN_SCHEMA)

    def replace_organization_patterns(
        self, *, organization_id: str, patterns: tuple[AOTResolutionPattern, ...]
    ) -> None:
        if not organization_id.strip():
            raise ValueError("organization_id must be non-empty")
        if any(pattern.organization_id != organization_id for pattern in patterns):
            raise ValueError("pattern organization mismatch")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "DELETE FROM aot_resolution_patterns WHERE organization_id = ?",
                    (organization_id,),
                )
                for pattern in patterns:
                    connection.execute(
                        """
                        INSERT INTO aot_resolution_patterns (
                            pattern_id, organization_id, signature_json,
                            root_cause_class, support_count, supporting_client_count,
                            contradiction_count, contradiction_rate, outcome_quality,
                            recency_factor, confidence, latest_support_at,
                            promotion_mode, steps_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            pattern.pattern_id,
                            pattern.organization_id,
                            json.dumps(
                                {
                                    "category": pattern.signature.category,
                                    "product": pattern.signature.product,
                                    "device_role": pattern.signature.device_role,
                                    "platform": pattern.signature.platform,
                                    "product_version": pattern.signature.product_version,
                                    "symptoms": list(pattern.signature.symptoms),
                                    "attributes": dict(pattern.signature.attributes),
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            pattern.root_cause_class,
                            pattern.support_count,
                            pattern.supporting_client_count,
                            pattern.contradiction_count,
                            pattern.contradiction_rate,
                            pattern.outcome_quality,
                            pattern.recency_factor,
                            pattern.confidence,
                            pattern.latest_support_at.isoformat(),
                            pattern.promotion_mode,
                            json.dumps(
                                [
                                    {
                                        "action_key": step.action_key,
                                        "attempts": step.attempts,
                                        "successes": step.successes,
                                        "failures": step.failures,
                                        "inconclusive": step.inconclusive,
                                        "confidence": step.confidence,
                                        "read_only": step.read_only,
                                        "approval_required": step.approval_required,
                                        "disruptive": step.disruptive,
                                        "disposition": step.disposition,
                                    }
                                    for step in pattern.steps
                                ],
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_patterns(
        self, *, organization_id: str, limit: int = 500
    ) -> tuple[AOTResolutionPattern, ...]:
        if not organization_id.strip():
            raise ValueError("organization_id must be non-empty")
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM aot_resolution_patterns
                WHERE organization_id = ?
                ORDER BY confidence DESC, support_count DESC, pattern_id
                LIMIT ?
                """,
                (organization_id, limit),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def count_patterns(self, *, organization_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM aot_resolution_patterns WHERE organization_id = ?",
                (organization_id,),
            ).fetchone()
        return int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AOTResolutionPattern:
        signature = json.loads(row["signature_json"])
        steps = json.loads(row["steps_json"])
        return AOTResolutionPattern(
            pattern_id=row["pattern_id"],
            organization_id=row["organization_id"],
            signature=ResolutionSignature(
                category=signature["category"],
                product=signature["product"],
                device_role=signature["device_role"],
                platform=signature["platform"],
                product_version=signature.get("product_version", ""),
                symptoms=tuple(signature.get("symptoms", [])),
                attributes=dict(signature.get("attributes", {})),
            ),
            root_cause_class=row["root_cause_class"],
            support_count=int(row["support_count"]),
            supporting_client_count=int(row["supporting_client_count"]),
            contradiction_count=int(row["contradiction_count"]),
            contradiction_rate=float(row["contradiction_rate"]),
            outcome_quality=float(row["outcome_quality"]),
            recency_factor=float(row["recency_factor"]),
            confidence=float(row["confidence"]),
            latest_support_at=datetime.fromisoformat(row["latest_support_at"]),
            promotion_mode=row["promotion_mode"],
            steps=tuple(
                PatternStepEvidence(
                    action_key=item["action_key"],
                    attempts=int(item["attempts"]),
                    successes=int(item["successes"]),
                    failures=int(item["failures"]),
                    inconclusive=int(item["inconclusive"]),
                    confidence=float(item["confidence"]),
                    read_only=bool(item["read_only"]),
                    approval_required=bool(item["approval_required"]),
                    disruptive=bool(item["disruptive"]),
                    disposition=item["disposition"],
                )
                for item in steps
            ),
        )
