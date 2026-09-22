from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from connectors.core.connector_base import ConnectorBase, PreparedRequest
from connectors.core.provider_adaptation import BoundedCollectionReadAdapter
from connectors.core.contracts import ConnectorRequest, ConnectorResult, require_capability
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials
from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence


class DattoRmmConnector(ConnectorBase):
    # Provider-specific declarations consumed by the generic adaptation layer.
    # The algorithm itself remains provider-neutral.
    adaptive_collection_keys = {
        "datto_rmm.site.search": "sites",
        "datto_rmm.device.patches.list": "patches",
    }
    provider_name = "datto_rmm"
    logical_secret = "datto_rmm.readonly"
    default_device_search_max = 25
    fallback_discovery_page_size = 250
    fallback_discovery_max_pages = 20
    device_scoped_read_capabilities = frozenset(
        {
            "datto_rmm.device.alerts.open",
            "datto_rmm.device.alerts.resolved",
            "datto_rmm.device.audit.get",
            "datto_rmm.device.software.list",
            "datto_rmm.device.patches.list",
        }
    )

    capabilities = frozenset(
        {
            "datto_rmm.device.get",
            "datto_rmm.device.search",
            "datto_rmm.device.alerts.open",
            "datto_rmm.device.alerts.resolved",
            "datto_rmm.device.audit.get",
            "datto_rmm.device.software.list",
            "datto_rmm.device.patches.list",
            "datto_rmm.account.alerts.open",
            "datto_rmm.site.search",
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
                request.context.capability == "datto_rmm.device.search"
                and (
                    self._requested_facts_present(
                        request.arguments
                    )
                    or self._has_device_discovery_selector(
                        request.arguments
                    )
                )
            )
            should_resolve_scoped_read = (
                request.context.capability in self.device_scoped_read_capabilities
                and not self._durable_device_identity_present(request.arguments)
            )

            if should_resolve_device:
                data = self._execute_device_resolve(
                    request=request,
                    credentials=credentials,
                    access_token=token.access_token,
                    token_type=token.token_type,
                )
            elif should_resolve_scoped_read:
                data = self._execute_device_scoped_read(
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
                data = self._normalize_result(
                    request.context.capability,
                    payload,
                )
                data = self._adapt_collection_result(
                    request=request,
                    initial_data=data,
                    credentials=credentials,
                    access_token=token.access_token,
                    token_type=token.token_type,
                )
                if request.context.capability == "datto_rmm.device.patches.list":
                    data = self._filter_device_patch_result(
                        payload=data,
                        arguments=request.arguments,
                    )
        finally:
            token = None

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    @staticmethod
    def _durable_device_identity_present(arguments: Mapping[str, Any]) -> bool:
        return bool(
            str(
                arguments.get("device_uid")
                or arguments.get("resource_id")
                or ""
            ).strip()
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

        Datto's hostname filter may behave as an exact filter. If the human supplied a
        grounded name fragment such as ``50282`` and that exact provider query returns
        no records, the connector performs bounded account discovery and compares the
        human fragment only against provider-returned hostnames. It never manufactures
        a prefix, site, tenant, or hostname. A unique durable UID may be resolved only
        after complete discovery; ambiguity or incomplete discovery fails closed.
        """

        user_reference = self._user_identity_reference(
            request.arguments
        )

        if user_reference:
            discovery = self._execute_user_identity_discovery(
                request=request,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
                user_reference=user_reference,
            )
            matches = discovery["resource_matches"]

        elif not self._has_device_discovery_selector(
            request.arguments
        ):
            discovery = self._execute_account_device_collection(
                request=request,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )
            matches = discovery["resource_matches"]

        elif self._site_reference(request.arguments) and not self._hostname_reference(request.arguments):
            # A site-only provider search may return only the provider default page.
            # Enumerate the authorized account collection to completion and filter
            # locally so a client-wide review cannot mistake a partial site sample
            # for complete inventory evidence.
            discovery = self._execute_account_device_collection(
                request=request,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )
            site_reference = self._site_reference(request.arguments)
            matches = [
                match for match in discovery["resource_matches"]
                if self._site_reference_matches(
                    reference=site_reference,
                    site=str(match.get("site", "")),
                )
            ]
            discovery = {**dict(discovery), "resource_matches": matches}

        else:
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
            discovery = self._normalize_result(
                "datto_rmm.device.search",
                search_payload,
            )
            matches = discovery["resource_matches"]

            hostname_reference = self._hostname_reference(
                request.arguments
            )
            site_reference = self._site_reference(
                request.arguments
            )

            if hostname_reference:
                exact_matches = self._exact_hostname_site_matches(
                    matches=matches,
                    hostname_reference=hostname_reference,
                    site_reference=site_reference,
                )
                discovery = {
                    **dict(discovery),
                    "resource_matches": exact_matches,
                }
                matches = exact_matches

        hostname_reference = self._hostname_reference(request.arguments)
        if not matches and hostname_reference:
            discovery = self._execute_hostname_fragment_discovery(
                request=request,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
                hostname_reference=hostname_reference,
            )
            matches = discovery["resource_matches"]

        if len(matches) != 1 or discovery.get("discovery_complete") is False:
            return discovery

        resource_id = str(
            matches[0].get(
                "resource_id",
                "",
            )
        ).strip()

        if not resource_id:
            # Preserve the unique candidate as evidence, but do not issue a
            # second provider request without durable provider identity.
            return discovery

        # A complete, unique provider discovery may establish durable
        # resource identity without reading detailed resource facts.
        #
        # This is intentionally distinct from promoting the human selector:
        # the canonical identity is still the provider-returned resource_id.
        #
        # Pure discovery therefore returns the provider-neutral resolution
        # envelope and stops. An exact device GET is performed only when the
        # governed request actually asks for facts.
        if not self._requested_facts_present(
            request.arguments
        ):
            return {
                **dict(discovery),
                "resolved_resource_id": resource_id,
            }

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
            "provider_data": adapt_datto_device_semantic_evidence(read_payload),
        }

    def _execute_device_scoped_read(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> Any:
        """Resolve one human endpoint selector before a device-scoped read.

        Human endpoint names remain discovery selectors. The provider must return
        exactly one durable device UID before the requested device-scoped read is
        issued. Ambiguous or incomplete discovery fails closed.
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

        discovery = self._normalize_result(
            "datto_rmm.device.search",
            search_payload,
        )

        matches = discovery["resource_matches"]

        hostname_reference = self._hostname_reference(request.arguments)
        site_reference = self._site_reference(request.arguments)

        if hostname_reference:
            exact_matches = self._exact_hostname_site_matches(
                matches=matches,
                hostname_reference=hostname_reference,
                site_reference=site_reference,
            )
            discovery = {
                **dict(discovery),
                "resource_matches": exact_matches,
            }
            matches = exact_matches

        if not matches and hostname_reference:
            discovery = self._execute_hostname_fragment_discovery(
                request=request,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
                hostname_reference=hostname_reference,
            )
            matches = discovery["resource_matches"]

        if len(matches) != 1 or discovery.get("discovery_complete") is False:
            return discovery

        resource_id = str(
            matches[0].get("resource_id", "")
        ).strip()

        if not resource_id:
            return discovery

        resolved_arguments = dict(request.arguments)
        resolved_arguments["resource_id"] = resource_id
        resolved_arguments["device_uid"] = resource_id

        prepared = self._prepare_provider_request(
            capability=request.context.capability,
            arguments=resolved_arguments,
            credentials=credentials,
            access_token=access_token,
            token_type=token_type,
        )

        payload = self._execute_prepared_request(
            request=request,
            prepared=prepared,
        )

        return {
            "resource_matches": matches,
            "resolved_resource_id": resource_id,
            "provider_data": adapt_datto_device_semantic_evidence(payload),
        }


    def _adapt_collection_result(
        self,
        *,
        request: ConnectorRequest,
        initial_data: Any,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> Any:
        collection_key = self.adaptive_collection_keys.get(
            request.context.capability
        )

        if not collection_key or not isinstance(initial_data, Mapping):
            return initial_data

        adapter = BoundedCollectionReadAdapter(max_probes=5)

        def probe(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
            merged_arguments = dict(request.arguments)
            merged_arguments.update(arguments)

            prepared = self._prepare_provider_request(
                capability=request.context.capability,
                arguments=merged_arguments,
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )

            payload = self._execute_prepared_request(
                request=request,
                prepared=prepared,
            )

            normalized = self._normalize_result(
                request.context.capability,
                payload,
            )

            if not isinstance(normalized, Mapping):
                return {}

            return normalized

        result = adapter.recover(
            payload=initial_data,
            collection_key=collection_key,
            request_arguments=request.arguments,
            probe=probe,
            complete=(
                str(
                    request.arguments.get(
                        "completeness_requirement",
                        "sufficient",
                    )
                ).strip()
                == "complete"
                or request.context.capability
                in {
                    "datto_rmm.site.search",
                    "datto_rmm.device.patches.list",
                }
            ),
        )

        if result.observation is not None:
            observation = result.observation

            self._audit.record(
                "connector.adaptation_observed",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "collection_key": observation.collection_key,
                    "declared_total": observation.declared_total,
                    "initial_count": observation.initial_count,
                    "probes_attempted": observation.probes_attempted,
                    "recovered": observation.recovered,
                    "accepted_arguments": dict(
                        observation.accepted_arguments or {}
                    ),
                    "pages_aggregated": observation.pages_aggregated,
                    "final_count": observation.final_count,
                    "complete": observation.complete,
                },
            )

        payload = result.payload

        if (
            request.context.capability
            == "datto_rmm.site.search"
        ):
            payload = self._filter_site_search_result(
                payload=payload,
                arguments=request.arguments,
            )

        return payload


    @staticmethod
    def _site_selector_present(
        arguments: Mapping[str, Any],
    ) -> bool:
        return any(
            str(arguments.get(key) or "").strip()
            for key in (
                "name",
                "site",
                "site_id",
                "site_uid",
            )
        )


    @classmethod
    def _filter_site_search_result(
        cls,
        *,
        payload: Any,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Apply canonical site selectors to complete provider evidence.

        Datto account site enumeration is used as discovery evidence.
        Filtering occurs only against provider-returned identifiers and names;
        no site identity is invented or inferred.
        """

        if not isinstance(payload, Mapping):
            return payload

        sites = payload.get("sites")

        if not isinstance(sites, list):
            return payload

        name_reference = str(
            arguments.get("name")
            or arguments.get("site")
            or ""
        ).strip()

        id_reference = str(
            arguments.get("site_id")
            or arguments.get("site_uid")
            or ""
        ).strip()

        matches = []

        for site in sites:
            if not isinstance(site, Mapping):
                continue

            if id_reference:
                provider_ids = {
                    str(site.get("uid") or "").strip(),
                    str(site.get("id") or "").strip(),
                }

                if id_reference not in provider_ids:
                    continue

            if name_reference:
                provider_name = str(
                    site.get("name") or ""
                ).strip()

                if (
                    name_reference.casefold()
                    not in provider_name.casefold()
                ):
                    continue

            matches.append(dict(site))

        result = dict(payload)
        result["sites"] = matches

        details = result.get("pageDetails")

        if isinstance(details, Mapping):
            result["pageDetails"] = {
                **dict(details),
                "count": len(matches),
                "totalCount": len(matches),
                "prevPageUrl": None,
                "nextPageUrl": None,
            }

        result["discovery_complete"] = True

        return result


    def _execute_hostname_fragment_discovery(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
        hostname_reference: str,
    ) -> Mapping[str, Any]:
        """Complete bounded local hostname discovery after provider-filter failure.

        Datto's account-device hostname filter is useful as a fast positive lookup but
        has proven unsafe as definitive negative evidence. If that filtered lookup
        returns no exact match, Jason enumerates the authorized account device
        collection from Datto page zero and matches only provider-returned hostnames
        and sites locally.

        Exact case-insensitive hostname matches always take precedence over delimited
        identifier-segment matches. A supplied site is used as an exact
        case-insensitive disambiguator. Enumeration is complete only after Datto
        returns an empty provider page. Safety bounds and repeated-page stalls are
        explicit incomplete discovery, never definitive not-found evidence.
        """

        site_reference = self._site_reference(request.arguments)
        provider_pages: list[Any] = []
        exact_matches: list[Mapping[str, str]] = []
        fragment_matches: list[Mapping[str, str]] = []
        seen_matches: set[str] = set()
        seen_provider_records: set[str] = set()
        discovery_complete = False
        incomplete_reason = ""

        for page in range(self.fallback_discovery_max_pages):
            prepared = self._prepare_provider_request(
                capability="datto_rmm.device.search",
                arguments={
                    "page": page,
                    "max": self.fallback_discovery_page_size,
                },
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )
            payload = self._execute_prepared_request(
                request=request,
                prepared=prepared,
            )
            provider_pages.append(payload)
            records = self._device_records(payload)

            if not records:
                discovery_complete = True
                break

            new_provider_records = 0

            for record in records:
                match = self._canonical_device_match(record)
                provider_key = self._device_match_key(match)

                if provider_key and provider_key not in seen_provider_records:
                    seen_provider_records.add(provider_key)
                    new_provider_records += 1

                hostname = str(match.get("hostname", "")).strip()
                if not hostname:
                    continue

                if site_reference and not self._site_reference_matches(
                    reference=site_reference,
                    site=str(match.get("site", "")),
                ):
                    continue

                is_exact = (
                    hostname_reference.strip().casefold()
                    == hostname.casefold()
                )

                if not is_exact and not self._hostname_reference_matches(
                    reference=hostname_reference,
                    hostname=hostname,
                ):
                    continue

                dedupe_key = self._device_match_key(match)
                if not dedupe_key or dedupe_key in seen_matches:
                    continue

                seen_matches.add(dedupe_key)
                if is_exact:
                    exact_matches.append(match)
                else:
                    fragment_matches.append(match)

            if records and new_provider_records == 0:
                incomplete_reason = "pagination_stalled"
                break

        if not discovery_complete and not incomplete_reason:
            incomplete_reason = "page_limit_reached"

        matches = (
            exact_matches
            if exact_matches
            else fragment_matches
        )

        result: dict[str, Any] = {
            "resource_matches": matches,
            "provider_data": {
                "discovery_mode": "hostname_local_enumeration",
                "hostname_reference": hostname_reference,
                "site_reference": site_reference or None,
                "pages": provider_pages,
            },
            "discovery_complete": discovery_complete,
        }

        if not discovery_complete:
            result["incomplete_reason"] = incomplete_reason

        return result

    @staticmethod
    def _has_device_discovery_selector(
        arguments: Mapping[str, Any],
    ) -> bool:
        """Return whether the request supplies a concrete endpoint selector."""

        return any(
            str(arguments.get(key) or "").strip()
            for key in (
                "hostname",
                "name",
                "resource_id",
                "site",
                "serial_number",
                "user_identity",
            )
        )

    def _execute_account_device_collection(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> Mapping[str, Any]:
        """Enumerate the bounded authorized endpoint collection from Datto page zero."""

        provider_pages: list[Any] = []
        matches: list[Mapping[str, str]] = []
        seen: set[str] = set()
        discovery_complete = False
        incomplete_reason = ""

        for page in range(self.fallback_discovery_max_pages):
            prepared = self._prepare_provider_request(
                capability="datto_rmm.device.search",
                arguments={
                    "page": page,
                    "max": self.fallback_discovery_page_size,
                },
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )

            payload = self._execute_prepared_request(
                request=request,
                prepared=prepared,
            )
            provider_pages.append(payload)
            records = self._device_records(payload)

            if not records:
                discovery_complete = True
                break

            added = 0

            for record in records:
                match = self._canonical_device_match(record)
                key = self._device_match_key(match)

                if not key or key in seen:
                    continue

                seen.add(key)
                matches.append(match)
                added += 1

            if records and added == 0:
                incomplete_reason = "pagination_stalled"
                break

        if not discovery_complete and not incomplete_reason:
            incomplete_reason = "page_limit_reached"

        result: dict[str, Any] = {
            "resource_matches": matches,
            "provider_data": {
                "discovery_mode": "authorized_account_collection",
                "pages": provider_pages,
            },
            "discovery_complete": discovery_complete,
        }

        if not discovery_complete:
            result["incomplete_reason"] = incomplete_reason

        return result

    def _execute_user_identity_discovery(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
        user_reference: str,
    ) -> Mapping[str, Any]:
        """Resolve endpoint association from complete bounded provider user evidence."""

        provider_pages: list[Any] = []
        matches: list[Mapping[str, str]] = []
        seen: set[str] = set()
        seen_provider_records: set[str] = set()
        discovery_complete = False
        incomplete_reason = ""

        for page in range(self.fallback_discovery_max_pages):
            prepared = self._prepare_provider_request(
                capability="datto_rmm.device.search",
                arguments={
                    "page": page,
                    "max": self.fallback_discovery_page_size,
                },
                credentials=credentials,
                access_token=access_token,
                token_type=token_type,
            )
            payload = self._execute_prepared_request(
                request=request,
                prepared=prepared,
            )
            provider_pages.append(payload)
            records = self._device_records(payload)

            if not records:
                discovery_complete = True
                break

            new_provider_records = 0

            for record in records:
                provider_match = self._canonical_device_match(record)
                provider_key = self._device_match_key(provider_match)

                if provider_key and provider_key not in seen_provider_records:
                    seen_provider_records.add(provider_key)
                    new_provider_records += 1

                provider_user = self._first_scalar(
                    record,
                    "lastUser",
                    "last_user",
                    "lastLoggedInUser",
                    "last_logged_in_user",
                    "username",
                    "userName",
                )
                if not provider_user or not self._user_identity_matches(
                    reference=user_reference,
                    provider_identity=provider_user,
                ):
                    continue

                key = self._device_match_key(provider_match)
                if not key or key in seen:
                    continue

                seen.add(key)
                matches.append(provider_match)

            if records and new_provider_records == 0:
                incomplete_reason = "pagination_stalled"
                break

        if not discovery_complete and not incomplete_reason:
            incomplete_reason = "page_limit_reached"

        result: dict[str, Any] = {
            "resource_matches": matches,
            "provider_data": {
                "discovery_mode": "user_identity_relationship",
                "pages": provider_pages,
            },
            "discovery_complete": discovery_complete,
        }

        if not discovery_complete:
            result["incomplete_reason"] = incomplete_reason

        return result

    @staticmethod
    def _user_identity_reference(arguments: Mapping[str, Any]) -> str:
        return str(arguments.get("user_identity") or "").strip()

    @staticmethod
    def _normalized_human_identity(value: str) -> str:
        text = value.strip()
        if "\\" in text:
            text = text.rsplit("\\", 1)[-1]
        elif "/" in text:
            text = text.rsplit("/", 1)[-1]
        if "@" in text:
            text = text.split("@", 1)[0]
        return "".join(ch for ch in text.casefold() if ch.isalnum())

    @classmethod
    def _user_identity_matches(cls, *, reference: str, provider_identity: str) -> bool:
        left = cls._normalized_human_identity(reference)
        right = cls._normalized_human_identity(provider_identity)
        return bool(left and right and left == right)

    @staticmethod
    def _hostname_reference(arguments: Mapping[str, Any]) -> str:
        return str(arguments.get("hostname") or arguments.get("name") or "").strip()

    @staticmethod
    def _site_reference(arguments: Mapping[str, Any]) -> str:
        return str(arguments.get("site") or "").strip()

    @staticmethod
    def _site_reference_matches(*, reference: str, site: str) -> bool:
        normalized_reference = " ".join(reference.split()).casefold()
        normalized_site = " ".join(site.split()).casefold()
        return bool(
            normalized_reference
            and normalized_site
            and normalized_reference == normalized_site
        )

    @classmethod
    def _exact_hostname_site_matches(
        cls,
        *,
        matches: Sequence[Mapping[str, str]],
        hostname_reference: str,
        site_reference: str = "",
    ) -> list[Mapping[str, str]]:
        hostname_key = hostname_reference.strip().casefold()
        if not hostname_key:
            return []

        exact: list[Mapping[str, str]] = []
        for match in matches:
            hostname = str(match.get("hostname", "")).strip()
            if hostname.casefold() != hostname_key:
                continue
            if site_reference and not cls._site_reference_matches(
                reference=site_reference,
                site=str(match.get("site", "")),
            ):
                continue
            exact.append(match)
        return exact

    @staticmethod
    def _device_match_key(match: Mapping[str, str]) -> str:
        resource_id = str(match.get("resource_id", "")).strip()
        if resource_id:
            return resource_id

        hostname = str(match.get("hostname", "")).strip().casefold()
        site_id = str(match.get("site_id", "")).strip()
        site = str(match.get("site", "")).strip().casefold()
        if not hostname:
            return ""
        return f"{hostname}|{site_id or site}"

    @staticmethod
    def _hostname_reference_matches(*, reference: str, hostname: str) -> bool:
        """Match a grounded human reference as a hostname identifier segment.

        Exact hostnames match directly. Otherwise the reference must be delimited by
        non-alphanumeric hostname punctuation, so ``50282`` matches ``AOT-50282`` but
        not ``AOT-150282``. This is discovery only and never infers what a prefix means.
        """

        normalized_reference = reference.strip()
        normalized_hostname = hostname.strip()
        if not normalized_reference or not normalized_hostname:
            return False
        if normalized_reference.casefold() == normalized_hostname.casefold():
            return True
        pattern = rf"(?<![A-Za-z0-9]){re.escape(normalized_reference)}(?![A-Za-z0-9])"
        return re.search(pattern, normalized_hostname, flags=re.IGNORECASE) is not None

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

    @classmethod
    def _filter_device_patch_result(
        cls,
        *,
        payload: Any,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Filter complete provider patch evidence by an exact grounded patch token.

        The provider collection is completed before this filter runs. A KB/title
        selector is matched only against provider-returned scalar values using
        case-insensitive token boundaries; zero or multiple matches remain visible
        and are never converted into first-match identity.
        """

        if not isinstance(payload, Mapping):
            raise ValueError("Datto device patch response is not an object")

        patches = payload.get("patches")
        if not isinstance(patches, list):
            raise ValueError("Datto device patch response does not expose a patches collection")
        if not all(isinstance(item, Mapping) for item in patches):
            raise ValueError("Datto device patch response contains a non-object patch record")

        reference = str(
            arguments.get("kb")
            or arguments.get("patch_identity")
            or arguments.get("patch")
            or ""
        ).strip()

        if not reference:
            return payload

        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(reference)}(?![A-Za-z0-9])",
            flags=re.IGNORECASE,
        )

        numeric_reference = ""
        if reference.casefold().startswith("kb"):
            numeric_reference = reference[2:].strip()

        def scalar_values(value: Any) -> Sequence[str]:
            values: list[str] = []
            if isinstance(value, Mapping):
                for nested in value.values():
                    values.extend(scalar_values(nested))
            elif isinstance(value, (list, tuple)):
                for nested in value:
                    values.extend(scalar_values(nested))
            elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
                text = str(value).strip()
                if text:
                    values.append(text)
            return tuple(values)

        matches: list[Mapping[str, Any]] = []
        for patch in patches:
            values = scalar_values(patch)
            if any(pattern.search(value) for value in values):
                matches.append(dict(patch))
                continue
            if numeric_reference and any(
                value.casefold() == numeric_reference.casefold()
                for value in values
            ):
                matches.append(dict(patch))

        result = dict(payload)
        result["patches"] = matches
        result["match_count"] = len(matches)
        result["patch_selector"] = reference
        result["exact_selector_match"] = len(matches) == 1
        result["ambiguous"] = len(matches) > 1
        return result

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
                # Datto account-device pagination is zero-based. Starting at page
                # one silently skips the first provider page and can turn a partial
                # scan into false not-found evidence.
                "page": max(int(arguments.get("page", 0)), 0),
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
        if capability == "datto_rmm.device.alerts.open":
            device_uid = str(
                arguments.get("device_uid") or arguments.get("resource_id") or ""
            ).strip()
            if not device_uid:
                raise ValueError("device_uid or resource_id is required")
            return f"/api/v2/device/{device_uid}/alerts/open", None

        if capability == "datto_rmm.device.alerts.resolved":
            device_uid = str(
                arguments.get("device_uid") or arguments.get("resource_id") or ""
            ).strip()
            if not device_uid:
                raise ValueError("device_uid or resource_id is required")
            return f"/api/v2/device/{device_uid}/alerts/resolved", None

        if capability == "datto_rmm.device.audit.get":
            device_uid = str(
                arguments.get("device_uid") or arguments.get("resource_id") or ""
            ).strip()
            if not device_uid:
                raise ValueError("device_uid or resource_id is required")
            return f"/api/v2/audit/device/{device_uid}", None

        if capability == "datto_rmm.device.software.list":
            device_uid = str(
                arguments.get("device_uid") or arguments.get("resource_id") or ""
            ).strip()
            if not device_uid:
                raise ValueError("device_uid or resource_id is required")

            # Datto software inventory is paginated. Keep the provider request
            # deliberately bounded; callers can request subsequent pages when
            # needed. A very large default page has produced empty provider
            # collections even when software inventory exists.
            return f"/api/v2/audit/device/{device_uid}/software", {
                "page": max(int(arguments.get("page", 1)), 1),
                "max": max(1, min(int(arguments.get("max", 50)), 50)),
            }

        if capability == "datto_rmm.device.patches.list":
            device_uid = str(
                arguments.get("device_uid") or arguments.get("resource_id") or ""
            ).strip()
            if not device_uid:
                raise ValueError("device_uid or resource_id is required")

            params: dict[str, Any] = {
                "page": max(int(arguments.get("page", 0)), 0),
                "max": max(1, min(int(arguments.get("max", 250)), 250)),
            }

            install_status = str(
                arguments.get("install_status") or arguments.get("installStatus") or ""
            ).strip().upper().replace(" ", "_").replace("-", "_")
            if install_status:
                allowed_statuses = {
                    "INSTALLED",
                    "APPROVED_PENDING",
                    "NOT_APPROVED",
                }
                if install_status not in allowed_statuses:
                    raise ValueError(
                        "install_status must be INSTALLED, APPROVED_PENDING, or NOT_APPROVED"
                    )
                params["installStatus"] = install_status

            return f"/api/v2/device/{device_uid}/patches", params

        if capability == "datto_rmm.account.alerts.open":
            params = {
                "page": max(int(arguments.get("page", 1)), 1),
                "max": max(1, min(int(arguments.get("max", 250)), 250)),
            }
            site_uid = str(
                arguments.get("site_uid") or arguments.get("site_id") or ""
            ).strip()
            if site_uid:
                params["siteUid"] = site_uid
            return "/api/v2/account/alerts/open", params

        if capability == "datto_rmm.site.search":
            selector_present = any(
                str(arguments.get(key) or "").strip()
                for key in (
                    "name",
                    "site",
                    "site_id",
                    "site_uid",
                )
            )

            # Datto site pagination is zero-based. A selector-driven discovery
            # must begin at the first provider page so completeness can be
            # proven before canonical filtering is applied.
            page = (
                0
                if selector_present
                else max(
                    int(arguments.get("page", 0)),
                    0,
                )
            )

            maximum = (
                250
                if selector_present
                else max(
                    2,
                    min(
                        int(
                            arguments.get(
                                "max",
                                250,
                            )
                        ),
                        250,
                    ),
                )
            )

            return "/api/v2/account/sites", {
                "page": page,
                "max": maximum,
            }

        # Legacy provider-specific alias retained until callers converge on the
        # governed provider-neutral alert resource capability.
        if capability == "datto_rmm.alerts.list":
            return "/api/v2/account/alerts/open", {
                "siteUid": arguments.get("site_uid")
            }

        if capability == "datto_rmm.patch_status.get":
            return f"/api/v2/device/{arguments['device_uid']}/audit", None
        if capability == "datto_rmm.component_results.list":
            return f"/api/v2/device/{arguments['device_uid']}/jobs", None
        raise ValueError(f"Unsupported capability: {capability}")
