"""Canonical Datto RMM device selectors for J-Assist screen evidence.

Datto may expose device UIDs as UUIDs (current native API) or decimal
legacy identifiers. The browser URL is only a selector, never proof of
device ownership. A separate governed provider read MUST verify the
selected device and pinned AOT Datto site on every authorization.
"""
from __future__ import annotations
import re

_DECIMAL = re.compile(r"^[0-9]{1,24}$")
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_NIL = "00000000-0000-0000-0000-000000000000"

def canonical_device_uid(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value.lower()
    if _DECIMAL.fullmatch(candidate):
        return candidate
    if _GUID.fullmatch(candidate) and candidate != _NIL:
        return candidate
    return None

def valid_device_uid(value: object) -> bool:
    return isinstance(value, str) and canonical_device_uid(value) == value
