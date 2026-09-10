from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class CorrelationAcceptanceError(ValueError):
    pass


class CorrelationStageStatus(str, Enum):
    PROVEN = "proven"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class AutotaskTicketLinks:
    ticket_id: str
    company_id: str
    contact_id: str | None
    configuration_item_id: str | None


@dataclass(frozen=True, slots=True)
class EndpointIdentityHint:
    name: str
    serial_number: str | None = None


@dataclass(frozen=True, slots=True)
class CorrelationStageEvidence:
    stage: str
    status: CorrelationStageStatus
    candidate_count: int
    matched_attributes: tuple[str, ...] = ()
    provider_ids: tuple[str, ...] = ()
    resource_hashes: tuple[str, ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.stage.strip():
            raise ValueError("correlation acceptance stage is required")
        if self.candidate_count < 0:
            raise ValueError("candidate_count must not be negative")
        if self.status is CorrelationStageStatus.PROVEN and self.candidate_count != 1:
            raise ValueError("a proven correlation stage must have exactly one candidate")
        if self.status is CorrelationStageStatus.AMBIGUOUS and self.candidate_count < 2:
            raise ValueError("an ambiguous correlation stage requires multiple candidates")


@dataclass(frozen=True, slots=True)
class RealRecordCorrelationAcceptance:
    correlation_id: str
    ticket_selector_sha256: str
    stages: tuple[CorrelationStageEvidence, ...]
    hosted_model_used: bool = False
    hosted_model_input_tokens: int = 0
    hosted_model_output_tokens: int = 0
    hosted_model_cost_usd: str = "0"
    raw_provider_payload_persisted: bool = False
    raw_provider_payload_printed: bool = False

    def __post_init__(self) -> None:
        if not self.correlation_id.strip():
            raise ValueError("correlation_id is required")
        if len(self.ticket_selector_sha256) != 64:
            raise ValueError("ticket selector hash must be SHA-256")
        if self.hosted_model_used:
            raise ValueError("real-record correlation acceptance must remain deterministic")
        if self.hosted_model_input_tokens or self.hosted_model_output_tokens:
            raise ValueError("deterministic acceptance cannot report hosted-model tokens")
        if self.hosted_model_cost_usd not in {"0", "0.0", "0.00", "0.000000"}:
            raise ValueError("deterministic acceptance must report zero hosted-model cost")
        if self.raw_provider_payload_persisted or self.raw_provider_payload_printed:
            raise ValueError("raw provider payload must not leave acceptance memory")


def sha256_text(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise CorrelationAcceptanceError("cannot hash a blank governed identifier")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_payload_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def require_single_autotask_item(output: Mapping[str, Any]) -> Mapping[str, Any]:
    data = output.get("data")
    if not isinstance(data, Mapping):
        raise CorrelationAcceptanceError("Autotask result is missing the governed data envelope")
    items = data.get("items")
    if not isinstance(items, list):
        raise CorrelationAcceptanceError("Autotask result is missing its item collection")
    if len(items) != 1:
        raise CorrelationAcceptanceError(
            f"Autotask acceptance requires exactly one record; observed {len(items)}"
        )
    item = items[0]
    if not isinstance(item, Mapping):
        raise CorrelationAcceptanceError("Autotask record has an unexpected shape")
    return item


def require_single_it_glue_item(output: Mapping[str, Any]) -> Mapping[str, Any]:
    data = output.get("data")
    if not isinstance(data, Mapping):
        raise CorrelationAcceptanceError("IT Glue result is missing the governed data envelope")
    items = data.get("data")
    if not isinstance(items, list):
        raise CorrelationAcceptanceError("IT Glue result is missing its resource collection")
    if len(items) != 1:
        raise CorrelationAcceptanceError(
            f"IT Glue acceptance requires exactly one record; observed {len(items)}"
        )
    item = items[0]
    if not isinstance(item, Mapping):
        raise CorrelationAcceptanceError("IT Glue resource has an unexpected shape")
    return item


def collection_count(output: Mapping[str, Any], *, provider: str) -> int:
    data = output.get("data")
    if not isinstance(data, Mapping):
        raise CorrelationAcceptanceError(f"{provider} result is missing the governed data envelope")
    if provider == "autotask":
        collection = data.get("items")
    elif provider == "it_glue":
        collection = data.get("data")
    else:
        raise CorrelationAcceptanceError(f"unsupported acceptance provider: {provider}")
    if not isinstance(collection, list):
        raise CorrelationAcceptanceError(f"{provider} result is missing its collection")
    return len(collection)


def extract_autotask_ticket_links(record: Mapping[str, Any]) -> AutotaskTicketLinks:
    ticket_id = _required_scalar(record, ("id",), "Autotask ticket id")
    company_id = _required_scalar(record, ("companyID", "companyId"), "Autotask company id")
    contact_id = _optional_scalar(record, ("contactID", "contactId"))
    configuration_item_id = _optional_scalar(
        record,
        (
            "configurationItemID",
            "configurationItemId",
            "installedProductID",
            "installedProductId",
        ),
    )
    return AutotaskTicketLinks(
        ticket_id=ticket_id,
        company_id=company_id,
        contact_id=contact_id,
        configuration_item_id=configuration_item_id,
    )


def extract_autotask_company_name(record: Mapping[str, Any]) -> str:
    return _required_scalar(record, ("companyName", "name"), "Autotask company name")


def extract_autotask_endpoint_hint(record: Mapping[str, Any]) -> EndpointIdentityHint:
    name = _required_scalar(
        record,
        ("referenceTitle", "referenceName", "name"),
        "Autotask configuration name",
    )
    serial = _optional_scalar(record, ("serialNumber", "serial", "serialNo"))
    return EndpointIdentityHint(name=name, serial_number=serial)


def extract_it_glue_resource_id(record: Mapping[str, Any]) -> str:
    return _required_scalar(record, ("id",), "IT Glue resource id")


def extract_it_glue_name(record: Mapping[str, Any]) -> str:
    attributes = record.get("attributes")
    if not isinstance(attributes, Mapping):
        raise CorrelationAcceptanceError("IT Glue resource is missing attributes")
    return _required_scalar(attributes, ("name",), "IT Glue resource name")


def extract_it_glue_endpoint_hint(record: Mapping[str, Any]) -> EndpointIdentityHint:
    attributes = record.get("attributes")
    if not isinstance(attributes, Mapping):
        raise CorrelationAcceptanceError("IT Glue configuration is missing attributes")
    name = _required_scalar(attributes, ("name", "hostname"), "IT Glue configuration name")
    serial = _optional_scalar(
        attributes,
        (
            "serial-number",
            "serial_number",
            "serialNumber",
            "serial",
        ),
    )
    return EndpointIdentityHint(name=name, serial_number=serial)


def exact_name_match(left: str, right: str) -> bool:
    return _normalized(left) == _normalized(right)


def endpoint_matched_attributes(
    left: EndpointIdentityHint,
    right: EndpointIdentityHint,
) -> tuple[str, ...]:
    matches: list[str] = []
    if exact_name_match(left.name, right.name):
        matches.append("name")
    if (
        left.serial_number
        and right.serial_number
        and _normalized(left.serial_number) == _normalized(right.serial_number)
    ):
        matches.append("serial_number")
    return tuple(matches)


def safe_stage(
    *,
    stage: str,
    candidate_count: int,
    provider_ids: Sequence[str],
    resource_ids: Sequence[Any] = (),
    matched_attributes: Sequence[str] = (),
    not_applicable: bool = False,
    note: str | None = None,
) -> CorrelationStageEvidence:
    if not_applicable:
        status = CorrelationStageStatus.NOT_APPLICABLE
    elif candidate_count == 0:
        status = CorrelationStageStatus.NOT_FOUND
    elif candidate_count == 1:
        status = CorrelationStageStatus.PROVEN
    else:
        status = CorrelationStageStatus.AMBIGUOUS
    return CorrelationStageEvidence(
        stage=stage,
        status=status,
        candidate_count=candidate_count,
        matched_attributes=tuple(str(item) for item in matched_attributes if str(item).strip()),
        provider_ids=tuple(str(item) for item in provider_ids if str(item).strip()),
        resource_hashes=tuple(sha256_text(item) for item in resource_ids if str(item).strip()),
        note=note,
    )


def _required_scalar(
    record: Mapping[str, Any],
    names: Sequence[str],
    label: str,
) -> str:
    value = _optional_scalar(record, names)
    if value is None:
        raise CorrelationAcceptanceError(f"{label} is absent")
    return value


def _optional_scalar(record: Mapping[str, Any], names: Sequence[str]) -> str | None:
    for name in names:
        value = record.get(name)
        if value is None or isinstance(value, (Mapping, list, tuple, set, bool)):
            continue
        text = str(value).strip()
        if text and text not in {"0", "None", "null"}:
            return text
    return None


def _normalized(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())
