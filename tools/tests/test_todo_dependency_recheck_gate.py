from tools.todo_release_bridge import dependency_recheck_gate


def test_fails_closed_without_exact_dependency_identity():
    item = {"blocker_category": "dependency"}
    assert dependency_recheck_gate(item, {})["retry_eligible"] is False


def test_github_closed_is_not_production_acceptance():
    item = {"blocker_category": "dependency", "governing_dependencies": ["issue-1078"]}
    assert dependency_recheck_gate(item, {"issue-1078": {"state": "closed"}})["retry_eligible"] is False


def test_complete_verification_requires_commit_provenance():
    item = {"blocker_category": "dependency", "governing_dependencies": ["issue-1078", "issue-1069"]}
    facts = {"issue-1078": {"state": "production_verified", "release_sha": "a" * 40},
             "issue-1069": {"state": "production_verified", "release_sha": "b" * 40}}
    assert dependency_recheck_gate(item, facts)["retry_eligible"] is True
    facts["issue-1069"].pop("release_sha")
    assert dependency_recheck_gate(item, facts)["retry_eligible"] is False


def test_non_dependency_never_promoted():
    item = {"blocker_category": "external_authority", "governing_dependencies": ["issue-1078"]}
    assert dependency_recheck_gate(item, {})["retry_eligible"] is False
