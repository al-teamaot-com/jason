"""Provider-neutral sanitization for evidence entering Jason reasoning contexts.

The sanitizer preserves evidence structure while replacing credential-bearing
values. It intentionally operates independently of any provider schema so the
same boundary can be used for Datto RMM, Autotask, IT Glue, Microsoft, and
future connectors.

This module does not determine authorization and does not mutate provider state.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(?:"
    r"password|passwd|pwd|"
    r"secret|"
    r"token|"
    r"credential|"
    r"authorization|"
    r"api[-_ ]?key|"
    r"private[-_ ]?key|"
    r"client[-_ ]?secret|"
    r"access[-_ ]?key|"
    r"session[-_ ]?key|"
    r"connection[-_ ]?string|"
    r"shared[-_ ]?access[-_ ]?key|"
    r"account[-_ ]?key"
    r")",
    flags=re.IGNORECASE,
)

_PRIVATE_KEY = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----",
    flags=re.IGNORECASE,
)

_BEARER = re.compile(
    r"^\s*Bearer\s+\S+",
    flags=re.IGNORECASE,
)

_JWT = re.compile(
    r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$"
)

_SECRET_ASSIGNMENT = re.compile(
    r"(?:"
    r"password|passwd|pwd|"
    r"client[_ -]?secret|"
    r"api[_ -]?key|"
    r"access[_ -]?token|"
    r"refresh[_ -]?token|"
    r"secret[_ -]?key|"
    r"shared[_ -]?access[_ -]?key|"
    r"account[_ -]?key|"
    r"authorization"
    r")\s*[:=]\s*[^;\s]+",
    flags=re.IGNORECASE,
)

_CREDENTIAL_URI = re.compile(
    r"^[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
)

_AWS_ACCESS_KEY = re.compile(r"^(?:AKIA|ASIA)[A-Z0-9]{16}$")

_KNOWN_TOKEN_PREFIX = re.compile(
    r"^(?:"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}"
    r")$"
)

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def _looks_like_opaque_secret(value: str) -> bool:
    """Conservatively identify long credential-like opaque values.

    Standard UUIDs and pure hexadecimal values are not classified solely by
    shape because those frequently represent durable identifiers or hashes.
    Secret-bearing field names still redact them when context says they are
    credentials.
    """

    if len(value) < 48:
        return False

    if any(character.isspace() for character in value):
        return False

    if _UUID.fullmatch(value):
        return False

    if re.fullmatch(r"[0-9a-fA-F]+", value):
        return False

    if "://" in value:
        return False

    # Long API and filesystem paths can have enough character variety to look
    # statistically opaque even though their structure is plainly non-secret.
    # Explicit secret formats are detected before this heuristic.
    if value.startswith("/") and "/" in value[1:]:
        return False

    if re.match(r"^[A-Za-z]:[\\/]", value):
        return False

    if value.startswith("\\\\"):
        return False

    classes = sum(
        bool(pattern.search(value))
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"[0-9]"),
            re.compile(r"[^A-Za-z0-9]"),
        )
    )

    return classes >= 3 and _entropy(value) >= 4.0


def is_sensitive_value(value: str) -> bool:
    candidate = value.strip()

    if not candidate:
        return False

    return any(
        (
            bool(_PRIVATE_KEY.search(candidate)),
            bool(_BEARER.search(candidate)),
            bool(_JWT.fullmatch(candidate)),
            bool(_SECRET_ASSIGNMENT.search(candidate)),
            bool(_CREDENTIAL_URI.search(candidate)),
            bool(_AWS_ACCESS_KEY.fullmatch(candidate)),
            bool(_KNOWN_TOKEN_PREFIX.fullmatch(candidate)),
            _looks_like_opaque_secret(candidate),
        )
    )


_SENSITIVE_DESCRIPTOR_KEYS = {
    "name",
    "key",
    "variable",
    "variablename",
    "settingname",
    "propertyname",
    "fieldname",
}

_SENSITIVE_RECORD_VALUE_KEYS = {
    "value",
    "values",
    "data",
    "content",
    "settingvalue",
    "text",
}


def _normalized_key(value: str) -> str:
    return "".join(
        character
        for character in value.casefold()
        if character.isalnum()
    )


def _mapping_declares_sensitive_value(value: Mapping[Any, Any]) -> bool:
    """Detect generic name/value records whose metadata identifies a secret.

    Provider variable APIs commonly represent a secret as, for example:

        {"name": "IntegrationPassword", "value": "..."}

    The literal object key ``value`` is not sensitive by itself, so the sibling
    metadata must be considered without adding provider-specific field names.
    """

    for raw_key, descriptor in value.items():
        if _normalized_key(str(raw_key)) not in _SENSITIVE_DESCRIPTOR_KEYS:
            continue
        if isinstance(descriptor, str) and _SENSITIVE_KEY.search(descriptor):
            return True
    return False


def sanitize_evidence_tree(
    value: Any,
    *,
    key_name: str | None = None,
    depth: int = 0,
    max_depth: int = 64,
) -> Any:
    """Return a sanitized copy of arbitrary structured evidence.

    Sensitive field names and sensitive scalar value shapes are replaced with
    ``[REDACTED]``. Keys and container structure are preserved so reasoning can
    still understand what evidence exists without receiving the credential.
    """

    if key_name and _SENSITIVE_KEY.search(key_name):
        return REDACTED

    if depth > max_depth:
        return "[MAX_DEPTH_REACHED]"

    if isinstance(value, Mapping):
        sensitive_record = _mapping_declares_sensitive_value(value)
        sanitized: dict[str, Any] = {}

        for raw_key, child in value.items():
            key = str(raw_key)

            if (
                sensitive_record
                and _normalized_key(key) in _SENSITIVE_RECORD_VALUE_KEYS
            ):
                sanitized[key] = REDACTED
                continue

            sanitized[key] = sanitize_evidence_tree(
                child,
                key_name=key,
                depth=depth + 1,
                max_depth=max_depth,
            )

        return sanitized

    if isinstance(value, (list, tuple)):
        return [
            sanitize_evidence_tree(
                child,
                depth=depth + 1,
                max_depth=max_depth,
            )
            for child in value
        ]

    if isinstance(value, str):
        return REDACTED if is_sensitive_value(value) else value

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    rendered = str(value)
    return REDACTED if is_sensitive_value(rendered) else rendered
