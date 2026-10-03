from __future__ import annotations

import json
from pathlib import Path

from tools.runtime_portability_audit import (
    audit_runtime_portability,
    load_rules,
    summarize_findings,
)


ROOT = Path(__file__).resolve().parents[2]


def rules():
    return load_rules(
        ROOT / "config/runtime-portability-rules.v1.json",
        ROOT / "config/schemas/runtime-portability-rules.schema.json",
    )


def test_current_runtime_has_known_portability_blockers():
    findings = audit_runtime_portability(
        repository_root=ROOT,
        rules=rules(),
    )
    summary = summarize_findings(findings)
    assert summary["status"] == "blocked"

    ids = {item.rule_id for item in findings}
    assert "operator-home-path" in ids
    assert "aot-email-domain" in ids
    assert "aot-component-label" in ids
    assert "aot-profile-name" in ids

    paths = {item.path for item in findings}
    assert "infrastructure/jason-runtime/compose.yaml" in paths


def test_findings_do_not_echo_full_runtime_lines():
    findings = audit_runtime_portability(
        repository_root=ROOT,
        rules=rules(),
    )
    for finding in findings:
        assert "\n" not in finding.matched_fragment
        assert len(finding.matched_fragment) < 160
        assert "JASON_" not in finding.matched_fragment


def test_portable_synthetic_runtime_passes(tmp_path):
    root = tmp_path / "repo"
    compose = root / "infrastructure/jason-runtime/compose.yaml"
    compose.parent.mkdir(parents=True)
    compose.write_text(
        """
services:
  runtime:
    image: example/jason@sha256:abc
    environment:
      DEFAULT_SENDER: required-at-runtime
      COMPONENT_NAME: configured-at-runtime
""".lstrip(),
        encoding="utf-8",
    )
    findings = audit_runtime_portability(
        repository_root=root,
        rules=rules(),
    )
    assert summarize_findings(findings)["status"] == "portable"


def test_rules_document_is_machine_readable():
    payload = json.loads(
        (ROOT / "config/runtime-portability-rules.v1.json").read_text()
    )
    assert payload["schema_version"] == "1.0"
    assert payload["scan_globs"]
    assert payload["rules"]
