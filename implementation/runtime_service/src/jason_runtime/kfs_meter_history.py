from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from kernel.resolution import CapabilityResolutionResult
from orchestrator.contracts import OrchestrationRequest
from orchestrator.print_capability_catalog import (
    KYOCERA_KFS_PROVIDER,
    PRINT_METER_HISTORY_SEARCH,
    PRINT_METER_USAGE_READ,
)
from orchestrator.service import InvocationResult


DEFAULT_COUNTERS = (
    "total",
    "blackWhite",
    "color",
    "printerTotal",
    "printerBw",
    "printerColorTotal",
    "copierTotal",
    "copierBw",
    "copierColorTotal",
    "scanTotal",
)


def _load_password(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("KFS history database password file is empty")
    return value
@dataclass(frozen=True, slots=True)
class KfsMeterHistoryStore:
    host: str
    port: int
    database: str
    user: str
    password_file: Path
    connect_timeout_seconds: int = 5

    def _connect(self):
        try:
            import psycopg
        except Exception as exc:
            raise RuntimeError("KFS history reads require psycopg") from exc
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=_load_password(self.password_file),
            connect_timeout=self.connect_timeout_seconds,
            options="-c default_transaction_read_only=on",
        )

    @staticmethod
    def _selector(arguments: Mapping[str, Any]) -> tuple[str, str]:
        serial = str(arguments.get("serial_number") or "").strip()
        device = str(
            arguments.get("device_id") or arguments.get("resource_id") or ""
        ).strip()
        if serial:
            return "serial_number", serial
        if device:
            return "device_id", device
        raise ValueError("serial_number, device_id, or resource_id is required")

    @staticmethod
    def _counter_names(arguments: Mapping[str, Any]) -> tuple[str, ...]:
        raw = arguments.get("counters")
        if raw in (None, "", []):
            return DEFAULT_COUNTERS
        if isinstance(raw, str):
            values = tuple(item.strip() for item in raw.split(",") if item.strip())
        elif isinstance(raw, (list, tuple)):
            values = tuple(str(item).strip() for item in raw if str(item).strip())
        else:
            raise ValueError("counters must be a comma-separated string or list")
        if not values or len(values) > 32:
            raise ValueError("counters must contain between 1 and 32 names")
        return values
    def search(
        self,
        *,
        arguments: Mapping[str, Any],
        start: datetime,
        end: datetime,
    ) -> Mapping[str, Any]:
        selector_name, selector_value = self._selector(arguments)
        counters = self._counter_names(arguments)
        limit = int(arguments.get("limit") or 500)
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")

        sql = f"""
            SELECT reading_at, device_id, serial_number, equipment_id,
                   customer_id, customer_name, counter_name, counter_value
            FROM kfs_meter_readings
            WHERE {selector_name} = %s
              AND reading_at >= %s
              AND reading_at < %s
              AND counter_name = ANY(%s)
            ORDER BY reading_at ASC, counter_name ASC
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (selector_value, start, end, list(counters), limit))
                rows = cur.fetchall()

        return {
            "selector": {selector_name: selector_value},
            "start": start.isoformat(),
            "end": end.isoformat(),
            "counters": list(counters),
            "readings": [
                {
                    "reading_at": row[0].isoformat(),
                    "device_id": row[1],
                    "serial_number": row[2],
                    "equipment_id": row[3],
                    "customer_id": row[4],
                    "customer_name": row[5],
                    "counter_name": row[6],
                    "counter_value": row[7],
                }
                for row in rows
            ],
            "count": len(rows),
        }
    def usage(
        self,
        *,
        arguments: Mapping[str, Any],
        start: datetime,
        end: datetime,
    ) -> Mapping[str, Any]:
        selector_name, selector_value = self._selector(arguments)
        counters = self._counter_names(arguments)
        boundary_hours = int(arguments.get("boundary_hours") or 36)
        if boundary_hours < 1 or boundary_hours > 168:
            raise ValueError("boundary_hours must be between 1 and 168")
        sql = f"""
            WITH wanted(counter_name) AS (
                SELECT unnest(%s::text[])
            )
            SELECT w.counter_name,
                   b.counter_value, b.reading_at,
                   e.counter_value, e.reading_at,
                   COALESCE(e.device_id, b.device_id),
                   COALESCE(e.serial_number, b.serial_number),
                   COALESCE(e.equipment_id, b.equipment_id),
                   COALESCE(e.customer_id, b.customer_id),
                   COALESCE(e.customer_name, b.customer_name)
            FROM wanted w
            LEFT JOIN LATERAL (
                SELECT m.counter_value, m.reading_at, m.device_id,
                       m.serial_number, m.equipment_id, m.customer_id,
                       m.customer_name
                FROM kfs_meter_readings m
                WHERE m.{selector_name} = %s
                  AND m.counter_name = w.counter_name
                  AND m.reading_at BETWEEN %s - (%s * interval '1 hour')
                                       AND %s + (%s * interval '1 hour')
                ORDER BY ABS(EXTRACT(EPOCH FROM (m.reading_at - %s))) ASC,
                         CASE WHEN m.reading_at <= %s THEN 0 ELSE 1 END ASC
                LIMIT 1
            ) b ON TRUE
            LEFT JOIN LATERAL (
                SELECT m.counter_value, m.reading_at, m.device_id,
                       m.serial_number, m.equipment_id, m.customer_id,
                       m.customer_name
                FROM kfs_meter_readings m
                WHERE m.{selector_name} = %s
                  AND m.counter_name = w.counter_name
                  AND m.reading_at BETWEEN %s - (%s * interval '1 hour')
                                       AND %s + (%s * interval '1 hour')
                ORDER BY ABS(EXTRACT(EPOCH FROM (m.reading_at - %s))) ASC,
                         CASE WHEN m.reading_at <= %s THEN 0 ELSE 1 END ASC
                LIMIT 1
            ) e ON TRUE
            ORDER BY w.counter_name
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        list(counters),
                        selector_value, start, boundary_hours, start, boundary_hours, start, start,
                        selector_value, end, boundary_hours, end, boundary_hours, end, end,
                    ),
                )
                rows = cur.fetchall()
        deltas: dict[str, int | None] = {}
        boundaries: dict[str, Mapping[str, Any]] = {}
        identity: dict[str, Any] = {}
        warnings: list[str] = []
        for row in rows:
            name, before, before_at, after, after_at = row[:5]
            if not identity and any(row[5:]):
                identity = {
                    "device_id": row[5],
                    "serial_number": row[6],
                    "equipment_id": row[7],
                    "customer_id": row[8],
                    "customer_name": row[9],
                }
            delta = None
            if before is not None and after is not None:
                candidate = int(after) - int(before)
                if candidate >= 0:
                    delta = candidate
                else:
                    warnings.append(
                        f"{name} decreased across the period; possible meter reset/replacement"
                    )
            else:
                warnings.append(f"{name} lacks a complete period boundary")
            deltas[name] = delta
            boundaries[name] = {
                "start_value": before,
                "start_reading_at": before_at.isoformat() if before_at else None,
                "end_value": after,
                "end_reading_at": after_at.isoformat() if after_at else None,
            }

        return {
            "selector": {selector_name: selector_value},
            "device": identity,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "counter_deltas": deltas,
            "boundary_readings": boundaries,
            "usage": {
                "total_impressions": deltas.get("total"),
                "black_white_impressions": deltas.get("blackWhite"),
                "color_impressions": deltas.get("color"),
                "printer_impressions": deltas.get("printerTotal"),
                "copier_impressions": deltas.get("copierTotal"),
                "scans": deltas.get("scanTotal"),
            },
            "warnings": warnings,
        }
def resolve_period(arguments: Mapping[str, Any]) -> tuple[datetime, datetime]:
    month = str(arguments.get("month") or "").strip()
    timezone_name = str(arguments.get("timezone") or "America/New_York").strip()
    tz = ZoneInfo(timezone_name)

    if month:
        try:
            year_text, month_text = month.split("-", 1)
            year = int(year_text)
            month_number = int(month_text)
            start_local = datetime(year, month_number, 1, tzinfo=tz)
        except (ValueError, TypeError) as exc:
            raise ValueError("month must use YYYY-MM format") from exc
        if month_number == 12:
            end_local = datetime(year + 1, 1, 1, tzinfo=tz)
        else:
            end_local = datetime(year, month_number + 1, 1, tzinfo=tz)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    start_text = str(arguments.get("start") or arguments.get("period_start") or "").strip()
    end_text = str(arguments.get("end") or arguments.get("period_end") or "").strip()
    if not start_text or not end_text:
        raise ValueError("month or explicit start/end period is required")
    start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_text.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    if end.tzinfo is None:
        end = end.replace(tzinfo=tz)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    if end <= start:
        raise ValueError("period end must be after period start")
    return start, end
@dataclass(frozen=True, slots=True)
class GovernedKfsMeterHistoryInvoker:
    store: KfsMeterHistoryStore

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if request.permission_mode != "observe":
            raise PermissionError("KFS meter history capabilities are read-only")
        if resolution.selected_provider_id != KYOCERA_KFS_PROVIDER:
            raise PermissionError("KFS meter history resolved to an unexpected provider")
        if request.organization_id != "aot" or request.client_id is not None:
            raise PermissionError(
                "KFS meter history is currently AOT-internal organization-wide only"
            )
        if request.capability_name != resolution.capability_name:
            raise ValueError("resolved KFS meter history capability does not match request")

        start, end = resolve_period(request.arguments)
        if resolution.capability_name == PRINT_METER_HISTORY_SEARCH:
            data = self.store.search(arguments=request.arguments, start=start, end=end)
        elif resolution.capability_name == PRINT_METER_USAGE_READ:
            data = self.store.usage(arguments=request.arguments, start=start, end=end)
        else:
            raise LookupError(
                f"unsupported KFS meter history capability: {resolution.capability_name}"
            )

        return InvocationResult(
            output={
                "provider": KYOCERA_KFS_PROVIDER,
                "provider_capability": resolution.capability_name,
                "data": data,
                "evidence_ids": (),
                "warnings": tuple(data.get("warnings", ())),
            },
            attempts=1,
        )
