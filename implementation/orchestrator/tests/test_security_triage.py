import json
import pytest
from orchestrator.security_triage import SecurityTriageClassification, SecurityTriageEvaluator


class Client:
    def __init__(self,result): self.result=result; self.calls=[]
    def complete(self,**kwargs): self.calls.append(kwargs); return self.result


def result(**overrides):
    base={"classification":"suspicious","confidence":"medium","threat_evidence_refs":["ev-1"],"benign_evidence_refs":[],"missing_evidence":["Determine whether the entry is an approved vendor exception."],"recommended_next_step":"Check same-client approved documentation and endpoint security evidence.","human_review_required":True,"reasoning_summary":"The supplied drift is unexplained and requires corroboration."}
    base.update(overrides); return base


def test_triage_passes_only_supplied_evidence_and_returns_bounded_result():
    client=Client(result()); evaluator=SecurityTriageEvaluator(client)
    assessment=evaluator.evaluate(incident_type="hosts_file_drift", evidence=[{"evidence_ref":"ev-1","fact":"HOSTS contains unexpected mapping"}])
    assert assessment.classification == SecurityTriageClassification.SUSPICIOUS
    payload=json.loads(client.calls[0]["user"])
    assert payload["incident_type"] == "hosts_file_drift"
    assert payload["governed_evidence"][0]["evidence_ref"] == "ev-1"
    assert "tools" not in client.calls[0]


def test_unknown_evidence_reference_is_rejected():
    evaluator=SecurityTriageEvaluator(Client(result(threat_evidence_refs=["invented"])))
    with pytest.raises(ValueError,match="unknown"):
        evaluator.evaluate(incident_type="hosts_file_drift", evidence=[{"evidence_ref":"ev-1","fact":"x"}])


def test_confirmed_threat_requires_human_review_and_threat_evidence():
    with pytest.raises(ValueError,match="human review"):
        SecurityTriageEvaluator(Client(result(classification="confirmed_threat",human_review_required=False))).evaluate(incident_type="x",evidence=[{"evidence_ref":"ev-1","fact":"malicious execution established"}])
    with pytest.raises(ValueError,match="cited threat"):
        SecurityTriageEvaluator(Client(result(classification="confirmed_threat",threat_evidence_refs=[],human_review_required=True))).evaluate(incident_type="x",evidence=[{"evidence_ref":"ev-1","fact":"malicious execution established"}])


def test_benign_requires_affirmative_benign_evidence():
    with pytest.raises(ValueError,match="benign evidence"):
        SecurityTriageEvaluator(Client(result(classification="benign",confidence="high",threat_evidence_refs=[],benign_evidence_refs=[],missing_evidence=[],human_review_required=False))).evaluate(incident_type="x",evidence=[{"evidence_ref":"ev-1","fact":"unknown"}])
    assessment=SecurityTriageEvaluator(Client(result(classification="benign",confidence="high",threat_evidence_refs=[],benign_evidence_refs=["ev-1"],missing_evidence=[],recommended_next_step="Verify expected state and follow the playbook completion gate.",human_review_required=False,reasoning_summary="Approved documentation matches the exact condition."))).evaluate(incident_type="x",evidence=[{"evidence_ref":"ev-1","fact":"approved exception"}])
    assert assessment.may_close_as_benign is True


def test_empty_or_duplicate_evidence_fails_closed():
    evaluator=SecurityTriageEvaluator(Client(result()))
    with pytest.raises(ValueError,match="requires governed evidence"): evaluator.evaluate(incident_type="x",evidence=[])
    with pytest.raises(ValueError,match="duplicate"):
        evaluator.evaluate(incident_type="x",evidence=[{"evidence_ref":"ev-1"},{"evidence_ref":"ev-1"}])
