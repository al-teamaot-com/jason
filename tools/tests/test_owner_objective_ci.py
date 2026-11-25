from copy import deepcopy
from datetime import datetime,timezone
import pytest
from tools.owner_objective_ci import require_acceptance

NOW=datetime(2026,11,21,tzinfo=timezone.utc)
SHA="a"*40


def payload():
    return {"total":1,"rows":[{"name":"Owner Objective Completion","sha":SHA,"branch":"main",
        "event":"push","status":"completed","conclusion":"success","at":NOW.isoformat()}]}


def test_exact_main_push_acceptance_required():
    assert require_acceptance(lambda *a:payload(),SHA,now=NOW)


@pytest.mark.parametrize("field,value",[
 ("name","other"),("sha","b"*40),("branch","feature"),("event","pull_request"),
 ("status","in_progress"),("conclusion","failure"),("at","2020-01-01T00:00:00+00:00")])
def test_other_source_failed_stale_or_nonmain_acceptance_denies(field,value):
    data=payload();data["rows"][0][field]=value
    with pytest.raises(PermissionError):require_acceptance(lambda *a:data,SHA,now=NOW)


def test_ambiguous_or_incomplete_workflow_records_deny():
    data=payload();data["total"]=2
    with pytest.raises(PermissionError):require_acceptance(lambda *a:data,SHA,now=NOW)
