"""Exact-source integrity for all 19 conversion traceability maps."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from tools.legacy_json_migration_source_maps import build, publish, OUTPUT, ROOT


def test_all_legacy_sources_have_exact_line_hash_maps():
    report = build(ROOT)
    assert report["count"] == 19
    assert report["markdown"] == 18
    assert report["python"] == 1
    assert len({r["id"] for r in report["entries"]}) == 19
    for entry in report["entries"]:
        source = ROOT / entry["legacy_source"]
        raw = source.read_bytes()
        assert sha256(raw).hexdigest() == entry["source_sha256"]
        assert entry["source_blob_sha"]
        assert entry["json_source_conversion_accepted"] is False
        assert entry["live_approval_granted_by_map"] is False
        for section in entry["section_map"]:
            lines = source.read_text().splitlines(keepends=True)
            content = "".join(lines[section["first_line"] - 1:section["last_line"]])
            assert sha256(content.encode("utf-8")).hexdigest() == section["section_sha256"]
        if entry["source_format"] == "md":
            assert any(x["number"] == 1 for x in entry["section_map"])
        else:
            assert entry["python_symbols"]


def test_source_map_generation_is_deterministic():
    before = {
        str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
        for path in (ROOT / OUTPUT).glob("*.json")
    }
    publish(ROOT)
    after = {
        str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
        for path in (ROOT / OUTPUT).glob("*.json")
    }
    assert before == after
    assert len(after) == 20
    index = json.loads((ROOT / OUTPUT / "INDEX.json").read_text())
    assert index["count"] == 19
