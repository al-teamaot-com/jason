from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from jason_runtime.provider_read_credentials import (
    ProviderRuntimeCredentialError,
    build_provider_read_specs,
    inspect_private_source,
    preflight_provider_read_runtime_credentials,
    stage_provider_read_runtime_credentials,
)


def _fixture_specs(tmp_path: Path):
    bootstrap = tmp_path / "bootstrap"
    runtime = tmp_path / "runtime"
    specs = build_provider_read_specs(
        bootstrap_root=bootstrap,
        runtime_host_root=runtime,
    )
    for index, item in enumerate(specs, start=1):
        item.source.parent.mkdir(parents=True, exist_ok=True)
        item.source.write_text(f"opaque-test-value-{index}\n", encoding="utf-8")
        item.source.chmod(0o600)
    return specs, runtime


def test_default_provider_layout_keeps_approles_separate() -> None:
    specs = build_provider_read_specs()
    destinations = {item.provider: set() for item in specs}
    sources = {item.provider: set() for item in specs}
    for item in specs:
        destinations[item.provider].add(item.destination.parent.name)
        sources[item.provider].add(item.source.parent.name)

    assert destinations["it_glue"] == {"it-glue"}
    assert destinations["autotask"] == {"autotask"}
    assert sources["it_glue"] == {"itglue-read-approle"}
    assert sources["autotask"] == {"autotask-read-approle"}
    assert {item.destination.name for item in specs} == {"role_id", "secret_id"}
    assert {item.source.name for item in specs} == {"role-id", "secret-id"}


def test_preflight_reads_metadata_only_and_never_opens_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs, _ = _fixture_specs(tmp_path)

    def denied_open(*args, **kwargs):
        raise AssertionError("credential content must not be opened by preflight")

    monkeypatch.setattr(os, "open", denied_open)
    evidence = preflight_provider_read_runtime_credentials(
        specs=specs,
        expected_source_owner_uid=os.getuid(),
    )

    assert evidence["status"] == "credential_staging_preflight_pass"
    assert evidence["source_content_read"] is False
    assert evidence["destination_content_written"] is False
    assert evidence["provider_network_contacted"] is False
    assert evidence["openbao_contacted"] is False
    assert evidence["credential_values_printed"] is False
    assert evidence["source_files_changed"] is False


def test_private_source_rejects_symlink_and_broad_permissions(tmp_path: Path) -> None:
    source = tmp_path / "role-id"
    source.write_text("opaque\n", encoding="utf-8")
    source.chmod(0o644)

    with pytest.raises(ProviderRuntimeCredentialError, match="permissions are too broad"):
        inspect_private_source(source, expected_owner_uid=os.getuid())

    source.chmod(0o600)
    link = tmp_path / "role-link"
    link.symlink_to(source)
    with pytest.raises(ProviderRuntimeCredentialError, match="must not be a symlink"):
        inspect_private_source(link, expected_owner_uid=os.getuid())


def test_stage_requires_root_even_when_sources_are_valid(tmp_path: Path) -> None:
    specs, _ = _fixture_specs(tmp_path)
    if os.geteuid() == 0:
        pytest.skip("runner is root; non-root gate is covered by source contract inspection")
    with pytest.raises(PermissionError, match="must run as root"):
        stage_provider_read_runtime_credentials(
            specs=specs,
            runtime_uid=os.getuid(),
            runtime_gid=os.getgid(),
            expected_source_owner_uid=os.getuid(),
            runtime_directory_owner_uid=os.getuid(),
            runtime_directory_owner_gid=os.getgid(),
        )


def test_stage_creates_opaque_0400_runtime_copies_without_changing_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs, runtime = _fixture_specs(tmp_path)
    before = {
        item.source: (
            os.lstat(item.source).st_ino,
            stat.S_IMODE(os.lstat(item.source).st_mode),
            item.source.read_bytes(),
        )
        for item in specs
    }
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    evidence = stage_provider_read_runtime_credentials(
        specs=specs,
        runtime_uid=os.getuid(),
        runtime_gid=os.getgid(),
        expected_source_owner_uid=os.getuid(),
        runtime_directory_owner_uid=os.getuid(),
        runtime_directory_owner_gid=os.getgid(),
    )

    assert evidence["status"] == "credential_staging_pass"
    assert evidence["credential_values_printed"] is False
    assert evidence["provider_network_contacted"] is False
    assert evidence["openbao_contacted"] is False
    assert evidence["source_files_changed"] is False
    assert evidence["destination_mode"] == "0400"

    assert stat.S_IMODE(os.lstat(runtime).st_mode) == 0o700
    for item in specs:
        info = os.lstat(item.destination)
        assert stat.S_ISREG(info.st_mode)
        assert not stat.S_ISLNK(info.st_mode)
        assert stat.S_IMODE(info.st_mode) == 0o400
        assert info.st_uid == os.getuid()
        assert info.st_gid == os.getgid()
        assert item.destination.read_bytes() == before[item.source][2]

        after = os.lstat(item.source)
        assert after.st_ino == before[item.source][0]
        assert stat.S_IMODE(after.st_mode) == before[item.source][1]


def test_stage_denies_overwrite_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs, _ = _fixture_specs(tmp_path)
    first = specs[0]
    first.destination.parent.mkdir(parents=True, exist_ok=True)
    first.destination.parent.chmod(0o700)
    first.destination.write_text("existing\n", encoding="utf-8")
    existing = first.destination.read_bytes()

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(
        ProviderRuntimeCredentialError,
        match="replacement requires explicit approval",
    ):
        stage_provider_read_runtime_credentials(
            specs=specs,
            runtime_uid=os.getuid(),
            runtime_gid=os.getgid(),
            expected_source_owner_uid=os.getuid(),
            runtime_directory_owner_uid=os.getuid(),
            runtime_directory_owner_gid=os.getgid(),
        )

    assert first.destination.read_bytes() == existing
    assert not any(item.destination.exists() for item in specs[1:])


def test_stage_replace_requires_explicit_true_and_preserves_provider_separation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs, _ = _fixture_specs(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    common = dict(
        specs=specs,
        runtime_uid=os.getuid(),
        runtime_gid=os.getgid(),
        expected_source_owner_uid=os.getuid(),
        runtime_directory_owner_uid=os.getuid(),
        runtime_directory_owner_gid=os.getgid(),
    )
    stage_provider_read_runtime_credentials(**common)

    expected = {}
    for index, item in enumerate(specs, start=10):
        item.source.chmod(0o600)
        item.source.write_text(f"rotated-test-value-{index}\n", encoding="utf-8")
        item.source.chmod(0o600)
        expected[item.destination] = item.source.read_bytes()

    evidence = stage_provider_read_runtime_credentials(
        **common,
        replace_existing=True,
    )
    assert evidence["replace_existing"] is True
    for item in specs:
        assert item.destination.read_bytes() == expected[item.destination]

    itg = {item.destination for item in specs if item.provider == "it_glue"}
    autotask = {item.destination for item in specs if item.provider == "autotask"}
    assert itg.isdisjoint(autotask)
