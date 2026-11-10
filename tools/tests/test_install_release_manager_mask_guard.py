"""Never overwrite the protected release-manager systemd mask by copying through it."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tools import install_release_manager as installer


def test_copy_refuses_existing_mask_without_following_link(tmp_path):
    source=tmp_path/"approved.timer"
    source.write_text("[Timer]\nOnUnitActiveSec=300\n")
    sink=tmp_path/"device-file-surrogate"
    sink.write_bytes(b"MUST_NOT_CHANGE")
    unit=tmp_path/"installed.timer"
    unit.symlink_to(sink)
    with pytest.raises(PermissionError,match="masked/symlinked"):
        installer.copy_mode(source,unit,0o644)
    assert unit.is_symlink()
    assert sink.read_bytes()==b"MUST_NOT_CHANGE"


def test_copy_uses_atomic_replacement_of_regular_destination(tmp_path):
    src=tmp_path/"approved.service"
    src.write_bytes(b"reviewed-source\n")
    dst=tmp_path/"installed.service"
    dst.write_bytes(b"old-source\n")
    installer.copy_mode(src,dst,0o644)
    assert dst.read_bytes()==b"reviewed-source\n"
    assert (dst.stat().st_mode&0o777)==0o644
    assert not dst.is_symlink()
    assert not list(tmp_path.glob(".release-manager-install-*"))


def test_copy_refuses_symlink_source_and_directory_destination(tmp_path):
    target=tmp_path/"source-file"
    target.write_text("reviewed")
    link=tmp_path/"source-link"
    link.symlink_to(target)
    destination=tmp_path/"destination"
    with pytest.raises(PermissionError,match="source"):
        installer.copy_mode(link,destination,0o644)
    assert not destination.exists()
    with pytest.raises(PermissionError,match="destination"):
        installer.copy_mode(target,tmp_path,0o644)


def test_preflight_rejects_mask_before_any_install_or_activation(
    tmp_path,monkeypatch,
):
    home=tmp_path/"home"
    unit_dir=home/".config/systemd/user"
    unit_dir.mkdir(parents=True)
    (unit_dir/"jason-release-manager.timer").symlink_to("/dev/null")
    lib=home/".local/lib/jason"
    state=tmp_path/"private-state"
    monkeypatch.setattr(installer,"UNIT_DIR",unit_dir)
    monkeypatch.setattr(installer,"LIB",lib)
    monkeypatch.setattr(installer,"STATE",state)
    monkeypatch.setattr(sys,"argv",["install_release_manager.py","--activate"])
    with pytest.raises(PermissionError,match="governed incident recovery"):
        installer.main()
    assert not lib.exists()
    assert not state.exists()
    assert (unit_dir/"jason-release-manager.timer").is_symlink()
