from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
    require_capability,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository

from .client import DnsFilterClient, require_dnsfilter_credentials

DNSFILTER_PROVIDER = "dnsfilter"
DNSFILTER_PROFILE = "dnsfilter-organization-read"
DNSFILTER_READONLY_SECRET = "dnsfilter.readonly"

_CAPABILITY_OPERATIONS = {
    "dnsfilter.organization.read": "organization_read",
    "dnsfilter.network.search": "network_search",
    "dnsfilter.policy.search": "policy_search",
    "dnsfilter.user_agent.search": "agent_search",
    "dnsfilter.user_agent.counts": "agent_counts",
}

_ALLOWED_ARGUMENTS = {
    "organization_read": {"company_id"},
    "network_search": {
        "company_id", "protected", "unprotected", "page_number", "page_size",
    },
    "policy_search": {
        "company_id", "include_global_policies", "page_number", "page_size",
    },
    "agent_search": {
        "company_id", "search", "state", "status", "agent_state",
        "policy_id", "traffic_received_last_15_mins", "page_number", "page_size",
    },
    "agent_counts": {
        "company_id", "search", "state", "status", "new_agent_states",
    },
}

_FORBIDDEN_SCOPE_ARGUMENTS = frozenset(
    {"organization_id", "organization_ids", "msp_id", "network_id", "network_ids", "site_id", "site_ids"}
)


class DnsFilterConnector:
    provider_name = DNSFILTER_PROVIDER
    capabilities = frozenset(_CAPABILITY_OPERATIONS)

    def __init__(
        self,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        boundaries: ClientBoundaryRepository,
        *,
        client_factory=DnsFilterClient,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._boundaries = boundaries
        self._client_factory = client_factory

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id != "aot":
            raise ConnectorAuthorizationError(
                "DNSFilter reads are restricted to the AOT organization."
            )

        operation = _CAPABILITY_OPERATIONS[request.context.capability]
        arguments = dict(request.arguments)
        self._validate_arguments(operation, arguments)
        company_id, organization_id, network_ids = self._resolve_boundary(
            request, arguments
        )
        client_scoped = company_id != "0"

        if client_scoped and operation == "policy_search" and bool(
            arguments.get("include_global_policies")
        ):
            raise ConnectorAuthorizationError(
                "DNSFilter global policy views are not approved for client-scoped reads."
            )
        if client_scoped and operation == "network_search" and any(
            key in arguments for key in ("protected", "unprotected")
        ):
            raise ConnectorConfigurationError(
                "Client-scoped DNSFilter site reads do not support "
                "protected/unprotected collection filters."
            )

        credentials = self._secrets.resolve(
            DNSFILTER_READONLY_SECRET,
            request.context,
        )
        require_dnsfilter_credentials(credentials)
        client = self._client_factory(credentials)

        audit_scope = {
            "provider": self.provider_name,
            "operation": operation,
            "company_id": company_id,
            "organization_id": organization_id,
            "network_scope_ids": list(network_ids),
            "organization_boundary_validated": True,
            "network_boundary_validated": bool(network_ids) or not client_scoped,
        }
        self._audit.record("connector.requested", request.context, audit_scope)

        data = self._execute_operation(
            client,
            operation,
            arguments,
            organization_id,
            network_ids,
            client_scoped=client_scoped,
        )
        data, verification = self._enforce_response_scope(
            operation,
            data,
            organization_id,
            network_ids,
            client_scoped=client_scoped,
        )
        self._audit.record(
            "connector.completed",
            request.context,
            {
                **audit_scope,
                "scope_verification": verification,
            },
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _validate_arguments(operation: str, arguments: Mapping[str, Any]) -> None:
        if _FORBIDDEN_SCOPE_ARGUMENTS.intersection(arguments):
            raise ConnectorAuthorizationError(
                "DNSFilter organization and network scope is server-derived and may not be supplied."
            )
        unexpected = sorted(set(arguments) - _ALLOWED_ARGUMENTS[operation])
        if unexpected:
            raise ConnectorConfigurationError(
                "DNSFilter request contains unsupported argument(s): "
                + ", ".join(unexpected)
            )
        if operation in {"network_search", "policy_search", "agent_search"}:
            try:
                page_number = int(arguments.get("page_number", 1))
                page_size = int(arguments.get("page_size", 100))
            except (TypeError, ValueError) as exc:
                raise ConnectorConfigurationError(
                    "DNSFilter paging values must be integers."
                ) from exc
            if page_number < 1 or not 1 <= page_size <= 500:
                raise ConnectorConfigurationError(
                    "DNSFilter page_number must be positive and page_size must be 1-500."
                )
        if operation == "agent_search":
            agent_state = str(arguments.get("agent_state") or "").strip()
            if agent_state and agent_state not in {
                "protected", "unprotected", "bypassed", "pending_uninstall",
                "uninstalled", "offline",
            }:
                raise ConnectorConfigurationError(
                    "DNSFilter agent_state is not supported."
                )
            state = str(arguments.get("state") or "").strip()
            if state and state not in {"online", "offline"}:
                raise ConnectorConfigurationError(
                    "DNSFilter state must be online or offline."
                )

    def _resolve_boundary(
        self,
        request: ConnectorRequest,
        arguments: Mapping[str, Any],
    ) -> tuple[str, int, tuple[int, ...]]:
        raw_company_id = arguments.get("company_id")
        if isinstance(raw_company_id, bool):
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for DNSFilter access."
            )
        try:
            company_id = str(int(raw_company_id))
        except (TypeError, ValueError) as exc:
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for DNSFilter access."
            ) from exc
        if int(company_id) < 0:
            raise ConnectorAuthorizationError(
                "An exact Autotask company_id is required for DNSFilter access."
            )
        if (
            request.context.client_id is not None
            and str(request.context.client_id) != company_id
        ):
            raise ConnectorAuthorizationError(
                "DNSFilter request client scope does not match the selected company."
            )

        boundary = self._boundaries.find_active_for_client(
            client_id=company_id,
            provider=DNSFILTER_PROVIDER,
        )
        if boundary is None or boundary.status is not BoundaryStatus.VALIDATED:
            raise ConnectorAuthorizationError(
                "No validated DNSFilter organization boundary exists for this company."
            )
        if boundary.profile != DNSFILTER_PROFILE:
            raise ConnectorAuthorizationError(
                "DNSFilter organization boundary uses an unapproved profile."
            )
        try:
            organization_id = int(str(boundary.external_tenant_id))
        except (TypeError, ValueError) as exc:
            raise ConnectorAuthorizationError(
                "DNSFilter organization boundary contains an invalid organization ID."
            ) from exc
        if organization_id < 1:
            raise ConnectorAuthorizationError(
                "DNSFilter organization boundary contains an invalid organization ID."
            )

        network_ids: list[int] = []
        for raw_scope in boundary.external_scope_ids:
            try:
                scope_id = int(str(raw_scope))
            except (TypeError, ValueError) as exc:
                raise ConnectorAuthorizationError(
                    "DNSFilter client boundary contains an invalid network ID."
                ) from exc
            if scope_id < 1:
                raise ConnectorAuthorizationError(
                    "DNSFilter client boundary contains an invalid network ID."
                )
            network_ids.append(scope_id)
        network_scope = tuple(sorted(set(network_ids)))
        if company_id != "0" and not network_scope:
            raise ConnectorAuthorizationError(
                "No validated DNSFilter network boundary exists for this company."
            )
        return company_id, organization_id, network_scope

    @staticmethod
    def _paging(arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "page[number]": int(arguments.get("page_number", 1)),
            "page[size]": int(arguments.get("page_size", 100)),
        }

    @classmethod
    def _execute_operation(
        cls,
        client: DnsFilterClient,
        operation: str,
        arguments: Mapping[str, Any],
        organization_id: int,
        network_ids: tuple[int, ...],
        *,
        client_scoped: bool,
    ) -> Mapping[str, Any]:
        if operation == "organization_read":
            return client.get(f"/v1/organizations/{organization_id}")

        if operation == "network_search":
            if client_scoped:
                resources = [
                    cls._exact_resource(
                        client,
                        f"/v1/networks/{network_id}",
                        label="network",
                    )
                    for network_id in network_ids
                ]
                return {"data": resources}

            params = cls._paging(arguments)
            params["organization_id"] = organization_id
            for key in ("protected", "unprotected"):
                if key in arguments:
                    params[key] = arguments[key]
            return client.get("/v1/networks/msp", params)

        if operation == "policy_search":
            if client_scoped:
                policy_ids: set[int] = set()
                for network_id in network_ids:
                    network = cls._exact_resource(
                        client,
                        f"/v1/networks/{network_id}",
                        label="network",
                    )
                    cls._assert_resource_id(network, network_id, "network")
                    cls._assert_relationship_organization(
                        network,
                        organization_id,
                    )
                    policy_ids.update(cls._relationship_policy_ids(network))
                resources = [
                    cls._exact_resource(
                        client,
                        f"/v1/policies/{policy_id}",
                        label="policy",
                    )
                    for policy_id in sorted(policy_ids)
                ]
                return {"data": resources}

            params = cls._paging(arguments)
            params["organization_id"] = organization_id
            if "include_global_policies" in arguments:
                params["include_global_policies"] = arguments["include_global_policies"]
            return client.get("/v1/policies", params)

        if operation == "agent_search":
            params = cls._paging(arguments)
            params["organization_ids"] = [organization_id]
            if client_scoped:
                params["network_ids"] = list(network_ids)
            for key in (
                "search", "state", "status", "agent_state",
                "policy_id", "traffic_received_last_15_mins",
            ):
                if key in arguments:
                    params[key] = arguments[key]
            return client.get("/v1/user_agents", params)

        if operation == "agent_counts":
            params: dict[str, Any] = {"organization_ids": [organization_id]}
            if client_scoped:
                params["network_ids"] = list(network_ids)
            for key in ("search", "state", "status", "new_agent_states"):
                if key in arguments:
                    params[key] = arguments[key]
            return client.get("/v1/user_agents/counts", params)

        raise ConnectorConfigurationError("Unsupported DNSFilter operation.")

    @classmethod
    def _enforce_response_scope(
        cls,
        operation: str,
        data: Mapping[str, Any],
        expected_organization_id: int,
        network_ids: tuple[int, ...],
        *,
        client_scoped: bool,
    ) -> tuple[Mapping[str, Any], str]:
        payload = data.get("data")

        if operation == "organization_read":
            cls._assert_resource_id(payload, expected_organization_id, "organization")
            if not client_scoped:
                return data, "organization_id_exact"
            resource = dict(payload) if isinstance(payload, Mapping) else {}
            minimized = {
                key: resource[key]
                for key in ("id", "type")
                if key in resource
            }
            return {**dict(data), "data": minimized}, "organization_minimized_for_client"

        if operation == "agent_counts":
            return data, (
                "provider_request_network_scope"
                if client_scoped
                else "organization_scope"
            )

        resources = payload if isinstance(payload, list) else [payload]
        if not resources or resources == [None]:
            return data, "empty_response_scope_safe"

        authorized = frozenset(network_ids)
        for resource in resources:
            if operation != "agent_search":
                cls._assert_relationship_organization(
                    resource, expected_organization_id
                )
            if client_scoped:
                observed = (
                    {cls._resource_id(resource, "network")}
                    if operation == "network_search"
                    else cls._relationship_network_ids(resource)
                )
                if not observed:
                    raise ConnectorAuthorizationError(
                        "DNSFilter response did not prove the client network boundary."
                    )
                if not observed.issubset(authorized):
                    raise ConnectorAuthorizationError(
                        "DNSFilter response crossed the authorized client network boundary."
                    )

        return data, (
            "network_scope_exact"
            if client_scoped
            else "organization_scope"
        )

    @staticmethod
    def _exact_resource(
        client: DnsFilterClient,
        path: str,
        *,
        label: str,
    ) -> Mapping[str, Any]:
        response = client.get(path)
        resource = response.get("data")
        if not isinstance(resource, Mapping):
            raise ConnectorAuthorizationError(
                f"DNSFilter exact {label} read returned an invalid shape."
            )
        return resource

    @staticmethod
    def _relationship_policy_ids(resource: Any) -> set[int]:
        if not isinstance(resource, Mapping):
            raise ConnectorAuthorizationError(
                "DNSFilter network response has an invalid shape."
            )
        relationships = resource.get("relationships")
        if not isinstance(relationships, Mapping):
            raise ConnectorAuthorizationError(
                "DNSFilter network response did not prove policy relationships."
            )
        observed: set[int] = set()
        for key in ("policy", "policies", "scheduled_policy"):
            relationship = relationships.get(key)
            if not isinstance(relationship, Mapping):
                continue
            related = relationship.get("data")
            items = related if isinstance(related, list) else [related]
            for item in items:
                if item is None:
                    continue
                if not isinstance(item, Mapping):
                    raise ConnectorAuthorizationError(
                        "DNSFilter network response contained an invalid policy relationship."
                    )
                try:
                    observed.add(int(str(item.get("id"))))
                except (TypeError, ValueError) as exc:
                    raise ConnectorAuthorizationError(
                        "DNSFilter network response contained an invalid policy identifier."
                    ) from exc
        return observed

    @staticmethod
    def _resource_id(resource: Any, label: str) -> int:
        if not isinstance(resource, Mapping):
            raise ConnectorAuthorizationError(
                f"DNSFilter {label} response has an invalid shape."
            )
        try:
            return int(str(resource.get("id")))
        except (TypeError, ValueError) as exc:
            raise ConnectorAuthorizationError(
                f"DNSFilter {label} response did not prove its resource ID."
            ) from exc

    @classmethod
    def _assert_resource_id(
        cls,
        resource: Any,
        expected_id: int,
        label: str,
    ) -> None:
        if cls._resource_id(resource, label) != expected_id:
            raise ConnectorAuthorizationError(
                f"DNSFilter {label} response crossed the authorized boundary."
            )

    @staticmethod
    def _relationship_network_ids(resource: Any) -> set[int]:
        if not isinstance(resource, Mapping):
            raise ConnectorAuthorizationError(
                "DNSFilter returned a non-object resource."
            )
        relationships = resource.get("relationships")
        if not isinstance(relationships, Mapping):
            return set()
        observed: set[int] = set()
        for key in ("network", "networks", "site", "sites"):
            relationship = relationships.get(key)
            if not isinstance(relationship, Mapping):
                continue
            related = relationship.get("data")
            items = related if isinstance(related, list) else [related]
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                try:
                    observed.add(int(str(item.get("id"))))
                except (TypeError, ValueError) as exc:
                    raise ConnectorAuthorizationError(
                        "DNSFilter response contained an invalid network relationship."
                    ) from exc
        return observed

    @staticmethod
    def _assert_relationship_organization(
        resource: Any,
        expected_organization_id: int,
    ) -> None:
        if not isinstance(resource, Mapping):
            raise ConnectorAuthorizationError(
                "DNSFilter returned a non-object resource."
            )
        relationships = resource.get("relationships")
        if not isinstance(relationships, Mapping):
            raise ConnectorAuthorizationError(
                "DNSFilter response did not prove the organization boundary."
            )
        organization = relationships.get("organization")
        if not isinstance(organization, Mapping):
            raise ConnectorAuthorizationError(
                "DNSFilter response did not prove the organization boundary."
            )
        org_data = organization.get("data")
        if not isinstance(org_data, Mapping):
            raise ConnectorAuthorizationError(
                "DNSFilter response did not prove the organization boundary."
            )
        try:
            observed = int(str(org_data.get("id")))
        except (TypeError, ValueError) as exc:
            raise ConnectorAuthorizationError(
                "DNSFilter response contained an invalid organization relationship."
            ) from exc
        if observed != expected_organization_id:
            raise ConnectorAuthorizationError(
                "DNSFilter response crossed the authorized organization boundary."
            )
