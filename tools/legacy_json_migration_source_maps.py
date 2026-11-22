"""Authoritative source maps for every enabled legacy playbook.

Static source analysis only: no activation, inferred provider authority, or
second execution registry. Each section is referenced by exact file lines and
SHA256, with discovery-only implementation mentions for focused conversion.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("implementation/autonomous_remediation/playbook_registry.json")
OUTPUT = Path("docs/playbooks/json/migration/source_maps")
SECTION_HEADING = re.compile(r"(?m)^## (?P<number>[0-9]{1,2})\. (?P<title>[^\r\n]+)\r?$")
CAPABILITY = re.compile(
    r"\b(?:service|endpoint|automation|backup|management|communication|identity|security)"
    r"\.[a-z0-9_.:-]+\b"
)


def blob_sha(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def sections_of(text: str) -> tuple[dict[str, Any], ...]:
    matches = list(SECTION_HEADING.finditer(text))
    parts = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        part = text[match.start():end]
        parts.append({
            "number": int(match.group("number")),
            "heading": match.group("title").strip(),
            "first_line": text.count("\n", 0, match.start()) + 1,
            "last_line": text.count("\n", 0, end) + (
                1 if end > 0 and text[end - 1] != "\n" else 0
            ),
            "section_sha256": hashlib.sha256(part.encode("utf-8")).hexdigest(),
            "capability_mentions_unreviewed": sorted(set(CAPABILITY.findall(part))),
        })
    return tuple(parts)


def build(root: Path = ROOT) -> dict[str, Any]:
    raw = json.loads((root / REGISTRY).read_text())
    source_rows = [entry for entry in raw["playbooks"] if entry.get("enabled") is True]
    source_files = [
        path for path in (root / "implementation").rglob("*.py")
        if not path.name.startswith("test_") and "tests" not in path.parts
    ]
    refs = []
    for row in source_rows:
        relative = Path(row["source"])
        file = root / relative
        data = file.read_bytes()
        text = data.decode("utf-8")
        suffix = relative.suffix.lower()
        methods = []
        if suffix == ".py":
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    methods.append({
                        "name": node.name, "first_line": node.lineno,
                        "last_line": node.end_lineno,
                    })
        match_paths = []
        for candidate in source_files:
            if candidate == file:
                continue
            try:
                content = candidate.read_text()
            except (OSError, UnicodeError):
                continue
            if row["id"] in content:
                match_paths.append(str(candidate.relative_to(root)))
        match_paths.sort()
        sections = sections_of(text) if suffix == ".md" else []
        refs.append({
            "id": row["id"],
            "legacy_registry_version": row["version"],
            "legacy_registry_lifecycle": row["lifecycle"],
            "legacy_enabled": True,
            "legacy_source": str(relative),
            "source_blob_sha": blob_sha(file),
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "source_size_bytes": len(data),
            "source_format": suffix.lstrip("."),
            "section_map": sections,
            "python_symbols": methods,
            "implementation_mentions_unreviewed": match_paths,
            "registry_allowed_mutations": sorted(
                row.get("autonomy", {}).get("allowed_capabilities", [])
            ),
            "mapping_is_not_parity_or_authority": True,
            "json_source_conversion_accepted": False,
            "live_approval_granted_by_map": False,
        })
    if len(refs) != len({item["id"] for item in refs}):
        raise RuntimeError("DUPLICATE_LEGACY_SOURCE_ID")
    return {
        "registry_blob_sha": blob_sha(root / REGISTRY),
        "count": len(refs),
        "markdown": sum(x["source_format"] == "md" for x in refs),
        "python": sum(x["source_format"] == "py" for x in refs),
        "entries": refs,
    }


def publish(root: Path = ROOT) -> dict[str, Any]:
    report = build(root)
    target = root / OUTPUT
    target.mkdir(parents=True, exist_ok=True)
    for item in report["entries"]:
        path = target / (item["id"] + ".source-map.json")
        path.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n")
    summary = {
        "registry_blob_sha": report["registry_blob_sha"],
        "count": report["count"],
        "markdown": report["markdown"],
        "python": report["python"],
        "source_maps": [
            {"id": row["id"], "source": row["legacy_source"],
             "source_blob_sha": row["source_blob_sha"]}
            for row in report["entries"]
        ],
    }
    (target / "INDEX.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return report


if __name__ == "__main__":
    result = publish()
    print(f"source_maps={result['count']} markdown={result['markdown']} "
          f"python={result['python']}")
    print("versioned maps generated; these are source indices, NOT converted playbooks")
