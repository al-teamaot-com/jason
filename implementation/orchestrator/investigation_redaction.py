"""Generic redaction for provider evidence before hosted reasoning.

This is intentionally provider-neutral. It does not know DRMM, Microsoft,
Autotask, or any provider schema.

It removes values carried by structurally sensitive keys and also handles
generic name/value records such as:
    {"name": "api_token", "value": "..."}
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


_REDACTED = "[REDACTED]"

_SENSITIVE_TERMS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "private_key",
    "privatekey",
    "api_key",
    "apikey",
    "access_key",
    "accesskey",
    "client_secret",
    "clientsecret",
    "recovery_key",
    "recoverykey",
    "connection_string",
    "connectionstring",
)


def _normalized(value: Any) -> str:
    return (
        str(value)
        .strip()
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _sensitive_label(value: Any) -> bool:
    label = _normalized(value)
    return any(
        term in label
        for term in _SENSITIVE_TERMS
    )


def redact_model_evidence(value: Any) -> Any:
    if isinstance(value, Mapping):
        source = {
            str(key): item
            for key, item in value.items()
        }

        descriptive_label = None

        for label_key in (
            "name",
            "key",
            "label",
            "variable",
            "variable_name",
            "property",
        ):
            if label_key in source:
                descriptive_label = source[label_key]
                break

        redact_companion_value = (
            descriptive_label is not None
            and _sensitive_label(descriptive_label)
        )

        result = {}

        for key, item in source.items():
            if _sensitive_label(key):
                result[key] = _REDACTED
                continue

            if (
                redact_companion_value
                and _normalized(key)
                in {
                    "value",
                    "data",
                    "content",
                    "setting",
                }
            ):
                result[key] = _REDACTED
                continue

            result[key] = redact_model_evidence(
                item
            )

        return result

    if (
        isinstance(value, Sequence)
        and not isinstance(
            value,
            (str, bytes, bytearray),
        )
    ):
        return [
            redact_model_evidence(item)
            for item in value
        ]

    return value


# Hosted reasoning must never receive an unbounded provider response.
#
# Full governed evidence remains in InvestigationEvidence.data. This function
# creates only a bounded model-facing representation. It is provider-neutral:
# it does not know Datto, Microsoft, Autotask, or any provider schema.
_MODEL_MAX_DEPTH = 8
_MODEL_MAX_MAPPING_ITEMS = 64
_MODEL_MAX_SEQUENCE_ITEMS = 12
_MODEL_MAX_SCALAR_CHARS = 800
_MODEL_MAX_TOTAL_CHARS = 48000


def bounded_model_evidence(value: Any) -> Any:
    """Return a redacted, structurally bounded model-facing evidence view."""

    redacted = redact_model_evidence(value)

    bounded = _bound_model_value(
        redacted,
        depth=0,
    )

    # Enforce a final serialized-size ceiling as a defense in depth.
    #
    # Structural bounding above should normally keep us under this ceiling.
    # If not, reduce sequence/mapping breadth uniformly rather than forwarding
    # an arbitrarily huge prompt to hosted reasoning.
    import json

    rendered = json.dumps(
        bounded,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )

    if len(rendered) <= _MODEL_MAX_TOTAL_CHARS:
        return bounded

    return _bound_model_value(
        redacted,
        depth=0,
        mapping_items=24,
        sequence_items=5,
        scalar_chars=400,
    )


def _bound_model_value(
    value: Any,
    *,
    depth: int,
    mapping_items: int = _MODEL_MAX_MAPPING_ITEMS,
    sequence_items: int = _MODEL_MAX_SEQUENCE_ITEMS,
    scalar_chars: int = _MODEL_MAX_SCALAR_CHARS,
) -> Any:
    if depth >= _MODEL_MAX_DEPTH:
        if isinstance(value, Mapping):
            return {
                "_truncated": "maximum depth reached",
            }

        if (
            isinstance(value, Sequence)
            and not isinstance(
                value,
                (str, bytes, bytearray),
            )
        ):
            return [
                "[TRUNCATED: maximum depth reached]"
            ]

    if isinstance(value, Mapping):
        items = list(value.items())

        result = {}

        for key, item in items[:mapping_items]:
            result[str(key)] = _bound_model_value(
                item,
                depth=depth + 1,
                mapping_items=mapping_items,
                sequence_items=sequence_items,
                scalar_chars=scalar_chars,
            )

        if len(items) > mapping_items:
            result["_truncated_mapping_items"] = (
                len(items) - mapping_items
            )

        return result

    if (
        isinstance(value, Sequence)
        and not isinstance(
            value,
            (str, bytes, bytearray),
        )
    ):
        items = list(value)

        result = [
            _bound_model_value(
                item,
                depth=depth + 1,
                mapping_items=mapping_items,
                sequence_items=sequence_items,
                scalar_chars=scalar_chars,
            )
            for item in items[:sequence_items]
        ]

        if len(items) > sequence_items:
            result.append(
                {
                    "_truncated_sequence_items": (
                        len(items) - sequence_items
                    )
                }
            )

        return result

    if isinstance(value, str):
        if len(value) <= scalar_chars:
            return value

        return (
            value[:scalar_chars]
            + f"...[TRUNCATED {len(value) - scalar_chars} chars]"
        )

    if isinstance(
        value,
        (int, float, bool),
    ) or value is None:
        return value

    text = str(value)

    if len(text) > scalar_chars:
        text = (
            text[:scalar_chars]
            + f"...[TRUNCATED {len(text) - scalar_chars} chars]"
        )

    return text
