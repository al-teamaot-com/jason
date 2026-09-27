from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .contracts import ReflectionSignalKind


@dataclass(frozen=True, slots=True)
class ReflectionRegressionCase:
    case_id: str
    signal_kind: ReflectionSignalKind
    capability_name: str
    invariant: str
    test_reference: str

    def validate(self) -> None:
        for name, value, maximum in (
            ("case_id", self.case_id, 160),
            ("capability_name", self.capability_name, 200),
            ("invariant", self.invariant, 1200),
            ("test_reference", self.test_reference, 300),
        ):
            if not value.strip() or len(value) > maximum:
                raise ValueError(f"reflection regression {name} must be bounded and non-empty")
        if "::" not in self.test_reference:
            raise ValueError("reflection regression test_reference must identify one exact test")


def load_regression_registry(path: str | Path) -> tuple[ReflectionRegressionCase, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise ValueError("unsupported reflection regression registry schema")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("reflection regression registry requires cases")
    cases: list[ReflectionRegressionCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("reflection regression case must be an object")
        item = ReflectionRegressionCase(
            case_id=str(raw.get("case_id") or "").strip(),
            signal_kind=ReflectionSignalKind(str(raw.get("signal_kind") or "")),
            capability_name=str(raw.get("capability_name") or "").strip(),
            invariant=str(raw.get("invariant") or "").strip(),
            test_reference=str(raw.get("test_reference") or "").strip(),
        )
        item.validate()
        if item.case_id in seen:
            raise ValueError("duplicate reflection regression case_id")
        seen.add(item.case_id)
        cases.append(item)
    return tuple(cases)
