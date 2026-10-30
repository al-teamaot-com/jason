from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from kernel.identity_authority import AuthorityGrant, PermissionMode
from kernel.resolution import CapabilityResolutionResult
from orchestrator.contracts import OrchestrationRequest
from orchestrator.print_capability_catalog import (
    KYOCERA_KFS_PROVIDER,
    PRINT_METER_HISTORY_SEARCH,
    PRINT_METER_USAGE_READ,
    PRINT_FLEET_USAGE_RANK,
)
from orchestrator.service import InvocationResult


METER_HISTORY_AUTHORITY_GRANTS = (
    ("production-kfs-read-print-meter-history-search", PRINT_METER_HISTORY_SEARCH),
    ("production-kfs-read-print-meter-usage-read", PRINT_METER_USAGE_READ),
    ("production-kfs-read-print-fleet-usage-rank", PRINT_FLEET_USAGE_RANK),
)


def ensure_meter_history_read_authority(identity_authority, *, enabled: bool) -> tuple[str, ...]:
    """Seed the same AOT organization-wide observe authority as current KFS reads."""
    if not enabled:
        return ()
    created: list[str] = []
    for grant_id, capability in METER_HISTORY_AUTHORITY_GRANTS:
        grant = AuthorityGrant(
            grant_id=grant_id,
            subject_id="organization:aot",
            capability=capability,
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.OBSERVE,
            approval_required=False,
            status="active",
        )
        existing = identity_authority.grants.get(grant.grant_id)
        if existing is None:
            identity_authority.grants.put(grant)
            created.append(grant.grant_id)
        elif existing != grant:
            raise RuntimeError(
                f"KFS meter-history authority grant conflicts: {grant.grant_id}"
            )
    return tuple(created)


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

    def fleet_rank(
        self, *, arguments: Mapping[str, Any], start: datetime, end: datetime,
    ) -> Mapping[str, Any]:
        """Rank observed print impressions against the last completed KFS inventory.

        KFS keeps historical devices indefinitely, so using all meter history as the
        inventory produces false top-five results. A complete report requires an
        inventory from one successful recent collector run, every inventoried
        device accounted for, and valid deltas for all those devices.
        """
        limit = int(arguments.get("limit") or 5)
        hours = int(arguments.get("boundary_hours") or 36)
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not 1 <= hours <= 168:
            raise ValueError("boundary_hours must be between 1 and 168")

        sql = """
            WITH latest_snapshot AS (
                SELECT id, ended_at, device_count, error_count
                FROM kfs_runs
                WHERE status = 'ok' AND ended_at IS NOT NULL AND ended_at <= %s
                ORDER BY ended_at DESC
                LIMIT 1
            ), devices AS (
                SELECT DISTINCT s.device_id,
                       NULLIF(k.customer_name,'') AS inventory_customer,
                       NULLIF(k.equipment_id,'') AS inventory_equipment,
                       NULLIF(k.serial_number,'') AS inventory_serial
                FROM kfs_device_status_readings s
                JOIN latest_snapshot r ON s.run_id = r.id
                LEFT JOIN kfs_devices k ON k.device_id = s.device_id
                WHERE s.device_id IS NOT NULL AND s.device_id <> ''
            ), boundaries AS (
                SELECT d.device_id, counter.counter_name,
                       b.counter_value AS start_value, b.reading_at AS start_at,
                       e.counter_value AS end_value, e.reading_at AS end_at,
                       COALESCE(NULLIF(e.customer_name,''), NULLIF(b.customer_name,''), d.inventory_customer) AS customer_name,
                       COALESCE(NULLIF(e.equipment_id,''), NULLIF(b.equipment_id,''), d.inventory_equipment) AS equipment_id,
                       COALESCE(NULLIF(e.serial_number,''), NULLIF(b.serial_number,''), d.inventory_serial) AS serial_number
                FROM devices d
                CROSS JOIN (VALUES ('total'),('blackWhite'),('color')) counter(counter_name)
                LEFT JOIN LATERAL (
                    SELECT counter_value, reading_at, customer_name, equipment_id, serial_number
                    FROM kfs_meter_readings m
                    WHERE m.device_id=d.device_id AND m.counter_name=counter.counter_name
                      AND reading_at BETWEEN %s - (%s * interval '1 hour')
                                         AND %s + (%s * interval '1 hour')
                    ORDER BY ABS(EXTRACT(EPOCH FROM (reading_at-%s))), reading_at
                    LIMIT 1
                ) b ON TRUE
                LEFT JOIN LATERAL (
                    SELECT counter_value, reading_at, customer_name, equipment_id, serial_number
                    FROM kfs_meter_readings m
                    WHERE m.device_id=d.device_id AND m.counter_name=counter.counter_name
                      AND reading_at BETWEEN %s - (%s * interval '1 hour')
                                         AND %s + (%s * interval '1 hour')
                    ORDER BY ABS(EXTRACT(EPOCH FROM (reading_at-%s))), reading_at
                    LIMIT 1
                ) e ON TRUE
            )
            SELECT b.device_id, b.counter_name, b.start_value, b.start_at,
                   b.end_value, b.end_at, b.customer_name, b.equipment_id, b.serial_number,
                   r.id, r.ended_at, r.device_count, r.error_count,
                   (SELECT COUNT(*) FROM devices)
            FROM latest_snapshot r
            LEFT JOIN boundaries b ON TRUE
            ORDER BY b.device_id, b.counter_name
        """
        params = (
            end, start, hours, start, hours, start,
            end, hours, end, hours, end,
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        devices: dict[str, dict[str, Any]] = {}
        snapshot_id = None
        snapshot_ended_at = None
        reported_count = None
        snapshot_errors = None
        inventory_count = 0
        for row in rows:
            device_id, counter, before, before_at, after, after_at, customer, equipment, serial = row[:9]
            run_id, run_ended_at, run_count, run_errors, inventory_count = row[9:]
            snapshot_id = run_id
            snapshot_ended_at = run_ended_at
            reported_count = run_count
            snapshot_errors = run_errors
            if not device_id:
                continue
            item = devices.setdefault(device_id, {
                "device_id": device_id,
                "customer": customer or "Unknown (not mapped in KFS)",
                "customer_mapping_verified": bool(customer),
                "printer_id": equipment or serial or device_id,
                "counts": {}, "latest_reading_at": None, "warnings": [],
            })
            delta = None
            if (before is not None and after is not None
                    and before_at is not None and after_at is not None):
                difference = int(after) - int(before)
                if difference >= 0 and after_at > before_at:
                    delta = difference
                else:
                    item["warnings"].append(f"{counter}: invalid or reset meter boundary")
            else:
                item["warnings"].append(f"{counter}: missing meter boundary")
            item["counts"][counter] = delta
            if after_at is not None and (
                item["latest_reading_at"] is None or after_at > item["latest_reading_at"]
            ):
                item["latest_reading_at"] = after_at

        ranked: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []
        for item in devices.values():
            counts = item.pop("counts")
            item["black_white_pages"] = counts.get("blackWhite")
            item["total_pages"] = counts.get("total")
            color = counts.get("color")
            # Some monochrome printers do not expose a color counter. When
            # independently measured total and B&W usage are identical, a zero
            # color delta is mathematically determined, not estimated.
            if (
                color is None
                and "color: missing meter boundary" in item["warnings"]
                and item["total_pages"] is not None
                and item["black_white_pages"] is not None
                and item["total_pages"] == item["black_white_pages"]
            ):
                color = 0
                item["color_counter_status"] = "zero_verified_from_total_and_bw"
                item["warnings"].remove("color: missing meter boundary")
            else:
                item["color_counter_status"] = "measured" if color is not None else "unavailable"
            item["color_pages"] = color
            if None in (item["black_white_pages"], item["color_pages"], item["total_pages"]):
                exceptions.append(item)
            elif item["black_white_pages"] + item["color_pages"] != item["total_pages"]:
                item["warnings"].append("B&W plus color differs from total")
                exceptions.append(item)
            else:
                ranked.append(item)
        ranked.sort(key=lambda item: (-item["total_pages"], item["device_id"]))
        for item in ranked + exceptions:
            if item["latest_reading_at"] is not None:
                item["latest_reading_at"] = item["latest_reading_at"].isoformat()

        warnings: list[str] = []
        if snapshot_id is None or snapshot_ended_at is None:
            warnings.append("No successful KFS collection snapshot exists for the reporting period")
        elif end - snapshot_ended_at > timedelta(hours=36):
            warnings.append("Latest successful KFS inventory snapshot is stale")
        if snapshot_errors is None or snapshot_errors != 0:
            warnings.append("KFS inventory collection contains errors or lacks an error count")
        if reported_count is None or int(reported_count) != inventory_count:
            warnings.append("KFS reported device count differs from inventory records")
        if inventory_count != len(devices):
            warnings.append("Inventoried devices are missing from the meter comparison")
        if exceptions:
            warnings.append("Missing, reset, or inconsistent monthly meters for some printers")
        customer_mapping_missing_count = sum(
            not item["customer_mapping_verified"] for item in ranked + exceptions
        )
        color_zero_verified_count = sum(
            item["color_counter_status"] == "zero_verified_from_total_and_bw"
            for item in ranked + exceptions
        )
        if customer_mapping_missing_count:
            warnings.append(
                f"KFS customer assignments missing for {customer_mapping_missing_count} managed printers"
            )
        if any(not item["customer_mapping_verified"] for item in ranked[:limit]):
            warnings.append("A ranked printer is missing its customer assignment in KFS")

        coverage_verified = (
            snapshot_id is not None and snapshot_ended_at is not None
            and timedelta(0) <= end - snapshot_ended_at <= timedelta(hours=36)
            and snapshot_errors == 0 and reported_count is not None
            and int(reported_count) == inventory_count == len(devices)
        )
        return {
            "report_type": "ranked_monthly_usage",
            "schema_version": "1.0",
            "period_start": start.isoformat(), "period_end": end.isoformat(),
            "inventory_run_id": str(snapshot_id) if snapshot_id is not None else None,
            "inventory_reading_at": snapshot_ended_at.isoformat() if snapshot_ended_at else None,
            "fleet_devices_reported": reported_count,
            "fleet_devices_in_inventory": inventory_count,
            "fleet_devices_in_history": len(devices),
            "eligible_devices": len(ranked), "exception_count": len(exceptions),
            "customer_mapping_missing_count": customer_mapping_missing_count,
            "color_zero_verified_count": color_zero_verified_count,
            "top_devices": ranked[:limit], "exceptions": exceptions,
            "coverage_verified": coverage_verified,
            "complete": (
                coverage_verified and not exceptions
                and all(item["customer_mapping_verified"] for item in ranked[:limit])
            ),
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
        elif resolution.capability_name == PRINT_FLEET_USAGE_RANK:
            # Month-to-date rankings must not request future month-end readings.
            # Historical closed months retain their exact full-month boundary.
            now = datetime.now(timezone.utc)
            if start >= now:
                raise ValueError("fleet usage ranking period must have started")
            effective_end = min(end, now)
            data = self.store.fleet_rank(
                arguments=request.arguments, start=start, end=effective_end,
            )
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
