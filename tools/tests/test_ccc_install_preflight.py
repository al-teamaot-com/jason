"""CCC installer must fail before production mutation when approval is absent."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from tools.ccc_install_preflight import verify_install_review

OLD = "a" * 40
NEW = "b" * 40


def review(tmp_path: Path, revision: str = NEW, **changes) -> Path:
    record = {"schema_version": "1.0", "source_revision": revision,
              "status": "approved", "recorded_by": "person-al",
              "reason": "Reviewed exact CCC checker upgrade",
              "recorded_at": datetime.now(timezone.utc).isoformat()}
    record.update(changes)
    p = tmp_path / "review.json"
    p.write_text(json.dumps(record))
    p.chmod(0o600)
    return p


def link(tmp_path: Path, revision: str = OLD) -> Path:
    target = tmp_path / revision
    target.mkdir()
    active = tmp_path / "ccc-current"
    active.symlink_to(target, target_is_directory=True)
    return active


def test_new_checker_requires_exact_review_before_mutation(tmp_path):
    with pytest.raises(PermissionError, match="exact-revision owner review"):
        verify_install_review(revision=NEW, current_link=link(tmp_path), review_file=None)


def test_valid_review_allows_preflight_without_mutation(tmp_path):
    current = link(tmp_path)
    verify_install_review(revision=NEW, current_link=current, review_file=review(tmp_path))
    assert current.resolve().name == OLD


@pytest.mark.parametrize("changes", [
    {"source_revision": OLD}, {"status": "denied"},
    {"recorded_by": "assistant"}, {"schema_version": "2.0"},
    {"reason": ""}, {"recorded_at": "2026-10-16T09:30:00"},
])
def test_invalid_review_is_rejected(tmp_path, changes):
    with pytest.raises((ValueError, PermissionError)):
        verify_install_review(revision=NEW, current_link=link(tmp_path),
                              review_file=review(tmp_path, **changes))


def test_public_review_file_is_rejected(tmp_path):
    item = review(tmp_path)
    item.chmod(0o644)
    with pytest.raises(PermissionError, match="private"):
        verify_install_review(revision=NEW, current_link=link(tmp_path), review_file=item)


def test_symlink_review_is_rejected(tmp_path):
    item = review(tmp_path)
    alias = tmp_path / "review-link.json"
    alias.symlink_to(item)
    with pytest.raises(OSError):
        verify_install_review(revision=NEW, current_link=link(tmp_path), review_file=alias)


def test_same_revision_reinstall_needs_no_new_review(tmp_path):
    verify_install_review(revision=OLD, current_link=link(tmp_path), review_file=None)


def test_initial_install_requires_review(tmp_path):
    with pytest.raises(PermissionError):
        verify_install_review(revision=NEW, current_link=tmp_path / "missing", review_file=None)


def test_invalid_revision_rejected(tmp_path):
    with pytest.raises(ValueError):
        verify_install_review(revision="latest", current_link=link(tmp_path), review_file=None)


def test_shell_invokes_preflight_before_first_production_write():
    script = (Path(__file__).parents[1] / "install_ccc_scheduler.sh").read_text()
    preflight = script.index('git -C "$REPO_ROOT" show "$SOURCE_REVISION:tools/ccc_install_preflight.py"')
    first_mutation = script.index('mkdir -p "$RELEASE_ROOT"')
    assert preflight < first_mutation
    assert preflight < script.index('ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"')
    assert 'python3 - --revision "$SOURCE_REVISION"' in script
    assert 'python3 "$REPO_ROOT/tools/ccc_install_preflight.py"' not in script
