from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse


class ProviderEvidenceInconsistentError(RuntimeError):
    """Transport succeeded but provider evidence is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class AdaptationProbe:
    arguments: Mapping[str, Any]
    reason: str


@dataclass(frozen=True, slots=True)
class AdaptationObservation:
    collection_key: str
    declared_total: int
    initial_count: int
    probes_attempted: int
    recovered: bool
    accepted_arguments: Mapping[str, Any] | None = None
    pages_aggregated: int = 1
    final_count: int | None = None
    complete: bool = False


@dataclass(frozen=True, slots=True)
class AdaptationResult:
    payload: Mapping[str, Any]
    observation: AdaptationObservation | None = None


@dataclass(frozen=True, slots=True)
class BoundedCollectionReadAdapter:
    """Validate and, when requested, complete a read-only provider collection.

    Transport success is not treated as proof of semantic completeness.

    The adapter may:
    - recover contradictory empty pages with bounded read-only probes;
    - follow provider-supplied pagination evidence;
    - aggregate a complete authorized collection when the inquiry requires it.

    It never mutates provider state or production configuration.
    """

    max_probes: int = 5
    max_pages: int = 20
    max_items: int = 1000

    def recover(
        self,
        *,
        payload: Mapping[str, Any],
        collection_key: str,
        request_arguments: Mapping[str, Any],
        probe: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        complete: bool = False,
    ) -> AdaptationResult:
        current = payload
        collection = current.get(collection_key)

        if not isinstance(collection, list):
            return AdaptationResult(payload=current)

        page_details = current.get("pageDetails")
        if not isinstance(page_details, Mapping):
            return AdaptationResult(payload=current)

        declared_total = self._positive_int(page_details.get("totalCount"))
        initial_count = len(collection)

        observation: AdaptationObservation | None = None

        # Contradictory empty collection: provider says records exist.
        if declared_total > 0 and initial_count == 0:
            recovered = self._recover_first_usable_page(
                payload=current,
                collection_key=collection_key,
                request_arguments=request_arguments,
                probe=probe,
                declared_total=declared_total,
            )
            current = recovered.payload
            observation = recovered.observation

        if not complete:
            return AdaptationResult(
                payload=current,
                observation=observation,
            )

        completed = self._complete_collection(
            payload=current,
            collection_key=collection_key,
            probe=probe,
            request_arguments=request_arguments,
        )

        if completed.observation is not None:
            base = observation
            comp = completed.observation
            observation = AdaptationObservation(
                collection_key=collection_key,
                declared_total=comp.declared_total,
                initial_count=(
                    base.initial_count if base is not None else initial_count
                ),
                probes_attempted=(
                    (base.probes_attempted if base is not None else 0)
                    + comp.probes_attempted
                ),
                recovered=(
                    base.recovered if base is not None else True
                ),
                accepted_arguments=(
                    base.accepted_arguments
                    if base is not None
                    else comp.accepted_arguments
                ),
                pages_aggregated=comp.pages_aggregated,
                final_count=comp.final_count,
                complete=comp.complete,
            )

        return AdaptationResult(
            payload=completed.payload,
            observation=observation,
        )

    def _recover_first_usable_page(
        self,
        *,
        payload: Mapping[str, Any],
        collection_key: str,
        request_arguments: Mapping[str, Any],
        probe: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        declared_total: int,
    ) -> AdaptationResult:
        page_details = payload.get("pageDetails")
        if not isinstance(page_details, Mapping):
            raise ProviderEvidenceInconsistentError(
                "provider collection metadata is unavailable"
            )

        probes = self._candidate_probes(
            page_details=page_details,
            declared_total=declared_total,
            request_arguments=request_arguments,
        )

        attempts = 0

        for candidate in probes[: self.max_probes]:
            attempts += 1
            recovered = probe(candidate.arguments)
            recovered_collection = recovered.get(collection_key)

            if not isinstance(recovered_collection, list):
                continue

            if recovered_collection:
                return AdaptationResult(
                    payload=recovered,
                    observation=AdaptationObservation(
                        collection_key=collection_key,
                        declared_total=declared_total,
                        initial_count=0,
                        probes_attempted=attempts,
                        recovered=True,
                        accepted_arguments=dict(candidate.arguments),
                        pages_aggregated=1,
                        final_count=len(recovered_collection),
                        complete=False,
                    ),
                )

            recovered_details = recovered.get("pageDetails")
            if isinstance(recovered_details, Mapping):
                if self._positive_int(
                    recovered_details.get("totalCount")
                ) == 0:
                    return AdaptationResult(payload=recovered)

        raise ProviderEvidenceInconsistentError(
            f"provider reported {declared_total} {collection_key} "
            f"but returned an empty collection after {attempts} bounded probes"
        )

    def _complete_collection(
        self,
        *,
        payload: Mapping[str, Any],
        collection_key: str,
        probe: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        request_arguments: Mapping[str, Any],
    ) -> AdaptationResult:
        first = payload.get(collection_key)
        details = payload.get("pageDetails")

        if not isinstance(first, list) or not isinstance(details, Mapping):
            return AdaptationResult(payload=payload)

        declared_total = self._positive_int(details.get("totalCount"))

        if declared_total == 0:
            return AdaptationResult(
                payload=payload,
                observation=AdaptationObservation(
                    collection_key=collection_key,
                    declared_total=0,
                    initial_count=len(first),
                    probes_attempted=0,
                    recovered=True,
                    pages_aggregated=1,
                    final_count=len(first),
                    complete=True,
                ),
            )

        items = list(first)
        pages = 1
        probes = 0
        current_details = details
        seen_pages: set[tuple[int, int]] = set()

        while len(items) < declared_total:
            if pages >= self.max_pages:
                raise ProviderEvidenceInconsistentError(
                    f"provider collection requires more than {self.max_pages} pages"
                )
            if len(items) >= self.max_items:
                raise ProviderEvidenceInconsistentError(
                    f"provider collection exceeds bounded limit of {self.max_items} items"
                )

            next_args = self._next_page_arguments(
                current_details,
                request_arguments=request_arguments,
            )

            if next_args is None:
                raise ProviderEvidenceInconsistentError(
                    f"provider reports {declared_total} {collection_key} "
                    f"but pagination ended after {len(items)} records"
                )

            marker = (
                int(next_args["page"]),
                int(next_args["max"]),
            )

            if marker in seen_pages:
                raise ProviderEvidenceInconsistentError(
                    "provider pagination repeated a previously visited page"
                )

            seen_pages.add(marker)
            next_payload = probe(next_args)
            probes += 1

            next_items = next_payload.get(collection_key)
            next_details = next_payload.get("pageDetails")

            if not isinstance(next_items, list):
                raise ProviderEvidenceInconsistentError(
                    "provider pagination returned a non-collection page"
                )

            if not isinstance(next_details, Mapping):
                raise ProviderEvidenceInconsistentError(
                    "provider pagination omitted pageDetails"
                )

            if not next_items:
                raise ProviderEvidenceInconsistentError(
                    f"provider pagination returned an empty page before "
                    f"declared total {declared_total} was satisfied"
                )

            items.extend(next_items)
            pages += 1
            current_details = next_details

        # Never silently accept over-collection either.
        if len(items) != declared_total:
            raise ProviderEvidenceInconsistentError(
                f"provider declared {declared_total} records but aggregation "
                f"produced {len(items)}"
            )

        completed_payload = dict(payload)
        completed_payload[collection_key] = items
        completed_payload["pageDetails"] = {
            **dict(current_details),
            "count": len(items),
            "totalCount": declared_total,
            "nextPageUrl": None,
        }

        return AdaptationResult(
            payload=completed_payload,
            observation=AdaptationObservation(
                collection_key=collection_key,
                declared_total=declared_total,
                initial_count=len(first),
                probes_attempted=probes,
                recovered=True,
                pages_aggregated=pages,
                final_count=len(items),
                complete=True,
            ),
        )

    def _candidate_probes(
        self,
        *,
        page_details: Mapping[str, Any],
        declared_total: int,
        request_arguments: Mapping[str, Any],
    ) -> tuple[AdaptationProbe, ...]:
        candidate_pages: list[int] = []

        for key in ("prevPageUrl", "nextPageUrl"):
            parsed = self._pagination_arguments(page_details.get(key))
            if parsed is not None:
                page = parsed["page"]
                if page not in candidate_pages:
                    candidate_pages.append(page)

        for page in (0, 1):
            if page not in candidate_pages:
                candidate_pages.append(page)

        current_page = self._nonnegative_int(request_arguments.get("page"))
        if current_page is not None and current_page not in candidate_pages:
            candidate_pages.append(current_page)

        safe_sizes: list[int] = []
        for value in (
            min(25, max(declared_total - 1, 1)),
            min(10, max(declared_total - 1, 1)),
            min(5, max(declared_total - 1, 1)),
        ):
            if value > 0 and value not in safe_sizes:
                safe_sizes.append(value)

        probes: list[AdaptationProbe] = []
        seen: set[tuple[int, int]] = set()

        for page in candidate_pages:
            for maximum in safe_sizes:
                marker = (page, maximum)
                if marker in seen:
                    continue
                seen.add(marker)
                probes.append(
                    AdaptationProbe(
                        arguments={
                            "page": page,
                            "max": maximum,
                        },
                        reason=(
                            "collection metadata contradicted returned collection"
                        ),
                    )
                )

        return tuple(probes)

    def _next_page_arguments(
        self,
        page_details: Mapping[str, Any],
        *,
        request_arguments: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        parsed = self._pagination_arguments(
            page_details.get("nextPageUrl")
        )
        if parsed is not None:
            return parsed

        return None

    @classmethod
    def _pagination_arguments(
        cls,
        raw_url: Any,
    ) -> Mapping[str, int] | None:
        if not isinstance(raw_url, str) or not raw_url.strip():
            return None

        try:
            query = parse_qs(urlparse(raw_url).query)
            page = int(query["page"][0])
            maximum = int(query["max"][0])
        except (KeyError, IndexError, TypeError, ValueError):
            return None

        if page < 0 or maximum < 1:
            return None

        return {
            "page": page,
            "max": maximum,
        }

    @staticmethod
    def _positive_int(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    @staticmethod
    def _nonnegative_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None
