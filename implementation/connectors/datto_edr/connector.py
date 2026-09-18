from __future__ import annotations

import json
from typing import Any, Mapping

from connectors.core.connector_base import ConnectorBase, PreparedRequest
from connectors.core.contracts import (
    ConnectorRequest,
    ConnectorResult,
    require_capability,
)


class DattoEdrConnector(ConnectorBase):
    """Read-only Datto EDR/AV connector.

    The Datto tenant uses LoopBack-style API tokens carried as the
    access_token query parameter. Tokens are resolved at runtime from OpenBao
    and are never emitted in audit details or normalized provider evidence.
    """

    provider_name = "datto_edr"
    logical_secret = "datto_edr.readonly"
    capabilities = frozenset(
        {
            "datto_edr.endpoint.status.read",
            "datto_edr.alert.search",
            "datto_edr.alert.read",
            "datto_edr.policy.search",
            "datto_edr.scan_history.search",
            "datto_edr.quarantine.search",
        }
    )
    max_collection_limit = 200

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve(self.logical_secret, request.context)
        self._require_credentials(credentials)

        if request.context.capability == "datto_edr.alert.read":
            data = self._execute_alert_read(request, credentials)
        else:
            prepared = self.prepare_request(request, credentials)
            payload = self._execute_prepared(request, prepared)
            data = self._normalize_result(
                request.context.capability,
                payload,
                request.arguments,
            )

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        self._require_credentials(credentials)
        path, params = self._resolve_operation(
            request.context.capability,
            request.arguments,
        )
        params = dict(params)
        params["access_token"] = credentials["api_token"]
        return PreparedRequest(
            method="GET",
            url=f"{credentials['api_url'].rstrip('/')}{path}",
            headers={"Accept": "application/json"},
            params=params,
            audit_operation=path,
        )

    def _execute_prepared(
        self,
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

    def _execute_alert_read(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> Mapping[str, Any]:
        alert_id = self._required_text(request.arguments, "alert_id")
        detail = self._execute_prepared(
            request,
            self._prepared(
                credentials,
                f"/AlertDetails/{alert_id}",
                {},
            ),
        )
        quarantine = self._execute_prepared(
            request,
            self._prepared(
                credentials,
                "/QuarantinedFiles",
                {
                    "filter": self._filter(
                        where={"alertId": alert_id},
                        order="createdOn DESC",
                        limit=20,
                    )
                },
            ),
        )
        if not isinstance(detail, Mapping):
            raise ValueError("Datto EDR alert detail response must be an object")
        if not isinstance(quarantine, list):
            raise ValueError("Datto EDR quarantine response must be a collection")
        return self._normalize_alert_detail(detail, quarantine)

    @classmethod
    def _resolve_operation(
        cls,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any]]:
        if capability == "datto_edr.endpoint.status.read":
            device_uid = str(
                arguments.get("device_uid")
                or arguments.get("resource_id")
                or ""
            ).strip()
            if not device_uid:
                raise ValueError(
                    "datto_edr.endpoint.status.read requires device_uid or resource_id"
                )
            return (
                "/AgentDetails",
                {
                    "filter": cls._filter(
                        where={"deviceId": device_uid},
                        limit=2,
                    )
                },
            )

        if capability == "datto_edr.alert.search":
            agent_id = cls._required_text(arguments, "agent_id")
            limit = cls._bounded_limit(arguments.get("limit"), default=50)
            where: dict[str, Any] = {"agentId": agent_id}
            if "archived" in arguments and arguments.get("archived") is not None:
                where["archived"] = bool(arguments["archived"])
            return (
                "/Alerts",
                {
                    "filter": cls._filter(
                        where=where,
                        order="createdOn DESC",
                        limit=limit,
                    )
                },
            )

        if capability == "datto_edr.policy.search":
            agent_id = cls._required_text(arguments, "agent_id")
            return f"/Agents/{agent_id}/getAgentPolicies", {}

        if capability == "datto_edr.scan_history.search":
            agent_id = cls._required_text(arguments, "agent_id")
            limit = cls._bounded_limit(arguments.get("limit"), default=50)
            return (
                "/ScanHistoryTrackings",
                {
                    "filter": cls._filter(
                        where={"agentId": agent_id},
                        order="createdOn DESC",
                        limit=limit,
                    )
                },
            )
        if capability == "datto_edr.quarantine.search":
            limit = cls._bounded_limit(arguments.get("limit"), default=50)
            where: dict[str, Any] = {}
            if str(arguments.get("agent_id") or "").strip():
                where["agentId"] = str(arguments["agent_id"]).strip()
            if str(arguments.get("alert_id") or "").strip():
                where["alertId"] = str(arguments["alert_id"]).strip()
            if not where:
                raise ValueError(
                    "datto_edr.quarantine.search requires agent_id or alert_id"
                )
            return (
                "/QuarantinedFiles",
                {
                    "filter": cls._filter(
                        where=where,
                        order="createdOn DESC",
                        limit=limit,
                    )
                },
            )

        if capability == "datto_edr.alert.read":
            alert_id = cls._required_text(arguments, "alert_id")
            return f"/AlertDetails/{alert_id}", {}

        raise ValueError(f"Unsupported Datto EDR capability: {capability}")
    @classmethod
    def _normalize_result(
        cls,
        capability: str,
        payload: Any,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if capability == "datto_edr.endpoint.status.read":
            if not isinstance(payload, list):
                raise ValueError("Datto EDR AgentDetails response must be a collection")
            matches = [cls._normalize_agent_detail(item) for item in payload if isinstance(item, Mapping)]
            return {
                "resource_matches": matches,
                "match_count": len(matches),
                "identity_basis": "datto_rmm_device_uid_to_datto_edr_deviceId",
                "resolved": len(matches) == 1,
            }

        if capability == "datto_edr.alert.search":
            if not isinstance(payload, list):
                raise ValueError("Datto EDR alerts response must be a collection")
            return {
                "alerts": [
                    cls._normalize_alert_summary(item)
                    for item in payload
                    if isinstance(item, Mapping)
                ]
            }

        if capability == "datto_edr.policy.search":
            if not isinstance(payload, list):
                raise ValueError("Datto EDR policy response must be a collection")
            return {
                "policies": [
                    {
                        "id": str(item.get("id") or ""),
                        "name": str(item.get("name") or ""),
                        "type": str(item.get("type") or ""),
                        "active": item.get("active"),
                        "disabled": item.get("disabled"),
                    }
                    for item in payload
                    if isinstance(item, Mapping)
                ]
            }

        if capability == "datto_edr.scan_history.search":
            if not isinstance(payload, list):
                raise ValueError("Datto EDR scan-history response must be a collection")
            return {
                "scans": [
                    {
                        "id": str(item.get("id") or ""),
                        "agent_id": str(item.get("agentId") or ""),
                        "scan_type": str(item.get("scanType") or ""),
                        "status": str(item.get("status") or ""),
                        "created_on": str(item.get("createdOn") or ""),
                        "scan_time": item.get("scanTime"),
                    }
                    for item in payload
                    if isinstance(item, Mapping)
                ]
            }

        if capability == "datto_edr.quarantine.search":
            if not isinstance(payload, list):
                raise ValueError("Datto EDR quarantine response must be a collection")
            return {
                "quarantine": [
                    cls._normalize_quarantine(item)
                    for item in payload
                    if isinstance(item, Mapping)
                ]
            }

        raise ValueError(f"Unsupported Datto EDR normalization: {capability}")

    @classmethod
    def _normalize_agent_detail(cls, item: Mapping[str, Any]) -> Mapping[str, Any]:
        epp = item.get("eppData")
        datto_av = epp.get("dattoav") if isinstance(epp, Mapping) else None
        av_data = datto_av.get("data") if isinstance(datto_av, Mapping) else None
        av_data = av_data if isinstance(av_data, Mapping) else {}
        return {
            "resource_id": str(item.get("deviceId") or ""),
            "agent_id": str(item.get("id") or ""),
            "hostname": str(item.get("hostname") or ""),
            "status": str(item.get("status") or ""),
            "active": item.get("active"),
            "authorized": item.get("authorized"),
            "isolated": item.get("isolated"),
            "sync_status": item.get("syncStatus"),
            "heartbeat": str(item.get("heartbeat") or ""),
            "agent_version": str(item.get("version") or ""),
            "has_edr_license": item.get("hasEdrLicense"),
            "has_av_license": item.get("hasAvLicense"),
            "datto_av_enabled": item.get("dattoAvEnabled"),
            "alert_count": item.get("alertCount"),
            "last_av_scan_time": str(item.get("lastAvScanTime") or ""),
            "last_av_scan_type": str(item.get("lastAvScanType") or ""),
            "scan_status": str(item.get("scanStatus") or ""),
            "organization_id": str(item.get("organizationId") or ""),
            "organization_name": str(item.get("organizationName") or ""),
            "location_id": str(item.get("locationId") or ""),
            "location_name": str(item.get("locationName") or ""),
            "datto_av": {
                "enabled": datto_av.get("enabled") if isinstance(datto_av, Mapping) else None,
                "connected": av_data.get("connected"),
                "engine_ready": av_data.get("engineReady"),
                "engine_version": str(av_data.get("engineVersion") or ""),
                "core_engine_version": str(av_data.get("coreEngineVersion") or ""),
                "vdf_version": str(av_data.get("vdfVersion") or ""),
                "vdf_release_date": str(av_data.get("vdfReleaseDate") or ""),
                "engine_release_date": str(av_data.get("engineReleaseDate") or ""),
                "epp_version": str(av_data.get("eppVersion") or ""),
                "reboot_required": av_data.get("rebootRequired"),
            },
        }

    @classmethod
    def _normalize_alert_summary(cls, item: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "alert_id": str(item.get("id") or ""),
            "agent_id": str(item.get("agentId") or ""),
            "device_id": str(item.get("deviceId") or ""),
            "hostname": str(item.get("hostname") or ""),
            "name": str(item.get("name") or ""),
            "severity": str(item.get("severity") or ""),
            "source_name": str(item.get("sourceName") or ""),
            "source_type": str(item.get("sourceType") or ""),
            "signal": item.get("signal"),
            "archived": item.get("archived"),
            "event_time": str(item.get("eventTime") or ""),
            "created_on": str(item.get("createdOn") or ""),
            "scan_id": str(item.get("scanId") or ""),
            "mitre_id": str(item.get("mitreId") or ""),
            "mitre_tactic": str(item.get("mitreTactic") or ""),
            "response_actions": cls._response_actions(item.get("responseData")),
        }

    @classmethod
    def _normalize_alert_detail(
        cls,
        item: Mapping[str, Any],
        quarantine: list[Any],
    ) -> Mapping[str, Any]:
        q = [
            cls._normalize_quarantine(entry)
            for entry in quarantine
            if isinstance(entry, Mapping)
        ]
        quarantined = any(
            str(entry.get("status") or "").casefold() == "quarantined"
            for entry in q
        )
        restored = any(
            str(entry.get("status") or "").casefold() == "restored"
            for entry in q
        )
        provider_data = item.get("data")
        provider_data = provider_data if isinstance(provider_data, Mapping) else {}
        detected = bool(
            provider_data.get("detected") is True
            or item.get("sourceType")
            or item.get("sourceName")
            or item.get("threatName")
            or item.get("avThreatName")
            or item.get("signal") is True
        )
        provider_compromised = provider_data.get("compromised")
        provider_quarantined = provider_data.get("quarantined")
        provider_remediated = provider_data.get("remediated")
        return {
            "alert_id": str(item.get("id") or ""),
            "agent_id": str(item.get("agentId") or ""),
            "device_id": str(item.get("deviceId") or ""),
            "hostname": str(item.get("hostname") or ""),
            "name": str(item.get("name") or ""),
            "severity": str(item.get("severity") or ""),
            "source_name": str(item.get("sourceName") or ""),
            "source_type": str(item.get("sourceType") or ""),
            "threat_name": str(
                item.get("threatName")
                or item.get("avThreatName")
                or item.get("sourceName")
                or ""
            ),
            "detected": detected,
            "signal": item.get("signal"),
            "malicious": item.get("malicious"),
            "not_malicious": item.get("notMalicious"),
            "suspicious": item.get("suspicious"),
            "provider_compromised": provider_compromised,
            "compromise_signal": (
                "provider_indicated"
                if provider_compromised is True
                else "not_established"
            ),
            "detection_id": str(provider_data.get("detectionId") or ""),
            "detection_name": str(provider_data.get("detectionName") or ""),
            "execution_status": str(provider_data.get("executionStatus") or ""),
            "threat_status": str(provider_data.get("threatStatus") or ""),
            "provider_quarantined": provider_quarantined,
            "provider_remediated": provider_remediated,
            "provider_success": provider_data.get("success"),
            "provider_isolated": provider_data.get("isolated"),
            "engine_version": str(provider_data.get("engineVersion") or ""),
            "vdf_version": str(provider_data.get("vdfVersion") or ""),
            "reboot_needed": provider_data.get("rebootNeeded"),
            "sha256": str(
                provider_data.get("sha256")
                or item.get("sha256")
                or ""
            ),
            "archived": item.get("archived"),
            "event_time": str(
                provider_data.get("eventTime")
                or item.get("eventTime")
                or ""
            ),
            "created_on": str(item.get("createdOn") or ""),
            "response_actions": cls._response_actions(item.get("responseData")),
            "quarantined": bool(quarantined or provider_quarantined is True),
            "restored": restored,
            "quarantine_records": q,
        }

    @staticmethod
    def _normalize_quarantine(item: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "agent_id": str(item.get("agentId") or ""),
            "alert_id": str(item.get("alertId") or ""),
            "detection_id": str(item.get("detectionId") or ""),
            "name": str(item.get("name") or ""),
            "threat": str(item.get("threat") or ""),
            "status": str(item.get("status") or ""),
            "path": str(item.get("path") or ""),
            "created_on": str(item.get("createdOn") or ""),
            "updated_on": str(item.get("updatedOn") or ""),
        }

    @staticmethod
    def _response_actions(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        actions: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                if name:
                    actions.append(name)
        return tuple(actions)

    @classmethod
    def _filter(
        cls,
        *,
        where: Mapping[str, Any],
        limit: int,
        order: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "where": dict(where),
            "limit": limit,
        }
        if order:
            payload["order"] = order
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    @classmethod
    def _prepared(
        cls,
        credentials: Mapping[str, str],
        path: str,
        params: Mapping[str, Any],
    ) -> PreparedRequest:
        query = dict(params)
        query["access_token"] = credentials["api_token"]
        return PreparedRequest(
            method="GET",
            url=f"{credentials['api_url'].rstrip('/')}{path}",
            headers={"Accept": "application/json"},
            params=query,
            audit_operation=path,
        )

    @classmethod
    def _bounded_limit(cls, value: Any, *, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("limit must be an integer")
        if not 1 <= value <= cls.max_collection_limit:
            raise ValueError(
                f"limit must be between 1 and {cls.max_collection_limit}"
            )
        return value
    @staticmethod
    def _required_text(arguments: Mapping[str, Any], name: str) -> str:
        value = str(arguments.get(name) or "").strip()
        if not value:
            raise ValueError(f"{name} is required")
        return value

    @staticmethod
    def _require_credentials(credentials: Mapping[str, str]) -> None:
        api_url = str(credentials.get("api_url") or "").strip()
        token = str(credentials.get("api_token") or "").strip()
        if not api_url or not token:
            raise ValueError("Datto EDR credentials are incomplete")
        if not api_url.startswith("https://"):
            raise ValueError("Datto EDR api_url must use HTTPS")
