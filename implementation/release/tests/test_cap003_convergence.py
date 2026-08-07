from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_cap003_ticket_focus_is_the_convergence_path() -> None:
    tool = (REPO_ROOT / "tools" / "autotask_business_context.py").read_text(
        encoding="utf-8"
    )
    service = (
        REPO_ROOT
        / "implementation"
        / "cap-003"
        / "src"
        / "jason_cap_003"
        / "service.py"
    ).read_text(encoding="utf-8")
    context = (
        REPO_ROOT
        / "implementation"
        / "cap-003"
        / "src"
        / "jason_cap_003"
        / "context.py"
    ).read_text(encoding="utf-8")

    assert '"--ticket-number"' in tool
    assert 'capability_name = "autotask.business.context"' in service
    assert "focused_ticket_number" in service
    assert 'entity_field="ticketNumber"' in context
    assert 'error_code="TICKET_FOCUS_NOT_FOUND"' in context
    assert 'error_code="TICKET_FOCUS_COMPANY_MISMATCH"' in context


def test_cap002_duplicate_runtime_is_retired() -> None:
    retired_root = REPO_ROOT / "implementation" / "cap-002"
    tracked_runtime_files = [
        path
        for path in retired_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    ] if retired_root.exists() else []

    assert tracked_runtime_files == []
    assert not (REPO_ROOT / "tools" / "ticket_intelligence.py").exists()


def test_retired_ticket_capability_cannot_be_reintroduced() -> None:
    implementation = REPO_ROOT / "implementation"
    for path in implementation.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "support.ticket.analyze" not in text
        assert "jason_cap_002" not in text


def test_cap003_evidence_distinguishes_requested_and_canonical_identity() -> None:
    service = (
        REPO_ROOT
        / "implementation"
        / "cap-003"
        / "src"
        / "jason_cap_003"
        / "service.py"
    ).read_text(encoding="utf-8")
    assert "requested_company_name" in service
    assert "canonical_company_name" in service
    assert '"counts_are_bounded_reads": True' in service


def test_showcase_installer_reloads_observability_configuration() -> None:
    installer = (
        REPO_ROOT / "infrastructure" / "showcase" / "install_showcase.sh"
    ).read_text(encoding="utf-8")

    assert "restart prometheus grafana" in installer
    assert "http://127.0.0.1:9090/-/healthy" in installer
    assert "http://127.0.0.1:3000/api/health" in installer
