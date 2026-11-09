import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("surface", ROOT / "openclaw_workboard_release_surface.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from openclaw_workboard_release_scope import candidate_for, sha


class FakeGateway:
    def __init__(self, image_id, *, fail_first_health=False):
        self.image = image_id
        self.restarts = 0
        self.fail_first_health = fail_first_health
        self.plugin_ready = True

    def image_id(self):
        return self.image

    def restart(self):
        self.restarts += 1

    def health(self):
        return not self.fail_first_health or self.restarts != 1

    def workboard_enabled(self):
        return self.plugin_ready


def fixture(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    current = tmp_path / "openclaw.json"
    baseline = {
        "plugins": {"allow": ["msteams"], "entries": {"msteams": {"enabled": True}}},
        "agents": {"list": [{"id": "main"}]},
    }
    before = (json.dumps(baseline, indent=2) + "\n").encode()
    current.write_bytes(before)
    current.chmod(0o600)
    future = (json.dumps(candidate_for(baseline), indent=2, ensure_ascii=False) + "\n").encode()
    image = "sha256:" + "b" * 64
    declaration = {
        "schema_version": "1.0",
        "profile": "j-man-j-dev-workboard-v1",
        "candidate_id": "jman-workboard-activation-20261109",
        "base_config_sha256": sha(before),
        "rollback_config_sha256": sha(before),
        "candidate_config_sha256": sha(future),
        "reviewed_scope_sha256": "c" * 64,
        "image_id": image,
    }
    (repo / module.SOURCE_DECLARATION).write_text(json.dumps(declaration))
    cand_sha = "a" * 40
    record = {"release_id": "release-" + cand_sha[:16],
              "release_candidate": {"candidate_sha": cand_sha},
              "owner_approval": {"approved": True, "candidate_sha": cand_sha,
                  "source": "authenticated_mobile_teams_owner:relapproval-" + "d" * 32}}
    return repo, current, before, future, declaration, record, FakeGateway(image)


def test_off_profile_requires_no_restart(tmp_path):
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / module.SOURCE_DECLARATION).write_text('{"schema_version":"1.0","profile":"off"}')
    assert module.plan(repo)["status"] == "off"
    assert module.activate(repo, tmp_path / "state", {})["status"] == "off"


def test_signed_exact_release_activates_and_restores(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    state = tmp_path / "state"
    assert module.plan(repo, config)["status"] == "ready"
    result = module.activate(repo, state, record, config_path=config, ops=gateway)
    assert result["status"] == "active"
    assert config.read_bytes() == future
    assert gateway.restarts == 1
    path = state / "openclaw-workboard-release-backups" / (record["release_id"] + ".baseline")
    assert path.read_bytes() == before
    assert path.stat().st_mode & 0o077 == 0
    rest = module.rollback(repo, state, record, config_path=config, ops=gateway)
    assert rest["status"] == "restored_and_verified"
    assert config.read_bytes() == before
    assert gateway.restarts == 2


@pytest.mark.parametrize("problem", ["no_approval", "wrong_sha", "ordinary_chat", "release_id"])
def test_unapproved_release_never_restarts_or_writes(tmp_path, problem):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    if problem == "no_approval":
        record["owner_approval"]["approved"] = False
    elif problem == "wrong_sha":
        record["owner_approval"]["candidate_sha"] = "f" * 40
    elif problem == "ordinary_chat":
        record["owner_approval"]["source"] = "user_chat_approved"
    elif problem == "release_id":
        record["release_id"] = "release-" + "e" * 16
    with pytest.raises(module.WorkboardReleaseError):
        module.activate(repo, tmp_path / "state", record, config_path=config, ops=gateway)
    assert config.read_bytes() == before
    assert gateway.restarts == 0


def test_drift_or_unreviewed_change_fails_pre_mutation(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    config.write_bytes(before + b" ")
    with pytest.raises(module.WorkboardReleaseError):
        module.activate(repo, tmp_path / "state", record, config_path=config, ops=gateway)
    assert gateway.restarts == 0


def test_image_mismatch_fails_before_config_write(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    gateway.image = "sha256:" + "e" * 64
    with pytest.raises(module.WorkboardReleaseError, match="image"):
        module.activate(repo, tmp_path / "state", record, config_path=config, ops=gateway)
    assert config.read_bytes() == before
    assert gateway.restarts == 0


def test_failed_postflight_rolls_back_and_verifies(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    gateway.fail_first_health = True
    with pytest.raises(module.WorkboardReleaseError, match="verification failed"):
        module.activate(repo, tmp_path / "state", record, config_path=config, ops=gateway)
    assert config.read_bytes() == before
    assert gateway.restarts == 2


def test_consumed_release_backup_prevents_replay(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    state = tmp_path / "state"
    module.activate(repo, state, record, config_path=config, ops=gateway)
    with pytest.raises(module.WorkboardReleaseError):
        module.activate(repo, state, record, config_path=config, ops=gateway)
    assert gateway.restarts == 1


def test_invalid_declaration_fails_closed(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    declaration["surprise"] = "start_a_worker"
    (repo / module.SOURCE_DECLARATION).write_text(json.dumps(declaration))
    with pytest.raises(module.WorkboardReleaseError, match="unreviewed"):
        module.plan(repo, config)


def test_rollback_refuses_modified_backup(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    state = tmp_path / "state"
    module.activate(repo, state, record, config_path=config, ops=gateway)
    backup = state / "openclaw-workboard-release-backups" / (record["release_id"] + ".baseline")
    backup.write_bytes(before + b" ")
    with pytest.raises(module.WorkboardReleaseError, match="rollback baseline hash"):
        module.rollback(repo, state, record, config_path=config, ops=gateway)


def test_live_postflight_requires_exact_candidate_and_health(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    with pytest.raises(module.WorkboardReleaseError):
        module.verify_active(repo, config, gateway)
    module.activate(repo, tmp_path / "state", record, config_path=config, ops=gateway)
    result = module.verify_active(repo, config, gateway)
    assert result["status"] == "active_verified"
    config.write_bytes(future + b" ")
    with pytest.raises(module.WorkboardReleaseError):
        module.verify_active(repo, config, gateway)


def test_historical_source_declaration_is_off(tmp_path):
    assert module.source_declaration(tmp_path) == {
        "schema_version": "1.0", "profile": "off"
    }



def test_plugin_not_loaded_requires_automatic_rollback(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    gateway.plugin_ready = False
    with pytest.raises(module.WorkboardReleaseError, match="verification failed"):
        module.activate(repo, tmp_path / "state", record, config_path=config, ops=gateway)
    assert config.read_bytes() == before
    assert gateway.restarts == 2


def record_native_state(state, record, status):
    path = state / "records" / (record["release_id"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(record, state=status)))


def test_crash_after_activation_restores_baseline_before_next_release(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    state = tmp_path / "state"
    module.activate(repo, state, record, config_path=config, ops=gateway)
    record_native_state(state, record, "production")
    result = module.recover_interrupted(state, config_path=config, ops=gateway)
    assert result == [{"release_id": record["release_id"],
                       "result": "interrupted_restored"}]
    assert config.read_bytes() == before
    assert gateway.restarts == 2
    journal = state / "openclaw-workboard-release-backups" / (record["release_id"] + ".baseline.journal.json")
    assert json.loads(journal.read_text())["status"] == "restored"
    assert module.recover_interrupted(state, config_path=config, ops=gateway) == []


def test_closed_release_recovery_verifies_without_restart(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    state = tmp_path / "state"
    module.activate(repo, state, record, config_path=config, ops=gateway)
    record_native_state(state, record, "closed")
    result = module.recover_interrupted(state, config_path=config, ops=gateway)
    assert result == [{"release_id": record["release_id"],
                       "result": "committed_verified"}]
    assert config.read_bytes() == future
    assert gateway.restarts == 1
    journal = state / "openclaw-workboard-release-backups" / (record["release_id"] + ".baseline.journal.json")
    assert json.loads(journal.read_text())["status"] == "committed"


def test_recovery_rejects_source_drift_without_overwrite(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    state = tmp_path / "state"
    module.activate(repo, state, record, config_path=config, ops=gateway)
    record_native_state(state, record, "production")
    third_party = future + b"changed"
    config.write_bytes(third_party)
    with pytest.raises(module.WorkboardReleaseError, match="drift"):
        module.recover_interrupted(state, config_path=config, ops=gateway)
    assert config.read_bytes() == third_party
    assert gateway.restarts == 1


def test_recovery_requires_native_record_and_signed_origin(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    state = tmp_path / "state"
    module.activate(repo, state, record, config_path=config, ops=gateway)
    with pytest.raises(module.WorkboardReleaseError, match="native release record missing"):
        module.recover_interrupted(state, config_path=config, ops=gateway)
    record["owner_approval"]["source"] = "ordinary_chat"
    record_native_state(state, record, "production")
    with pytest.raises(module.WorkboardReleaseError, match="signed Teams"):
        module.recover_interrupted(state, config_path=config, ops=gateway)
    assert config.read_bytes() == future
    assert gateway.restarts == 1


def test_candidate_serializer_preserves_existing_config_order(tmp_path):
    repo, config, before, future, declaration, record, gateway = fixture(tmp_path)
    assert module.plan(repo, config)["candidate"] == future
    # Changing JSON ordering without new sealed approval must not deploy.
    sorted_variant = (json.dumps(json.loads(future), sort_keys=True, indent=2)
                      + "\n").encode()
    assert sorted_variant != future
    assert module.sha(sorted_variant) != declaration["candidate_config_sha256"]
