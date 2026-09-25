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

    def get(self, grant_id: str) -> AuthorityGrant | None:
        return self.records.get(grant_id)

    def put(self, record: AuthorityGrant) -> None:
        self.records[record.grant_id] = record

    def revoke(self, grant_id: str) -> AuthorityGrant | None:
        current = self.records.get(grant_id)
        if current is None or current.status == "revoked":
            return current
        revoked = AuthorityGrant(
            grant_id=current.grant_id, subject_id=current.subject_id,
            capability=current.capability, organization_id=current.organization_id,
            client_id=current.client_id, permission=current.permission,
            approval_required=current.approval_required, effective_from=current.effective_from,
            effective_until=current.effective_until, status="revoked",
        )
        self.records[grant_id] = revoked
        return revoked


@dataclass
class InMemoryApprovalRepository:
    records: dict[str, ApprovalRecord] = field(default_factory=dict)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self.records.get(approval_id)

    def put(self, record: ApprovalRecord) -> None:
        self.records[record.approval_id] = record
