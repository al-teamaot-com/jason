"""Read-only DNSFilter agent source-classification and decision gates.

No DNS settings/NIC change, service restart, reinstall, uninstall or reboot
occurs. The existing dedicated diagnostic component remains the authority for
service/install evidence; JSON only consumes independently parsed safe facts.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class JsonDnsAgentBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonDnsAgentAssessment:
    disposition: str
    filtering_service: str | None
    filtering_running: bool | None
    manager_running: bool | None
    dns_resolution_success: bool | None
    same_client_native_agent: bool | None
    install_candidate: bool
    reinstall_candidate: bool
    execute_authorized: bool = False


def classify_dns_agent_readonly(
    *,
    exact_client_id: str,
    exact_device_uid: str,
    exact_alert_uid: str,
    endpoint: Mapping[str, Any],
    source_alert: Mapping[str, Any],
    requires_dnsfilter: bool,
    services: Sequence[Mapping[str, Any]],
    installed_products: Sequence[Mapping[str, Any]],
    dns_resolution_success: bool | None,
    native_agents: Sequence[Mapping[str, Any]] | None = None,
    diagnostic_job_complete: bool = False,
) -> JsonDnsAgentAssessment:
    if (not exact_client_id or not exact_device_uid or
        not exact_alert_uid or not isinstance(requires_dnsfilter,bool) or
        str(endpoint.get("resource_id") or "")!=exact_device_uid or
        str(endpoint.get("companyID") or "")!=exact_client_id or
        str(source_alert.get("alertUid") or "")!=exact_alert_uid):
        raise JsonDnsAgentBoundaryError("DNS_AGENT_EXACT_SCOPE_CHANGED")
    source=source_alert.get("alertSourceInfo")
    if (not isinstance(source,Mapping) or
        str(source.get("deviceUid") or "")!=exact_device_uid):
        raise JsonDnsAgentBoundaryError("DNS_AGENT_ALERT_ENDPOINT_UNVERIFIED")
    if endpoint.get("online") is not True:
        return JsonDnsAgentAssessment(
            "waiting_device_access",None,None,None,None,None,
            False,False)
    if (diagnostic_job_complete is not True or
        not isinstance(services,Sequence) or
        not isinstance(installed_products,Sequence) or
        len(services)>100 or len(installed_products)>300):
        raise JsonDnsAgentBoundaryError("DNS_AGENT_DIAGNOSTIC_INCOMPLETE")
    names={
        str(row.get("Name") or "").casefold():row
        for row in services if isinstance(row,Mapping)
    }
    filter_name=next(
        (name for name in ("dns agent","dnsfilter agent") if name in names),
        None,
    )
    manager_name=next(
        (name for name in (
            "dns agent service manager","dnsfilter agent service manager"
        ) if name in names),None,
    )
    def running(name):
        if not name:return None
        return str(names[name].get("State") or "").casefold()=="running"
    filter_running=running(filter_name)
    manager_running=running(manager_name)
    if filter_name:
        version=str(names[filter_name].get("Version") or "")
        has_manager=manager_name is not None
    else:
        version=""
        has_manager=False
    installed=any(
        "dnsfilter" in str(item.get("name") or item.get("displayName") or "").casefold()
        or "dns agent" in str(item.get("name") or item.get("displayName") or "").casefold()
        for item in installed_products if isinstance(item,Mapping)
    )
    native_match=None
    if native_agents is not None:
        matching=[]
        for agent in native_agents:
            if not isinstance(agent,Mapping):
                raise JsonDnsAgentBoundaryError("DNS_AGENT_NATIVE_RECORD_INVALID")
            if str(agent.get("deviceUid") or "")==exact_device_uid:
                if str(agent.get("companyID") or "")!=exact_client_id:
                    raise JsonDnsAgentBoundaryError("DNS_AGENT_NATIVE_CROSS_CLIENT_SCOPE")
                matching.append(agent)
        if len(matching)>1:
            raise JsonDnsAgentBoundaryError("DNS_AGENT_NATIVE_AMBIGUOUS_DEVICE")
        native_match=len(matching)==1
    service_ok=bool(filter_running is True and (
        manager_running is True or not has_manager))
    if not requires_dnsfilter:
        disposition="policy_does_not_require_agent_human_review"
    elif service_ok and dns_resolution_success is True:
        disposition="local_healthy_alert_readback_required"
    elif not installed and not filter_name and native_match is not True:
        disposition="agent_absent_install_candidate"
    elif not service_ok:
        disposition="agent_partial_service_reinstall_candidate"
    elif dns_resolution_success is False:
        disposition="dnsfilter_attributable_dns_failure_unverified"
    else:
        disposition="diagnostic_inconclusive_human_review"
    return JsonDnsAgentAssessment(
        disposition,filter_name,filter_running,manager_running,
        dns_resolution_success,native_match,
        disposition=="agent_absent_install_candidate",
        disposition=="agent_partial_service_reinstall_candidate")
