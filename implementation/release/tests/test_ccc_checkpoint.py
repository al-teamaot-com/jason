from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from tools.ccc_checkpoint import CCCCheckpointError, LastKnownCompliantPromoter


NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
RUNTIME = "b" * 40


def run(command: tuple[str, ...], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert completed.returncode == 0, completed.stdout
    return (completed.stdout or "").strip()


def repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "jason"
    root.mkdir()
    run(("git", "init", "-q"), root)
    run(("git", "config", "user.name", "Jason Test"), root)
    run(("git", "config", "user.email", "jason@example.test"), root)
    (root / "README.md").write_text("Jason\n", encoding="utf-8")
    run(("git", "add", "README.md"), root)
    run(("git", "commit", "-q", "-m", "Initial"), root)
    return root, run(("git", "rev-parse", "HEAD"), root)


def evidence(tmp_path: Path, source: str, *, status: str = "PASS", runtime: str = RUNTIME):
    report = tmp_path / "ccc-report.json"
    runtime_manifest = tmp_path / "runtime-manifest.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": status,
                "source_revision": source,
                "runtime_revision": runtime,
            }
        ),
        encoding="utf-8",
    )
    runtime_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "runtime_revision": runtime,
                "immutable_release_path": f"/opt/jason/releases/{runtime}",
            }
        ),
        encoding="utf-8",
    )
    return report, runtime_manifest


class Builder:
    def __init__(self, root: Path, destination: Path) -> None:
        self.root = root
        self.destination = destination

    def build(self, version: str, *, release_name: str, ref: str):
        target = self.destination / version
        target.mkdir(parents=True)
        commit = run(("git", "rev-parse", "HEAD"), self.root)
        (target / "release-manifest.json").write_text(
            json.dumps({"version": version, "commit": commit}), encoding="utf-8"
        )
        (target / "SHA256SUMS.txt").write_text("test\n", encoding="utf-8")
        return SimpleNamespace(destination=target, commit=commit)


class Verifier:
    def __init__(self, root: Path, *, commit: str | None = None) -> None:
        self.root = root
        self.commit = commit

    def verify(self, package_directory: Path):
        commit = self.commit or run(("git", "rev-parse", "HEAD"), self.root)
        return SimpleNamespace(commit=commit)


def promoter(tmp_path: Path, root: Path, *, restored_commit: str | None = None):
    return LastKnownCompliantPromoter(
        root,
        tmp_path / "recovery",
        tmp_path / "checkpoints",
        clock=lambda: NOW,
        package_builder_factory=Builder,
        restore_verifier_factory=lambda repo: Verifier(repo, commit=restored_commit),
    )


def test_pass_creates_checkpoint_and_atomically_promotes_pointer(tmp_path: Path) -> None:
    root, source = repository(tmp_path)
    report, runtime = evidence(tmp_path, source)

    result = promoter(tmp_path, root).promote(report, runtime)

    assert result.source_revision == source
    assert result.runtime_revision == RUNTIME
    assert result.checkpoint_directory.is_dir()
    pointer = json.loads(result.pointer_path.read_text(encoding="utf-8"))
    assert pointer["status"] == "PASS"
    assert pointer["restore_verified"] is True
    assert pointer["source_revision"] == source
    assert pointer["runtime_revision"] == RUNTIME


def test_fail_and_not_proven_never_promote(tmp_path: Path) -> None:
    root, source = repository(tmp_path)
    for status in ("FAIL", "NOT PROVEN"):
        report, runtime = evidence(tmp_path, source, status=status)
        with pytest.raises(CCCCheckpointError, match="must be PASS"):
            promoter(tmp_path, root).promote(report, runtime)
    assert not (tmp_path / "checkpoints" / "last-known-compliant.json").exists()


def test_runtime_revision_mismatch_fails_closed(tmp_path: Path) -> None:
    root, source = repository(tmp_path)
    report, runtime = evidence(tmp_path, source)
    runtime.write_text(
        json.dumps({"runtime_revision": "c" * 40}), encoding="utf-8"
    )
    with pytest.raises(CCCCheckpointError, match="revision mismatch"):
        promoter(tmp_path, root).promote(report, runtime)


def test_certified_source_must_match_clean_head(tmp_path: Path) -> None:
    root, source = repository(tmp_path)
    report, runtime = evidence(tmp_path, "c" * 40)
    with pytest.raises(CCCCheckpointError, match="does not match certified source"):
        promoter(tmp_path, root).promote(report, runtime)

    report, runtime = evidence(tmp_path, source)
    (root / "dirty.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(CCCCheckpointError, match="must be clean"):
        promoter(tmp_path, root).promote(report, runtime)


def test_restore_commit_must_equal_certified_source(tmp_path: Path) -> None:
    root, source = repository(tmp_path)
    report, runtime = evidence(tmp_path, source)
    with pytest.raises(CCCCheckpointError, match="did not reproduce"):
        promoter(tmp_path, root, restored_commit="c" * 40).promote(report, runtime)
    assert not (tmp_path / "checkpoints" / "last-known-compliant.json").exists()


def test_failed_run_preserves_existing_last_known_compliant_pointer(tmp_path: Path) -> None:
    root, source = repository(tmp_path)
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint_root.mkdir()
    pointer = checkpoint_root / "last-known-compliant.json"
    original = '{"checkpoint_id":"previous-good","status":"PASS"}\n'
    pointer.write_text(original, encoding="utf-8")
    report, runtime = evidence(tmp_path, source, status="FAIL")

    with pytest.raises(CCCCheckpointError, match="must be PASS"):
        promoter(tmp_path, root).promote(report, runtime)

    assert pointer.read_text(encoding="utf-8") == original
