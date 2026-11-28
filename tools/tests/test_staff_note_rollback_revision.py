"""Rollback note-profile truth comes from the exact immutable LKG Git tree."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "resolve_staff_note_profile_at_revision.py"
spec = importlib.util.spec_from_file_location("staff_note_resolver", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    def commit(profile):
        p = tmp_path / "config/aot-staff-internal-note-profile.json"
        p.parent.mkdir(exist_ok=True)
        if profile is not None:
            p.write_text(json.dumps({"schema_version": "1.0", "profile": profile}))
            subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        else:
            (tmp_path / "readme").write_text("historical")
            subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit",
                        "-qm", "profile"], check=True)
        return subprocess.check_output(["git", "-C", str(tmp_path),
                                         "rev-parse", "HEAD"], text=True).strip()
    return tmp_path, commit


def test_approved_on_and_historical_off(repo):
    path, commit = repo
    old = commit(None)
    enabled = commit("internal-note-v1")
    disabled = commit("off")
    assert mod.resolve(path, old) == ""
    assert mod.resolve(path, enabled) == "internal-note-v1"
    assert mod.resolve(path, disabled) == ""


def test_invalid_revision_fails_closed(repo):
    path, commit = repo
    commit("internal-note-v1")
    for bad in ["main", "a" * 40, "54f4", "../etc/passwd"]:
        with pytest.raises(ValueError):
            mod.resolve(path, bad)


def test_malformed_committed_policy_fails_closed(repo):
    path, commit = repo
    commit("unknown")
    sha = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    with pytest.raises(ValueError):
        mod.resolve(path, sha)
