"""Pure multi-device VulScan child plan, reusing existing split runtime.

The source ticket's exact company, active CI and DRMM UID/hostname are checked
for every node. No provider action or mutation authority is created.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import re

from .autonomy_worker_runtime import OperationalAutonomyMaintenance
from .ticket_split_runtime import TicketSplitRequest, TicketSplitTarget, TicketSplitExecutor


class JsonVulscanSplitBoundaryError(RuntimeError):
    pass


def plan_json_vulscan_split(
    *,
    source_ticket: Mapping[str, Any],
    exact_client_id: str,
    ci_search_by_hostname: Mapping[str, Mapping[str, Any]],
    endpoint_read_by_uid: Mapping[str, Mapping[str, Any]],
) -> TicketSplitRequest:
    try:
        ticket_id = int(source_ticket["id"])
        company_id = int(source_ticket["companyID"])
        priority = int(source_ticket.get("priority") or 1)
    except (TypeError,ValueError,KeyError) as exc:
        raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_SOURCE_IDENTITY_INCOMPLETE") from exc
    number = str(source_ticket.get("ticketNumber") or "").strip()
    title = str(source_ticket.get("title") or "").strip()
    description = str(source_ticket.get("description") or "").strip()
    if (ticket_id <= 0 or company_id <= 0 or
        str(company_id) != exact_client_id or not number or
        not title or not description):
        raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_TICKET_SCOPE_CHANGED")
    nodes = OperationalAutonomyMaintenance._vulscan_affected_nodes(source_ticket)
    if not 2 <= len(nodes) <= 40:
        raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_TARGET_COUNT_INVALID")
    # Deployed source parser deduplicates; a duplicate in original VulScan
    # evidence is not permission to silently lose/overwrite a target.
    source_material = re.search(
        r"Affected Nodes:\s*(.+)", description, re.IGNORECASE | re.DOTALL)
    raw = re.findall(
        r"(?:Discovery Agent\s+)?([A-Za-z0-9_.-]+)\s*\([^)]*\)",
        source_material.group(1) if source_material else "",
        re.IGNORECASE,
    )
    if len(raw) != len(nodes) or len({x.casefold() for x in raw}) != len(raw):
        raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_DUPLICATE_NODE_IDENTITY")
    targets=[]
    used_ci=set()
    used_uid=set()
    for node in nodes:
        source=ci_search_by_hostname.get(node)
        if not isinstance(source, Mapping) or source.get("status") != "succeeded":
            raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_CI_READ_FAILED")
        evidence=source.get("evidence")
        data=evidence.get("data") if isinstance(evidence,Mapping) else None
        items=data.get("items") if isinstance(data,Mapping) else None
        if (not isinstance(items,list) or
            data.get("has_more") or data.get("next_cursor") or data.get("nextCursor") or
            (data.get("total_count") is not None and
             int(data["total_count"]) > len(items))):
            raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_CI_PAGE_INCOMPLETE")
        matches=[ci for ci in items
                 if isinstance(ci,Mapping) and
                 ci.get("isActive") is True and
                 str(ci.get("companyID"))==exact_client_id and
                 str(ci.get("rmmDeviceAuditHostname") or
                     ci.get("referenceTitle") or "").casefold()==node.casefold() and
                 str(ci.get("referenceNumber") or "").strip()]
        if len(matches)!=1:
            raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_CI_NOT_UNIQUE")
        ci=matches[0]
        try: ci_id=int(ci["id"])
        except (ValueError,TypeError,KeyError) as exc:
            raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_CI_ID_INVALID") from exc
        uid=str(ci.get("referenceNumber") or "").strip()
        if ci_id<=0 or not uid or ci_id in used_ci or uid.casefold() in used_uid:
            raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_TARGET_COLLISION")
        used_ci.add(ci_id);used_uid.add(uid.casefold())
        endpoint_result=endpoint_read_by_uid.get(uid)
        if (not isinstance(endpoint_result,Mapping) or
            endpoint_result.get("status")!="succeeded"):
            raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_ENDPOINT_READ_FAILED")
        out=endpoint_result.get("evidence")
        endpoint=out.get("record") if isinstance(out,Mapping) else None
        if (not isinstance(endpoint,Mapping) or
            str(endpoint.get("resource_id") or "")!=uid or
            str(endpoint.get("hostname") or "").casefold()!=node.casefold() or
            str(endpoint.get("companyID") or "") != exact_client_id):
            raise JsonVulscanSplitBoundaryError("VULSCAN_SPLIT_ENDPOINT_SCOPE_MISMATCH")
        targets.append(TicketSplitTarget(
            target_key=uid,
            title=f"{title} - {node}",
            description=(f"Target device: {node}\nTarget Datto UID: {uid}\n\n"
                         f"Original VulScan finding:\n{description}"),
            configuration_item_id=ci_id,
        ))
    return TicketSplitRequest(
        source_ticket_id=ticket_id,
        source_ticket_number=number,
        company_id=company_id,
        queue_id="Jason",
        priority=priority,
        status="New",
        issue_type=(
            int(source_ticket["issueType"])
            if source_ticket.get("issueType") else None),
        sub_issue_type=(
            int(source_ticket["subIssueType"])
            if source_ticket.get("subIssueType") else None),
        ticket_type=(
            int(source_ticket["ticketType"])
            if source_ticket.get("ticketType") else None),
        targets=tuple(targets),
    )
