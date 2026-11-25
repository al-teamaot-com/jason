from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator


@dataclass(frozen=True, slots=True)
class PortabilityFinding:
    rule_id: str
    severity: str
    path: str
    line: int
    matched_fragment: str
    description: str


def load_rules(
    rules_path: str | Path,
    schema_path: str | Path,
) -> dict[str, Any]:
    rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(rules),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        raise ValueError("runtime portability rules invalid: " + first.message)
    return rules


def audit_runtime_portability(
    *,
    repository_root: str | Path,
    rules: Mapping[str, Any],
) -> tuple[PortabilityFinding, ...]:
    root = Path(repository_root).resolve()
    paths: set[Path] = set()
    for pattern in rules["scan_globs"]:
        for candidate in root.glob(str(pattern)):
            if candidate.is_file():
                paths.add(candidate)

    compiled = [
        (
            str(rule["id"]),
            str(rule["severity"]),
            re.compile(str(rule["pattern"])),
            str(rule["description"]),
        )
        for rule in rules["rules"]
    ]

    findings: list[PortabilityFinding] = []
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            for rule_id, severity, pattern, description in compiled:
                for match in pattern.finditer(line):
                    findings.append(
                        PortabilityFinding(
                            rule_id=rule_id,
                            severity=severity,
                            path=relative,
                            line=line_number,
                            matched_fragment=match.group(0),
                            description=description,
                        )
                    )
    return tuple(findings)


def summarize_findings(
    findings: tuple[PortabilityFinding, ...],
) -> dict[str, Any]:
    blockers = [item for item in findings if item.severity == "blocker"]
    warnings = [item for item in findings if item.severity == "warning"]
    return {
        "status": "blocked" if blockers else "portable",
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "findings": [asdict(item) for item in findings],
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Audit Jason runtime artifacts for MSP/operator-specific portability blockers"
    )
    parser.add_argument("--repository-root", default=str(root))
    parser.add_argument(
        "--rules",
        default=str(root / "config/runtime-portability-rules.v1.json"),
    )
    parser.add_argument(
        "--schema",
        default=str(root / "config/schemas/runtime-portability-rules.schema.json"),
    )
    args = parser.parse_args()

    rules = load_rules(args.rules, args.schema)
    findings = audit_runtime_portability(
        repository_root=args.repository_root,
        rules=rules,
    )
    summary = summarize_findings(findings)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "portable" else 3


if __name__ == "__main__":
    raise SystemExit(main())
