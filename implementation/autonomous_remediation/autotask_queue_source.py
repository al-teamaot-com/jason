"""Autotask queue discovery adapter for the autonomous work scheduler.

The adapter performs governed reads only. Queue/status/priority IDs are resolved
from live Autotask field metadata so ticket selection does not depend on stale
numeric constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .autonomous_queue_worker import QueueCandidate


SERVICE_ENTITY_FIELDS_DESCRIBE = "service.entity.fields.describe"
SERVICE_TICKET_SEARCH = "service.ticket.search"


class GovernedReadPort(Protocol):
    def execute(self, capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class AutotaskQueueDiscoveryConfig:
    owned_queue_labels: tuple[str, ...] = ("Jason",)
    discovery_queue_labels: tuple[str, ...] = (
        "Help Desk I",
        "Help Desk II",
        "Monitoring Alert",
        "Client Portal",
    )
    owned_status_labels: tuple[str, ...] = (
        "New",
        "In Progress",
        "Updated by Email",
        "Updated by Email - Client",
        "Updated by AOT",
        "Emergency",
    )
    discovery_status_labels: tuple[str, ...] = ("New", "Emergency")
    page_size: int = 100
    allow_assigned_discovery: bool = False
    owned_resource_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 500:
            raise ValueError("page_size must be between 1 and 500")


class AutotaskQueueSource:
    def __init__(
        self,
        *,
        reads: GovernedReadPort,
        config: AutotaskQueueDiscoveryConfig | None = None,
    ) -> None:
        self.reads = reads
        self.config = config or AutotaskQueueDiscoveryConfig()
        self._queue_ids: dict[str, int] | None = None
        self._priority_scores: dict[int, int] | None = None
        self._critical_priority_ids: set[int] | None = None

    def reconcile_candidates(self) -> Sequence[QueueCandidate]:
        self._ensure_metadata()
        assert self._queue_ids is not None
        assert self._priority_scores is not None
        assert self._critical_priority_ids is not None

        candidates: dict[str, QueueCandidate] = {}
        for queue_label in self.config.owned_queue_labels:
            queue_id = self._required_queue_id(queue_label)
            self._collect(
                candidates,
                queue_label=queue_label,
                queue_id=queue_id,
                status_labels=self.config.owned_status_labels,
                owned=True,
            )

        for queue_label in self.config.discovery_queue_labels:
            queue_id = self._required_queue_id(queue_label)
            self._collect(
                candidates,
                queue_label=queue_label,
                queue_id=queue_id,
                status_labels=self.config.discovery_status_labels,
                owned=False,
            )

        return tuple(candidates[key] for key in sorted(candidates, key=lambda value: int(value)))

    def _collect(
        self,
        candidates: dict[str, QueueCandidate],
        *,
        queue_label: str,
        queue_id: int,
        status_labels: tuple[str, ...],
        owned: bool,
    ) -> None:
        for status_label in status_labels:
            result = self.reads.execute(
                SERVICE_TICKET_SEARCH,
                {
                    "status": status_label,
                    "filters": {"queueID": queue_id},
                    "page_size": self.config.page_size,
                },
            )
            items = self._items(result)
            for ticket in items:
                ticket_id = self._positive_int(ticket.get("id"), "ticket id")
                if not owned and not self.config.allow_assigned_discovery:
                    assigned = self._assigned_resource_id(ticket.get("assignedResourceID"))
                    if assigned is not None and assigned not in self.config.owned_resource_ids:
                        continue
                priority_id = self._positive_int(ticket.get("priority"), "priority id")
                priority_score = self._priority_scores.get(priority_id, 0)
                source_version = str(
                    ticket.get("lastTrackedModificationDateTime")
                    or ticket.get("lastActivityDate")
                    or ""
                ).strip() or None
                urgent = (
                    priority_id in self._critical_priority_ids
                    or status_label.strip().casefold() == "emergency"
                )
                candidate = QueueCandidate(
                    resource_id=str(ticket_id),
                    priority=priority_score,
                    source_queue=queue_label,
                    owned_by_jason=(owned or self._assigned_resource_id(ticket.get("assignedResourceID")) in self.config.owned_resource_ids),
                    urgent=urgent,
                    source_version=source_version,
                    context=dict(ticket),
                )
                prior = candidates.get(candidate.resource_id)
                if prior is None or candidate.priority > prior.priority:
                    candidates[candidate.resource_id] = candidate

    def _ensure_metadata(self) -> None:
        if self._queue_ids is not None and self._priority_scores is not None:
            return
        result = self.reads.execute(
            SERVICE_ENTITY_FIELDS_DESCRIBE,
            {"entity": "Tickets"},
        )
        fields = self._fields(result)
        by_name = {
            str(item.get("name") or "").strip(): item
            for item in fields
            if isinstance(item, Mapping)
        }
        queue_field = by_name.get("queueID")
        priority_field = by_name.get("priority")
        if not isinstance(queue_field, Mapping) or not isinstance(priority_field, Mapping):
            raise ValueError("Autotask ticket queue/priority metadata is incomplete")

        self._queue_ids = self._active_picklist_map(queue_field)
        self._priority_scores = self._priority_score_map(priority_field)
        self._critical_priority_ids = self._priority_ids_for_label(priority_field, "Critical")

    def _required_queue_id(self, label: str) -> int:
        assert self._queue_ids is not None
        if label not in self._queue_ids:
            raise ValueError(f"Autotask queue is missing or inactive: {label}")
        return self._queue_ids[label]

    @staticmethod
    def _active_picklist_map(field: Mapping[str, Any]) -> dict[str, int]:
        values = field.get("picklistValues")
        if not isinstance(values, list):
            raise ValueError("Autotask picklist metadata is invalid")
        result: dict[str, int] = {}
        for item in values:
            if not isinstance(item, Mapping) or item.get("isActive") is False:
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            value = AutotaskQueueSource._positive_int(item.get("value"), "picklist value")
            if label in result and result[label] != value:
                raise ValueError(f"Autotask picklist label is ambiguous: {label}")
            result[label] = value
        return result

    @staticmethod
    def _priority_ids_for_label(field: Mapping[str, Any], label: str) -> set[int]:
        values = field.get("picklistValues")
        if not isinstance(values, list):
            raise ValueError("Autotask priority metadata is invalid")
        matches = {
            AutotaskQueueSource._positive_int(item.get("value"), "priority value")
            for item in values
            if isinstance(item, Mapping)
            and item.get("isActive") is not False
            and str(item.get("label") or "").strip().casefold() == label.casefold()
        }
        if len(matches) != 1:
            raise ValueError(f"Autotask priority label is missing or ambiguous: {label}")
        return matches

    @staticmethod
    def _priority_score_map(field: Mapping[str, Any]) -> dict[int, int]:
        values = field.get("picklistValues")
        if not isinstance(values, list):
            raise ValueError("Autotask priority metadata is invalid")
        result: dict[int, int] = {}
        for item in values:
            if not isinstance(item, Mapping) or item.get("isActive") is False:
                continue
            value = AutotaskQueueSource._positive_int(item.get("value"), "priority value")
            sort_order = AutotaskQueueSource._positive_int(item.get("sortOrder"), "priority sort order")
            # Lower Autotask sort order is higher operational priority. Normalize
            # to a provider-neutral score where larger means more important.
            result[value] = 10_000 - sort_order
        return result

    @staticmethod
    def _assigned_resource_id(value: Any) -> int | None:
        if value is None or value == "" or isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("assignedResourceID must be a positive integer when present") from exc
        if parsed < 1:
            raise ValueError("assignedResourceID must be a positive integer when present")
        return parsed

    @staticmethod
    def _positive_int(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{label} must be a positive integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a positive integer") from exc
        if parsed < 1:
            raise ValueError(f"{label} must be a positive integer")
        return parsed

    @staticmethod
    def _data(result: Mapping[str, Any]) -> Mapping[str, Any]:
        if str(result.get("status") or "") != "succeeded":
            raise RuntimeError(
                f"governed Autotask read failed: {result.get('error_code') or result.get('reason_codes')}"
            )
        evidence = result.get("evidence")
        data = evidence.get("data") if isinstance(evidence, Mapping) else None
        if not isinstance(data, Mapping):
            raise RuntimeError("governed Autotask read returned no structured data")
        return data

    @classmethod
    def _items(cls, result: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        items = cls._data(result).get("items")
        if not isinstance(items, list):
            raise RuntimeError("Autotask ticket search returned invalid items")
        return tuple(item for item in items if isinstance(item, Mapping))

    @classmethod
    def _fields(cls, result: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        fields = cls._data(result).get("fields")
        if not isinstance(fields, list):
            raise RuntimeError("Autotask entity fields read returned invalid fields")
        return tuple(item for item in fields if isinstance(item, Mapping))
