#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


class DocumentationImpactError(RuntimeError):
    pass


def validate_pull_request_body(body: str) -> None:
    text = body or ""
    if "## Documentation impact" not in text:
        raise DocumentationImpactError("PR body is missing required '## Documentation impact' section")
    updated = re.search(r"^- \[[xX]\] Documentation updated\s*$", text, re.MULTILINE)
    none = re.search(r"^- \[[xX]\] No documentation impact\s*$", text, re.MULTILINE)
    if bool(updated) == bool(none):
        raise DocumentationImpactError(
            "Select exactly one documentation-impact outcome: Documentation updated OR No documentation impact"
        )
    if none:
        match = re.search(r"^No-documentation-impact reason:\s*(.+?)\s*$", text, re.MULTILINE)
        if match is None or len(match.group(1).strip()) < 12:
            raise DocumentationImpactError(
                "No documentation impact requires a concrete reason of at least 12 characters"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.event.read_text(encoding="utf-8"))
    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        print("DOCUMENTATION_IMPACT_GATE=SKIP non-pull-request event")
        return 0
    validate_pull_request_body(str(pr.get("body") or ""))
    print("DOCUMENTATION_IMPACT_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
