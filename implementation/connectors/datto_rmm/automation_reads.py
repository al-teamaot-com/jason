from __future__ import annotations

from typing import Any, Mapping, Sequence

from connectors.core.contracts import ConnectorRequest
from connectors.datto_rmm.connector import DattoRmmConnector


class DattoRmmAutomationReadConnector(DattoRmmConnector):
    """Read-only Datto automation evidence used before governed execution.

    This connector deliberately reuses the existing ``datto_rmm.readonly``
    credential and the Datto read transport. It exposes no provider mutation
    method and cannot create a quick job.
    """

    capabilities = frozenset(
        {
            "datto_rmm.component.search",
            "datto_rmm.job.read",
        }
    )
    adaptive_collection_keys = {
        "datto_rmm.component.search": "components",
    }
    default_component_page_size = 250
    maximum_component_page_size = 250

    def execute(self, request: ConnectorRequest):
        if request.context.capability == "datto_rmm.component.search":
            # Canonical component discovery is complete-collection discovery,
            # not arbitrary provider-page navigation. Starting after page one
            # could produce a false zero/unique match, so fail closed.
            requested_page = int(request.arguments.get("page", 1))
            if requested_page != 1:
                raise ValueError("component search must begin at provider page 1")
        return super().execute(request)

    @classmethod
    def _resolve_operation(
        cls,
        capability: str,
        arguments: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any] | None]:
        if capability == "datto_rmm.component.search":
            requested_max = int(
                arguments.get(
                    "max",
                    cls.default_component_page_size,
                )
            )
            return "/api/v2/account/components", {
                "page": max(int(arguments.get("page", 1)), 1),
                "max": max(
                    1,
                    min(
                        requested_max,
                        cls.maximum_component_page_size,
                    ),
                ),
            }

        if capability == "datto_rmm.job.read":
            job_uid = str(
                arguments.get("job_uid")
                or arguments.get("resource_id")
                or ""
            ).strip()
            if not job_uid:
                raise ValueError("job_uid or resource_id is required")
            return f"/api/v2/job/{job_uid}", None

        raise ValueError(f"Unsupported capability: {capability}")

    def _adapt_collection_result(
        self,
        *,
        request: ConnectorRequest,
        initial_data: Any,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> Any:
        if request.context.capability == "datto_rmm.component.search":
            complete_arguments = dict(request.arguments)
            complete_arguments["completeness_requirement"] = "complete"
            complete_request = ConnectorRequest(
                context=request.context,
                arguments=complete_arguments,
            )
            payload = super()._adapt_collection_result(
                request=complete_request,
                initial_data=initial_data,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )
            return self._canonical_component_search_result(
                payload=payload,
                arguments=request.arguments,
            )

        if request.context.capability == "datto_rmm.job.read":
            return self._canonical_job_read_result(
                payload=initial_data,
                arguments=request.arguments,
            )

        return super()._adapt_collection_result(
            request=request,
            initial_data=initial_data,
            credentials=credentials,
            access_token=access_token,
            token_type=token_type,
        )

    @classmethod
    def _canonical_component_search_result(
        cls,
        *,
        payload: Any,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        records = cls._component_records(payload)
        name_reference = str(arguments.get("name") or "").strip()
        matches: list[Mapping[str, Any]] = []

        for record in records:
            uid = cls._first_scalar(record, "uid")
            name = cls._first_scalar(record, "name")

            # A component without durable provider identity cannot safely be
            # proposed for later execution. Do not degrade to display-name
            # identity.
            if not uid or not name:
                raise ValueError(
                    "Datto component record lacks durable uid or display name"
                )

            if (
                name_reference
                and name_reference.casefold() not in name.casefold()
            ):
                continue

            match: dict[str, Any] = {
                "resource_id": uid,
                "name": name,
            }

            description = cls._first_scalar(record, "description")
            category = cls._first_scalar(record, "categoryCode")
            if description:
                match["description"] = description
            if category:
                match["category"] = category

            if isinstance(record.get("credentialsRequired"), bool):
                match["credentials_required"] = record["credentialsRequired"]

            variables = record.get("variables")
            if variables is not None:
                if not isinstance(variables, (list, tuple)) or not all(
                    isinstance(item, Mapping) for item in variables
                ):
                    raise ValueError(
                        "Datto component variables are not a collection of objects"
                    )
                match["variables"] = [
                    cls._canonical_component_variable(item)
                    for item in variables
                ]

            matches.append(match)

        return {
            "resource_matches": matches,
            "match_count": len(matches),
            "discovery_complete": True,
        }

    @classmethod
    def _canonical_component_variable(
        cls,
        variable: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        # Default values are intentionally not released here. They can contain
        # operational or credential-like material and are not required to
        # identify an input contract.
        result: dict[str, Any] = {}
        for provider_key, canonical_key in (
            ("name", "name"),
            ("type", "type"),
            ("description", "description"),
        ):
            value = cls._first_scalar(variable, provider_key)
            if value:
                result[canonical_key] = value

        if isinstance(variable.get("direction"), bool):
            result["direction"] = variable["direction"]

        return result

    @staticmethod
    def _component_records(payload: Any) -> Sequence[Mapping[str, Any]]:
        if not isinstance(payload, Mapping):
            raise ValueError("Datto component search response is not an object")
        records = payload.get("components")
        if not isinstance(records, (list, tuple)):
            raise ValueError(
                "Datto component search response does not expose a components collection"
            )
        if not all(isinstance(item, Mapping) for item in records):
            raise ValueError(
                "Datto component search returned a non-object component record"
            )
        return tuple(records)

    @classmethod
    def _canonical_job_read_result(
        cls,
        *,
        payload: Any,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("Datto job read response is not an object")

        requested_uid = str(
            arguments.get("job_uid")
            or arguments.get("resource_id")
            or ""
        ).strip()
        provider_uid = cls._first_scalar(payload, "uid")
        if not requested_uid:
            raise ValueError("job_uid or resource_id is required")
        if not provider_uid:
            raise ValueError("Datto job read response lacks durable uid")
        if provider_uid != requested_uid:
            raise ValueError("Datto job read response identity does not match request")

        status = cls._first_scalar(payload, "status")
        if not status:
            raise ValueError("Datto job read response lacks status")

        job: dict[str, Any] = {
            "resource_id": provider_uid,
            "status": status,
        }
        name = cls._first_scalar(payload, "name")
        date_created = cls._first_scalar(payload, "dateCreated")
        if name:
            job["name"] = name
        if date_created:
            job["date_created"] = date_created

        return {
            "job": job,
            "discovery_complete": True,
        }
