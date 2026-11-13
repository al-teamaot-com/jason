"""Second-drive engineering worktree acceptance: no unsafe root fallback."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import jason_engineering_worktree_storage as storage


@pytest.fixture()
def storage_roots(monkeypatch, tmp_path):
    mount = tmp_path / "independent-archive"
    mount.mkdir()
    root = mount / "engineering-worktrees"
    legacy = tmp_path / "legacy-primary"
    legacy.mkdir()
    monkeypatch.setattr(storage, "ARCHIVE_MOUNT", mount)
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", root)
    monkeypatch.setattr(storage, "LEGACY_ROOT", legacy)
    return mount, root, legacy


def test_new_worktree_is_placed_on_second_drive_and_uses_private_roots(
    storage_roots, monkeypatch
):
    mount, root, legacy = storage_roots
    monkeypatch.setattr(storage, "_check_archive", lambda: None)
    selected = storage.path_for("owner-approved-development", "issue-2468")
    assert selected == root / "owner-approved-development" / "issue-2468"
    storage.prepare_parent(selected)
    assert selected.parent.is_dir()
    assert not selected.exists()
    assert root.stat().st_mode & 0o777 == 0o700
    assert selected.parent.stat().st_mode & 0o777 == 0o700
    assert not (legacy / "owner-approved-development").exists()


def test_existing_old_worktree_is_resumed_without_migration(storage_roots):
    _, root, legacy = storage_roots
    old = legacy / "support-repair" / "support-dev-123"
    old.mkdir(parents=True)
    chosen = storage.path_for("support-repair", "support-dev-123")
    assert chosen == old
    storage.prepare_parent(chosen)
    assert old.is_dir()
    assert not root.exists()


def test_missing_archive_refuses_new_work_without_fallback(storage_roots, monkeypatch):
    _, root, legacy = storage_roots
    monkeypatch.setattr(os.path, "ismount", lambda _path: False)
    target = storage.path_for("todo-closure", "todo-ops-123")
    with pytest.raises(storage.EngineeringStorageUnavailable, match="archive mount"):
        storage.prepare_parent(target)
    assert not root.exists()
    assert not (legacy / "todo-closure").exists()


def test_root_alias_refuses_work_even_when_called_a_mount(storage_roots, monkeypatch):
    mount, root, _ = storage_roots
    monkeypatch.setattr(os.path, "ismount", lambda _path: True)
    original_stat = Path.stat

    def aliased_root_stat(path, *args, **kwargs):
        if path == Path("/"):
            return original_stat(mount)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", aliased_root_stat)
    with pytest.raises(storage.EngineeringStorageUnavailable, match="aliases primary"):
        storage.prepare_parent(root / "support-repair" / "support-dev-888")
    assert not root.exists()


def test_symlink_to_protected_or_legacy_tree_refused(storage_roots, monkeypatch):
    _, root, legacy = storage_roots
    (legacy / "support-repair").symlink_to(root, target_is_directory=True)
    with pytest.raises(storage.EngineeringStorageUnavailable, match="symlink"):
        storage.path_for("support-repair", "support-dev-999")


@pytest.mark.parametrize("name", ["../oops", "foo/bar", "/tmp", "", "a" * 151])
def test_untrusted_relative_worktree_name_refused(storage_roots, name):
    with pytest.raises(storage.EngineeringStorageUnavailable):
        storage.path_for("support-repair", name)


def test_cannot_create_new_primary_worktree(storage_roots):
    _, _, legacy = storage_roots
    target = legacy / "owner-approved-development" / "issue-3"
    with pytest.raises(storage.EngineeringStorageUnavailable, match="primary"):
        storage.prepare_parent(target)
    assert not target.exists()


def test_current_service_and_installer_contracts_are_second_drive_aware():
    repo = Path(__file__).resolve().parents[2]
    installer = (repo / "tools/install_support_repair_host_worker.py").read_text()
    assert "worktree_storage.prepare_family(family)" in installer
    assert "_copy(worktree_storage_module, install_root" in installer
    for unit in (
        "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service",
        "infrastructure/openclaw-operations/systemd/user/jason-autonomous-repair-runner.service",
        "infrastructure/isolated-services/jason-independent-support.service",
        "infrastructure/isolated-services/jason-independent-development.service",
        "infrastructure/isolated-services/jason-independent-todo-intake.service",
        "infrastructure/isolated-services/jason-independent-supervisor.service",
        "infrastructure/openclaw-operations/systemd/jason-documentation-reconciliation.service",
    ):
        assert "-/srv/jason/archive/engineering-worktrees/" in (repo / unit).read_text()


def test_archive_low_allocatable_space_blocks_new_worktree(storage_roots, monkeypatch):
    mount, root, _ = storage_roots
    monkeypatch.setattr(os.path, "ismount", lambda _path: True)
    original_stat = Path.stat

    def separate_root_stat(path, *args, **kwargs):
        if path == Path("/"):
            fake = original_stat(mount)
            return type("RootStat", (), {"st_dev": fake.st_dev + 1})()
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", separate_root_stat)
    real_statvfs = os.statvfs

    def low_free_statvfs(path):
        if path == mount:
            return type("VFS", (), {
                "f_frsize": 4096,
                "f_bavail": 1024,
                "f_blocks": 50000,
                "f_bfree": 1024,
                "f_files": 1000000,
                "f_favail": 500000,
            })()
        return real_statvfs(path)

    monkeypatch.setattr(os, "statvfs", low_free_statvfs)
    with pytest.raises(storage.EngineeringStorageUnavailable, match="capacity"):
        storage.prepare_parent(root / "support-repair" / "support-dev-111")
    assert not root.exists()


def test_archive_root_symlink_refused_before_new_worktree(storage_roots, monkeypatch):
    mount, root, _ = storage_roots
    monkeypatch.setattr(storage, "_check_archive", lambda: None)
    alternate = mount / "alternate"
    alternate.mkdir()
    root.symlink_to(alternate, target_is_directory=True)
    with pytest.raises(storage.EngineeringStorageUnavailable, match="symlink"):
        storage.prepare_parent(root / "support-repair" / "support-dev-222")
