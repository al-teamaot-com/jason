"""Deterministic queries over complete governed evidence.

Hosted reasoning receives bounded evidence excerpts. This module allows the
model to request safe aggregate/list operations over the complete evidence
already retained inside Jason, without another provider request.

It is provider-neutral and does not know Datto, Microsoft, Autotask, or any
provider schema.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Mapping, Sequence

from .investigation_redaction import (
    bounded_model_evidence,
    redact_model_evidence,
)


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


def _sensitive_field(value: str) -> bool:
    label = _normalized(value)

    return any(
        term in label
        for term in _SENSITIVE_TERMS
    )


def _field_value(
    record: Mapping[str, Any],
    field: str,
) -> Any:
    wanted = _normalized(field)

    for key, value in record.items():
        if _normalized(key) == wanted:
            return value

    return None


def _scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        )
    )


def _record_identity(
    record: Mapping[str, Any],
) -> str | None:
    """Return a generic durable-looking identity when present."""

    identity_keys = (
        "resource_id",
        "uid",
        "device_uid",
        "deviceuid",
        "site_uid",
        "siteuid",
        "alert_uid",
        "alertuid",
        "guid",
        "id",
    )

    normalized = {
        _normalized(key): value
        for key, value in record.items()
    }

    for key in identity_keys:
        value = normalized.get(
            _normalized(key)
        )

        if (
            _scalar(value)
            and value is not None
            and str(value).strip()
        ):
            return str(value).strip()

    return None


def _collect_records(
    value: Any,
    *,
    required_field: str,
    output: list[Mapping[str, Any]],
) -> None:
    """Find mapping records containing the requested field.

    Only mappings occurring as collection members are considered records.
    Nested provider envelopes themselves are not counted.
    """

    if isinstance(value, Mapping):
        for item in value.values():
            _collect_records(
                item,
                required_field=required_field,
                output=output,
            )

        return

    if (
        isinstance(value, Sequence)
        and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        )
    ):
        for item in value:
            if isinstance(
                item,
                Mapping,
            ):
                if (
                    _field_value(
                        item,
                        required_field,
                    )
                    is not None
                ):
                    output.append(item)

                # A record may itself contain nested collections.
                for nested in item.values():
                    _collect_records(
                        nested,
                        required_field=required_field,
                        output=output,
                    )

            else:
                _collect_records(
                    item,
                    required_field=required_field,
                    output=output,
                )


def _deduplicate(
    records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()

    for record in records:
        identity = _record_identity(
            record
        )

        if identity:
            key = "identity:" + identity
        else:
            scalar_view = {
                str(key): value
                for key, value in record.items()
                if _scalar(value)
            }

            key = (
                "record:"
                + json.dumps(
                    scalar_view,
                    sort_keys=True,
                    default=str,
                    ensure_ascii=False,
                )
            )

        if key in seen:
            continue

        seen.add(key)
        result.append(record)

    return result


def _matches(
    value: Any,
    *,
    comparison: str,
    expected: str,
) -> bool:
    if value is None:
        return False

    if comparison == "exists":
        return True

    actual = str(value).strip().casefold()
    wanted = str(expected).strip().casefold()

    if comparison == "equals":
        return actual == wanted

    if comparison == "contains":
        return wanted in actual

    raise ValueError(
        "unsupported evidence comparison"
    )


def _source_complete(
    entries,
) -> bool | None:
    observed_true = False

    for entry in entries:
        data = entry.data

        if not isinstance(
            data,
            Mapping,
        ):
            continue

        complete = data.get(
            "discovery_complete"
        )

        if complete is False:
            return False

        if complete is True:
            observed_true = True

    if observed_true:
        return True

    return None


def query_governed_evidence(
    entries,
    *,
    action: str,
    resource_type: str,
    field: str,
    comparison: str,
    value: str,
    group_by: str,
    select_fields: Sequence[str],
    limit: int,
) -> Mapping[str, Any]:
    """Evaluate one bounded deterministic query over complete evidence."""

    action = str(action).strip().casefold()
    resource_type = str(
        resource_type
    ).strip().casefold()

    field = str(field).strip()
    comparison = str(
        comparison
    ).strip().casefold()

    group_by = str(
        group_by
    ).strip()

    select_fields = tuple(
        str(item).strip()
        for item in select_fields
        if str(item).strip()
    )

    limit = max(
        1,
        min(
            int(limit),
            100,
        ),
    )

    if action not in {
        "count",
        "distinct",
        "group_count",
        "list",
    }:
        raise ValueError(
            "unsupported evidence query action"
        )

    if comparison not in {
        "exists",
        "equals",
        "contains",
    }:
        raise ValueError(
            "unsupported evidence comparison"
        )

    if not field:
        raise ValueError(
            "evidence query field is required"
        )

    requested_fields = (
        field,
        group_by,
        *select_fields,
    )

    if any(
        _sensitive_field(item)
        for item in requested_fields
        if item
    ):
        raise ValueError(
            "sensitive evidence fields may not be queried"
        )

    selected_entries = tuple(
        entry
        for entry in entries
        if (
            not resource_type
            or str(
                entry.resource_type
            ).strip().casefold()
            == resource_type
        )
    )

    raw_records: list[
        Mapping[str, Any]
    ] = []

    for entry in selected_entries:
        _collect_records(
            entry.data,
            required_field=field,
            output=raw_records,
        )

    records = _deduplicate(
        raw_records
    )

    matched = [
        record
        for record in records
        if _matches(
            _field_value(
                record,
                field,
            ),
            comparison=comparison,
            expected=value,
        )
    ]

    result: dict[str, Any] = {
        "action": action,
        "resource_type": (
            resource_type
            or None
        ),
        "field": field,
        "comparison": comparison,
        "value": value,
        "source_complete": _source_complete(
            selected_entries
        ),
        "records_examined": len(
            records
        ),
        "matched_records": len(
            matched
        ),
    }

    if action == "count":
        result["count"] = len(
            matched
        )

    elif action == "distinct":
        values = sorted(
            {
                str(
                    _field_value(
                        record,
                        field,
                    )
                )
                for record in matched
                if _field_value(
                    record,
                    field,
                )
                is not None
            },
            key=str.casefold,
        )

        result["distinct_values"] = (
            values[:limit]
        )

        result[
            "distinct_value_count"
        ] = len(values)

        result["truncated"] = (
            len(values) > limit
        )

    elif action == "group_count":
        if not group_by:
            raise ValueError(
                "group_count requires group_by"
            )

        groups = Counter()

        for record in matched:
            group_value = _field_value(
                record,
                group_by,
            )

            label = (
                str(group_value)
                if group_value is not None
                else "[missing]"
            )

            groups[label] += 1

        ordered = sorted(
            groups.items(),
            key=lambda item: (
                -item[1],
                item[0].casefold(),
            ),
        )

        result["group_by"] = group_by
        result["groups"] = [
            {
                "value": name,
                "count": count,
            }
            for name, count
            in ordered[:limit]
        ]

        result["group_count"] = len(
            ordered
        )

        result["truncated"] = (
            len(ordered) > limit
        )

    elif action == "list":
        fields = (
            select_fields
            if select_fields
            else (
                field,
            )
        )

        rows = []

        for record in matched[:limit]:
            row = {
                name: _field_value(
                    record,
                    name,
                )
                for name in fields
            }

            rows.append(
                redact_model_evidence(
                    row
                )
            )

        result["records"] = rows
        result["returned_records"] = len(
            rows
        )
        result["truncated"] = (
            len(matched) > limit
        )

    return bounded_model_evidence(
        result
    )
