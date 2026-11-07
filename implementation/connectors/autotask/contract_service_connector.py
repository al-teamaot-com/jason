"""Dormant, client-scoped ContractServices GET connector.

No runtime/MCP/manifest integration is registered here. A future reviewed
adapter must supply an independently trusted requester/company authorizer and
activate this class only under an exact approved credential/role policy.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Protocol
from urllib.parse import urlparse

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.contract_service_scope import (
    scoped_contract_service_query, verify_contract_service_page,
)
from connectors.core.contracts import (
    ConnectorContext, ConnectorRequest, ConnectorResult,
)


class ContractCompanyAuthorizer(Protocol):
    def authorize_contract_company(
        self, *, context: ConnectorContext, company_id: int, contract_id: int,
    ) -> bool: ...


class DormantScopedContractServicesReadConnector(AutotaskConnector):
    """Allow only one contract's read after a trusted company authorization.

    Requests with no wired authorizer are unconstructable. No public endpoint
    or generic entity read becomes available merely by importing this class.
    """

    logical_secret = "autotask.write"
    capabilities = frozenset({"autotask.contract_service.scoped_query"})

    def __init__(self, *, company_authorizer: ContractCompanyAuthorizer, **kwargs: Any):
        if company_authorizer is None:
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_AUTHORIZER_REQUIRED")
        super().__init__(**kwargs)
        self._company_authorizer = company_authorizer

    @staticmethod
    def _api_root(prepared_url: str) -> str:
        parsed = urlparse(prepared_url)
        if (parsed.scheme != "https" or parsed.port not in (None, 443)
                or not parsed.hostname or not parsed.hostname.endswith(".autotask.net")
                or "/V1.0/Contracts/" not in parsed.path
                or parsed.username is not None or parsed.password is not None):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PROVIDER_ORIGIN_INVALID")
        return prepared_url.split("/V1.0/Contracts/", 1)[0] + "/V1.0"

    def _get(self, url: str, headers: Mapping[str, str], *, params=None):
        if not isinstance(url, str):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_URL_INVALID")
        return self._transport.request(
            method="GET", url=url, headers=headers, params=params,
            json=None, timeout_seconds=30.0,
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        context = request.context
        if (context.capability not in self.capabilities
                or context.mode != "observe"
                or context.organization_id != "aot"
                or context.client_id is not None
                or not str(context.principal_id).strip()):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_AUTHORITY_INVALID")
        if set(request.arguments) - {"contract_id", "page_size"}:
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_SELECTOR_INVALID")
        contract_id = request.arguments.get("contract_id")
        page_size = request.arguments.get("page_size", 25)
        if type(contract_id) is not int or contract_id < 1:
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_ID_INVALID")
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PAGE_LIMIT")

        credentials = self._secrets.resolve(self.logical_secret, context)
        # Use the canonical Autotask compiler to obtain zone + fixed parent URL.
        parent_request = ConnectorRequest(
            context=replace(context, capability="autotask.entity.get"),
            arguments={"entity": "Contracts", "entity_id": contract_id},
        )
        parent_prepared = super().prepare_request(parent_request, credentials)
        root = self._api_root(parent_prepared.url)
        headers = parent_prepared.headers
        parent_payload = self._get(parent_prepared.url, headers)
        if not isinstance(parent_payload, Mapping):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PARENT_UNVERIFIED")
        parent = parent_payload.get("item", parent_payload)
        if not isinstance(parent, Mapping):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PARENT_UNVERIFIED")
        company_id = parent.get("companyID")
        if type(company_id) is not int or company_id < 1:
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PARENT_UNVERIFIED")
        if self._company_authorizer.authorize_contract_company(
            context=context, company_id=company_id, contract_id=contract_id,
        ) is not True:
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_REQUESTER_DENIED")

        entity = self._get(root + "/ContractServices/entityInformation", headers)
        fields_payload = self._get(
            root + "/ContractServices/entityInformation/fields", headers,
        )
        if not isinstance(entity, Mapping) or not isinstance(fields_payload, Mapping):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_SCHEMA_INVALID")
        query = scoped_contract_service_query(
            contract_id=contract_id, expected_company_id=company_id,
            verified_parent_contract=parent, provider_info=entity,
            provider_fields=fields_payload.get("fields", ()),
            page_size=page_size,
        )
        child_payload = self._get(
            root + "/ContractServices/query", headers, params={"search": query},
        )
        if not isinstance(child_payload, Mapping):
            raise PermissionError("AUTOTASK_CONTRACT_SERVICE_RESPONSE_INVALID")
        details = child_payload.get("pageDetails")
        if details is not None:
            if not isinstance(details, Mapping):
                raise PermissionError("AUTOTASK_CONTRACT_SERVICE_PAGE_DETAILS_INVALID")
            if details.get("nextPageUrl"):
                raise PermissionError("AUTOTASK_CONTRACT_SERVICE_CONTINUATION_UNSUPPORTED")
        items = verify_contract_service_page(
            items=child_payload.get("items"), exact_contract_id=contract_id,
            expected_company_id=company_id, verified_parent_contract=parent,
            max_records=page_size,
        )
        return ConnectorResult(
            capability=context.capability, provider=self.provider_name,
            data={"items": list(items), "contractID": contract_id,
                  "companyID": company_id, "boundedPageValidated": True,
                  "fullContractCoverageVerified": False},
        )
