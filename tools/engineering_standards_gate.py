#!/usr/bin/env python3
"""Fail-closed validation of Jason's durable engineering instructions."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("docs/engineering/JASON_ENGINEERING_STANDARDS.md")
AGENTS = Path("AGENTS.md")
REQUIRED = ("JES-001", "JES-002", "JES-003", "JES-004")
STATUS_FIELDS = ("Status:", "Completed:", "Still required:", "What I'm doing next:", "What you need to do:")


def validate(registry: str, agents: str) -> list[str]:
    errors = []
    for code in REQUIRED:
        if len(re.findall(r"(?m)^## " + re.escape(code) + r"\b", registry)) != 1:
            errors.append(f"{code} must have exactly one heading")
    for field in STATUS_FIELDS:
        if field not in registry:
            errors.append(f"Missing status field: {field}")
    if str(REGISTRY) not in agents:
        errors.append("AI instructions must reference the canonical registry")
    for phrase in ("Before making development changes", "background", "authorization"):
        if phrase.casefold() not in (agents + registry).casefold():
            errors.append(f"Missing instruction concept: {phrase}")
    return errors


def main() -> int:
    errors = validate((ROOT / REGISTRY).read_text(), (ROOT / AGENTS).read_text())
    if errors:
        for error in errors:
            print(f"ENGINEERING_STANDARDS=FAIL {error}")
        return 1
    print("ENGINEERING_STANDARDS=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
