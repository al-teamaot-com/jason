"""Read-only complete source evidence includes changes later reverted."""
import pytest
from tools.owner_objective_source_verifier import newer_touched_paths

BASE,HEAD,OTHER="a"*40,"b"*40,"c"*40


def test_no_later_main_requires_no_network_call():
    assert newer_touched_paths({"gh_api":lambda *a:pytest.fail("unexpected API")},BASE,BASE)==set()


def test_per_commit_paths_preserve_a_change_even_if_final_compare_would_hide_revert():
    calls=[]
    def api(endpoint,query):
        calls.append(endpoint)
        if "/compare/" in endpoint:
            return {"total":2,"base":BASE,"status":"ahead","commits":[OTHER,HEAD]}
        return {"sha":OTHER if OTHER in endpoint else HEAD,
                "files":[{"name":"protected/changed-then-reverted.py","previous":"old/protected.py"}]}
    assert newer_touched_paths({"gh_api":api},BASE,HEAD)=={
        "protected/changed-then-reverted.py","old/protected.py"}
    assert len(calls)==3


@pytest.mark.parametrize("fault",["truncated","duplicate","wrongbase","headmissing","oversized","badpath"])
def test_incomplete_or_malformed_source_evidence_fails_closed(fault):
    def api(endpoint,query):
        if "/compare/" in endpoint:
            result={"total":1,"base":BASE,"status":"ahead","commits":[HEAD]}
            if fault=="truncated":result["total"]=2
            if fault=="duplicate":result.update(total=2,commits=[HEAD,HEAD])
            if fault=="wrongbase":result["base"]=OTHER
            if fault=="headmissing":result["commits"]=[OTHER]
            if fault=="oversized":result["total"]=1001
            return result
        return {"sha":HEAD,"files":[{"name":"../escape","previous":None}]}
    with pytest.raises(PermissionError):newer_touched_paths({"gh_api":api},BASE,HEAD)
