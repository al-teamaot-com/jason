"""Review six inert PMv4 timer/path pairs without deploying systemd units."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil

import pytest

from tools import pmv4_e_replacement_unit_bundle as unit
from tools import pmv4_e_scheduler_parity as parity
from tools import pmv4_e_unit_admission as guard


ROOT=Path(__file__).resolve().parents[1]


def test_exact_six_scheduled_controls_have_twelve_inert_reviewed_source_files():
    expected=unit.generate()
    result=unit.validate()
    assert len(expected)==12
    assert result["status"]=="source_only_units_reviewed_no_production_install"
    assert result["trigger_count"]==result["service_count"]==6
    assert result["guarded_by_future_exact_root_acceptance"] is True
    assert result["self_heal_and_reconcile_migration_accepted"] is False
    assert result["root_install_authorized"] is False
    assert result["production_mutations"] is False
    assert set(result["source_sha256"])==set(expected)


@pytest.mark.parametrize("pair",unit.PAIRS)
def test_each_unit_preserves_existing_backend_while_refusing_unauthorized_start(pair):
    generated=unit.generate()
    directory="user" if pair.side=="user" else "system"
    target=unit.TARGET/directory
    service=generated[str(target/pair.new_service)].decode()
    trigger=generated[str(target/pair.new_trigger)].decode()
    old_service=unit.safe_source(ROOT,pair.side,pair.old_service).decode()
    old_trigger=unit.safe_source(ROOT,pair.side,pair.old_trigger).decode()
    guard_line=("ExecCondition=/usr/bin/python3 "+unit.ADMISSION+
                " --mode "+pair.mode+"\n")
    assert service.count(guard_line)==1
    assert service.count("[Service]")==1
    assert service.count("Type=oneshot")==1
    assert service.replace(guard_line,"")==old_service
    assert trigger.replace("Unit="+pair.new_service,
                           "Unit="+pair.old_service)==old_trigger
    assert "Unit="+pair.new_service in trigger
    assert pair.new_trigger in (
        parity.USER_REPLACEMENT if pair.side=="user"
        else parity.ROOT_REPLACEMENT
    )
    assert guard.ROLE_UNITS[pair.mode][0]==pair.new_trigger
    assert guard.ROLE_UNITS[pair.mode][1]==(pair.side=="system")


def test_five_minute_engineering_approval_and_release_cadence_preserved():
    generated=unit.generate()
    for pair in unit.PAIRS:
        if pair.side!="user":
            continue
        timer=generated[str(unit.TARGET/"user"/pair.new_trigger)].decode()
        assert "OnCalendar=*-*-* *:00/5:00 America/New_York" in timer
        assert "Persistent=true" in timer
        assert "AccuracySec=15s" in timer
    assert len([p for p in unit.PAIRS if p.side=="user"])==3


def test_root_transition_readback_and_reconcile_activation_kept():
    generated=unit.generate()
    root=unit.TARGET/"system"
    transition=generated[str(root/"jason-pmv4-component-transition.timer")].decode()
    readback=generated[str(root/"jason-pmv4-component-readback.timer")].decode()
    reconcile=generated[str(root/"jason-pmv4-component-reconcile.path")].decode()
    assert "OnUnitActiveSec=5s" in transition
    assert "OnUnitActiveSec=30s" in readback
    assert "DirectoryNotEmpty=" in reconcile
    assert "Unit=jason-pmv4-component-reconcile.service" in reconcile


def test_no_unit_restarts_jason_runtime_or_bypasses_native_security():
    generated=unit.generate()
    for path,data in generated.items():
        raw=data.decode()
        assert "systemctl stop" not in raw
        assert "systemctl disable" not in raw
        assert "docker restart" not in raw
        assert "force_close_breaker" not in raw
        if path.endswith(".service"):
            # Preserve the original compiled unit's sandbox clauses.
            pair=next(x for x in unit.PAIRS
                if path.endswith(x.new_service))
            original=unit.safe_source(ROOT,pair.side,pair.old_service).decode()
            if "NoNewPrivileges=true" in original:
                assert "NoNewPrivileges=true" in raw
        assert "Unit=jason-release-" not in raw
        assert not any(s in raw for s in (
            "Environment=JASON_PMV4_SKIP_AUTH",
            "Environment=JASON_PMV4_OVERRIDE_FREEZE",
            "PMV4_ROOT_APPROVAL_USED=true",
        ))


def test_root_backend_reconcile_remains_blocking_dependency_in_source_only_stage():
    source=(ROOT/"tools/reconcile_production_host_services.sh").read_text()
    assert "install_support_repair_host_worker.py" in source
    assert "--activate" in source
    assert unit.validate()["self_heal_and_reconcile_migration_accepted"] is False


def test_modified_generated_unit_fails_deterministic_bundle_readback(tmp_path):
    # Run all mutations inside a disposable tree, never change Git files.
    for pair in unit.PAIRS:
        folder=unit.SOURCE/("user" if pair.side=="user" else "")
        for name in (pair.old_service,pair.old_trigger):
            target=tmp_path/folder/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/folder/name).read_bytes())
    generated=unit.generate(base=tmp_path)
    for relative,data in generated.items():
        target=tmp_path/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    target=tmp_path/unit.TARGET/"user/jason-pmv4-engineering.service"
    source=target.read_bytes()
    target.write_bytes(source.replace(
        b"--max-passes 3",b"--max-passes 999"))
    with pytest.raises(unit.PMv4EUnitBundleDenied,
                       match="REVIEWED_REPLACEMENT_UNIT_DIFFERS"):
        unit.validate(base=tmp_path)
    target.write_bytes(source)
    assert unit.validate(base=tmp_path)["source_unit_count"]==12


def test_missing_legacy_source_cannot_create_unreviewed_replacement(tmp_path):
    with pytest.raises(unit.PMv4EUnitBundleDenied,
                       match="LEGACY_UNIT_MISSING"):
        unit.generate(base=tmp_path)


def test_generator_is_pure_and_has_no_automatic_activation():
    source=Path(unit.__file__).read_text()
    for forbidden in (
        "systemctl enable","systemctl disable","systemctl start",
        "docker compose","os.replace(","os.chown(","os.chmod(",
        "break_circuit",'"owner_approval_issued":True',
    ):
        assert forbidden not in source
