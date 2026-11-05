"""One-page AOT styled PDF for a governed security assessment.

Production clients receive the public variant only when finding-level review
and protection evidence are complete.  A technician can see an explicitly marked
internal draft with open exceptions; neither variant silently invents findings.
ReportLab is intentionally imported only by the render boundary.
"""
from __future__ import annotations

from io import BytesIO
import re
from typing import Iterable

from .endpoint_security_assessment import Assessment, Disposition

NAVY = "#102B45"
TEAL = "#0E9C9C"
MUTED = "#5F7486"
LIGHT = "#EEF4F7"
WHITE = "#FFFFFF"
AMBER = "#C47D1C"
RED = "#B43E4B"


class ReportNotPublishable(PermissionError):
    pass


def _safe_text(text: str, limit: int = 320) -> str:
    """No escape sequences, deceptive controls, secrets or unbounded text."""
    value = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(text))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _to_wrapped_lines(text: str, font: str, size: float, width: float,
                      string_width) -> list[str]:
    words = _safe_text(text, 1000).split(" ")
    lines: list[str] = []
    cur = ""
    for word in words:
        test = f"{cur} {word}".strip()
        if not cur or string_width(test, font, size) <= width:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def render_security_pdf(assessment: Assessment, *,
                        audience: str = "technician") -> bytes:
    """Build PDF deterministically. No provider read or endpoint interaction."""
    if audience not in {"technician", "client"}:
        raise ValueError("AUDIENCE_INVALID")
    if audience == "client" and not assessment.report_publishable:
        raise ReportNotPublishable("UNVERIFIED_ASSESSMENT_CANNOT_BE_SENT_TO_CLIENT")
    actionable = [z for z in assessment.reviewed if z.raw.severity != "Info"]
    if audience == "client" and len(actionable) > 5:
        raise ReportNotPublishable("CLIENT_REPORT_EXCEEDS_SINGLE_PAGE_REVIEW_CAPACITY")
    try:
        from reportlab.lib.colors import HexColor, white
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen.canvas import Canvas
    except ImportError as exc:
        raise RuntimeError("REPORTLAB_RUNTIME_DEPENDENCY_MISSING") from exc

    out = BytesIO()
    page_w, page_h = 612, 792
    c = Canvas(out, pagesize=(page_w, page_h), pageCompression=1, invariant=1)
    c.setTitle(f"AOT Endpoint Security Assessment - {_safe_text(assessment.hostname, 60)}")
    c.setAuthor("Atlantic Office Technologies")
    x = 42
    right = page_w - 42
    usable = right - x
    y = page_h

    def box(left, bottom, width, height, color, radius=0):
        c.setFillColor(HexColor(color))
        if radius:
            c.roundRect(left, bottom, width, height, radius, stroke=0, fill=1)
        else:
            c.rect(left, bottom, width, height, stroke=0, fill=1)

    def line(text, at_x, at_y, font="Helvetica", size=10, color=NAVY):
        c.setFillColor(HexColor(color))
        c.setFont(font, size)
        c.drawString(at_x, at_y, _safe_text(text, 300))

    def paragraph(text, at_x, at_y, width, size=9, color=NAVY,
                  leading=14, max_lines=5):
        words = _to_wrapped_lines(text, "Helvetica", size, width, stringWidth)
        for index, row in enumerate(words[:max_lines]):
            line(row, at_x, at_y - index * leading, size=size, color=color)
        return at_y - min(len(words), max_lines) * leading

    box(0, page_h - 107, page_w, 107, NAVY)
    box(42, page_h - 79, 40, 40, TEAL, 7)
    line("AOT", 47, page_h - 66, "Helvetica-Bold", 16, WHITE)
    line("ATLANTIC OFFICE TECHNOLOGIES", 94, page_h - 44,
         "Helvetica-Bold", 12, WHITE)
    line("ENDPOINT SECURITY ASSESSMENT", 94, page_h - 65, "Helvetica-Bold", 17, WHITE)
    line("Managed endpoint | Read-only indicator assessment",
         94, page_h - 83, size=9, color="#C2D8E2")
    y = page_h - 131

    if not assessment.report_publishable:
        box(x, y - 35, usable, 35, "#FFF4E8", 6)
        line("INTERNAL REVIEW - NOT A CLIENT ALL-CLEAR", x + 14,
             y - 21, "Helvetica-Bold", 10, AMBER)
        y -= 54

    line(_safe_text(assessment.hostname, 65), x, y, "Helvetica-Bold", 20)
    line(_safe_text(assessment.company, 72), right - min(245, stringWidth(assessment.company, "Helvetica", 10)),
         y + 4, "Helvetica", 10, MUTED)
    y -= 24
    box(x, y - 67, usable, 67, LIGHT, 8)
    good_av = assessment.antivirus_status == "RunningAndUpToDate"
    line("MANAGED ANTIVIRUS", x+12, y-18, "Helvetica-Bold", 8, MUTED)
    line((assessment.antivirus_product + " | " +
          ("Running and up to date" if good_av else "Verification needed")),
         x+12, y-37, "Helvetica-Bold", 12, NAVY if good_av else RED)
    line("INDICATOR ASSESSMENT", x+320, y-18, "Helvetica-Bold", 8, MUTED)
    state = ("No elevated indicators after review" if assessment.report_publishable
             else "Review remains open")
    line(state, x+320, y-36, "Helvetica-Bold", 10, TEAL if assessment.report_publishable else AMBER)
    y -= 92

    line("ASSESSMENT FINDINGS", x, y, "Helvetica-Bold", 11)
    y -= 12
    counts = assessment.sweep.counts
    positions = ((0, "HIGH", RED), (132, "MEDIUM", AMBER),
                 (264, "LOW", "#507F9D"), (396, "INFO", "#507F9D"))
    for left, title, col in positions:
        box(x+left, y-54, 122, 54, LIGHT, 7)
        val = counts[title.title()]
        line(str(val), x+left+12, y-31, "Helvetica-Bold", 20, col)
        line(title, x+left+61, y-28, "Helvetica-Bold", 9, MUTED)
    y -= 74
    reviewed_count = sum(z.disposition is Disposition.VERIFIED_EXPECTED for z in assessment.reviewed)
    unresolved_count = assessment.unresolved_detail_count + sum(
        z.disposition is Disposition.UNRESOLVED for z in assessment.reviewed)
    disposition = (f"{reviewed_count} finding(s) verified as expected software; "
                   f"{unresolved_count} finding detail(s) still need evidence.")
    y = paragraph(disposition, x, y, usable, 9) - 14

    line("WHAT WAS CHECKED", x, y, "Helvetica-Bold", 11)
    y -= 14
    checked = assessment.sweep.inventory
    metrics = (("Processes", "processes"), ("Network connections", "established_tcp"),
               ("Services", "services"), ("Scheduled tasks", "scheduled_tasks"),
               ("Startup entries", "startup_files"), ("Autorun values", "autorun_values"))
    for index, (title, key) in enumerate(metrics):
        column = index % 3
        row = index // 3
        at_x = x + column*177
        at_y = y - row*33
        line(f"{checked.get(key, 'n/a'):,}", at_x, at_y-7, "Helvetica-Bold", 14, NAVY)
        line(title, at_x+40, at_y-6, "Helvetica", 8, MUTED)
    y -= 76

    line("INVESTIGATION & DISPOSITION", x, y, "Helvetica-Bold", 11)
    y -= 13
    reviewed = [z for z in assessment.reviewed if z.raw.severity != "Info"]
    if not reviewed:
        y = paragraph("No actionable items recorded in the retrieved finding details.",
                      x, y-4, usable, 9) - 2
    else:
        for z in reviewed[:5]:
            label = ("VERIFIED" if z.disposition is Disposition.VERIFIED_EXPECTED
                     else "REVIEW NEEDED")
            label_color = TEAL if z.disposition is Disposition.VERIFIED_EXPECTED else AMBER
            line(f"{label}  |  {_safe_text(z.raw.name, 47)}",
                 x+2, y-3, "Helvetica-Bold", 8.5, label_color)
            y = paragraph(z.explanation, x+12, y-17, usable-14, 8.5,
                          MUTED, 11, max_lines=2) - 8

    if len(reviewed) > 5:
        y = paragraph(
            f"{len(reviewed)-5} additional findings are recorded in the structured "
            "assessment. This one-page preview is incomplete; refer to the "
            "internal finding inventory before any client delivery.",
            x+2, y-1, usable, 8.5, AMBER, 11, 3) - 11

    if assessment.unresolved_detail_count:
        y = paragraph(
            f"{assessment.unresolved_detail_count} additional scanner finding(s) "
            "lack complete detail in the retrieved evidence and were not automatically cleared.",
            x+2, y-1, usable, 8.7, AMBER, 12, 3) - 11

    line("ASSESSMENT LIMITATIONS", x, y, "Helvetica-Bold", 10)
    y -= 16
    for limitation in assessment.limitations[:3]:
        y = paragraph("- "+limitation, x+3, y, usable-3, 8, MUTED, 11, 2)-3

    # Footer never overlaps content: tight reports must fail rather than shrink
    # critical qualifications to illegibility.
    if y < 53:
        raise ValueError("REPORT_LAYOUT_OVERFLOW_REQUIRES_REDESIGN")
    box(0, 0, page_w, 42, NAVY)
    line("Prepared by AOT | Project Jason", x, 22, "Helvetica", 8, WHITE)
    line("Diagnostic job: "+assessment.sweep.job_uid[:36],
         right-255, 22, "Helvetica", 8, "#C2D8E2")
    c.save()
    result = out.getvalue()
    if not result.startswith(b"%PDF-") or len(result)<1000:
        raise RuntimeError("PDF_GENERATION_FAILED")
    return result
