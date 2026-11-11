"""Private, content-addressed PDF artifact store for Jason assessments.

Only authenticated Jason/Teams adapters may call this with a trusted bound
principal. This creates no public URL, email or new provider permission.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import tempfile

from .endpoint_security_assessment_workflow import (
    AssessmentGovernanceError, AssessmentProgress, AssessmentRequest,
    SqliteAssessmentState,
)
from .endpoint_security_assessment_report import render_security_pdf


@dataclass(frozen=True)
class ArtifactReference:
    request_id: str
    sha256: str
    audience: str
    created_at: str
    expires_at: str
    content_type: str = "application/pdf"


class PrivateAssessmentArtifactStore:
    def __init__(self, db_path: str | Path, artifact_dir: str | Path,
                 *, retention_days: int = 30) -> None:
        if not 1 <= retention_days <= 90:
            raise ValueError("ARTIFACT_RETENTION_OUT_OF_BOUNDS")
        self.db_path = str(db_path)
        self.root = Path(artifact_dir).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.assessments = SqliteAssessmentState(self.db_path)
        self.retention_days = retention_days
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS endpoint_security_artifacts (
                request_id TEXT NOT NULL,
                site_uid TEXT NOT NULL,
                requester_identity TEXT NOT NULL,
                audience TEXT NOT NULL,
                digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                filename TEXT NOT NULL,
                PRIMARY KEY(request_id, audience, digest)
            )""")

    def _verify_request(self, req: AssessmentRequest,
                        *, bound_requester: str) -> dict:
        # Bound identity MUST come from trusted Entra / Central Orchestrator,
        # never an LLM-generated or unverified request parameter.
        row = self.assessments.create_or_get(req)
        if (not bound_requester or
            req.requester_identity != bound_requester or
            row["requester_identity"] != bound_requester):
            raise AssessmentGovernanceError("PDF_REQUESTER_NOT_AUTHENTICATED_OR_BOUND")
        if row["client_site_uid"] != req.client_site_uid:
            raise AssessmentGovernanceError("PDF_CLIENT_BOUNDARY_MISMATCH")
        return dict(row)

    def publish(self, req: AssessmentRequest, *,
                progress: AssessmentProgress,
                audience: str, bound_requester: str) -> ArtifactReference:
        row = self._verify_request(req, bound_requester=bound_requester)
        a = progress.assessment
        if a is None or not row["device_uid"] or not row["job_uid"]:
            raise AssessmentGovernanceError("PDF_NOT_BOUND_TO_COMPLETED_JOB")
        if (a.device_uid != row["device_uid"] or
            a.site_uid != req.client_site_uid or
            a.hostname.casefold() != req.hostname.casefold() or
            a.sweep.job_uid != row["job_uid"]):
            raise AssessmentGovernanceError("PDF_ASSESSMENT_TARGET_MISMATCH")
        if audience == "client" and not (a.report_publishable and
                                         progress.report_ready and
                                         row["state"] == "report_ready"):
            raise AssessmentGovernanceError("CLIENT_PDF_NOT_VERIFIED")
        if audience not in {"client", "technician"}:
            raise AssessmentGovernanceError("UNSUPPORTED_ARTIFACT_AUDIENCE")
        contents = render_security_pdf(a, audience=audience)
        digest = sha256(contents).hexdigest()
        filename = digest + ".pdf"
        target = self.root / filename
        if not target.is_file():
            fd, temp = tempfile.mkstemp(dir=self.root, prefix=".assessment-",suffix=".pdf")
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(contents)
                    out.flush()
                    os.fsync(out.fileno())
                os.chmod(temp, 0o600)
                os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        if sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError("STORED_PDF_DIGEST_MISMATCH")
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=self.retention_days)
        with sqlite3.connect(self.db_path) as db:
            db.execute("""INSERT OR IGNORE INTO endpoint_security_artifacts
              (request_id,site_uid,requester_identity,audience,digest,created_at,expires_at,filename)
              VALUES (?,?,?,?,?,?,?,?)""",
                (req.request_id, req.client_site_uid, bound_requester, audience,
                 digest, now.isoformat(), expiry.isoformat(), filename))
            record = db.execute("""SELECT created_at,expires_at FROM endpoint_security_artifacts
              WHERE request_id=? AND audience=? AND digest=?""",
                (req.request_id,audience,digest)).fetchone()
        assert record is not None
        return ArtifactReference(req.request_id,digest,audience,record[0],record[1])

    def retrieve(self, req: AssessmentRequest, *,
                 reference: ArtifactReference, bound_requester: str) -> bytes:
        self._verify_request(req, bound_requester=bound_requester)
        if reference.request_id != req.request_id:
            raise AssessmentGovernanceError("PDF_REFERENCE_REQUEST_MISMATCH")
        with sqlite3.connect(self.db_path) as db:
            record = db.execute("""SELECT filename,expires_at FROM endpoint_security_artifacts
              WHERE request_id=? AND site_uid=? AND requester_identity=?
                AND audience=? AND digest=?""",
               (req.request_id,req.client_site_uid,bound_requester,
                reference.audience,reference.sha256)).fetchone()
        if record is None:
            raise AssessmentGovernanceError("PDF_REFERENCE_NOT_AUTHORIZED")
        if datetime.fromisoformat(record[1]) < datetime.now(timezone.utc):
            raise AssessmentGovernanceError("PDF_ARTIFACT_EXPIRED")
        filename = record[0]
        if filename != reference.sha256 + ".pdf":
            raise AssessmentGovernanceError("PDF_FILENAME_NOT_CONTENT_ADDRESSED")
        path = self.root / filename
        if path.parent != self.root or not path.is_file():
            raise FileNotFoundError("PDF_ARTIFACT_UNAVAILABLE")
        data = path.read_bytes()
        if sha256(data).hexdigest() != reference.sha256 or not data.startswith(b"%PDF-"):
            raise RuntimeError("PDF_ARTIFACT_INTEGRITY_FAILURE")
        return data
