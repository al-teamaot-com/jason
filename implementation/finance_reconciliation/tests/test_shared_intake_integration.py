"""Read-only cross-language proof of Node Document Intake -> finance evidence.

Synthetic documents only. No provider access, real bank data, ledger writes,
Teams sending, or QuickBooks integration are exercised here.
"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess

import pytest

from finance_reconciliation.contracts import DocumentKind
from finance_reconciliation.pdf_preflight import SharedDocumentIntakeEvidenceAdapter


def _fixture_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(612, 792))
    pdf.drawString(60, 720, "AOT Synthetic Reconciliation Test")
    pdf.drawString(60, 680, "Statement opening balance 100.00")
    pdf.showPage()
    pdf.drawString(60, 720, "Statement closing balance 105.00")
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def _shared_intake(pdf_bytes: bytes, tmp_path: Path) -> dict:
    shared_path = os.environ.get("JASON_SHARED_INTAKE_PATH")
    assert shared_path, "CI must pin the exact reviewed shared Document Intake commit"
    module = Path(shared_path).resolve(strict=True)
    pdf_path = tmp_path / "synthetic-statement.pdf"
    pdf_path.write_bytes(pdf_bytes)
    script = (
        'import { readFileSync } from "node:fs";'
        'import { pathToFileURL } from "node:url";'
        'const { inspectPdfBuffer } = await import(pathToFileURL(process.env.JASON_SHARED_INTAKE_PATH));'
        'const evidence = inspectPdfBuffer(readFileSync(process.argv[1]), {pageInventory:true});'
        'process.stdout.write(JSON.stringify(evidence));'
    )
    # No shell, no credentials. Only a local synthetic PDF and pinned source.
    env = dict(os.environ, JASON_SHARED_INTAKE_PATH=str(module))
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(pdf_path)],
        env=env, capture_output=True, text=True, timeout=35, check=True,
    )
    return json.loads(result.stdout)


def test_real_shared_pdf_evidence_accepted_by_finance(tmp_path):
    source = _fixture_pdf()
    evidence = _shared_intake(source, tmp_path)
    assert evidence["source_sha256"] == sha256(source).hexdigest()
    assert evidence["extraction_complete"] is True
    assert evidence["rendered_verified"] is False
    assert evidence["accounting_validated"] is False
    assert evidence["page_count"] == 2
    assert "opening balance 100.00" in evidence["extracted_text"]
    assert "closing balance 105.00" in evidence["extracted_text"]
    result = SharedDocumentIntakeEvidenceAdapter().accept(source, evidence)
    assert result.document_kind is DocumentKind.NATIVE_TEXT
    assert len(result.pages) == 2
    assert all(page.has_native_text for page in result.pages)

    # The financial consumer must refuse stale/corrupted document evidence.
    tampered = {**evidence, "source_sha256": "f" * 64}
    with pytest.raises(ValueError, match="does not match"):
        SharedDocumentIntakeEvidenceAdapter().accept(source, tampered)

    with pytest.raises(ValueError, match="does not match"):
        SharedDocumentIntakeEvidenceAdapter().accept(
            source + b" changed after preflight", evidence
        )
