from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class SecretRequirementError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SecretRequirement:
    provider_id: str
    secret_reference: str
    required: bool = True


def _validate_reference(value: str) -> str:
    reference = value.strip()
    if not _REFERENCE_PATTERN.fullmatch(reference):
        raise SecretRequirementError(
            "secret reference must be a logical identifier, not a path/value"
        )
    return reference


def build_secret_requirements(
    msp_configuration: Mapping[str, Any],
) -> tuple[SecretRequirement, ...]:
    result: list[SecretRequirement] = []
    for provider_id, raw in sorted(
        dict(msp_configuration.get("providers") or {}).items()
    ):
        provider = dict(raw or {})
        if not bool(provider.get("enabled")):
            continue
        reference = provider.get("secret_reference")
        if reference is None or not str(reference).strip():
            raise SecretRequirementError(
                f"enabled provider {provider_id} has no governed secret reference"
            )
        result.append(
            SecretRequirement(
                provider_id=str(provider_id),
                secret_reference=_validate_reference(str(reference)),
            )
        )
    return tuple(result)


def write_secret_requirements(
    *,
    target_root: str | Path,
    requirements: Sequence[SecretRequirement],
) -> Path:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError("secret requirement staging may not target /")
    output = root / "var/lib/jason/secret-requirements.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "requirements": [asdict(item) for item in requirements],
        "contains_secret_values": False,
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def evaluate_secret_readiness(
    *,
    requirements: Sequence[SecretRequirement],
    available_references: Sequence[str],
) -> dict[str, Any]:
    required = {
        item.secret_reference
        for item in requirements
        if item.required
    }
    available = {
        _validate_reference(str(item))
        for item in available_references
    }
    missing = sorted(required - available)
    unexpected = sorted(available - required)
    return {
        "status": "ready" if not missing else "blocked",
        "required_count": len(required),
        "available_count": len(required & available),
        "missing_references": missing,
        "unexpected_references": unexpected,
        "secret_values_observed": False,
    }


def load_secret_presence_attestation(
    path: str | Path,
) -> tuple[str, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise SecretRequirementError(
            "unsupported secret presence attestation schema"
        )
    if payload.get("contains_secret_values") is not False:
        raise SecretRequirementError(
            "secret presence attestation must explicitly contain no secret values"
        )
    raw = payload.get("available_references")
    if not isinstance(raw, list):
        raise SecretRequirementError(
            "secret presence attestation requires available_references list"
        )
    return tuple(_validate_reference(str(item)) for item in raw)
