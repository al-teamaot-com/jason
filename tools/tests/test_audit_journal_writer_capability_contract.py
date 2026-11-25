"""Regression: UID1000 helper must be spawnable by hardened root services.

Static tests are necessary but insufficient: live systemd execution and child
CapEff=0 must be checked before promoting a production candidate.
"""
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]
UNIT = ROOT / "infrastructure" / "jason-audit-journal"
SERVICES = (
    "jason-audit-journal-release.service",
    "jason-audit-journal-maintenance.service",
    "jason-audit-journal-data-recovery.service",
)


def _require_hardened_uid_handoff(text):
    assert re.search(r"(?m)^User=root$", text)
    assert re.search(r"(?m)^Group=root$", text)
    assert re.search(r"(?m)^NoNewPrivileges=true$", text)
    assert re.findall(r"(?m)^AmbientCapabilities=(.*)$", text) == ["CAP_SETUID"]
    caps = re.findall(r"(?m)^CapabilityBoundingSet=(.*)$", text)
    assert len(caps) == 1
    assert "CAP_SETUID" in caps[0].split()
    assert "CAP_SETGID" in caps[0].split()
    assert "CAP_SYS_RESOURCE" not in caps[0].split()
    assert "CAP_SETPCAP" not in caps[0].split()
    assert re.search(r"(?m)^RestrictAddressFamilies=AF_UNIX AF_NETLINK$", text)
    assert "runuser " not in text
    assert "/usr/bin/python3 -I -B -c" in text
    assert "audit_journal_control.py" in text
    assert "ConditionPathExists=" in text
    assert "RestrictNamespaces=no" not in text


@pytest.mark.parametrize("name", SERVICES)
def test_real_root_unit_source_preserves_fixed_uid_helper_capability(name):
    _require_hardened_uid_handoff((UNIT / name).read_text())


@pytest.mark.parametrize("failure", ("missing_ambient", "wrong_ambient", "missing_bounding", "nnp_removed"))
def test_unit_contract_rejects_regressions(failure):
    text = (UNIT / SERVICES[0]).read_text()
    assert "AmbientCapabilities=CAP_SETUID" in text
    assert "NoNewPrivileges=true" in text
    if failure == "missing_ambient":
        text = text.replace("AmbientCapabilities=CAP_SETUID", "")
    if failure == "wrong_ambient":
        text = text.replace("AmbientCapabilities=CAP_SETUID", "AmbientCapabilities=CAP_SYS_RESOURCE")
    if failure == "missing_bounding":
        text = text.replace("CAP_SETUID CAP_SETGID", "CAP_SETGID")
    if failure == "nnp_removed":
        text = text.replace("NoNewPrivileges=true", "NoNewPrivileges=false")
    with pytest.raises(AssertionError):
        _require_hardened_uid_handoff(text)


def test_installed_python_writer_stays_unprivileged_with_no_groups():
    source = (ROOT / "tools/audit_journal_control.py").read_text()
    assert '"user":1000,"group":1000,"extra_groups":()' in source
    assert "start_new_session=True,**self.writer_identity()" in source
    assert "CapEff" not in source  # No new privilege acquisition in writer
