import os
from pathlib import Path
import subprocess

import pytest

from tools import independent_component_release_bundle as b


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )
    return p.stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    for rel in b.FILES:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "" if path.name == "__init__.py" else
            "# source-only trusted module fixture\n"
        )
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Jason Test", "-c", "user.email=jason@test.invalid",
        "commit", "-qm", "fixture")
    return repo, git(repo, "rev-parse", "HEAD")


def test_prepares_exact_pinned_source_without_production_install(tmp_path):
    repo, sha = repository(tmp_path)
    dest = tmp_path / "staged"
    result = b.prepare(repo, sha, dest)
    assert result["status"] == "source_bundle_verified"
    assert result["source_sha"] == sha
    assert result["file_count"] == len(b.FILES)
    assert result["production_installed"] is False
    assert (dest / "source-bundle.json").is_file()
    assert dest.stat().st_mode & 0o777 == 0o700
    assert all(
        (dest / rel).stat().st_mode & 0o777 == 0o400
        for rel in b.FILES
    )
    assert b.verify(repo, sha, dest)["status"] == "source_bundle_verified"


def test_workspace_modification_not_used_when_git_object_is_pinned(tmp_path):
    repo, sha = repository(tmp_path)
    source = repo / b.FILES[0]
    source.write_text("# DANGEROUS UNTRACKED MODIFICATION\n")
    dest = tmp_path / "stage"
    b.prepare(repo, sha, dest)
    assert (dest / b.FILES[0]).read_text() != source.read_text()
    assert (dest / b.FILES[0]).read_bytes() == b._git_file(repo, sha, b.FILES[0])


def test_rejects_symlink_in_source_commit(tmp_path):
    repo, sha = repository(tmp_path)
    path = repo / b.FILES[0]
    path.unlink()
    path.symlink_to("../other.py")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Jason Test", "-c", "user.email=jason@test.invalid",
        "commit", "-qm", "symlink rejected")
    sha2 = git(repo, "rev-parse", "HEAD")
    dest = tmp_path / "stage"
    with pytest.raises(b.ComponentBundleDenied, match="NOT_PLAIN_SOURCE_BLOB"):
        b.prepare(repo, sha2, dest)
    assert not dest.exists()


@pytest.mark.parametrize("dest", [
    "/var/lib/jason/source-staging",
    "/opt/jason/source-staging",
    "/etc/jason/new",
    "/run/jason-component",
    "/srv/jason/source-staging",
])
def test_rejects_production_target_without_writing(tmp_path, dest):
    repo, sha = repository(tmp_path)
    with pytest.raises(b.ComponentBundleDenied, match="PRODUCTION_DESTINATION_DENIED"):
        b.prepare(repo, sha, Path(dest))


def test_staging_does_not_replace_existing_files(tmp_path):
    repo, sha = repository(tmp_path)
    dest = tmp_path / "stage"
    b.prepare(repo, sha, dest)
    with pytest.raises(b.ComponentBundleDenied, match="REPLACE_DENIED"):
        b.prepare(repo, sha, dest)


def test_drift_in_bundle_bytes_is_detected(tmp_path):
    repo, sha = repository(tmp_path)
    dest = tmp_path / "stage"
    b.prepare(repo, sha, dest)
    f = dest / b.FILES[0]
    os.chmod(f, 0o600)
    f.write_text("# corrupted\n")
    os.chmod(f, 0o400)
    with pytest.raises(b.ComponentBundleDenied, match="SOURCE_BYTES_DRIFT"):
        b.verify(repo, sha, dest)


def test_extra_file_or_symlink_in_stage_is_denied(tmp_path):
    repo, sha = repository(tmp_path)
    dest = tmp_path / "stage"
    b.prepare(repo, sha, dest)
    (dest / "extra").write_text("unreviewed")
    (dest / "extra").chmod(0o400)
    with pytest.raises(b.ComponentBundleDenied, match="FILE_SET_DRIFT"):
        b.verify(repo, sha, dest)
    (dest / "extra").unlink()
    (dest / "link").symlink_to(dest / b.FILES[0])
    with pytest.raises(b.ComponentBundleDenied, match="SYMLINK_DENIED"):
        b.verify(repo, sha, dest)


def test_invalid_commit_and_partial_missing_source_never_stage(tmp_path):
    repo, sha = repository(tmp_path)
    dest = tmp_path / "stage"
    with pytest.raises(b.ComponentBundleDenied, match="EXACT_SHA"):
        b.prepare(repo, "main", dest)
    with pytest.raises(b.ComponentBundleDenied, match="GIT_OBJECT_UNAVAILABLE"):
        b.prepare(repo, "b" * 40, dest)
    (repo / b.FILES[2]).unlink()
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Jason Test", "-c", "user.email=jason@test.invalid",
        "commit", "-qm", "removed required module")
    new_sha = git(repo, "rev-parse", "HEAD")
    with pytest.raises(b.ComponentBundleDenied, match="NOT_PLAIN_SOURCE_BLOB"):
        b.prepare(repo, new_sha, dest)
    assert not dest.exists()
