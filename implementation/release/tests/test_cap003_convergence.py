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

    assert '"--ticket-number"' in tool
    assert 'capability_name = "autotask.business.context"' in service
    assert 'error_code="TICKET_FOCUS_NOT_FOUND"' in service
    assert "focused_ticket_number" in service


def test_cap002_is_not_retired_before_parity_closeout() -> None:
    assert (REPO_ROOT / "implementation" / "cap-002").is_dir()


def test_showcase_installer_reloads_observability_configuration() -> None:
    installer = (
        REPO_ROOT / "infrastructure" / "showcase" / "install_showcase.sh"
    ).read_text(encoding="utf-8")

    assert "restart prometheus grafana" in installer
    assert "http://127.0.0.1:9090/-/healthy" in installer
    assert "http://127.0.0.1:3000/api/health" in installer
