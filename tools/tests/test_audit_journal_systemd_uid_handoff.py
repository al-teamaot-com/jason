"""Prevent repeating Ubuntu systemd CAP_SETUID / NoNewPrivileges UID handoff EPERM."""
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]/"infrastructure/jason-audit-journal"
UNITS=(
 "jason-audit-journal-release.service",
 "jason-audit-journal-maintenance.service",
 "jason-audit-journal-data-recovery.service",
)

@pytest.mark.parametrize("unit",UNITS)
def test_minimal_ambient_capability_enables_fixed_writer_uid_without_weaker_nnp(unit):
 text=(ROOT/unit).read_text()
 lines=[line.strip() for line in text.splitlines() if line and not line.startswith("#")]
 assert lines.count("User=root")==1
 assert lines.count("NoNewPrivileges=true")==1
 assert lines.count("AmbientCapabilities=CAP_SETUID")==1
 assert lines.count("CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_FOWNER CAP_SETUID CAP_SETGID CAP_SYS_ADMIN CAP_SYS_PTRACE CAP_KILL CAP_AUDIT_WRITE")==1
 assert "NoNewPrivileges=false" not in lines
 assert not any(line.startswith("AmbientCapabilities=") and line!="AmbientCapabilities=CAP_SETUID" for line in lines)
 assert not any("CAP_SYS_RESOURCE" in line for line in lines)

@pytest.mark.parametrize("unit",UNITS)
def test_no_disruptive_new_unit_commands(unit):
 text=(ROOT/unit).read_text()
 assert not any(v in text for v in ("/usr/bin/systemctl restart","/usr/bin/reboot","/sbin/reboot","--force","--privileged"))
