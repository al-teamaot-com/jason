"""Tenant-isolated registry for governed Microsoft Teams approval delivery targets.

Configuration is policy data, not authority. The registry only resolves where an
already-governed approval request may be delivered. It never determines who may
approve, whether approval is sufficient, or whether execution may resume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .teams_approval_delivery import TeamsApprovalDeliveryTarget


@dataclass(frozen=True, slots=True)
class TeamsApprovalTargetRecord:
    organization_id: str
    team_id: str
    channel_id: str
    enabled: bool = True

    def validate(self) -> None:
        TeamsApprovalDeliveryTarget(
            organization_id=self.organization_id,
            team_id=self.team_id,
            channel_id=self.channel_id,
        ).validate()


@dataclass
class TeamsApprovalTargetRegistry:
    """Fail-closed organization -> Teams target registry.

    Exactly one enabled target may exist for an organization. Duplicate or ambiguous
    configuration is rejected rather than selecting an arbitrary destination.
    """

    records: tuple[TeamsApprovalTargetRecord, ...] = field(default_factory=tuple)

    @classmethod
    def from_records(cls, records: Iterable[TeamsApprovalTargetRecord]) -> "TeamsApprovalTargetRegistry":
        normalized = tuple(records)
        for record in normalized:
            record.validate()
        registry = cls(records=normalized)
        registry._validate_uniqueness()
        return registry

    def resolve(self, *, organization_id: str) -> TeamsApprovalDeliveryTarget | None:
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ValueError("organization_id must be non-empty")
        organization_id = organization_id.strip()
        matches = [
            record for record in self.records
            if record.enabled and record.organization_id == organization_id
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise PermissionError("ambiguous Teams approval target configuration")
        record = matches[0]
        return TeamsApprovalDeliveryTarget(
            organization_id=record.organization_id,
            team_id=record.team_id,
            channel_id=record.channel_id,
        )

    def _validate_uniqueness(self) -> None:
        enabled_by_org: dict[str, int] = {}
        for record in self.records:
            if not record.enabled:
                continue
            enabled_by_org[record.organization_id] = enabled_by_org.get(record.organization_id, 0) + 1
        ambiguous = sorted(org for org, count in enabled_by_org.items() if count > 1)
        if ambiguous:
            raise ValueError(
                "multiple enabled Teams approval targets configured for organization(s): "
                + ", ".join(ambiguous)
            )
