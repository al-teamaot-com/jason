"""DNS Agent source-only dedicated diagnostic classification tests."""
import pytest
from jason_runtime.json_dns_agent_classifier import (
    JsonDnsAgentBoundaryError,classify_dns_agent_readonly,
)

ENDPOINT={"resource_id":"dev-1","hostname":"PC-1",
          "companyID":"777","online":True}
ALERT={"alertUid":"dns-alert","alertSourceInfo":{"deviceUid":"dev-1"}}
FILTER={"Name":"DNS Agent","State":"Running"}
MANAGER={"Name":"DNS Agent Service Manager","State":"Running"}


def classify(**change):
    options={
        "exact_client_id":"777","exact_device_uid":"dev-1",
        "exact_alert_uid":"dns-alert",
        "endpoint":ENDPOINT,"source_alert":ALERT,
        "requires_dnsfilter":True,
        "services":[FILTER,MANAGER],
        "installed_products":[{"name":"DNSFilter Agent"}],
        "dns_resolution_success":True,
        "native_agents":None,
        "diagnostic_job_complete":True,
    }
    options.update(change)
    return classify_dns_agent_readonly(**options)


def test_full_filter_and_manager_local_healthy_requires_alert_readback():
    result=classify()
    assert result.disposition=="local_healthy_alert_readback_required"
    assert result.filtering_running is True
    assert result.manager_running is True
    assert not result.execute_authorized


def test_true_absence_candidate_requires_both_software_and_services():
    result=classify(services=[],installed_products=[],
                    dns_resolution_success=None)
    assert result.disposition=="agent_absent_install_candidate"
    assert result.install_candidate is True
    assert not result.execute_authorized


def test_missing_software_list_alone_is_not_enough_for_install():
    result=classify(installed_products=[],services=[FILTER,MANAGER])
    assert result.disposition=="local_healthy_alert_readback_required"
    assert not result.install_candidate


def test_stopped_service_is_reinstall_candidate_never_autonomous_exec():
    result=classify(services=[{**FILTER,"State":"Stopped"},MANAGER])
    assert result.disposition=="agent_partial_service_reinstall_candidate"
    assert result.reinstall_candidate
    assert not result.execute_authorized


def test_dns_resolution_failure_is_not_permission_to_modify_dns_or_nic():
    result=classify(dns_resolution_success=False)
    assert result.disposition=="dnsfilter_attributable_dns_failure_unverified"
    assert not result.execute_authorized


def test_client_policy_not_required_denies_install():
    result=classify(requires_dnsfilter=False,services=[],
                    installed_products=[])
    assert result.disposition=="policy_does_not_require_agent_human_review"
    assert not result.install_candidate


def test_offline_endpoint_only_waits():
    result=classify(endpoint={**ENDPOINT,"online":False},
                    diagnostic_job_complete=False)
    assert result.disposition=="waiting_device_access"


@pytest.mark.parametrize("override",[
    {"exact_client_id":"other"},
    {"exact_device_uid":"other"},
    {"exact_alert_uid":"different"},
    {"endpoint":{**ENDPOINT,"companyID":"other"}},
    {"source_alert":{**ALERT,"alertSourceInfo":{"deviceUid":"foreign"}}},
    {"diagnostic_job_complete":False},
    {"native_agents":[{"deviceUid":"dev-1","companyID":"foreign"}]},
    {"native_agents":[
        {"deviceUid":"dev-1","companyID":"777"},
        {"deviceUid":"dev-1","companyID":"777"}]},
])
def test_unverified_identity_provider_scope_or_job_completion_denied(override):
    with pytest.raises(JsonDnsAgentBoundaryError):
        classify(**override)
