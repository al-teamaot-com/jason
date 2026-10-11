from tools.todo_release_bridge import explicit_operational_dependencies, operational_evidence_gate, dependency_state_for_item


def test_explicit_identity_does_not_infer_from_issue_text():
    assert explicit_operational_dependencies('Depends on SUPPORT-CAP-009') == []
    assert explicit_operational_dependencies('- Governing operational dependencies: acceptance-network-posture, acceptance-awareness') == ['acceptance-awareness', 'acceptance-network-posture']
    assert explicit_operational_dependencies('- Governing operational dependencies: issue-120') == []


def test_untrusted_and_missing_receipts_fail_closed():
    item = {'governing_operational_dependencies': ['acceptance-network-posture']}
    assert operational_evidence_gate(item, {})['operational_eligible'] is False
    proof = {'acceptance-network-posture': {'state':'operationally_accepted','identity':'acceptance-network-posture','evidence_ref':'issue-closed','authority_verified':False}}
    assert operational_evidence_gate(item, proof)['operational_eligible'] is False
    proof['acceptance-network-posture']['authority_verified'] = True
    assert operational_evidence_gate(item, proof)['operational_eligible'] is True


def test_production_does_not_admit_without_trusted_receipt(tmp_path):
    item = {'blocker_category':'dependency', 'governing_dependencies':['release-1234567890abcdef'],
            'governing_operational_dependencies':['acceptance-network-posture']}
    assert dependency_state_for_item(item, tmp_path)['retry_eligible'] is False
