import json
from pathlib import Path

from jason_runtime.constant_contact_reconcile_entrypoint import main


ROOT = Path(__file__).resolve().parents[3]
INFRA = ROOT / "infrastructure/constant-contact-readback"


def test_packaged_cli_stays_dormant_when_profile_unset(monkeypatch, capsys):
    monkeypatch.delenv("JASON_CONSTANT_CONTACT_RECONCILE_PROFILE", raising=False)
    assert main(["--check-only"]) == 0
    assert '"executed": false' in capsys.readouterr().out
    assert main(["--run-once"]) == 2
    assert '"disabled"' in capsys.readouterr().out


def test_independent_timer_never_installs_enabled():
    service = (INFRA / "systemd/jason-constant-contact-reconcile.service").read_text()
    timer = (INFRA / "systemd/jason-constant-contact-reconcile.timer").read_text()
    installer = (INFRA / "install.sh").read_text()
    desired = json.loads((ROOT / "config/production-desired-state.json").read_text())
    assert "docker exec" in service
    assert "jason_runtime.constant_contact_reconcile_entrypoint" in service
    assert "OnCalendar=*:0/15" in timer
    assert "Persistent=false" in timer
    assert "systemctl --user enable" not in installer
    assert "systemctl --user start" not in installer
    assert "jason-constant-contact-reconcile.timer" in desired["allowed_user_units"]
    assert "jason-constant-contact-reconcile.timer" not in desired["required_user_units"]
