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
            "datto_rmm.job.output.read",
        }
    )
    adaptive_collection_keys = {
        "datto_rmm.component.search": "components",
    }
    default_component_page_size = 250
    maximum_component_page_size = 250
    maximum_job_output_records = 20
    maximum_job_output_chars = 65536

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

        if capability == "datto_rmm.job.output.read":
            job_uid = str(
                arguments.get("job_uid")
                or arguments.get("resource_id")
                or ""
            ).strip()
            device_uid = str(
                arguments.get("device_uid") or ""
            ).strip()
            component_uid = str(
                arguments.get("component_uid") or ""
            ).strip()
            stream = str(
                arguments.get("stream") or "stdout"
            ).strip().casefold()

            if not job_uid:
                raise ValueError(
                    "job_uid or resource_id is required"
                )
            if not device_uid:
                raise ValueError(
                    "device_uid is required for job output"
                )
            if not component_uid:
                raise ValueError(
                    "component_uid is required for job output"
                )
            if stream not in {"stdout", "stderr"}:
                raise ValueError(
                    "stream must be stdout or stderr"
                )

            return (
                f"/api/v2/job/{job_uid}/results/"
                f"{device_uid}/{stream}",
                None,
            )

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
            payload = self._complete_component_collection(
                request=request,
                initial_data=initial_data,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )
            return self._canonical_component_search_result(
                payload=payload,
                arguments=request.arguments,
            )

        if (
            request.context.capability
            == "datto_rmm.job.output.read"
        ):
            return self._canonical_job_output_result(
                payload=initial_data,
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

    def _record_component_completion(
        self,
        *,
        request: ConnectorRequest,
        declared_total: int,
        initial_count: int,
        pages_read: int,
        final_count: int,
        page_size: int,
    ) -> None:
        self._audit.record(
            "connector.adaptation_observed",
            request.context,
            {
                "provider": self.provider_name,
                "capability": request.context.capability,
                "collection_key": "components",
                "declared_total": declared_total,
                "initial_count": initial_count,
                "probes_attempted": max(pages_read - 1, 0),
                "recovered": True,
                "accepted_arguments": {
                    "page": 1,
                    "max": page_size,
                },
                "pages_aggregated": pages_read,
                "final_count": final_count,
                "complete": True,
            },
        )

    def _complete_component_collection(
        self,
        *,
        request: ConnectorRequest,
        initial_data: Any,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> Mapping[str, Any]:
        """Enumerate Datto's full component catalog before local filtering.

        Datto component search has no reliable server-side display-name filter.
        A first page is therefore not sufficient evidence for zero or unique
        name resolution. Keep following provider pages until the declared total
        is satisfied. If the provider omits nextPageUrl, advance the page number
        using the already accepted page size while still enforcing bounded
        collection limits.
        """
        if not isinstance(initial_data, Mapping):
            raise ValueError("Datto component search response is not an object")

        components = initial_data.get("components")
        if not isinstance(components, list):
            raise ValueError(
                "Datto component search response does not expose a components collection"
            )

        initial_count = len(components)
        details = initial_data.get("pageDetails")
        if not isinstance(details, Mapping):
            # Without provider pagination metadata, a full first page is
            # ambiguous: there may be additional records we cannot prove absent.
            if len(components) >= self.maximum_component_page_size:
                raise ValueError(
                    "Datto component discovery is incomplete: pagination metadata missing"
                )
            return dict(initial_data)

        try:
            declared_total = int(details.get("totalCount") or 0)
        except (TypeError, ValueError):
            declared_total = 0

        if declared_total <= 0:
            if len(components) >= self.maximum_component_page_size:
                raise ValueError(
                    "Datto component discovery is incomplete: totalCount unavailable"
                )
            return dict(initial_data)

        if declared_total > 5000:
            raise ValueError(
                "Datto component catalog exceeds bounded discovery limit"
            )

        items = list(components)
        if len(items) > declared_total:
            raise ValueError(
                "Datto component search returned more records than declared total"
            )

        try:
            current_page = max(int(request.arguments.get("page", 1)), 1)
        except (TypeError, ValueError):
            current_page = 1

        requested_max = request.arguments.get(
            "max",
            self.default_component_page_size,
        )
        try:
            page_size = max(
                1,
                min(int(requested_max), self.maximum_component_page_size),
            )
        except (TypeError, ValueError):
            page_size = self.default_component_page_size

        seen_uids: set[str] = set()
        for record in items:
            if isinstance(record, Mapping):
                uid = self._first_scalar(record, "uid")
                if uid:
                    seen_uids.add(uid)

        max_pages = 20
        pages_read = 1
        next_page = current_page + 1

        while len(items) < declared_total:
            if pages_read >= max_pages:
                raise ValueError(
                    "Datto component discovery exceeded bounded page limit"
                )

            prepared = self._prepare_provider_request(
                capability="datto_rmm.component.search",
                arguments={"page": next_page, "max": page_size},
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )
            payload = self._execute_prepared_request(
                request=request,
                prepared=prepared,
            )
            normalized = self._normalize_result(
                "datto_rmm.component.search",
                payload,
            )
            if not isinstance(normalized, Mapping):
                raise ValueError(
                    "Datto component pagination returned a non-object response"
                )

            page_items = normalized.get("components")
            if not isinstance(page_items, list):
                raise ValueError(
                    "Datto component pagination omitted components collection"
                )
            if not page_items:
                raise ValueError(
                    "Datto component pagination ended before declared total"
                )

            added = 0
            for record in page_items:
                if not isinstance(record, Mapping):
                    raise ValueError(
                        "Datto component pagination returned a non-object component record"
                    )
                uid = self._first_scalar(record, "uid")
                if not uid:
                    raise ValueError(
                        "Datto component record lacks durable uid"
                    )
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                items.append(record)
                added += 1

            if added == 0:
                raise ValueError(
                    "Datto component pagination repeated previously returned records"
                )

            pages_read += 1
            next_page += 1

            if len(items) > declared_total:
                raise ValueError(
                    "Datto component pagination exceeded declared total"
                )

        if len(items) != declared_total:
            raise ValueError(
                "Datto component discovery did not satisfy declared total"
            )

        self._record_component_completion(
            request=request,
            declared_total=declared_total,
            initial_count=initial_count,
            pages_read=pages_read,
            final_count=len(items),
            page_size=page_size,
        )

        completed = dict(initial_data)
        completed["components"] = items
        completed["pageDetails"] = {
            **dict(details),
            "count": len(items),
            "totalCount": declared_total,
            "nextPageUrl": None,
        }
        return completed

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
    def _canonical_job_output_result(
        cls,
        *,
        payload: Any,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not isinstance(payload, (list, tuple)):
            raise ValueError(
                "Datto job output response is not a collection"
            )

        requested_job_uid = str(
            arguments.get("job_uid")
            or arguments.get("resource_id")
            or ""
        ).strip()
        requested_device_uid = str(
            arguments.get("device_uid") or ""
        ).strip()
        requested_component_uid = str(
            arguments.get("component_uid") or ""
        ).strip()
        stream = str(
            arguments.get("stream") or "stdout"
        ).strip().casefold()

        if not requested_job_uid:
            raise ValueError(
                "job_uid or resource_id is required"
            )
        if not requested_device_uid:
            raise ValueError(
                "device_uid is required for job output"
            )
        if not requested_component_uid:
            raise ValueError(
                "component_uid is required for job output"
            )
        if stream not in {"stdout", "stderr"}:
            raise ValueError(
                "stream must be stdout or stderr"
            )

        outputs: list[Mapping[str, Any]] = []
        matching_records = 0
        remaining_chars = cls.maximum_job_output_chars
        bounded = False

        for record in payload:
            if not isinstance(record, Mapping):
                raise ValueError(
                    "Datto job output returned a non-object record"
                )

            provider_component_uid = cls._first_scalar(
                record,
                "componentUid",
            )

            if not provider_component_uid:
                raise ValueError(
                    "Datto job output record lacks componentUid"
                )

            if provider_component_uid != requested_component_uid:
                continue

            matching_records += 1

            if (
                len(outputs)
                >= cls.maximum_job_output_records
            ):
                bounded = True
                continue

            std_data = record.get("stdData")

            if std_data is None:
                text = ""
            elif isinstance(std_data, str):
                text = std_data
            else:
                raise ValueError(
                    "Datto job output stdData is not text"
                )

            truncated = False

            if remaining_chars <= 0:
                bounded = True
                continue

            if len(text) > remaining_chars:
                text = text[:remaining_chars]
                truncated = True
                bounded = True

            remaining_chars -= len(text)

            output: dict[str, Any] = {
                "component_uid": provider_component_uid,
                "stream": stream,
                "text": text,
                "truncated": truncated,
            }

            component_name = cls._first_scalar(
                record,
                "componentName",
            )

            if component_name:
                output["component_name"] = component_name

            outputs.append(output)

        return {
            "resource_id": requested_job_uid,
            "device_uid": requested_device_uid,
            "component_uid": requested_component_uid,
            "stream": stream,
            "outputs": outputs,
            "match_count": matching_records,
            "output_bounded": bounded,
            "discovery_complete": True,
        }

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
