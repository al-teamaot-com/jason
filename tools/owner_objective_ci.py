"""Required Main-push acceptance for the exact Owner-objective source."""
from datetime import datetime,timedelta,timezone
import re


def require_acceptance(api, candidate, *, now=None):
    if not isinstance(candidate,str) or not re.fullmatch("[0-9a-f]{40}",candidate):
        raise PermissionError("OBJECTIVE_EXACT_CI_SOURCE_REQUIRED")
    evidence=api("repos/al-teamaot-com/jason/actions/workflows/owner-objective-completion.yml/runs"
        "?head_sha="+candidate+"&event=push&per_page=100",
        "{total:.total_count,rows:[.workflow_runs[]|{name,sha:.head_sha,branch:.head_branch,event,status,conclusion,at:.updated_at}]}")
    rows=evidence.get("rows")
    if (type(evidence.get("total")) is not int or not isinstance(rows,list)
            or not 1<=len(rows)<=100 or evidence["total"]!=len(rows)):
        raise PermissionError("OBJECTIVE_CI_EVIDENCE_INCOMPLETE")
    relevant=[r for r in rows if r.get("sha")==candidate and r.get("branch")=="main" and r.get("event")=="push"]
    if len(relevant)!=1:
        raise PermissionError("OBJECTIVE_MAIN_CI_MISSING_OR_AMBIGUOUS")
    row=relevant[0]
    now=now or datetime.now(timezone.utc)
    at=datetime.fromisoformat(row["at"].replace("Z","+00:00"))
    if (row.get("name")!="Owner Objective Completion" or row.get("status")!="completed"
            or row.get("conclusion")!="success" or at.tzinfo is None
            or not now-timedelta(days=7)<=at<=now):
        raise PermissionError("OBJECTIVE_MAIN_CI_NOT_SUCCESSFUL_OR_FRESH")
    return True
