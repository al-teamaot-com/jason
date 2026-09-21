from __future__ import annotations

import json
from string import Formatter
from typing import Any, Mapping
from urllib.parse import urlparse

from connectors.core.connector_base import ConnectorBase, PreparedRequest
from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorRequest,
)

KFS_PUBLIC_API_HOST = "api.kyods.com"
KFS_DEFAULT_API_URL = f"https://{KFS_PUBLIC_API_HOST}"

_REQUIRED_CREDENTIAL_KEYS = (
    "access_id",
    "access_password",
    "request_from",
    "request_to",
    "authorization",
    "kfs_username",
    "kfs_password",
    "headers_json",
    "operations_json",
)

_CAPABILITY_OPERATIONS = {
    "kyocera_kfs.device.search": "device_search",
    "kyocera_kfs.device.get": "device_get",
    "kyocera_kfs.meters.get": "meters_get",
    "kyocera_kfs.supplies.get": "supplies_get",
    "kyocera_kfs.alerts.list": "alerts_list",
}

_ALLOWED_METHODS = frozenset({"GET", "POST"})


def require_kfs_credentials(credentials: Mapping[str, str]) -> None:
    """Validate the durable Kyocera KFS credential/configuration contract.

    Kyocera issues the durable API credential fields. Exact endpoint paths and
    header names are intentionally configuration-driven because the public KFS
    product material confirms an API but does not publish the private dealer API
    contract. Jason therefore fails closed until AOT receives the official KFS
    integration package.
    """

    missing = [key for key in _REQUIRED_CREDENTIAL_KEYS if not credentials.get(key)]
    if missing:
        raise ConnectorConfigurationError(
            "Kyocera KFS credential contract is incomplete: " + ", ".join(missing)
        )

    api_url = credentials.get("api_url", KFS_DEFAULT_API_URL).strip()
    parsed = urlparse(api_url)
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != KFS_PUBLIC_API_HOST
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ConnectorConfigurationError(
            "Kyocera KFS api_url must be the approved HTTPS api.kyods.com endpoint."
        )

    headers = _parse_json_object(credentials["headers_json"], "headers_json")
    operations = _parse_json_object(credentials["operations_json"], "operations_json")
    if not headers:
        raise ConnectorConfigurationError("Kyocera KFS headers_json may not be empty.")
    if not operations:
        raise ConnectorConfigurationError("Kyocera KFS operations_json may not be empty.")


def _parse_json_object(raw: str, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConnectorConfigurationError(
            f"Kyocera KFS {field_name} must contain valid JSON."
        ) from exc
    if not isinstance(value, dict):
        raise ConnectorConfigurationError(
            f"Kyocera KFS {field_name} must contain a JSON object."
        )
    return value


def _template_fields(value: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(value):
        if field_name:
            fields.add(field_name)
    return fields


def _render_string(template: str, values: Mapping[str, Any]) -> str:
    missing = sorted(name for name in _template_fields(template) if name not in values)
    if missing:
        raise ConnectorConfigurationError(
            "Kyocera KFS request template requires missing value(s): "
            + ", ".join(missing)
        )
    try:
        return template.format_map({key: str(value) for key, value in values.items()})
    except (KeyError, ValueError) as exc:
        raise ConnectorConfigurationError(
            "Kyocera KFS request template could not be rendered."
        ) from exc


def _render_value(value: Any, values: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_string(value, values)
    if isinstance(value, dict):
        return {str(key): _render_value(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_value(item, values) for item in value]
    return value


class KyoceraKfsConnector(ConnectorBase):
    provider_name = "kyocera_kfs"
    logical_secret = "kyocera_kfs.readonly"

    capabilities = frozenset(_CAPABILITY_OPERATIONS)

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        require_kfs_credentials(credentials)

        operation_name = _CAPABILITY_OPERATIONS.get(request.context.capability)
        if operation_name is None:
            raise ConnectorConfigurationError(
                f"Unsupported Kyocera KFS capability: {request.context.capability}"
            )

        operations = _parse_json_object(credentials["operations_json"], "operations_json")
        raw_operation = operations.get(operation_name)
        if not isinstance(raw_operation, dict):
            raise ConnectorConfigurationError(
                f"Kyocera KFS operation is not configured: {operation_name}"
            )

        method = str(raw_operation.get("method", "GET")).upper().strip()
        if method not in _ALLOWED_METHODS:
            raise ConnectorConfigurationError(
                "Kyocera KFS read-only connector allows only GET or POST operations."
            )

        path_template = raw_operation.get("path")
        if not isinstance(path_template, str) or not path_template.strip():
            raise ConnectorConfigurationError(
                f"Kyocera KFS operation {operation_name} requires a path."
            )

        values: dict[str, Any] = dict(credentials)
        values.update(request.arguments)
        path = _render_string(path_template, values).strip()
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "://" in path
            or ".." in path.split("/")
        ):
            raise ConnectorConfigurationError(
                "Kyocera KFS operation path must be an absolute provider-local path."
            )

        header_templates = _parse_json_object(credentials["headers_json"], "headers_json")
        headers = {
            str(key): str(_render_value(value, values))
            for key, value in header_templates.items()
        }
        headers.setdefault("Accept", "application/json")

        params = raw_operation.get("params")
        if params is not None and not isinstance(params, dict):
            raise ConnectorConfigurationError(
                f"Kyocera KFS operation {operation_name} params must be an object."
            )

        body = raw_operation.get("json")
        if body is not None and not isinstance(body, dict):
            raise ConnectorConfigurationError(
                f"Kyocera KFS operation {operation_name} json must be an object."
            )

        rendered_params = (
            {
                str(key): _render_value(value, values)
                for key, value in params.items()
            }
            if isinstance(params, dict)
            else None
        )
        rendered_body = (
            {
                str(key): _render_value(value, values)
                for key, value in body.items()
            }
            if isinstance(body, dict)
            else None
        )

        base_url = credentials.get("api_url", KFS_DEFAULT_API_URL).rstrip("/")
        return PreparedRequest(
            method=method,
            url=f"{base_url}{path}",
            headers=headers,
            params=rendered_params,
            json=rendered_body,
            timeout_seconds=float(raw_operation.get("timeout_seconds", 30.0)),
            audit_operation=operation_name,
        )


# Runtime-compatible alias: the documented KFS API requires a login cookie.
from connectors.kyocera_kfs.session_connector import KyoceraKfsSessionConnector
KyoceraKfsConnector = KyoceraKfsSessionConnector
