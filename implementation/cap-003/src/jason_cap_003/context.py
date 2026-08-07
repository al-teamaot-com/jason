from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from connectors.core.contracts import Connector, ConnectorContext, ConnectorRequest


class AutotaskBusinessContextError(RuntimeError):
    """Safe failure for governed Autotask business-context assembly."""

    def __init__(self, message: str, *, error_code: str = "AUTOTASK_CONTEXT_READ_FAILED") -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AutotaskBusinessContext:
    company: Mapping[str, Any]
    contacts: tuple[Mapping[str, Any], ...]
    configurations: tuple[Mapping[str, Any], ...]
    tickets: tuple[Mapping[str, Any], ...]
    contracts: tuple[Mapping[str, Any], ...]
    projects: tuple[Mapping[str, Any], ...]

    @property
    def company_id(self) -> str:
        return str(self.company["id"])


class AutotaskBusinessContextReader:
    """Compose narrow canonical Autotask reads into one company context."""

    def __init__(self, connector: Connector, *, max_related_records: int = 25) -> None:
        if max_related_records < 1 or max_related_records > 100:
            raise ValueError("max_related_records must be between 1 and 100.")
        self._connector = connector
        self._max_related_records = max_related_records

    def read_company_context(
        self,
        *,
        company_name: str,
        correlation_id: str,
        principal_id: str,
        organization_id: str,
    ) -> AutotaskBusinessContext:
        canonical_name = company_name.strip()
        if not canonical_name:
            raise AutotaskBusinessContextError(
                "company_name must be non-empty.",
                error_code="COMPANY_NAME_INVALID",
            )

        companies = self._query(
            capability="autotask.company.search",
            entity_field="companyName",
            value=canonical_name,
            correlation_id=correlation_id,
            principal_id=principal_id,
            organization_id=organization_id,
            client_id=None,
            max_records=2,
            error_code="COMPANY_LOOKUP_FAILED",
        )
        exact = [
            item
            for item in companies
            if str(item.get("companyName", "")).casefold() == canonical_name.casefold()
        ]
        if len(exact) != 1:
            raise AutotaskBusinessContextError(
                "Company lookup must resolve to exactly one exact Autotask company.",
                error_code="COMPANY_LOOKUP_NOT_UNIQUE",
            )
        company = exact[0]
        company_id = company.get("id")
        if company_id is None:
            raise AutotaskBusinessContextError(
                "Resolved Autotask company is missing its provider identifier.",
                error_code="COMPANY_ID_MISSING",
            )
        client_id = str(company_id)

        return AutotaskBusinessContext(
            company=company,
            contacts=tuple(
                self._query(
                    capability="autotask.contact.search",
                    entity_field="companyID",
                    value=company_id,
                    correlation_id=correlation_id,
                    principal_id=principal_id,
                    organization_id=organization_id,
                    client_id=client_id,
                    error_code="CONTACTS_READ_FAILED",
                )
            ),
            configurations=tuple(
                self._query(
                    capability="autotask.configuration_item.search",
                    entity_field="companyID",
                    value=company_id,
                    correlation_id=correlation_id,
                    principal_id=principal_id,
                    organization_id=organization_id,
                    client_id=client_id,
                    error_code="CONFIGURATIONS_READ_FAILED",
                )
            ),
            tickets=tuple(
                self._query(
                    capability="autotask.ticket.search",
                    entity_field="companyID",
                    value=company_id,
                    correlation_id=correlation_id,
                    principal_id=principal_id,
                    organization_id=organization_id,
                    client_id=client_id,
                    error_code="TICKETS_READ_FAILED",
                )
            ),
            contracts=tuple(
                self._query(
                    capability="autotask.contract.search",
                    entity_field="companyID",
                    value=company_id,
                    correlation_id=correlation_id,
                    principal_id=principal_id,
                    organization_id=organization_id,
                    client_id=client_id,
                    error_code="CONTRACTS_READ_FAILED",
                )
            ),
            projects=tuple(
                self._query(
                    capability="autotask.project.search",
                    entity_field="companyID",
                    value=company_id,
                    correlation_id=correlation_id,
                    principal_id=principal_id,
                    organization_id=organization_id,
                    client_id=client_id,
                    error_code="PROJECTS_READ_FAILED",
                )
            ),
        )

    def _query(
        self,
        *,
        capability: str,
        entity_field: str,
        value: object,
        correlation_id: str,
        principal_id: str,
        organization_id: str,
        client_id: str | None,
        max_records: int | None = None,
        error_code: str,
    ) -> tuple[Mapping[str, Any], ...]:
        search = json.dumps(
            {
                "filter": [
                    {
                        "op": "eq",
                        "field": entity_field,
                        "value": value,
                    }
                ],
                "MaxRecords": max_records or self._max_related_records,
            },
            separators=(",", ":"),
        )
        try:
            result = self._connector.execute(
                ConnectorRequest(
                    context=ConnectorContext(
                        correlation_id=correlation_id,
                        principal_id=principal_id,
                        organization_id=organization_id,
                        client_id=client_id,
                        capability=capability,
                        mode="observe",
                    ),
                    arguments={"search": search},
                )
            )
        except Exception as exc:
            raise AutotaskBusinessContextError(
                f"Governed Autotask read failed for {capability}.",
                error_code=error_code,
            ) from exc
        items = result.data.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise AutotaskBusinessContextError(
                "Autotask query returned an invalid items collection.",
                error_code=f"{error_code}_INVALID_RESPONSE",
            )
        return tuple(items)
