"""Compile and execute bounded Microsoft Graph reads from discovered metadata.

Conversation input never supplies a Graph URL or raw OData expression.  A caller
selects a resource handle that was created from provider-published metadata plus
structured fields/operators.  This module validates those choices against the
catalog and only then builds a governed Microsoft read request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import ConnectorTransportError, HttpTransport

from .platform import GovernedMicrosoftRequest, MicrosoftCloudRequest, build_governed_request
from .resource_metadata import (
    MicrosoftGraphMetadataError,
    MicrosoftGraphResource,
    MicrosoftGraphResourceCatalog,
)
from .service_catalog import MicrosoftOperationMode, MicrosoftService


_ALLOWED_FILTER_OPERATORS = frozenset(
    {"eq", "ne", "gt", "ge", "lt", "le", "startswith", "contains"}
)
_MAX_SELECT_FIELDS = 64
_MAX_FILTERS = 16
_MAX_ORDER_FIELDS = 8
_MAX_TOP = 999


class MicrosoftGraphResourceReadError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MicrosoftGraphFilter:
    field: str
    operator: str
    value: Any

    def __post_init__(self) -> None:
        if not str(self.field).strip():
            raise MicrosoftGraphResourceReadError("Graph filter field is required")
        operator = str(self.operator).strip().casefold()
        if operator not in _ALLOWED_FILTER_OPERATORS:
            raise MicrosoftGraphResourceReadError(
                f"unsupported structured Graph filter operator: {self.operator!r}"
            )
        object.__setattr__(self, "operator", operator)


@dataclass(frozen=True, slots=True)
class MicrosoftGraphOrder:
    field: str
    direction: str = "asc"

    def __post_init__(self) -> None:
        field_name = str(self.field).strip()
        direction = str(self.direction).strip().casefold()
        if not field_name:
            raise MicrosoftGraphResourceReadError("Graph order field is required")
        if direction not in {"asc", "desc"}:
            raise MicrosoftGraphResourceReadError(
                "Graph order direction must be 'asc' or 'desc'"
            )
        object.__setattr__(self, "field", field_name)
        object.__setattr__(self, "direction", direction)


@dataclass(frozen=True, slots=True)
class MicrosoftGraphReadIntent:
    resource_handle: str
    select: tuple[str, ...]
    resource_id: str | None = None
    filters: tuple[MicrosoftGraphFilter, ...] = ()
    order_by: tuple[MicrosoftGraphOrder, ...] = ()
    top: int = 50

    def __post_init__(self) -> None:
        if not str(self.resource_handle).strip():
            raise MicrosoftGraphResourceReadError("Graph resource handle is required")
        if not self.select:
            raise MicrosoftGraphResourceReadError(
                "Graph reads require an explicit bounded field projection"
            )
        if len(self.select) > _MAX_SELECT_FIELDS:
            raise MicrosoftGraphResourceReadError("Graph projection exceeds field bound")
        if len(self.filters) > _MAX_FILTERS:
            raise MicrosoftGraphResourceReadError("Graph filter count exceeds bound")
        if len(self.order_by) > _MAX_ORDER_FIELDS:
            raise MicrosoftGraphResourceReadError("Graph order count exceeds bound")
        if isinstance(self.top, bool) or not 1 <= int(self.top) <= _MAX_TOP:
            raise MicrosoftGraphResourceReadError(
                f"Graph top must be an integer between 1 and {_MAX_TOP}"
            )
        if self.resource_id is not None:
            resource_id = str(self.resource_id).strip()
            if not resource_id:
                raise MicrosoftGraphResourceReadError("Graph resource id cannot be empty")
            if len(resource_id) > 1024 or any(ord(char) < 32 for char in resource_id):
                raise MicrosoftGraphResourceReadError("Graph resource id is unsafe")
            if self.filters:
                raise MicrosoftGraphResourceReadError(
                    "exact Graph resource reads cannot also carry collection filters"
                )
            object.__setattr__(self, "resource_id", resource_id)


@dataclass(frozen=True, slots=True)
class CompiledMicrosoftGraphRead:
    resource: MicrosoftGraphResource
    request: GovernedMicrosoftRequest
    selected_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MicrosoftGraphReadCompiler:
    catalog: MicrosoftGraphResourceCatalog
    service: MicrosoftService = MicrosoftService.GRAPH

    def compile(
        self,
        *,
        intent: MicrosoftGraphReadIntent,
        permission_profile_name: str,
    ) -> CompiledMicrosoftGraphRead:
        resource = self.catalog.get(intent.resource_handle)
        known_fields = set(resource.field_names)

        selected = _unique_fields(intent.select)
        _require_known_fields(
            selected,
            known_fields=known_fields,
            purpose="projection",
        )

        for filter_item in intent.filters:
            _require_known_fields(
                (filter_item.field,),
                known_fields=known_fields,
                purpose="filter",
            )
        for order in intent.order_by:
            _require_known_fields(
                (order.field,),
                known_fields=known_fields,
                purpose="order",
            )

        path = resource.collection_path
        if intent.resource_id is not None:
            path = f"{path}/{quote(intent.resource_id, safe='')}"

        query: dict[str, str] = {"$select": ",".join(selected)}
        if intent.resource_id is None:
            query["$top"] = str(int(intent.top))
            if intent.filters:
                query["$filter"] = " and ".join(
                    _compile_filter(item) for item in intent.filters
                )
            if intent.order_by:
                query["$orderby"] = ",".join(
                    f"{item.field} {item.direction}" for item in intent.order_by
                )

        governed = build_governed_request(
            MicrosoftCloudRequest(
                service=self.service,
                method="GET",
                path=path,
                permission_profile_name=permission_profile_name,
                mode=MicrosoftOperationMode.READ,
                query=query,
            )
        )
        return CompiledMicrosoftGraphRead(
            resource=resource,
            request=governed,
            selected_fields=selected,
        )


class TenantApplicationTokenProvider(Protocol):
    def access_token_for_tenant(
        self,
        *,
        microsoft_tenant_id: str,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphResourceReader:
    """Execute one compiled metadata-backed Graph read with bounded throttling retry."""

    compiler: MicrosoftGraphReadCompiler
    tokens: TenantApplicationTokenProvider
    transport: HttpTransport
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    max_retry_delay_seconds: float = 5.0
    sleeper: Callable[[float], None] = field(default=sleep, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise MicrosoftGraphResourceReadError(
                "Graph timeout must be greater than 0 and at most 60 seconds"
            )
        if not 1 <= self.max_attempts <= 5:
            raise MicrosoftGraphResourceReadError(
                "Graph retry attempts must be between 1 and 5"
            )
        if not 0 <= self.max_retry_delay_seconds <= 30:
            raise MicrosoftGraphResourceReadError(
                "Graph retry delay must be between 0 and 30 seconds"
            )

    def read(
        self,
        *,
        microsoft_tenant_id: str,
        intent: MicrosoftGraphReadIntent,
        permission_profile_name: str,
    ) -> Mapping[str, Any]:
        tenant_id = str(microsoft_tenant_id).strip()
        if not tenant_id:
            raise MicrosoftGraphResourceReadError("Microsoft tenant id is required")

        compiled = self.compiler.compile(
            intent=intent,
            permission_profile_name=permission_profile_name,
        )
        token = self.tokens.access_token_for_tenant(
            microsoft_tenant_id=tenant_id,
        )
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft Graph application token is unavailable")
        clean_token = token.strip()
        if any(char.isspace() for char in clean_token):
            raise PermissionError("Microsoft Graph application token is malformed")

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.transport.request(
                    method=compiled.request.method,
                    url=_request_url_without_query(compiled.request.url),
                    headers={
                        "Authorization": f"Bearer {clean_token}",
                        "Accept": "application/json",
                    },
                    params=_request_query(compiled.request.url),
                    timeout_seconds=self.timeout_seconds,
                )
                if not isinstance(response, Mapping):
                    raise MicrosoftGraphResourceReadError(
                        "Microsoft Graph response must be an object"
                    )
                return response
            except ConnectorTransportError as error:
                if error.status_code != 429 or attempt >= self.max_attempts:
                    raise
                delay = error.retry_after_seconds
                if delay is None:
                    delay = float(2 ** (attempt - 1))
                delay = min(max(float(delay), 0.0), self.max_retry_delay_seconds)
                if delay:
                    self.sleeper(delay)

        raise RuntimeError("unreachable Microsoft Graph retry state")


def _unique_fields(fields: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(str(field).strip() for field in fields)
    if any(not field for field in cleaned):
        raise MicrosoftGraphResourceReadError("Graph field names must be non-empty")
    return tuple(dict.fromkeys(cleaned))


def _require_known_fields(
    fields: tuple[str, ...],
    *,
    known_fields: set[str],
    purpose: str,
) -> None:
    unknown = tuple(field for field in fields if field not in known_fields)
    if unknown:
        raise MicrosoftGraphResourceReadError(
            f"Graph {purpose} references fields outside discovered metadata: {unknown!r}"
        )


def _compile_filter(item: MicrosoftGraphFilter) -> str:
    literal = _odata_literal(item.value)
    if item.operator in {"startswith", "contains"}:
        if not isinstance(item.value, str):
            raise MicrosoftGraphResourceReadError(
                f"Graph {item.operator} filter requires a string value"
            )
        return f"{item.operator}({item.field},{literal})"
    return f"{item.field} {item.operator} {literal}"


def _odata_literal(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if len(text) > 1024 or any(ord(char) < 32 for char in text):
        raise MicrosoftGraphResourceReadError("Graph filter literal is unsafe")
    return "'" + text.replace("'", "''") + "'"


def _request_url_without_query(url: str) -> str:
    return url.split("?", 1)[0]


def _request_query(url: str) -> Mapping[str, str] | None:
    if "?" not in url:
        return None
    from urllib.parse import parse_qsl

    return dict(parse_qsl(url.split("?", 1)[1], keep_blank_values=True))
