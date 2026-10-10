import json
from tools.todo_release_bridge import dependency_state_for_item


def test_verified_release_accepted_and_unverified_release_rejected(tmp_path):
    records = tmp_path / "records"
    records.mkdir()
    identity = "release-1234567890abcdef"
    sha = "a" * 40
    payload = {"release_id": identity, "state": "closed", "production": {"live_sha": sha},
               "release_manifest": {"candidate_sha": sha},
               "history": [{"state": "closed", "gate": "pass"}]}
    (records / (identity + ".json")).write_text(json.dumps(payload))
    item = {"blocker_category": "dependency", "governing_dependencies": [identity]}
    assert dependency_state_for_item(item, tmp_path)["retry_eligible"] is True
    payload["production"]["live_sha"] = "b" * 40
    (records / (identity + ".json")).write_text(json.dumps(payload))
    assert dependency_state_for_item(item, tmp_path)["retry_eligible"] is False


def test_issue_closure_does_not_count(tmp_path):
    item = {"blocker_category": "dependency", "governing_dependencies": ["issue-1078"]}
    assert dependency_state_for_item(item, tmp_path)["retry_eligible"] is False
