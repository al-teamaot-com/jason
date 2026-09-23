from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class SensitivityFindingKind(str, Enum):
    SECRET_FIELD = "secret_field"
    CREDENTIAL_ASSIGNMENT = "credential_assignment"
    PRIVATE_KEY = "private_key"
    TOKEN_SHAPE = "token_shape"


@dataclass(frozen=True, slots=True)
class SensitivityFinding:
    kind: SensitivityFindingKind
    path: str


@dataclass(frozen=True, slots=True)
class SensitivityAssessment:
    sensitive: bool
    findings: tuple[SensitivityFinding, ...] = ()


_SECRET_KEY_TOKENS = (
    "password",
    "passwd",
    "passphrase",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "client_secret",
    "secret_id",
    "credential",
)

_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(?:password|passwd|passphrase|api[_ -]?key|client[_ -]?secret|"
    r"access[_ -]?token|refresh[_ -]?token)\b\s*[:=]\s*\S+"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_TOKEN_SHAPE = re.compile(
    r"(?i)\b(?:bearer\s+)?(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})\b"
)

_MAX_DEPTH = 12
_MAX_FINDINGS = 20
_MAX_TEXT_SCAN = 100_000


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().casefold()).strip("_")


def assess_sensitive_evidence(value: Any) -> SensitivityAssessment:
    """Conservatively detect evidence that must not be released raw.

    This is a deterministic safety classifier, not a declassification mechanism.
    A clean assessment does not itself grant release authority; source and Jason
    authorization still have to allow release. A positive finding is sufficient to
    prevent raw release.
    """

    findings: list[SensitivityFinding] = []

    def add(kind: SensitivityFindingKind, path: str) -> None:
        if len(findings) < _MAX_FINDINGS:
            findings.append(SensitivityFinding(kind=kind, path=path))

    def walk(item: Any, *, path: str, depth: int) -> None:
        if len(findings) >= _MAX_FINDINGS or depth > _MAX_DEPTH:
            return

        if isinstance(item, Mapping):
            for raw_key, child in item.items():
                key = _normalized_key(raw_key)
                child_path = f"{path}.{key}" if path else key
                if any(token in key for token in _SECRET_KEY_TOKENS):
                    if child not in (None, "", [], {}, ()):
                        add(SensitivityFindingKind.SECRET_FIELD, child_path)
                    continue
                walk(child, path=child_path, depth=depth + 1)
            return

        if isinstance(item, (list, tuple)):
            for index, child in enumerate(item[:500]):
                walk(child, path=f"{path}[{index}]", depth=depth + 1)
                if len(findings) >= _MAX_FINDINGS:
                    break
            return

        if not isinstance(item, str):
            return

        text = item[:_MAX_TEXT_SCAN]
        if _PRIVATE_KEY.search(text):
            add(SensitivityFindingKind.PRIVATE_KEY, path)
        if _CREDENTIAL_ASSIGNMENT.search(text):
            add(SensitivityFindingKind.CREDENTIAL_ASSIGNMENT, path)
        if _TOKEN_SHAPE.search(text):
            add(SensitivityFindingKind.TOKEN_SHAPE, path)

    walk(value, path="evidence", depth=0)
    return SensitivityAssessment(
        sensitive=bool(findings),
        findings=tuple(findings),
    )
