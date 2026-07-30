from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class ContractValidationError(ValueError):
    """Raised when a CAP-001 document violates its versioned contract."""


_SCHEMA_FILES = {
    "investigation_request": "investigation-request.schema.json",
    "case_package": "case-package.schema.json",
    "reasoning_result": "reasoning-result.schema.json",
    "technician_response": "technician-response.schema.json",
    "recorded_outcome": "recorded-outcome.schema.json",
}


def _schema_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas"


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    try:
        filename = _SCHEMA_FILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown CAP-001 schema: {name}") from exc

    with (_schema_dir() / filename).open("r", encoding="utf-8") as handle:
        schema: dict[str, Any] = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


def validate_document(name: str, document: dict[str, Any]) -> None:
    validator = Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if not errors:
        return

    error: ValidationError = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "$"
    raise ContractValidationError(f"{name} contract violation at {location}: {error.message}")
