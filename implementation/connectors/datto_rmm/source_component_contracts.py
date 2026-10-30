"""Source-controlled, exact-identity contracts for high-risk Datto component inputs.

A contract defines parameter validation, NOT provider execution authority,
standing approval, target access or reboot permission. Only owner-reviewed,
protected-source entries belong here. Runtime component metadata must match
the complete UID/name pair; either partial collision fails closed.

Adding another reviewed component is a data-only entry using the same
validation mechanism. Provider quick-jobs still pass Central Orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class SourceComponentContract:
    uid: str
    name: str
    variables: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if not self.uid.strip() or not self.name.strip():
            raise ValueError("source component contract identity required")
        field_names = [str(item.get("name", "")).casefold() for item in self.variables]
        if not field_names or any(not field for field in field_names):
            raise ValueError("source component contract fields required")
        if len(set(field_names)) != len(field_names):
            raise ValueError("source component contract fields must be unique")


# Exact live Datto UID+name pairs. All operations are still PER-RUN unless
# independently certified as read-only and approved for standing use.
# No endpoint, ticket, tenant, or technician-specific identifiers appear here.
SOURCE_COMPONENT_CONTRACTS: tuple[SourceComponentContract, ...] = (
    SourceComponentContract(
        uid="479d1a75-8f98-42b7-b6fb-408242bcc17e",
        name="Change Hostname [WIN]",
        variables=(
            {"name": "usrNewName", "variable_type": "hostname",
             "required": True, "maximum_length": 15},
            {"name": "usrReboot", "variable_type": "boolean",
             "required": True, "allowed_values": ("false",)},
        ),
    ),
    SourceComponentContract(
        uid="3770a86b-26d4-414f-a87c-87a0835f4278",
        name="Datto Endpoint Backup: Retrieve Errors and Warnings from Logs [WIN]",
        variables=(
            {"name": "usrMaxResults", "variable_type": "selection",
             "required": True, "allowed_values": ("25", "50", "100")},
            {"name": "usrAdditionalInfo", "variable_type": "boolean",
             "required": True, "allowed_values": ("false",)},
        ),
    ),
    SourceComponentContract(
        uid="6725d709-f3b4-415f-b6f7-4185ebde71df",
        name="AOT Event log search Ver09192024",
        variables=(
            {"name": "SearchTerm", "variable_type": "search_term",
             "required": True, "maximum_length": 80},
            {"name": "DaysBack", "variable_type": "selection",
             "required": True, "allowed_values": ("1", "3", "7", "14")},
        ),
    ),
)


def resolve_source_component_contract(
    uid: str,
    name: str,
    *,
    contracts: Sequence[SourceComponentContract] = SOURCE_COMPONENT_CONTRACTS,
) -> SourceComponentContract | None:
    """Match only the exact pair; reject any stale/renamed identity collision."""
    normalized_name = str(name or "").strip().casefold()
    normalized_uid = str(uid or "").strip()
    candidates = tuple(
        contract for contract in contracts
        if contract.uid == normalized_uid
        or contract.name.casefold() == normalized_name
    )
    if not candidates:
        return None
    if len(candidates) != 1 or (
        candidates[0].uid != normalized_uid
        or candidates[0].name.casefold() != normalized_name
    ):
        raise PermissionError("source-locked component identity mismatch")
    return candidates[0]
