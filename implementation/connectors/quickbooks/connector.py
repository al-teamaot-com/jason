from __future__ import annotations

from datetime import date
from typing import Any, Mapping
from urllib.parse import quote

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

from .oauth import (
    QuickBooksOAuthError,
    QuickBooksOAuthStore,
    quickbooks_access_context,
)

QUICKBOOKS_PROVIDER = "quickbooks"
QUICKBOOKS_LOGICAL_SECRET = "quickbooks.oauth_client"

QUICKBOOKS_COMPANY_READ = "quickbooks.company.read"
QUICKBOOKS_ACCOUNT_SEARCH = "quickbooks.account.search"
QUICKBOOKS_VENDOR_SEARCH = "quickbooks.vendor.search"
QUICKBOOKS_CUSTOMER_SEARCH = "quickbooks.customer.search"
QUICKBOOKS_INVOICE_SEARCH = "quickbooks.invoice.search"
QUICKBOOKS_BILL_SEARCH = "quickbooks.bill.search"
QUICKBOOKS_PROFIT_LOSS_READ = "quickbooks.report.profit_loss.read"
QUICKBOOKS_BALANCE_SHEET_READ = "quickbooks.report.balance_sheet.read"

_CAPABILITY_OPERATIONS = {
    QUICKBOOKS_COMPANY_READ: ("company", None),
    QUICKBOOKS_ACCOUNT_SEARCH: ("query", "Account"),
    QUICKBOOKS_VENDOR_SEARCH: ("query", "Vendor"),
    QUICKBOOKS_CUSTOMER_SEARCH: ("query", "Customer"),
    QUICKBOOKS_INVOICE_SEARCH: ("query", "Invoice"),
    QUICKBOOKS_BILL_SEARCH: ("query", "Bill"),
    QUICKBOOKS_PROFIT_LOSS_READ: ("report", "ProfitAndLoss"),
    QUICKBOOKS_BALANCE_SHEET_READ: ("report", "BalanceSheet"),
}

_QUERY_ARGUMENTS = frozenset({"start_position", "max_results"})
_REPORT_ARGUMENTS = frozenset({"start_date", "end_date"})


class QuickBooksConnector:
    """Read-only QuickBooks Online connector bound to one OAuth-authorized Realm ID."""

    provider_name = QUICKBOOKS_PROVIDER
    capabilities = frozenset(_CAPABILITY_OPERATIONS)

    def __init__(
        self,
        *,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        oauth_store: QuickBooksOAuthStore,
        expected_environment: str = "sandbox",
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._oauth_store = oauth_store
        expected = str(expected_environment or "").strip().casefold()
        if expected not in {"sandbox", "production"}:
            raise ConnectorConfigurationError(
                "QuickBooks expected environment must be sandbox or production."
            )
        self._expected_environment = expected

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id.strip().casefold() != "aot":
            raise ConnectorAuthorizationError(
                "QuickBooks reads are restricted to the AOT organization."
            )

        operation, entity = _CAPABILITY_OPERATIONS[request.context.capability]
        arguments = dict(request.arguments)
        self._validate_arguments(operation, arguments)

        credentials = self._secrets.resolve(
            QUICKBOOKS_LOGICAL_SECRET,
            request.context,
        )
        try:
            access_token, realm_id, environment = quickbooks_access_context(
                self._oauth_store,
                credentials=credentials,
            )
        except QuickBooksOAuthError as exc:
            raise ConnectorAuthorizationError(
                "QuickBooks OAuth connection is unavailable."
            ) from exc

        if environment != self._expected_environment:
            raise ConnectorAuthorizationError(
                "QuickBooks OAuth environment does not match the active connector profile."
            )

        base_url = (
            "https://sandbox-quickbooks.api.intuit.com"
            if environment == "sandbox"
            else "https://quickbooks.api.intuit.com"
        )
        url, params = self._request_target(
            base_url=base_url,
            realm_id=realm_id,
            operation=operation,
            entity=entity,
            arguments=arguments,
        )
        self._audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": request.context.capability,
                "environment": environment,
                "realm_bound_by_oauth": True,
            },
        )
        payload = self._transport.request(
            method="GET",
            url=url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            params=params,
            timeout_seconds=30.0,
        )
        if not isinstance(payload, Mapping):
            raise ConnectorConfigurationError(
                "QuickBooks returned an invalid response shape."
            )
        self._audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
                "environment": environment,
                "realm_bound_by_oauth": True,
            },
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=dict(payload),
        )

    @staticmethod
    def _validate_arguments(
        operation: str,
        arguments: Mapping[str, Any],
    ) -> None:
        forbidden = {"realm_id", "realmId", "environment", "query"}
        supplied_forbidden = sorted(forbidden.intersection(arguments))
        if supplied_forbidden:
            raise ConnectorAuthorizationError(
                "QuickBooks company scope and raw query text are server-derived."
            )

        allowed = (
            frozenset()
            if operation == "company"
            else _QUERY_ARGUMENTS
            if operation == "query"
            else _REPORT_ARGUMENTS
        )
        unexpected = sorted(set(arguments) - set(allowed))
        if unexpected:
            raise ConnectorConfigurationError(
                "QuickBooks request contains unsupported argument(s): "
                + ", ".join(unexpected)
            )

        if operation == "query":
            try:
                start = int(arguments.get("start_position", 1))
                maximum = int(arguments.get("max_results", 100))
            except (TypeError, ValueError) as exc:
                raise ConnectorConfigurationError(
                    "QuickBooks paging values must be integers."
                ) from exc
            if start < 1 or not 1 <= maximum <= 1000:
                raise ConnectorConfigurationError(
                    "QuickBooks start_position must be positive and max_results 1-1000."
                )

        if operation == "report":
            start_date = arguments.get("start_date")
            end_date = arguments.get("end_date")
            parsed_start = _optional_iso_date(start_date, "start_date")
            parsed_end = _optional_iso_date(end_date, "end_date")
            if parsed_start and parsed_end and parsed_start > parsed_end:
                raise ConnectorConfigurationError(
                    "QuickBooks start_date must not be after end_date."
                )

    @staticmethod
    def _request_target(
        *,
        base_url: str,
        realm_id: str,
        operation: str,
        entity: str | None,
        arguments: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any] | None]:
        company_base = f"{base_url}/v3/company/{quote(realm_id, safe='')}"
        if operation == "company":
            return f"{company_base}/companyinfo/{quote(realm_id, safe='')}", None
        if operation == "query" and entity is not None:
            start = int(arguments.get("start_position", 1))
            maximum = int(arguments.get("max_results", 100))
            query = (
                f"select * from {entity} "
                f"startposition {start} maxresults {maximum}"
            )
            return f"{company_base}/query", {"query": query}
        if operation == "report" and entity is not None:
            params = {
                key: str(value)
                for key, value in arguments.items()
                if value is not None and str(value).strip()
            }
            return f"{company_base}/reports/{entity}", params or None
        raise ConnectorConfigurationError(
            "Unsupported QuickBooks operation."
        )


def _optional_iso_date(value: Any, field_name: str) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ConnectorConfigurationError(
            f"QuickBooks {field_name} must use YYYY-MM-DD."
        ) from exc
