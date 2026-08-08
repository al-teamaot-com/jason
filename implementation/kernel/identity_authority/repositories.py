from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import ApprovalRecord, AuthorityGrant, IdentityRecord


@dataclass
class InMemoryIdentityRepository:
    records: dict[str, IdentityRecord] = field(default_factory=dict)

    def get(self, identity_id: str) -> IdentityRecord | None:
        return self.records.get(identity_id)

    def put(self, record: IdentityRecord) -> None:
        self.records[record.identity_id] = record


@dataclass
class InMemoryAuthorityGrantRepository:
    records: dict[str, AuthorityGrant] = field(default_factory=dict)

    def list_for_subject(self, subject_id: str) -> tuple[AuthorityGrant, ...]:
        return tuple(record for record in self.records.values() if record.subject_id == subject_id)

    def put(self, record: AuthorityGrant) -> None:
        self.records[record.grant_id] = record


@dataclass
class InMemoryApprovalRepository:
    records: dict[str, ApprovalRecord] = field(default_factory=dict)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self.records.get(approval_id)

    def put(self, record: ApprovalRecord) -> None:
        self.records[record.approval_id] = record
