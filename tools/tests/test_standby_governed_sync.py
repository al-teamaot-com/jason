import json
import pytest
from tools.standby_governed_sync import MirrorBlocked, apply_cas, build_updates

A, B, C = "a" * 40, "b" * 40, "c" * 40


def authority(tmp_path, enabled=True):
    p = tmp_path / "authority.json"
    p.write_text(json.dumps({"active_provider": "github", "standby_provider": "azure-devops",
                             "mirroring_enabled": enabled, "failover_state": "inactive"}))
    return p


def test_cas_updates_and_preserves_azure_only(tmp_path):
    old = {"refs/heads/main": A, "refs/heads/azure-only": C}
    new = {"refs/heads/main": B, "refs/heads/new": C}
    state = dict(old)
    def update(rows):
        for item in rows:
            assert state.get(item["name"], "0" * 40) == item["oldObjectId"]
            state[item["name"]] = item["newObjectId"]
        return [{"success": True} for _ in rows]
    out = apply_cas(new, lambda: dict(state), lambda o, n: o == A and n == B,
                    update, authority(tmp_path), lambda: dict(state))
    assert out == {"verified": True, "applied_count": 2, "preserved_azure_only": 1}
    assert state["refs/heads/azure-only"] == C


def test_missing_authority_blocks_before_update(tmp_path):
    with pytest.raises(MirrorBlocked):
        apply_cas({"refs/heads/main": B}, lambda: {"refs/heads/main": A},
                  lambda *_: True, lambda _: pytest.fail("write called"),
                  tmp_path / "missing", lambda: {})


def test_disabled_authority_blocks(tmp_path):
    with pytest.raises(MirrorBlocked):
        apply_cas({"refs/heads/main": B}, lambda: {"refs/heads/main": A},
                  lambda *_: True, lambda _: pytest.fail("write called"),
                  authority(tmp_path, False), lambda: {})


def test_concurrent_change_blocks_before_update(tmp_path):
    seq = iter([{"refs/heads/main": A}, {"refs/heads/main": C}])
    with pytest.raises(MirrorBlocked, match="changed"):
        apply_cas({"refs/heads/main": B}, lambda: next(seq), lambda *_: True,
                  lambda _: pytest.fail("write called"), authority(tmp_path), lambda: {})


def test_divergence_blocks_before_update(tmp_path):
    with pytest.raises(MirrorBlocked, match="conflicting"):
        apply_cas({"refs/heads/main": B}, lambda: {"refs/heads/main": A},
                  lambda *_: False, lambda _: pytest.fail("write called"),
                  authority(tmp_path), lambda: {})


def test_failing_cas_never_reports_success(tmp_path):
    with pytest.raises(MirrorBlocked, match="CAS"):
        apply_cas({"refs/heads/main": B}, lambda: {"refs/heads/main": A},
                  lambda *_: True, lambda _: [{"success": False}],
                  authority(tmp_path), lambda: {})


def test_bad_readback_blocks(tmp_path):
    with pytest.raises(MirrorBlocked, match="readback"):
        apply_cas({"refs/heads/main": B}, lambda: {"refs/heads/main": A},
                  lambda *_: True, lambda _: [{"success": True}],
                  authority(tmp_path), lambda: {"refs/heads/main": A})
