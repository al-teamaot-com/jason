"""Generic Microsoft Graph resource connector backed by provider metadata.

The connector implements two provider-neutral execution classes:
``provider.resource.search`` and ``provider.resource.read``.  It does not contain a
list of Microsoft business entities or question-specific request paths.  The resource
handle and field vocabulary are accepted only after they are revalidated against a
catalog derived from Microsoft's authoritative Graph metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, urlsplit

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    ConnectorTransportError,
    HttpTransport,
    bounded_transport_timeout,
    require_capability,
)

from .resource_metadata import MicrosoftGraphResourceCatalog
from .resource_read import (
    MicrosoftGraphFilter,
    MicrosoftGraphOrder,
    MicrosoftGraphReadCompiler,
    MicrosoftGraphReadIntent,
    MicrosoftGraphResourceReadError,
)


PROVIDER_RESOURCE_SEARCH = "provider.resource.search"
PROVIDER_RESOURCE_READ = "provider.resource.read"
_CAPABILITIES = frozenset({PROVIDER_RESOURCE_SEARCH, PROVIDER_RESOURCE_READ})
_MAX_RESPONSE_ITEMS = 999


class MicrosoftGraphClientTokenProvider(Protocol):
    def acquire_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> Any: ...


class MicrosoftGraphResourceCatalogSource(Protocol):
    def catalog_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> MicrosoftGraphResourceCatalog: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphResourceConnector:
    """Execute bounded structural Graph reads without entity-specific code."""

    tokens: MicrosoftGraphClientTokenProvider
    catalogs: MicrosoftGraphResourceCatalogSource
    transport: HttpTransport
    audit: AuditSink
    permission_profile_name: str = "directory-read"
    provider_name: str = "microsoft_graph"
    capabilities: frozenset[str] = _CAPABILITIES
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if not self.permission_profile_name.strip():
            raise ValueError("Microsoft Graph permission profile is required")
        if self.provider_name != "microsoft_graph":
            raise ValueError("Microsoft Graph resource connector provider name is fixed")
        if self.capabilities != _CAPABILITIES:
            raise ValueError("Microsoft Graph resource connector capability surface is fixed")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("Microsoft Graph timeout must be between 0 and 60 seconds")

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        client_id = (request.context.client_id or "").strip()
        if not client_id:
            raise ConnectorAuthorizationError(
                "Microsoft Graph resource reads require a governed client boundary."
            )

        catalog = self.catalogs.catalog_for_client(
            client_id=client_id,
            correlation_id=request.context.correlation_id,
        )
        intent = self._intent(request=request, catalog=catalog)
        compiled = MicrosoftGraphReadCompiler(catalog=catalog).compile(
            intent=intent,
            permission_profile_name=self.permission_profile_name,
        )

        token = self.tokens.acquire_for_client(
            client_id=client_id,
            correlation_id=request.context.correlation_id,
        )
        access_token = str(getattr(token, "access_token", "")).strip()
        if not access_token or any(character.isspace() for character in access_token):
            raise ConnectorAuthorizationError(
                "Microsoft Graph application token is unavailable or malformed."
            )

        self.audit.record(
            "connector.microsoft_graph.resource_read.requested",
            request.context,
            {
                "provider_resource_handle": compiled.resource.resource_handle,
                "operation": request.context.capability,
                "selected_field_count": len(compiled.selected_fields),
                "bounded_top": intent.top if intent.resource_id is None else 1,
                "metadata_source": catalog.source_reference,
            },
        )

        try:
            response = self.transport.request(
                method=compiled.request.method,
                url=_url_without_query(compiled.request.url),
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                params=_query_parameters(compiled.request.url),
                timeout_seconds=bounded_transport_timeout(self.timeout_seconds),
            )
        except ConnectorTransportError:
            raise
        except Exception as error:
            raise ConnectorTransportError(
                "Microsoft Graph resource transport failed."
            ) from error

        data, warnings = self._shape_response(
            response=response,
            selected_fields=compiled.selected_fields,
            search=intent.resource_id is None,
            top=intent.top,
        )

        self.audit.record(
            "connector.microsoft_graph.resource_read.completed",
            request.context,
            {
                "provider_resource_handle": compiled.resource.resource_handle,
                "operation": request.context.capability,
                "result_count": _result_count(data),
                "warning_count": len(warnings),
            },
        )

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
            evidence_ids=(),
            warnings=warnings,
        )

    def _intent(
        self,
        *,
        request: ConnectorRequest,
        catalog: MicrosoftGraphResourceCatalog,
    ) -> MicrosoftGraphReadIntent:
        arguments = request.arguments
        handle = _required_string(arguments, "provider_resource_handle")
        # Fail before any token acquisition if the trusted resource binding does not
        # exist in the provider's current metadata catalog.
        catalog.get(handle)

        selected = _string_tuple(arguments.get("field_paths"), field_name="field_paths")
        if not selected:
            raise MicrosoftGraphResourceReadError(
                "provider resource read requires a bounded field projection"
            )

        if request.context.capability == PROVIDER_RESOURCE_READ:
            resource_id = _required_string(arguments, "resource_id")
            return MicrosoftGraphReadIntent(
                resource_handle=handle,
                resource_id=resource_id,
                select=selected,
            )

        filters = _filters(arguments.get("filters"))
        order_by = _orders(arguments.get("order_by"))
        top = arguments.get("top", 50)
        if isinstance(top, bool):
            raise MicrosoftGraphResourceReadError("provider resource top must be an integer")
        try:
            top = int(top)
        except (TypeError, ValueError) as error:
            raise MicrosoftGraphResourceReadError(
                "provider resource top must be an integer"
            ) from error
        return MicrosoftGraphReadIntent(
            resource_handle=handle,
            select=selected,
            filters=filters,
            order_by=order_by,
            top=top,
        )

    @staticmethod
    def _shape_response(
        *,
        response: Mapping[str, Any],
        selected_fields: tuple[str, ...],
        search: bool,
        top: int,
    ) -> tuple[Mapping[str, Any], tuple[str, ...]]:
        if not isinstance(response, Mapping):
            raise MicrosoftGraphResourceReadError(
                "Microsoft Graph response must be an object"
            )

        if not search:
            item = _project_record(response, selected_fields)
            return {"item": item}, ()

        raw_items = response.get("value", ())
        if not isinstance(raw_items, Sequence) or isinstance(
            raw_items, (str, bytes, bytearray)
        ):
            raise MicrosoftGraphResourceReadError(
                "Microsoft Graph collection response is invalid"
            )

        limit = min(int(top), _MAX_RESPONSE_ITEMS)
        items = tuple(
            _project_record(item, selected_fields)
            for item in raw_items[:limit]
            if isinstance(item, Mapping)
        )
        warnings: tuple[str, ...] = ()
        if len(raw_items) > limit:
            warnings = ("provider_result_truncated_to_governed_limit",)
        elif response.get("@odata.nextLink"):
            # Never expose provider navigation URLs to the reasoning layer.  The
            # caller can request another bounded read through governed pagination
            # once a provider-neutral continuation contract exists.
            warnings = ("provider_has_additional_results",)

        return {"items": items, "count": len(items)}, warnings


def _required_string(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise MicrosoftGraphResourceReadError(f"{name} is required")
    return value.strip()


def _string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MicrosoftGraphResourceReadError(f"{field_name} must be an array")
    output = tuple(str(item).strip() for item in value)
    if any(not item for item in output):
        raise MicrosoftGraphResourceReadError(f"{field_name} contains an empty value")
    return tuple(dict.fromkeys(output))


def _filters(value: Any) -> tuple[MicrosoftGraphFilter, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MicrosoftGraphResourceReadError("filters must be an array")
    output: list[MicrosoftGraphFilter] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise MicrosoftGraphResourceReadError("each filter must be an object")
        output.append(
            MicrosoftGraphFilter(
                field=_required_string(item, "field"),
                operator=_required_string(item, "operator"),
                value=item.get("value"),
            )
        )
    return tuple(output)


def _orders(value: Any) -> tuple[MicrosoftGraphOrder, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MicrosoftGraphResourceReadError("order_by must be an array")
    output: list[MicrosoftGraphOrder] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise MicrosoftGraphResourceReadError("each order_by item must be an object")
        output.append(
            MicrosoftGraphOrder(
                field=_required_string(item, "field"),
                direction=str(item.get("direction", "asc")),
            )
        )
    return tuple(output)


def _project_record(record: Mapping[str, Any], fields: tuple[str, ...]) -> Mapping[str, Any]:
    return {field: record.get(field) for field in fields if field in record}


def _url_without_query(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _query_parameters(url: str) -> Mapping[str, str] | None:
    query = urlsplit(url).query
    return dict(parse_qsl(query, keep_blank_values=True)) if query else None


def _result_count(data: Mapping[str, Any]) -> int:
    count = data.get("count")
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    return 1 if "item" in data else 0
