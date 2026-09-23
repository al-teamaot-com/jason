from orchestrator.conversation_kernel import _SYSTEM_INSTRUCTIONS
from orchestrator.conversation_interpretation_quality import _REVIEW_INSTRUCTIONS


def test_independently_verifiable_facts_are_independent_information_needs():
    assert "independently answerable fact" in _SYSTEM_INSTRUCTIONS


def test_review_requires_independent_fact_granularity():
    assert "separate information need" in _REVIEW_INSTRUCTIONS



def test_information_need_must_not_expand_human_semantic_scope():
    assert "do not add unrequested factual dimensions" in _SYSTEM_INSTRUCTIONS
    assert "make the answer more demanding than the human request" in _SYSTEM_INSTRUCTIONS


def test_interpretation_review_rejects_unrequested_evidence_requirements():
    assert "adds unrequested factual dimensions" in _REVIEW_INSTRUCTIONS
    assert "more demanding than the human message" in _REVIEW_INSTRUCTIONS
