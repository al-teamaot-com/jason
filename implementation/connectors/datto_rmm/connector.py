from __future__ import annotations

from typing import Any, Mapping, Sequence

from connectors.core.connector_base import ConnectorBase, PreparedRequest
from connectors.core.contracts import ConnectorRequest, ConnectorResult, require_capability
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials


class DattoRmmConnector(ConnectorBase):
    provider_name = "datto_rmm"
    logical_secret = "datto_rmm.readonly"
    default_device_search_max = 25

    capabilities = frozenset(
        {
            "datto_rmm.device.get",
            "datto_rmm.device.search",
            "datto_rmm.device.resolve",
            "datto_rmm.alerts.list",
            "datto_rmm.patch_status.get",
            "datto_rmm.component_results.list",
        }
    )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve(self.logical_secret, request.context)
        require_durable_credentials(credentials)
        token = acquire_access_token(credentials=credentials)
        try:
            should_resolve_device = (
                request.context.capability == "datto_rmm.device.resolve"
                or (
                    request.context.capability == "datto_rmm.device.search"
                    and self._requested_facts_present(request.arguments)
                )
            )
            if should_resolve_device:
                data = self._execute_device_resolve(
                    request=request,
                    credentials=credentials,
                    access_token=token.access_token,
                    token_type=token.token_type,
                )
            else:
                prepared = self._prepare_api_request(
                    request=request,
                    credentials=credentials,
                    access_token=token.access_token,
                    token_type=token.token_type,
                )
                payload = self._execute_prepared_request(
                    request=request,
                    prepared=prepared,
                )
                data = self._normalize_result(request.context.capability, payload)
        finally:
            token = None

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _requested_facts_present(arguments: Mapping[str, Any]) -> bool:
        requested = arguments.get("requested_facts")
        return isinstance(requested, (list, tuple)) and any(
            str(item).strip() for item in requested
        )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        require_durable_credentials(credentials)
        raise RuntimeError(
            "Datto RMM API requests require runtime token acquisition; use execute()."
        )

    def _prepare_api_request(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> PreparedRequest:
        return self._prepare_provider_request(
            capability=request.context.capability,
            arguments=request.arguments,
            credentials=credentials,
            access_token=access_token,
            token_type=token_type,
        )

    @classmethod
    def _prepare_provider_request(
        cls,
        *,
        capability: str,
        arguments: Mapping[str, Any],
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> PreparedRequest:
        path, params = cls._resolve_operation(capability, arguments)
        return PreparedRequest(
            method="GET",
            url=f"{credentials['api_url'].rstrip('/')}{path}",
            headers={
                "Authorization": f"{token_type} {access_token}",
                "Accept": "application/json",
            },
            params=params,
            audit_operation=path,
        )

    def _execute_prepared_request(
        self,
        *,
        request: ConnectorRequest,
        prepared: PreparedRequest,
    ) -> Any:
        operation = prepared.audit_operation or prepared.url
        self._audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        payload = self._transport.request(
            method=prepared.method,
            url=prepared.url,
            headers=prepared.headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
        )
        self._audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        return payload

    def _execute_device_resolve(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> Any:
        """Resolve a human selector without promoting it to identity.

        A fact-bearing endpoint search is a provider-neutral request for information,
        not permission to treat a hostname as identity. Datto first performs bounded
        discovery. Zero or multiple matches are returned as discovery evidence only.
        Exactly one match may proceed to an exact GET, and only after Datto supplied a
        durable device UID. Pure discovery calls without requested_facts remain search
        operations and do not trigger the exact read.
        """

        search_request = self._prepare_provider_request(
            capability="datto_rmm.device.search",
            arguments=request.arguments,
            credentials=credentials,
            access_token=access_token,
            token_type=token_type,
        )
        search_payload = self._execute_prepared_request(
            request=request,
            prepared=search_request,
        )
        discovery = self._normalize_result("datto_rmm.device.search", search_payload)
        matches = discovery["resource_matches"]

        if len(matches) != 1:
            return discovery

        resource_id = str(matches[0].get("resource_id", "")).strip()
        if not resource_id:
            # Preserve the unique candidate as evidence, but do not issue a second
            # provider request without a durable provider identity. The response layer
            # will fail closed if exact resource facts were requested.
            return discovery

        read_request = self._prepare_provider_request(
            capability="datto_rmm.device.get",
            arguments={"resource_id": resource_id},
            credentials=credentials,
            access_token=access_token,
            token_type=token_type,
        )
        read_payload = self._execute_prepared_request(
            request=request,
            prepared=read_request,
        )
        return {
            "resource_matches": matches,
            "resolved_resource_id": resource_id,
            # Requested facts must be located in the exact device read, never in a
            # summary record returned by the discovery request.
            "provider_data": read_payload,
        }

    @classmethod
    def _normalize_result(cls, capability: str, payload: Any) -> Any:
        """Preserve provider evidence while exposing canonical discovery candidates.

        Human-friendly endpoint names and hostnames are discovery selectors, not durable
        identities. Search responses therefore carry a provider-neutral resource_matches
        collection so orchestration can deterministically detect zero, one, or multiple
        candidates before any evidence reasoner is allowed to interpret device facts.
        """

        if capability != "datto_rmm.device.search":
            return payload
        records = cls._device_records(payload)
        return {
            "resource_matches": [cls._canonical_device_match(record) for record in records],
            "provider_data": payload,
        }

    @staticmethod
    def _device_records(payload: Any) -> Sequence[Mapping[str, Any]]:
        if isinstance(payload, (list, tuple)):
            records = payload
        elif isinstance(payload, Mapping):
            records = payload.get("devices")
        else:
            records = None
        if not isinstance(records, (list, tuple)):
            raise ValueError("Datto device search response does not expose a devices collection")
        if not all(isinstance(item, Mapping) for item in records):
            raise ValueError("Datto device search returned a non-object device record")
        return tuple(records)

    @classmethod
    def _canonical_device_match(cls, record: Mapping[str, Any]) -> Mapping[str, str]:
        match: dict[str, str] = {}
        resource_id = cls._first_scalar(record, "uid", "deviceUid", "device_uid")
        hostname = cls._first_scalar(record, "hostname", "name")
        site = cls._first_scalar(record, "siteName", "site_name")
        site_uid = cls._first_scalar(record, "siteUid", "site_uid")
        if resource_id:
            match["resource_id"] = resource_id
        if hostname:
            match["hostname"] = hostname
        if site:
            match["site"] = site
        if site_uid:
            match["site_id"] = site_uid
        return match

    @staticmethod
    def _first_scalar(record: Mapping[str, Any], *keys: str) -> str:
        for key in keys:
            value = record.get(key)
            if isinstance(value, (str, int, float)) and str(value).strip():
                return str(value).strip()
        return ""

    @classmethod
    def _resolve_operation(
        cls,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any] | None]:
        if capability == "datto_rmm.device.get":
            device_uid = str(
                arguments.get("device_uid") or arguments.get("resource_id") or ""
            ).strip()
            if not device_uid:
                raise ValueError("device_uid or resource_id is required")
            return f"/api/v2/device/{device_uid}", None
        if capability == "datto_rmm.device.search":
            requested_max = int(arguments.get("max", cls.default_device_search_max))
            params: dict[str, Any] = {
                "page": max(int(arguments.get("page", 1)), 1),
                # Discovery must be able to observe ambiguity. Never let a caller
                # collapse a name/hostname search to a single provider result.
                "max": max(2, min(requested_max, 250)),
            }
            # Canonical resource inquiries use provider-neutral selectors. Datto's
            # account-device endpoint exposes hostname and siteName query filters,
            # so those selectors are translated here rather than introducing a
            # workflow-specific lookup script. Both are discovery filters only;
            # neither becomes durable resource identity.
            hostname = str(
                arguments.get("hostname")
                or arguments.get("name")
                or ""
            ).strip()
            site = str(arguments.get("site") or "").strip()
            if hostname:
                params["hostname"] = hostname
            if site:
                params["siteName"] = site
            return "/api/v2/account/devices", params
        if capability == "datto_rmm.alerts.list":
            return "/api/v2/account/alerts/open", {
                "siteUid": arguments.get("site_uid")
            }
        if capability == "datto_rmm.patch_status.get":
            return f"/api/v2/device/{arguments['device_uid']}/audit", None
        if capability == "datto_rmm.component_results.list":
            return f"/api/v2/device/{arguments['device_uid']}/jobs", None
        raise ValueError(f"Unsupported capability: {capability}")
