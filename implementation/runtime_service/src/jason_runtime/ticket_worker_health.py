"""Container health check for the independent PMv4 Ticket Core."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from .autonomy_worker_supervisor import read_worker_heartbeat

def _parse(value: object) -> datetime | None:
    text=str(value or "").strip()
    if not text:
        return None
    try:
        item=datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError:
        return None
    if item.tzinfo is None:
        item=item.replace(tzinfo=timezone.utc)
    return item.astimezone(timezone.utc)

def status(*, db: Path, interval_seconds: int,
           now: datetime | None = None) -> dict[str, object]:
    heartbeat=read_worker_heartbeat(db)
    if heartbeat is None:
        return {"status":"degraded","reason":"heartbeat_missing"}
    current=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if bool(heartbeat.get("scan_in_progress")):
        started=_parse(heartbeat.get("last_started_at"))
        if started is None:
            return {"status":"degraded","reason":"scan_started_at_invalid"}
        age=(current-started).total_seconds()
        limit=max(300,int(interval_seconds)*5)
        if 0 <= age <= limit:
            return {"status":"ok","reason":"scan_in_progress","age_seconds":age}
        return {"status":"degraded","reason":"scan_stalled","age_seconds":age}
    completed=_parse(heartbeat.get("last_completed_at"))
    if completed is None:
        return {"status":"degraded","reason":"completion_missing"}
    age=(current-completed).total_seconds()
    limit=max(180,int(interval_seconds)*3)
    if 0 <= age <= limit:
        return {"status":"ok","reason":"recent_completed_scan","age_seconds":age}
    return {"status":"degraded","reason":"completion_stale","age_seconds":age}

def main() -> int:
    db=Path(os.getenv(
        "JASON_AUTONOMY_WORKER_DB",
        "/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3",
    ))
    try:
        interval=int(os.getenv("JASON_AUTONOMY_WORKER_INTERVAL_SECONDS","60"))
    except ValueError:
        return 2
    result=status(db=db,interval_seconds=interval)
    if result["status"]=="ok":
        print("TICKET_CORE_HEALTH=PASS")
        return 0
    print("TICKET_CORE_HEALTH=FAIL reason="+str(result.get("reason","unknown")))
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
