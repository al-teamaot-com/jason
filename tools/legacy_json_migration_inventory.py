"""Source-only, reproducible inventory of the legacy JSON migration population.

This report describes evidence and blockers; it does not convert or activate a
playbook. The source registry is the only population authority.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

REGISTRY = Path("implementation/autonomous_remediation/playbook_registry.json")
SECTION = re.compile(r"^#{1,3}\s+(\d{1,2})\.\s+(.+)$", re.M)
CAP = re.compile(r"\b(?:service|endpoint|automation|backup|identity|security|print|user|site)\.[a-z][a-z0-9_.:-]+")
TARGET_SECTIONS = list(range(1, 23))


def git_blob_sha(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def inspect_one(root: Path, row: dict) -> dict:
    source = root / row["source"]
    if not source.is_file():
        return {"id": row["id"], "source": row["source"], "error": "SOURCE_MISSING"}
    data = source.read_bytes()
    content = data.decode("utf-8")
    markdown = source.suffix.lower() == ".md"
    headings = {int(m.group(1)): m.group(2).strip() for m in SECTION.finditer(content)}
    discovered = sorted(set(CAP.findall(content)))
    registry_capabilities = sorted(set(row.get("autonomy", {}).get("allowed_capabilities", [])))
    functions = []
    classes = []
    if not markdown:
        tree = ast.parse(content, filename=str(source))
        functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    missing_sections = [n for n in TARGET_SECTIONS if n not in headings] if markdown else TARGET_SECTIONS
    gate_signals = {
        "approval": bool(re.search(r"approval|promot|authoriz", content, re.I)),
        "identity": bool(re.search(r"identit|same.company|same.client|configuration.item", content, re.I)),
        "persistence": bool(re.search(r"persist|durable|resum", content, re.I)),
        "retry": bool(re.search(r"retry|attempt|backoff", content, re.I)),
        "verification": bool(re.search(r"verify|readback|authoritative", content, re.I)),
        "escalation": bool(re.search(r"escalat|human.review|handoff", content, re.I)),
    }
    return {
        "id": row["id"],
        "name": row["name"],
        "version": row["version"],
        "lifecycle": row["lifecycle"],
        "enabled": row["enabled"],
        "source": row["source"],
        "source_format": "markdown" if markdown else "python",
        "source_git_blob_sha": git_blob_sha(source),
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "section_numbers_found": sorted(headings),
        "missing_canonical_sections": missing_sections,
        "registry_capabilities": registry_capabilities,
        "source_capability_references_unreviewed": discovered,
        "python_functions": functions,
        "python_classes": classes,
        "governance_signal_presence_not_semantic_proof": gate_signals,
        "migration_status": "requires_semantic_mapping_and_independent_acceptance",
        "parity_verified": False,
        "isolated_shadow_verified": False,
        "known_architecture_gap": "External trusted fact/state adapter must guarantee current reads, gating, persisted resume, exact approvals, provider output and readback; plain JSON validation cannot prove parity.",
    }


def build(root: Path) -> dict:
    path = root / REGISTRY
    raw = json.loads(path.read_text())
    rows = [p for p in raw["playbooks"] if p.get("enabled") is True]
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_LEGACY_IDS")
    entries = [inspect_one(root, row) for row in rows]
    missing = [x for x in entries if "error" in x]
    if missing:
        raise ValueError(f"SOURCE_MISSING: {[x['id'] for x in missing]}")
    return {
        "source_registry": str(REGISTRY),
        "source_registry_git_blob_sha": git_blob_sha(path),
        "population_count": len(entries),
        "markdown": sum(x["source_format"] == "markdown" for x in entries),
        "python": sum(x["source_format"] == "python" for x in entries),
        "production_activation_permitted": False,
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="docs/playbooks/json/migration/source-audit-20261119.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report = build(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"verified={report['population_count']} markdown={report['markdown']} python={report['python']}")
    for row in report["entries"]:
        print(row["id"], "sections_missing=" + str(len(row["missing_canonical_sections"])),
              "source_git_blob_sha=" + row["source_git_blob_sha"])
    print("report:", output)


if __name__ == "__main__":
    main()
