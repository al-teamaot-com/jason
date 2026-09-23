from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from connectors.autotask.operations import resolve_operation_request
from connectors.core.connector_base import (
    ConnectorBase,
    PreparedRequest,
)
from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorRequest,
    ConnectorResult,
    ConnectorTransportError,
    require_capability,
)


_MAX_PAGINATION_PAGES = 20


class AutotaskConnector(ConnectorBase):
    provider_name = "autotask"
    logical_secret = "autotask.readonly"

    # Keep the base connector deliberately read-only. Mutation capabilities are
    # exposed only by the stricter requester-impersonating mutation connector.
    capabilities = frozenset(
        {
            "autotask.entity.describe",
            "autotask.entity.fields.describe",
            "autotask.entity.get",
            "autotask.entity.query",
            "autotask.ticket.get",
            "autotask.ticket.search",
            "autotask.ticket.count",
            "autotask.ticket.notes.list",
            "autotask.notification_history.search",
            "autotask.company.get",
            "autotask.company.search",
            "autotask.contact.get",
            "autotask.contact.search",
            "autotask.configuration.get",
            "autotask.configuration.search",
            "autotask.contract.search",
            "autotask.project.search",
        }
    )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        """Execute one bounded read, following Autotask continuation pages safely.

        Canonical Autotask searches carry a bounded ``MaxRecords`` value in the
        structured ``search`` expression. Autotask may satisfy that request across
        multiple provider pages. Follow ``pageDetails.nextPageUrl`` only until that
        caller-requested bound is satisfied or the provider reports no continuation.

        Continuation URLs must remain on the exact discovered Autotask API origin and
        beneath the same API root. Repeated URLs, malformed page bodies, and an
        excessive page chain fail closed rather than returning silently incomplete
        evidence.
        """

        require_capability(request, self.capabilities)

        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )
        prepared = self.prepare_request(request, credentials)
        operation = prepared.audit_operation or prepared.url

        self._audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": operation,
            },
        )

        payload = self._transport.request(
            method=prepared.method,
            url=prepared.url,
            headers=prepared.headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
        )

        page_count = 1
        limit = self._requested_record_limit(prepared)

        if limit is not None:
            payload, page_count = self._complete_bounded_search(
                prepared=prepared,
                first_payload=payload,
                requested_limit=limit,
            )

        self._audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
                "provider_pages_examined": page_count,
            },
        )

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=payload,
        )

    @staticmethod
    def _requested_record_limit(
        prepared: PreparedRequest,
    ) -> int | None:
        if prepared.method.upper() != "GET":
            return None
        if not isinstance(prepared.params, Mapping):
            return None

        raw_search = prepared.params.get("search")
        if not isinstance(raw_search, str) or not raw_search.strip():
            return None

        try:
            search = json.loads(raw_search)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

        if not isinstance(search, Mapping):
            return None

        raw_limit = search.get("MaxRecords")
        if isinstance(raw_limit, bool):
            return None

        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return None

        if limit < 1:
            return None

        # The canonical argument adapter already caps MaxRecords at 500. Keep
        # this connector boundary independently bounded in case it is called
        # through a lower-level provider-specific path.
        return min(limit, 500)

    def _complete_bounded_search(
        self,
        *,
        prepared: PreparedRequest,
        first_payload: Mapping[str, Any],
        requested_limit: int,
    ) -> tuple[Mapping[str, Any], int]:
        first_items = first_payload.get("items")
        first_page_details = first_payload.get("pageDetails")

        if not isinstance(first_items, list):
            return first_payload, 1
        if not isinstance(first_page_details, Mapping):
            return first_payload, 1

        aggregated = list(first_items[:requested_limit])
        page_count = 1
        current_payload: Mapping[str, Any] = first_payload
        seen_continuations: set[str] = set()

        while len(aggregated) < requested_limit:
            details = current_payload.get("pageDetails")
            if not isinstance(details, Mapping):
                break

            next_page_url = details.get("nextPageUrl")
            if not isinstance(next_page_url, str) or not next_page_url.strip():
                break

            if page_count >= _MAX_PAGINATION_PAGES:
                raise ConnectorTransportError(
                    "Autotask pagination exceeded the bounded page limit."
                )

            continuation = self._validated_continuation_url(
                prepared.url,
                next_page_url,
            )
            if continuation in seen_continuations:
                raise ConnectorTransportError(
                    "Autotask pagination repeated a continuation URL."
                )
            seen_continuations.add(continuation)

            current_payload = self._transport.request(
                method="GET",
                url=continuation,
                headers=prepared.headers,
                params=None,
                json=None,
                timeout_seconds=prepared.timeout_seconds,
            )
            page_count += 1

            page_items = current_payload.get("items")
            if not isinstance(page_items, list):
                raise ConnectorTransportError(
                    "Autotask pagination returned an invalid page body."
                )

            remaining = requested_limit - len(aggregated)
            aggregated.extend(page_items[:remaining])

        combined = dict(first_payload)
        combined["items"] = aggregated

        # Preserve provider page metadata from the terminal page, but never
        # manufacture a provider continuation. Add bounded Jason metadata so
        # downstream evidence can distinguish one-page from multi-page reads.
        terminal_details = current_payload.get("pageDetails")
        if isinstance(terminal_details, Mapping):
            combined["pageDetails"] = dict(terminal_details)

        combined["jasonPagination"] = {
            "pagesFetched": page_count,
            "itemCount": len(aggregated),
            "requestedMaxRecords": requested_limit,
            "requestedLimitSatisfied": len(aggregated) >= requested_limit,
        }

        return combined, page_count

    @staticmethod
    def _validated_continuation_url(
        initial_url: str,
        continuation: str,
    ) -> str:
        candidate = urljoin(initial_url, continuation.strip())
        initial = urlparse(initial_url)
        parsed = urlparse(candidate)

        if (
            parsed.scheme.casefold() != initial.scheme.casefold()
            or parsed.netloc.casefold() != initial.netloc.casefold()
        ):
            raise ConnectorTransportError(
                "Autotask pagination continuation left the discovered API origin."
            )

        initial_path = initial.path
        marker = initial_path.casefold().find("/v1.0/")
        if marker < 0:
            raise ConnectorTransportError(
                "Autotask discovered API URL did not contain the expected API root."
            )

        api_root = initial_path[: marker + len("/v1.0/")]
        if not parsed.path.casefold().startswith(api_root.casefold()):
            raise ConnectorTransportError(
                "Autotask pagination continuation left the discovered API root."
            )

        return candidate

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        zone_information = self._transport.request(
            method="GET",
            url=(
                "https://webservices.autotask.net/"
                "atservicesrest/v1.0/zoneInformation"
            ),
            headers={"Accept": "application/json"},
            params={"user": credentials["username"]},
            timeout_seconds=30.0,
        )

        discovered_url = zone_information.get("url")

        if (
            not isinstance(discovered_url, str)
            or not discovered_url.strip()
        ):
            raise ConnectorConfigurationError(
                "Autotask zone discovery returned an invalid API URL."
            )

        method, path, params, body = resolve_operation_request(
            request.context.capability,
            request.arguments,
        )

        return PreparedRequest(
            method=method,
            url=f"{discovered_url.rstrip('/')}{path}",
            headers={
                "ApiIntegrationCode": credentials["integration_code"],
                "UserName": credentials["username"],
                "Secret": credentials["secret"],
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            params=params,
            json=body,
            timeout_seconds=30.0,
            audit_operation=path,
        )
