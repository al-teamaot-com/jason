from tools.standby_safe_ref_plan import plan
import pytest

A = "a" * 40
B = "b" * 40
C = "c" * 40


def test_preserves_standby_only_branch_and_adds_missing():
    result = plan(
        {"refs/heads/main": B, "refs/heads/new": C},
        {"refs/heads/main": A, "refs/heads/azure-only": A},
        lambda old, new: old == A and new == B,
    )
    assert result["ready"]
    assert len(result["add_only"]) == 1
    assert len(result["fast_forward_only"]) == 1
    assert result["preserve_azure_only"] == ["refs/heads/azure-only"]
    assert not result["writes_performed"]
    assert not result["execution_authorized"]


def test_divergence_fails_closed():
    result = plan({"refs/heads/main": B}, {"refs/heads/main": A}, lambda *_: False)
    assert result["ready"] is False
    assert result["hold"][0]["reason"] == "non_fast_forward"


def test_tags_immutable_even_when_ancestry_passes():
    result = plan(
        {"refs/heads/main": A, "refs/tags/t": B},
        {"refs/heads/main": A, "refs/tags/t": C},
        lambda *_: True,
    )
    assert result["ready"] is False
    assert result["hold"][0]["reason"] == "tag_conflict"


def test_rejects_invalid_refs_and_missing_main():
    with pytest.raises(ValueError):
        plan({"refs/heads/main": "oops"}, {"refs/heads/main": A}, lambda *_: True)
    with pytest.raises(ValueError):
        plan({"refs/heads/dev": A}, {"refs/heads/main": A}, lambda *_: True)
