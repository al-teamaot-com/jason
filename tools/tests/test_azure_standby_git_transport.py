import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from tools.azure_standby_git_transport import guarded_push, secure_git_env
from tools.standby_governed_sync import MirrorBlocked

A = "a" * 40
B = "b" * 40
C = "c" * 40


def auth(tmp_path):
    p = tmp_path / "authority.json"
    p.write_text(json.dumps({"active_provider": "github",
                             "standby_provider": "azure-devops",
                             "mirroring_enabled": True, "failover_state": "inactive"}))
    return p


def source(tmp_path):
    p = tmp_path / "mirror.git"
    p.mkdir()
    (p / "HEAD").write_text("ref: refs/heads/main")
    return p


def test_credential_config_is_not_written_to_argv():
    env = secure_git_env("opaque-token")
    assert env["GIT_CONFIG_VALUE_0"] == "AUTHORIZATION: bearer opaque-token"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_token_injection_rejected():
    with pytest.raises(MirrorBlocked):
        secure_git_env("secret\rheader")


def test_atomic_nonforce_push_and_preservation(tmp_path):
    before = {"refs/heads/main": A, "refs/heads/azureonly": C}
    after = {**before, "refs/heads/main": B}
    snapshots = iter([before, before, after, after])
    calls = []
    def runner(args, **kw):
        calls.append((args, kw))
        return SimpleNamespace(returncode=0)
    result = guarded_push(bare_source=source(tmp_path), github={"refs/heads/main": B},
        azure_before=before, ancestor=lambda a,b: True,
        read_azure=lambda: next(snapshots), token_provider=lambda: "secret",
        authority_path=auth(tmp_path), runner=runner)
    assert result["verified"]
    assert "--atomic" not in calls[0][0]
    assert "--force" not in calls[0][0]
    assert "secret" not in str(calls[0][0])


def test_disabled_authority_no_remote_write(tmp_path):
    p = auth(tmp_path)
    p.write_text(p.read_text().replace("true", "false"))
    with pytest.raises(MirrorBlocked):
        guarded_push(bare_source=source(tmp_path), github={"refs/heads/main": B},
            azure_before={"refs/heads/main": A}, ancestor=lambda *_: True,
            read_azure=lambda: {}, token_provider=lambda: "secret",
            authority_path=p, runner=lambda *_a, **_k: pytest.fail("push called"))


def test_failed_remote_push_is_not_verified(tmp_path):
    before = {"refs/heads/main": A}
    with pytest.raises(MirrorBlocked, match="rejected"):
        guarded_push(bare_source=source(tmp_path), github={"refs/heads/main": B},
            azure_before=before, ancestor=lambda *_: True, read_azure=lambda: before,
            token_provider=lambda: "secret", authority_path=auth(tmp_path),
            runner=lambda *_a, **_k: SimpleNamespace(returncode=1))
