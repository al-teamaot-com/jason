from tools.todo_release_bridge import next_work_gate


def test_explicit_pending_gates():
    assert next_work_gate("waiting_operational_acceptance", "")["blocker_category"] == "acceptance"
    assert next_work_gate("closure_validating", "")["next_action"] == "recheck_closure_pr_and_todo_readback"
    assert next_work_gate("development_blocked", "Missing exact source excerpt")["blocker_category"] == "source_context"
    assert next_work_gate("development_blocked", "Blocked by prerequisite #1078")["blocker_category"] == "dependency"
    assert next_work_gate("development_blocked", "API details and credentials unavailable")["blocker_category"] == "external_authority"
    assert next_work_gate("complete", "") == {"blocker_category": "none", "next_action": "none"}
