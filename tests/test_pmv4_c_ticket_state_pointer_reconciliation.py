from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))

from tools.pmv4_host_release_guard import (
    HostGateDenied,select_trusted_ticket_ledger,
)
import jason_self_heal_watchdog as selfheal


@pytest.fixture
def roots(tmp_path):
    legacy=tmp_path/"old"
    migrated=tmp_path/"new"
    legacy.mkdir(mode=0o700);migrated.mkdir(mode=0o700)
    legacy.chmod(0o700);migrated.chmod(0o700)
    return (legacy/"autonomy-operational-work.sqlite3",
            migrated/"autonomy-operational-work.sqlite3")


def create(path):
    path.write_bytes(b"synthetic canonical ticket metadata")
    path.chmod(0o600)
    return path


def test_legacy_and_migrated_are_independently_recognized(roots):
    old,new=roots
    uid=os.getuid()
    with pytest.raises(HostGateDenied,match="CANONICAL_OWNER_AMBIGUOUS"):
        select_trusted_ticket_ledger(old,new,uid=uid)
    create(old)
    assert select_trusted_ticket_ledger(old,new,uid=uid)==old
    assert selfheal.canonical_autonomy_db(old,new,uid=uid)==old
    old.unlink()
    create(new)
    assert select_trusted_ticket_ledger(old,new,uid=uid)==new
    assert selfheal.canonical_autonomy_db(old,new,uid=uid)==new


def test_duplicate_paths_fail_closed(roots):
    old,new=roots
    create(old);create(new)
    with pytest.raises(HostGateDenied,match="CANONICAL_OWNER_AMBIGUOUS"):
        select_trusted_ticket_ledger(old,new,uid=os.getuid())
    with pytest.raises(ValueError,match="AUTONOMY_LEDGER_AMBIGUOUS"):
        selfheal.canonical_autonomy_db(old,new,uid=os.getuid())


@pytest.mark.parametrize("bad",("0644","symlink","hardlink"))
def test_untrusted_migrated_db_refused(roots,bad):
    old,new=roots
    if bad=="symlink":
        new.symlink_to(create(old))
    else:
        create(new)
        if bad=="0644":new.chmod(0o644)
        else:os.link(new,new.parent/"other_link")
    with pytest.raises(HostGateDenied):
        select_trusted_ticket_ledger(old,new,uid=os.getuid())
    with pytest.raises(ValueError):
        selfheal.canonical_autonomy_db(old,new,uid=os.getuid())


def test_untrusted_directory_refused(roots):
    old,new=roots
    create(new)
    new.parent.chmod(0o755)
    with pytest.raises(HostGateDenied,match="UNTRUSTED"):
        select_trusted_ticket_ledger(old,new,uid=os.getuid())


def test_readonly_no_new_db_created(roots):
    old,new=roots
    with pytest.raises(HostGateDenied):
        select_trusted_ticket_ledger(old,new,uid=os.getuid())
    assert not old.exists() and not new.exists()


def test_protected_breaker_is_still_mandatory():
    from tools.pmv4_host_release_guard import IndependentHostGuard
    with pytest.raises(HostGateDenied,match="PROTECTED_BREAKER_CANNOT_BE_DISABLED"):
        IndependentHostGuard(production=True,enforce_protected_control=False)
