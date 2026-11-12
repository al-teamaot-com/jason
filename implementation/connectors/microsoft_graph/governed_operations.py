"""Declarative, non-executable Microsoft 365 operation catalog.

This module describes a reusable capability surface. It intentionally does not
send Graph requests, grant permissions, mint tokens, or register production tools.
Actual writes must flow through the existing central governed execution plan,
tenant boundary registry and separate write-scoped application identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class GovernedMicrosoftOperation:
    name: str
    service: str
    permission_profile: str
    method: str
    route: str
    required_fields: frozenset[str]
    optional_fields: frozenset[str] = frozenset()
    requires_exact_approval: bool = True
    requires_readback: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.route.startswith("/") or self.method not in {"POST", "PATCH", "DELETE"}:
            raise ValueError("Invalid governed Microsoft operation descriptor")
        if not self.permission_profile or not self.requires_exact_approval or not self.requires_readback:
            raise ValueError("Microsoft write operations must require approval and readback")
        if self.required_fields & self.optional_fields:
            raise ValueError("Required and optional fields overlap")

    def validate_arguments(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Fail closed on unknown/missing fields; no caller-chosen URL or HTTP verb."""
        if not isinstance(arguments, Mapping):
            raise ValueError("Operation arguments must be a mapping")
        names = set(arguments)
        if not self.required_fields <= names or names - (self.required_fields | self.optional_fields):
            raise ValueError("Missing or unrecognized Microsoft operation arguments")
        for name, value in arguments.items():
            if not isinstance(value, str) or not value.strip() or len(value) > 256 or any(ord(c) < 32 for c in value):
                raise ValueError(f"Invalid Microsoft operation field: {name}")
        if self.name == "identity.group.create" and arguments["group_type"] not in {"security", "microsoft365"}:
            raise ValueError("Unsupported group type")
        if self.name == "identity.group.member.add":
            for field_name in ("verified_group_id", "verified_member_id"):
                try:
                    parsed = UUID(arguments[field_name])
                except (ValueError, AttributeError) as error:
                    raise ValueError("Verified Microsoft object identifiers must be UUIDs") from error
                if str(parsed) != arguments[field_name].lower():
                    raise ValueError("Microsoft object identifiers must be canonical UUIDs")
        return dict(arguments)


_OPERATIONS = {
    "identity.group.create": GovernedMicrosoftOperation(
        name="identity.group.create",
        service="microsoft_graph",
        permission_profile="group-create",
        method="POST",
        route="/v1.0/groups",
        required_fields=frozenset({"display_name", "mail_nickname", "group_type"}),
        optional_fields=frozenset({"description"}),
    ),
    "identity.group.member.add": GovernedMicrosoftOperation(
        name="identity.group.member.add",
        service="microsoft_graph",
        permission_profile="group-membership-write",
        method="POST",
        route="/v1.0/groups/{verified_group_id}/members/$ref",
        required_fields=frozenset({"verified_group_id", "verified_member_id"}),
    ),
}
MICROSOFT_GOVERNED_OPERATIONS: Mapping[str, GovernedMicrosoftOperation] = MappingProxyType(_OPERATIONS)


def operation(name: str) -> GovernedMicrosoftOperation:
    """Lookup only approved descriptors, never accept a raw Graph path."""
    try:
        return MICROSOFT_GOVERNED_OPERATIONS[name]
    except (KeyError, TypeError) as error:
        raise PermissionError("Microsoft operation is not registered") from error
