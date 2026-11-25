"""Initial activation permits only its exact declared inventory additions."""
from copy import deepcopy
import pytest
from tools.owner_objective_install_scope import desired_policy,validate_policy_delta,grants,CAPABILITIES


@pytest.fixture
def before():
    return dict(schema_version="1.0",allowed_running_containers=["jason-runtime"],
        allowed_system_units=["jason-existing.service"],max_stopped_rollback_containers=21,
        required_containers=["jason-runtime"],required_system_units=["jason-required.timer"],
        forbidden_execution_prefixes=["/tmp/"])


def test_exact_new_component_and_two_units_retain_all_other_safety_fields(before):
    snapshot=deepcopy(before)
    after=desired_policy(before)
    assert before==snapshot
    assert after["max_stopped_rollback_containers"]==22
    assert after["required_containers"]==["jason-runtime"]
    assert after["forbidden_execution_prefixes"]==["/tmp/"]


@pytest.mark.parametrize("change",["foreign_container","foreign_unit","extra_rollback","required","forbidden","duplicate"])
def test_out_of_scope_policy_delta_denied(before,change):
    after=desired_policy(before)
    if change=="foreign_container":after["allowed_running_containers"].append("jason-foreign")
    if change=="foreign_unit":after["allowed_system_units"].append("jason-foreign.service")
    if change=="extra_rollback":after["max_stopped_rollback_containers"]+=1
    if change=="required":after["required_containers"]=[]
    if change=="forbidden":after["forbidden_execution_prefixes"]=[]
    if change=="duplicate":after["allowed_system_units"].append("jason-existing.service")
    with pytest.raises(PermissionError):validate_policy_delta(before,after)


def test_six_grants_never_add_wildcard_or_standing_service_execution():
    rows=grants("licensed-owner","jason-autonomy-worker")
    assert len(rows)==6 and len({g["grant_id"] for g in rows})==6
    assert {g["capability"] for g in rows}==set(CAPABILITIES)
    assert all(g["approval_required"] is True for g in rows if g["subject_id"]=="jason-autonomy-worker")
    assert all(g["client_id"] is None and g["organization_id"]=="aot" for g in rows)
