"""Deterministic analysis helpers for non-KB VulScan findings.

The helper classifies scanner evidence and correlates it with governed endpoint
software inventory. It does not authorize or perform remediation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>\]\[\)\(\"']+")


@dataclass(frozen=True, slots=True)
class NonKBVulScanAssessment:
    classification: str
    cves: tuple[str, ...]
    matched_software: tuple[str, ...]
    scanner_references: tuple[str, ...]
    authoritative_references: tuple[str, ...]
    remediation_kind: str
    confidence: str
    limitations: tuple[str, ...]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _software_label(item: Mapping[str, Any]) -> str:
    name = _clean(
        item.get("name")
        or item.get("softwareName")
        or item.get("displayName")
        or item.get("product")
    )
    version = _clean(
        item.get("version")
        or item.get("softwareVersion")
        or item.get("displayVersion")
    )
    if not name:
        return ""
    return f"{name} {version}".strip()


def _software_tokens(label: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9.+_-]{2,}", label.casefold())
        if token not in {
            "microsoft",
            "windows",
            "update",
            "security",
            "version",
            "application",
            "software",
        }
    }


def analyze_non_kb_vulscan(
    material: str,
    software_items: Sequence[Mapping[str, Any]] = (),
) -> NonKBVulScanAssessment:
    text = _clean(material)
    folded = text.casefold()
    cves = tuple(sorted({match.upper() for match in CVE_RE.findall(text)}))

    if any(token in folded for token in ("false positive", "not vulnerable", "detection artifact")):
        classification = "false_positive_candidate"
        remediation = "validate_scanner_evidence"
    elif any(token in folded for token in ("end of life", "end-of-life", "eol", "unsupported version")):
        classification = "end_of_life_software"
        remediation = "upgrade_or_replace"
    elif any(token in folded for token in ("certificate", "tls", "ssl", "cipher")):
        classification = "certificate_or_tls_issue"
        remediation = "configuration_or_certificate_change"
    elif any(token in folded for token in ("smbv1", "protocol", "open port", "exposed service", "rdp", "telnet")):
        classification = "service_or_protocol_exposure"
        remediation = "service_protocol_or_firewall_change"
    elif any(token in folded for token in ("registry", "configuration", "misconfiguration", "policy setting")):
        classification = "insecure_configuration"
        remediation = "configuration_change"
    elif cves or any(token in folded for token in ("outdated", "upgrade", "update available", "vulnerable version")):
        classification = "third_party_or_runtime_vulnerability"
        remediation = "software_update_or_upgrade"
    else:
        classification = "non_kb_vulnerability_review"
        remediation = "authoritative_research_required"

    material_tokens = _software_tokens(text)
    matches: list[str] = []
    for item in software_items:
        if not isinstance(item, Mapping):
            continue
        label = _software_label(item)
        if not label:
            continue
        tokens = _software_tokens(label)
        if tokens and material_tokens and len(tokens & material_tokens) >= 1:
            matches.append(label)
    matched = tuple(dict.fromkeys(matches))[:10]

    scanner_refs: list[str] = []
    authoritative: list[str] = []
    for raw in URL_RE.findall(text):
        url = raw.rstrip(".,;:")
        host = (urlparse(url).hostname or "").casefold()
        scanner_refs.append(url)
        if host.endswith(
            (
                "microsoft.com",
                "cisa.gov",
                "nist.gov",
                "nvd.nist.gov",
                "cve.org",
                "adobe.com",
                "google.com",
                "mozilla.org",
                "oracle.com",
                "vmware.com",
                "broadcom.com",
                "cisco.com",
            )
        ):
            authoritative.append(url)

    for cve in cves:
        authoritative.extend(
            (
                f"https://www.cve.org/CVERecord?id={cve}",
                f"https://nvd.nist.gov/vuln/detail/{cve}",
            )
        )

    limitations: list[str] = []
    if not cves:
        limitations.append("No CVE identifier was present in the ticket evidence.")
    if not matched:
        limitations.append(
            "No installed-software record was confidently correlated to the finding."
        )
    if not authoritative:
        limitations.append(
            "No authoritative vendor/CVE reference was present; remediation specifics require authoritative research."
        )

    confidence = "high" if cves and matched else "moderate" if cves or matched else "low"
    return NonKBVulScanAssessment(
        classification=classification,
        cves=cves,
        matched_software=matched,
        scanner_references=tuple(dict.fromkeys(scanner_refs))[:10],
        authoritative_references=tuple(dict.fromkeys(authoritative))[:10],
        remediation_kind=remediation,
        confidence=confidence,
        limitations=tuple(limitations),
    )


def render_non_kb_assessment(assessment: NonKBVulScanAssessment) -> str:
    parts = [
        f"NonKBClassification={assessment.classification}",
        f"Confidence={assessment.confidence}",
        f"RecommendedRemediationClass={assessment.remediation_kind}",
        "CVEs=" + (",".join(assessment.cves) if assessment.cves else "none identified"),
        "MatchedInstalledSoftware="
        + ("; ".join(assessment.matched_software) if assessment.matched_software else "none confidently matched"),
    ]
    if assessment.authoritative_references:
        parts.append(
            "AuthoritativeReferences=" + "; ".join(assessment.authoritative_references)
        )
    elif assessment.scanner_references:
        parts.append("ScannerReferences=" + "; ".join(assessment.scanner_references))
    if assessment.limitations:
        parts.append("Limitations=" + " ".join(assessment.limitations))
    parts.append(
        "No endpoint modification is authorized by this assessment; use an existing separately approved remediation path or technician approval."
    )
    return " ".join(parts)
