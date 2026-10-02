"""Shared Microsoft Teams gateway transport.

This module owns only the mechanical gateway/token/HTTP behavior. Canonical
capabilities and approval workflows keep their own validation, authority,
recipient, evidence, and execution-plan semantics above this boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from kernel.execution_deadline import bounded_execution_timeout


@dataclass(frozen=True, slots=True)
class TeamsGatewayPreparedRequest:
    gateway_url: str
    payload: dict[str, Any]
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class TeamsGatewayTransport:
    gateway_url: str
    token_file: str | Path
    timeout_seconds: float = 20.0

    def prepare(self, payload: Mapping[str, Any]) -> TeamsGatewayPreparedRequest:
        gateway_url = str(self.gateway_url).rstrip("/")
        if not gateway_url:
            raise ValueError("Teams gateway URL is required")
        token = Path(self.token_file).read_text(encoding="utf-8").strip()
        if not token:
            raise PermissionError("Teams proactive token unavailable")
        body = dict(payload)
        if not body:
            raise ValueError("Teams gateway payload is required")
        return TeamsGatewayPreparedRequest(
            gateway_url=gateway_url,
            payload=body,
            token=token,
        )

    def send(
        self,
        prepared: TeamsGatewayPreparedRequest,
        *,
        path: str = "/internal/proactive/send",
    ) -> Mapping[str, Any]:
        expected_gateway = str(self.gateway_url).rstrip("/")
        if prepared.gateway_url != expected_gateway:
            raise PermissionError("prepared Teams gateway endpoint changed")
        normalized_path = "/" + str(path).lstrip("/")
        body = json.dumps(
            prepared.payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            prepared.gateway_url + normalized_path,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + prepared.token,
                "Content-Type": "application/json",
            },
        )
        with urlopen(
            request,
            timeout=bounded_execution_timeout(self.timeout_seconds),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, Mapping):
            raise RuntimeError("Teams gateway returned an invalid response")
        return result
