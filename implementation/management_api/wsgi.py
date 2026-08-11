from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from urllib.parse import parse_qs

from management_api.service import (
    ManagementApiService,
    ManagementReadContext,
    ManagementReadDenied,
)

StartResponse = Callable[[str, list[tuple[str, str]]], None]


class ManagementWsgiApp:
    """Small dependency-free HTTP boundary for the read-only Management API.

    Identity headers are accepted only as resolved upstream context. Production
    deployment must place this app behind the approved Jason authentication and
    identity propagation boundary; Grafana must never invent these values.
    """

    def __init__(self, service: ManagementApiService) -> None:
        self._service = service

    def __call__(
        self,
        environ: dict[str, object],
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        try:
            if str(environ.get("REQUEST_METHOD", "GET")) != "GET":
                return self._json(start_response, "405 Method Not Allowed", {"error": "read_only_api"})

            context = self._context(environ)
            path = str(environ.get("PATH_INFO", ""))
            query = parse_qs(str(environ.get("QUERY_STRING", "")))

            if path == "/api/management/v0.1/overview":
                payload = self._service.overview(context)
            elif path == "/api/management/v0.1/system/health":
                payload = self._service.system_health(context)
            elif path == "/api/management/v0.1/capabilities":
                payload = self._service.list_capabilities(context)
            elif path == "/api/management/v0.1/providers":
                payload = self._service.list_providers(context)
            elif path == "/api/management/v0.1/audit/events":
                payload = self._service.search_audit_events(
                    context,
                    execution_id=self._first(query, "execution_id"),
                    correlation_id=self._first(query, "correlation_id"),
                )
            else:
                return self._json(start_response, "404 Not Found", {"error": "not_found"})

            return self._json(start_response, "200 OK", payload)
        except (KeyError, ValueError):
            return self._json(start_response, "401 Unauthorized", {"error": "identity_context_required"})
        except ManagementReadDenied:
            return self._json(start_response, "403 Forbidden", {"error": "management_read_denied"})

    @staticmethod
    def _context(environ: dict[str, object]) -> ManagementReadContext:
        principal = str(environ["HTTP_X_JASON_PRINCIPAL_ID"])
        organization = str(environ["HTTP_X_JASON_ORGANIZATION_ID"])
        return ManagementReadContext(
            principal_id=principal,
            organization_id=organization,
        )

    @staticmethod
    def _first(query: dict[str, list[str]], key: str) -> str | None:
        values = query.get(key)
        return values[0] if values else None

    @staticmethod
    def _json(
        start_response: StartResponse,
        status: str,
        payload: object,
    ) -> Iterable[bytes]:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        start_response(
            status,
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]
