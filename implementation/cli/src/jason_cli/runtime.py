from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from connectors.autotask.connector import AutotaskConnector
from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver


DEFAULT_OPENBAO_URL = "http://127.0.0.1:8200"
DEFAULT_AUTOTASK_CREDENTIAL_DIR = Path(
    "/opt/jason/bootstrap/secrets/openbao/"
    "autotask-read-approle"
)


class UrllibHttpTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        if params:
            query_string = urllib.parse.urlencode(params)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query_string}"

        body = None
        request_headers = dict(headers)

        if json is not None:
            body = __import__("json").dumps(json).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url=url,
            data=body,
            headers=request_headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                response_body = response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(
                f"Provider request failed with HTTP {error.code}."
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise RuntimeError(
                "Provider request failed."
            ) from error

        try:
            parsed = __import__("json").loads(
                response_body.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError(
                "Provider returned an invalid JSON response."
            ) from error

        if not isinstance(parsed, Mapping):
            raise RuntimeError(
                "Provider returned an invalid response."
            )

        return parsed


class ConsoleAuditSink:
    def record(
        self,
        event_type: str,
        context: ConnectorContext,
        details: Mapping[str, Any],
    ) -> None:
        # The CLI intentionally emits no credential-bearing details.
        # Persistent audit storage will replace this console-safe sink.
        return None


def build_autotask_connector() -> AutotaskConnector:
    credential_dir = DEFAULT_AUTOTASK_CREDENTIAL_DIR

    resolver = OpenBaoSecretResolver(
        base_url=DEFAULT_OPENBAO_URL,
        role_id_path=credential_dir / "role-id",
        secret_id_path=credential_dir / "secret-id",
    )

    return AutotaskConnector(
        secrets=resolver,
        transport=UrllibHttpTransport(),
        audit=ConsoleAuditSink(),
    )
