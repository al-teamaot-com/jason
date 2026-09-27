from pathlib import Path
import json

from tools.documentation_success_reconciler import render_markdown, update_source, write_state
from tools.documentation_impact_gate import DocumentationImpactError, validate_pull_request_body


def test_documentation_impact_requires_exactly_one_outcome():
    validate_pull_request_body(
        "## Documentation impact\n\n- [x] Documentation updated\n- [ ] No documentation impact\n"
    )
    try:
        validate_pull_request_body(
            "## Documentation impact\n\n- [ ] Documentation updated\n- [ ] No documentation impact\n"
        )
    except DocumentationImpactError:
        pass
    else:
        raise AssertionError("missing documentation outcome should fail")


def test_no_documentation_impact_requires_reason():
    try:
        validate_pull_request_body(
            "## Documentation impact\n\n- [ ] Documentation updated\n- [x] No documentation impact\n"
        )
    except DocumentationImpactError:
        pass
    else:
        raise AssertionError("missing no-impact reason should fail")


def test_source_state_is_machine_owned_and_does_not_claim_production(tmp_path: Path):
    state = {"schema_version": "1.0"}
    update_source(state, revision="abc123", run_id="42", run_url="https://example.test/run/42")
    json_path = tmp_path / "state.json"
    md_path = tmp_path / "state.md"
    write_state(json_path, md_path, state)
    loaded = json.loads(json_path.read_text())
    assert loaded["validated_source"]["revision"] == "abc123"
    assert "production" not in loaded
    markdown = md_path.read_text()
    assert "No production alignment has been recorded" in markdown
    assert "does not grant authority" in markdown


def test_rendered_production_state_keeps_source_and_production_distinct():
    state = {
        "schema_version": "1.0",
        "validated_source": {"revision": "newer", "status": "ci_passed"},
        "production": {
            "revision": "older",
            "status": "aligned_and_healthy",
            "runtime": {"health": "healthy", "restart_count": 0},
            "mcp": {"state": "running", "restart_policy": "unless-stopped"},
            "host_release": "/opt/jason/releases/older",
            "host_units": {"one.service": "active"},
            "failed_systemd_units": 0,
            "observed_at": "2026-09-27T00:00:00+00:00",
        },
    }
    markdown = render_markdown(state)
    assert "Revision: `newer`" in markdown
    assert "Revision: `older`" in markdown
    assert "A validated source revision is not proof of production deployment" in markdown


def test_rendered_markdown_has_no_trailing_whitespace():
    markdown = render_markdown({"schema_version": "1.0"})
    assert all(line == line.rstrip() for line in markdown.splitlines())
