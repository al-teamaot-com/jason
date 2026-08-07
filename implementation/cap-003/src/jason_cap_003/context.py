from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from connectors.core.contracts import (
    Connector,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolutionError


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
                error_code="COMPANY_NAME_REQUIRED",
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
            failure_prefix="COMPANY_LOOKUP",
        )
        exact = [
            item
            for item in companies
            if str(item.get("companyName", "")).casefold() == canonical_name.casefold()
        ]
        if not exact:
            raise AutotaskBusinessContextError(
                "Company lookup returned no exact Autotask company.",
                error_code="COMPANY_MATCH_NOT_FOUND",
            )
        if len(exact) > 1:
            raise AutotaskBusinessContextError(
                "Company lookup returned multiple exact Autotask companies.",
                error_code="COMPANY_MATCH_AMBIGUOUS",
            )
        company = exact[0]
        company_id = company.get("id")
        if company_id is None:
            raise AutotaskBusinessContextError(
                "Resolved Autotask company is missing its provider identifier.",
                error_code="COMPANY_PROVIDER_ID_MISSING",
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
                    failure_prefix="CONTACTS_READ",
                )
            ),
            configurations=tuple(
                self._query(
                    capability="autotask.configuration.search",
                    entity_field="companyID",
                    value=company_id,
                    correlation_id=correlation_id,
                    principal_id=principal_id,
                    organization_id=organization_id,
                    client_id=client_id,
                    failure_prefix="CONFIGURATIONS_READ",
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
                    failure_prefix="TICKETS_READ",
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
                    failure_prefix="CONTRACTS_READ",
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
                    failure_prefix="PROJECTS_READ",
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
        failure_prefix: str,
        max_records: int | None = None,
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
        except OpenBaoSecretResolutionError as exc:
            raise AutotaskBusinessContextError(
                "Autotask read could not resolve its governed secret.",
                error_code=f"{failure_prefix}_SECRET_RESOLUTION_FAILED",
            ) from exc
        except ConnectorConfigurationError as exc:
            raise AutotaskBusinessContextError(
                "Autotask connector configuration is unavailable.",
                error_code=f"{failure_prefix}_CONNECTOR_CONFIGURATION_FAILED",
            ) from exc
        except RuntimeError as exc:
            raise AutotaskBusinessContextError(
                "Autotask provider request failed.",
                error_code=f"{failure_prefix}_PROVIDER_REQUEST_FAILED",
            ) from exc
        except Exception as exc:
            raise AutotaskBusinessContextError(
                "Autotask read failed safely.",
                error_code=f"{failure_prefix}_UNEXPECTED_FAILURE",
            ) from exc

        items = result.data.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise AutotaskBusinessContextError(
                "Autotask query returned an invalid items collection.",
                error_code=f"{failure_prefix}_INVALID_RESPONSE",
            )
        return tuple(items)
