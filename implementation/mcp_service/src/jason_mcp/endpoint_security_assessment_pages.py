"""Sanitized, page-bounded findings from a fully governed Datto job read.

This module is a *projection*, not a provider client or authorization layer.
The caller MUST execute Datto's existing automation.job.output.read capability
through Central Orchestrator with exact job, device, component and read authority
before passing its internal result here. Raw stdout never leaves that boundary.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

_COMPONENT = "8ff72744-cb29-4cad-a11b-7a1c2a199f06"
_MAX_RECORDS = 300
_MAX_CHARS = 65536
_MAX_PAGE = 25
_TEXT_LIMITS = {"name": 160, "path": 512, "category": 80, "title": 300}


class FindingPageError(ValueError):
    pass


def _safe_string(value: Any, *, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise FindingPageError("FINDING_TEXT_INVALID_OR_UNBOUNDED")
    if any(ord(ch) < 32 for ch in value):
        raise FindingPageError("FINDING_CONTROL_CHARACTERS_REJECTED")
    return value


def project_finding_page(
    output: Mapping[str, Any], *, job_uid: str, device_uid: str,
    component_uid: str, hostname: str, page_index: int, page_size: int = 15,
) -> Mapping[str, Any]:
    """Only a validated findings array is shown; never raw command lines."""
    if (component_uid != _COMPONENT or
        not all((job_uid.strip(),device_uid.strip(),hostname.strip()))):
        raise FindingPageError("EXACT_COMPONENT_DEVICE_JOB_REQUIRED")
    if (type(page_index) is not int or page_index < 0 or
        type(page_size) is not int or not 1 <= page_size <= _MAX_PAGE):
        raise FindingPageError("PAGE_BOUND_INVALID")
    envelope = output.get("data") if isinstance(output, Mapping) else None
    if not isinstance(envelope, Mapping):
        raise FindingPageError("DATTO_NORMALIZED_OUTPUT_UNAVAILABLE")
    # Central Orchestrator's provider-neutral output is commonly wrapped as
    # data.provider_data. The governed-read API presents a flattened view.
    # Support both and reject contradictions if both layers bind selectors.
    data = envelope.get("provider_data")
    if not isinstance(data, Mapping):
        data = envelope
    selectors = (
        ("resource_id", job_uid), ("device_uid", device_uid),
        ("component_uid", component_uid), ("stream", "stdout"),
    )
    if any(data.get(key) != val for key, val in selectors):
        raise FindingPageError("DATTO_JOB_OUTPUT_SELECTOR_MISMATCH")
    if data is not envelope and any(
        key in envelope and envelope[key] != val
        for key, val in selectors
    ):
        raise FindingPageError("DATTO_OUTPUT_ENVELOPE_SELECTOR_CONFLICT")
    if data.get("output_bounded") is True or data.get("match_count") != 1:
        raise FindingPageError("PROVIDER_OUTPUT_INCOMPLETE")
    outputs = data.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 1:
        raise FindingPageError("EXACT_PROVIDER_OUTPUT_REQUIRED")
    record = outputs[0]
    if (not isinstance(record, Mapping)
        or record.get("component_uid") != component_uid
        or record.get("stream") != "stdout"
        or record.get("truncated") is True):
        raise FindingPageError("OUTPUT_COMPONENT_OR_STREAM_MISMATCH")
    full_text = record.get("text")
    if not isinstance(full_text, str) or len(full_text)>_MAX_CHARS:
        raise FindingPageError("OUTPUT_TYPE_OR_SIZE_INVALID")
    start_marker="AOT_SECURITY_JSON_BEGIN"
    end_marker="AOT_SECURITY_JSON_END"
    if full_text.count(start_marker)!=1 or full_text.count(end_marker)!=1:
        raise FindingPageError("FULL_JSON_END_MARKER_REQUIRED")
    serialized=full_text.split(start_marker,1)[1].split(end_marker,1)[0].strip()
    try:
        report=json.loads(serialized)
    except (ValueError,TypeError) as exc:
        raise FindingPageError("FULL_JSON_PARSE_ERROR") from exc
    if (not isinstance(report, Mapping)
        or report.get("schema_version") != "1.0"
        or report.get("read_only") is not True
        or str(report.get("computer") or "").casefold() != hostname.casefold()):
        raise FindingPageError("SCANNER_REPORT_CONTRACT_OR_HOSTNAME_MISMATCH")
    findings=report.get("findings")
    summary=report.get("summary")
    if (not isinstance(findings,list) or not isinstance(summary,Mapping)
        or len(findings)>_MAX_RECORDS or summary.get("omitted_findings") != 0):
        raise FindingPageError("FINDINGS_OMITTED_OR_NOT_BOUNDED")
    counts={
        "High":summary.get("high"),"Medium":summary.get("medium"),
        "Low":summary.get("low"),"Info":summary.get("info"),
    }
    if any(type(n) is not int or n < 0 for n in counts.values()):
        raise FindingPageError("INVALID_SEVERITY_COUNTS")
    if sum(counts.values()) != len(findings):
        raise FindingPageError("FULL_FINDING_COUNT_CONFLICT")
    normalized=[]
    observed={key:0 for key in counts}
    for entry in findings:
        if not isinstance(entry, Mapping):
            raise FindingPageError("FINDING_NOT_STRUCTURED")
        severity=entry.get("severity")
        if severity not in counts:
            raise FindingPageError("UNEXPECTED_FINDING_SEVERITY")
        item={"severity":severity}
        for key,limit in _TEXT_LIMITS.items():
            val=entry.get(key)
            if key=="path" and not val:
                item[key]=""
                continue
            item[key]=_safe_string(val,limit=limit)
        observed[severity]+=1
        normalized.append(item)
    if observed!=counts:
        raise FindingPageError("SEVERITY_DISTRIBUTION_CONFLICT")
    first=page_index*page_size
    if first > len(normalized):
        raise FindingPageError("PAGE_BEYOND_COLLECTION")
    page=normalized[first:first+page_size]
    normalized_serial=json.dumps(normalized,sort_keys=True,separators=(",",":"),ensure_ascii=True)
    return {
        "status":"succeeded",
        "job_uid":job_uid,"device_uid":device_uid,
        "component_uid":component_uid,"hostname":hostname,
        "page_index":page_index,"page_size":page_size,
        "total_findings":len(normalized),
        "severity_counts":counts,
        "full_list_sha256":sha256(normalized_serial.encode("utf-8")).hexdigest(),
        "findings":page,
        "complete":first+len(page)==len(normalized),
        "source":"governed_datto_terminal_job_full_structured_report",
    }
