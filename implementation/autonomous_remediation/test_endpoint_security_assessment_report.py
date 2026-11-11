"""AOT PDF delivery and client-publication gate tests."""
from __future__ import annotations

import io
import pytest

pytest.importorskip("reportlab")
from pypdf import PdfReader

from .endpoint_security_assessment import RawFinding
from .endpoint_security_assessment_report import (
    ReportNotPublishable, render_security_pdf,
)
from .test_endpoint_security_assessment import (
    HUNT, LENOVO_A, LENOVO_B, MAPS, parse, output, assessment, verified,
)


def page_text(pdf):
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def test_verified_presentation_preserves_original_counts_and_dispositions():
    findings = [HUNT, LENOVO_A, LENOVO_B]
    a = assessment(parse(output(findings)), [verified(x.name) for x in findings])
    assert a.report_publishable
    pdf = render_security_pdf(a, audience="client")
    text = page_text(pdf)
    for expected in ("ATLANTIC OFFICE TECHNOLOGIES",
                     "ENDPOINT SECURITY ASSESSMENT", "CCPC-50960",
                     "Robert B. Hansen", "Datto AV",
                     "Running and up to date",
                     "VantageCoreAddinIdleScheduleTask",
                     "HUNTAgent",
                     "3 finding(s) verified as expected software"):
        assert expected in text, expected
    assert "INTERNAL REVIEW" not in text
    assert "DurationSec" not in text


def test_unknown_low_never_generates_client_all_clear():
    findings=[HUNT, LENOVO_A, LENOVO_B, MAPS]
    a=assessment(parse(output(findings)),
                 [verified(x.name) for x in findings[:3]])
    assert not a.report_publishable
    with pytest.raises(ReportNotPublishable, match="UNVERIFIED"):
        render_security_pdf(a, audience="client")
    pdf = render_security_pdf(a, audience="technician")
    text = page_text(pdf)
    assert "INTERNAL REVIEW - NOT A CLIENT ALL-CLEAR" in text
    assert "MapS.bat" in text
    assert "REVIEW NEEDED" in text


def test_bounded_low_hidden_is_reported_not_silently_suppressed():
    findings=[HUNT, LENOVO_A, LENOVO_B, MAPS]
    a=assessment(parse(output(findings, bounded=True)),
                 [verified(x.name) for x in findings[:3]])
    assert a.unresolved_detail_count > 0
    internal=page_text(render_security_pdf(a, audience="technician"))
    assert "finding detail(s) still need evidence" in internal
    assert "remaining" not in internal.casefold() or "review" in internal.casefold()
    with pytest.raises(ReportNotPublishable):
        render_security_pdf(a, audience="client")


def test_client_pdf_rejects_silent_finding_row_overflow():
    from .endpoint_security_assessment import RawFinding
    extra = [
        RawFinding("Low", "StartupFile", f"startup_{i}.bat", "Startup observation",
                   fr"C:\\Users\\Public\\startup_{i}.bat")
        for i in range(6)
    ]
    scan = parse(output(extra))
    a = assessment(scan)
    # No all-clear without verified evidence; even a contrived fully
    # classified 6-item report must not suppress its last row.
    from dataclasses import replace
    a = replace(a, report_publishable=True)
    with pytest.raises(ReportNotPublishable, match="EXCEEDS_SINGLE_PAGE"):
        render_security_pdf(a, audience="client")


def test_unknown_audience_is_rejected():
    a=assessment(parse(output()))
    with pytest.raises(ValueError, match="AUDIENCE"):
        render_security_pdf(a, audience="anonymous")
