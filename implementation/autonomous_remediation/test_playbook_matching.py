from .playbook_matching import EligibilityGate, GateState, MatchState, PlaybookMatcher


def gates(*extra):
    return [
        EligibilityGate("trigger", GateState.PASS),
        EligibilityGate("identity", GateState.PASS, blocking_on_fail=True),
        EligibilityGate("expected_condition", GateState.PASS),
        EligibilityGate("exclusions_clear", GateState.PASS, blocking_on_fail=True),
        EligibilityGate("evidence_fresh", GateState.PASS),
        EligibilityGate("governance_precheck", GateState.PASS, blocking_on_fail=True),
        EligibilityGate("autonomy_approved", GateState.PASS, blocking_on_fail=True),
        *extra,
    ]


def test_all_hard_gates_enable_standing_authority():
    result = PlaybookMatcher.evaluate(playbook_id="idle-logoff", gates=gates())
    assert result.state == MatchState.MATCHED_AUTONOMY
    assert result.standing_authority_active


def test_unknown_required_evidence_is_investigation_only():
    values = gates(EligibilityGate("recent_ticket_check", GateState.UNKNOWN, "Recent history not checked"))
    result = PlaybookMatcher.evaluate(playbook_id="shutdown", gates=values)
    assert result.state == MatchState.CANDIDATE_INVESTIGATION
    assert not result.standing_authority_active


def test_identity_conflict_blocks_instead_of_guessing():
    values = [
        gate if gate.name != "identity" else EligibilityGate("identity", GateState.FAIL, "Two devices match", True)
        for gate in gates()
    ]
    result = PlaybookMatcher.evaluate(playbook_id="shutdown", gates=values)
    assert result.state == MatchState.CONFLICT_BLOCKED


def test_trigger_mismatch_is_not_a_match():
    values = [
        gate if gate.name != "trigger" else EligibilityGate("trigger", GateState.FAIL)
        for gate in gates()
    ]
    result = PlaybookMatcher.evaluate(playbook_id="shutdown", gates=values)
    assert result.state == MatchState.NOT_MATCHED


def test_missing_autonomy_approval_never_activates_execution():
    values = [gate for gate in gates() if gate.name != "autonomy_approved"]
    result = PlaybookMatcher.evaluate(playbook_id="shutdown", gates=values)
    assert result.state == MatchState.CANDIDATE_INVESTIGATION
