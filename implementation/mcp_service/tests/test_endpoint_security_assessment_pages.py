"""Full structured finding pages through the already-authorized read boundary."""
from __future__ import annotations

from copy import deepcopy
import pytest

from jason_mcp.endpoint_security_assessment_pages import (
    FindingPageError, project_finding_page,
)
from autonomous_remediation.test_endpoint_security_assessment import (
    HOST,JOB,COMPONENT,HUNT,LENOVO_A,LENOVO_B,MAPS,output,
)
DEVICE="fa38813a-91c4-b2e8-201a-4801f5e3aab2"


def payload(findings=()):
    return {"data":{
        "resource_id":JOB, "device_uid":DEVICE, "component_uid":COMPONENT,
        "stream":"stdout","match_count":1,"output_bounded":False,
        "outputs":[{"component_uid":COMPONENT,"stream":"stdout",
                    "text":output(findings), "truncated":False}],
    }}


def page(data,page_index=0,page_size=2):
    return project_finding_page(data,job_uid=JOB,device_uid=DEVICE,
                               component_uid=COMPONENT,hostname=HOST,
                               page_index=page_index,page_size=page_size)


def test_pages_reconstruct_complete_findings_and_preserve_source_hash():
    f=[HUNT,LENOVO_A,LENOVO_B,MAPS]
    one=page(payload(f),0,2)
    two=page(payload(f),1,2)
    assert one["total_findings"]==4
    assert one["complete"] is False
    assert two["complete"] is True
    assert one["full_list_sha256"]==two["full_list_sha256"]
    assert one["severity_counts"]=={"High":0,"Medium":3,"Low":1,"Info":0}
    assert [x["name"] for x in one["findings"]+two["findings"]]==[x.name for x in f]
    assert all(set(x)=={"severity","category","name","title","path"}
               for x in one["findings"]+two["findings"])
    assert "stdout" not in one and "command_line" not in str(one)


@pytest.mark.parametrize("mod",[
    lambda data: data["data"].update(device_uid="unrelated-device"),
    lambda data: data["data"].update(resource_id="unrelated-job"),
    lambda data: data["data"].update(match_count=2),
    lambda data: data["data"].update(output_bounded=True),
    lambda data: data["data"]["outputs"][0].update(truncated=True),
    lambda data: data["data"]["outputs"][0].update(component_uid="different"),
    lambda data: data["data"]["outputs"][0].update(stream="stderr"),
    lambda data: data["data"]["outputs"][0].update(text="missing report"),
    lambda data: data["data"]["outputs"][0].update(text=output([HUNT],bounded=True)),
])
def test_invalid_or_partial_provider_output_fails_closed(mod):
    x=payload([HUNT])
    mod(x)
    with pytest.raises(FindingPageError):
        page(x)


def test_central_orchestrator_nested_provider_data_has_same_bound_findings():
    inner = payload([HUNT, MAPS])["data"]
    outer = {"data": {"provider_data": inner}}
    result = page(outer)
    assert result["total_findings"] == 2
    assert [f["name"] for f in result["findings"]] == ["HUNTAgent", "MapS.bat"]
    # A forged outer selector must never override the provider evidence.
    outer["data"]["resource_id"] = "unrelated-job"
    with pytest.raises(FindingPageError, match="ENVELOPE_SELECTOR_CONFLICT"):
        page(outer)


def test_omitted_finding_blocks_complete_report():
    x=payload([])
    x["data"]["outputs"][0]["text"]=output([],omitted=1)
    with pytest.raises(FindingPageError):
        page(x)


def test_bad_paging_bounds_are_rejected():
    x=payload([])
    for bad in (-1,True,2.1):
        with pytest.raises(FindingPageError):
            page(x,page_index=bad)
    with pytest.raises(FindingPageError):
        page(x,page_size=100)


def test_no_raw_user_command_line_or_unbounded_content_is_projected():
    x=payload([HUNT])
    text=x["data"]["outputs"][0]["text"]
    x["data"]["outputs"][0]["text"]=text.replace(
        '"path": "', '"path": "')
    result=page(x)
    assert "text" not in result and "stdout" not in result
    assert len(result["findings"])==1
