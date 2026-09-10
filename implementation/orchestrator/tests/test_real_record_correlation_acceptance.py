import pytest

from orchestrator.real_record_correlation_acceptance import (
    CorrelationAcceptanceError,
    CorrelationStageStatus,
    EndpointIdentityHint,
    RealRecordCorrelationAcceptance,
    collection_count,
    endpoint_matched_attributes,
    exact_name_match,
    extract_autotask_company_name,
    extract_autotask_endpoint_hint,
    extract_autotask_ticket_links,
    extract_it_glue_endpoint_hint,
    extract_it_glue_name,
    extract_it_glue_resource_id,
    require_single_autotask_item,
    require_single_it_glue_item,
    safe_stage,
    sha256_text,
)


def test_extract_real_ticket_relationship_fields_without_provider_specific_inference() -> None:
    output = {
        "data": {
            "items": [
                {
                    "id": 123,
                    "ticketNumber": "T20260909.0001",
                    "companyID": 42,
                    "contactID": 77,
                    "configurationItemID": 50282,
                }
            ]
        }
    }
    links = extract_autotask_ticket_links(require_single_autotask_item(output))
    assert links.ticket_id == "123"
    assert links.company_id == "42"
    assert links.contact_id == "77"
    assert links.configuration_item_id == "50282"
    assert collection_count(output, provider="autotask") == 1


def test_configuration_link_accepts_autotask_installed_product_alias() -> None:
    links = extract_autotask_ticket_links(
        {"id": 123, "companyID": 42, "installedProductID": 50282}
    )
    assert links.configuration_item_id == "50282"


def test_missing_optional_ticket_configuration_is_an_evidence_outcome_not_a_guess() -> None:
    links = extract_autotask_ticket_links({"id": 123, "companyID": 42})
    assert links.configuration_item_id is None
    stage = safe_stage(
        stage="ticket_to_endpoint",
        candidate_count=0,
        provider_ids=("autotask",),
        not_applicable=True,
        note="ticket contains no governed configuration reference",
    )
    assert stage.status is CorrelationStageStatus.NOT_APPLICABLE


def test_it_glue_json_api_resource_shape_is_bounded_and_deterministic() -> None:
    output = {
        "data": {
            "data": [
                {
                    "id": "9001",
                    "type": "configurations",
                    "attributes": {
                        "name": "AOT-50282",
                        "serial-number": "ABC123",
                    },
                }
            ]
        }
    }
    record = require_single_it_glue_item(output)
    assert extract_it_glue_resource_id(record) == "9001"
    assert extract_it_glue_name(record) == "AOT-50282"
    hint = extract_it_glue_endpoint_hint(record)
    assert hint == EndpointIdentityHint(name="AOT-50282", serial_number="ABC123")
    assert collection_count(output, provider="it_glue") == 1


def test_company_and_endpoint_names_require_exact_normalized_agreement() -> None:
    assert extract_autotask_company_name({"companyName": "  HER   Shelter "}) == "HER   Shelter"
    assert exact_name_match("  HER   Shelter ", "her shelter") is True
    assert exact_name_match("HER Shelter", "HER Shelter - Old") is False

    autotask = extract_autotask_endpoint_hint(
        {"referenceTitle": "AOT-50282", "serialNumber": "ABC-123"}
    )
    it_glue = EndpointIdentityHint(name="aot-50282", serial_number="abc-123")
    assert endpoint_matched_attributes(autotask, it_glue) == ("name", "serial_number")


def test_autotask_exact_read_singular_item_envelope_is_normalized() -> None:
    assert extract_autotask_company_name(
        {"item": {"id": 42, "companyName": "HER Shelter"}}
    ) == "HER Shelter"
    assert extract_autotask_endpoint_hint(
        {
            "item": {
                "id": 50282,
                "referenceTitle": "AOT-50282",
                "serialNumber": "ABC123",
            }
        }
    ) == EndpointIdentityHint(name="AOT-50282", serial_number="ABC123")


def test_malformed_or_conflicting_autotask_exact_read_envelope_fails_closed() -> None:
    with pytest.raises(CorrelationAcceptanceError, match="singular item envelope"):
        extract_autotask_company_name({"item": None})
    with pytest.raises(CorrelationAcceptanceError, match="conflicting"):
        extract_autotask_company_name(
            {"item": {"companyName": "A"}, "items": [{"companyName": "A"}]}
        )


def test_ambiguous_stage_never_silently_selects_one_candidate() -> None:
    stage = safe_stage(
        stage="organization_correlation",
        candidate_count=2,
        provider_ids=("autotask", "it_glue"),
        resource_ids=("1", "2"),
        matched_attributes=("name",),
    )
    assert stage.status is CorrelationStageStatus.AMBIGUOUS
    assert len(stage.resource_hashes) == 2
    assert "1" not in stage.resource_hashes
    assert "2" not in stage.resource_hashes


def test_single_stage_hashes_identifiers_instead_of_persisting_them() -> None:
    stage = safe_stage(
        stage="endpoint_correlation",
        candidate_count=1,
        provider_ids=("autotask", "it_glue", "datto_rmm"),
        resource_ids=("sensitive-provider-id",),
        matched_attributes=("name",),
    )
    assert stage.status is CorrelationStageStatus.PROVEN
    assert stage.resource_hashes == (sha256_text("sensitive-provider-id"),)
    assert "sensitive-provider-id" not in stage.resource_hashes


def test_zero_model_acceptance_contract_is_enforced() -> None:
    record = RealRecordCorrelationAcceptance(
        correlation_id="corr-1",
        ticket_selector_sha256=sha256_text("T20260909.0001"),
        stages=(
            safe_stage(
                stage="ticket_seed",
                candidate_count=1,
                provider_ids=("autotask",),
                resource_ids=("123",),
            ),
        ),
    )
    assert record.hosted_model_used is False
    assert record.hosted_model_input_tokens == 0
    assert record.hosted_model_output_tokens == 0
    assert record.hosted_model_cost_usd == "0"
    assert record.raw_provider_payload_persisted is False
    assert record.raw_provider_payload_printed is False

    with pytest.raises(ValueError, match="deterministic"):
        RealRecordCorrelationAcceptance(
            correlation_id="corr-1",
            ticket_selector_sha256=sha256_text("T20260909.0001"),
            stages=record.stages,
            hosted_model_used=True,
        )


def test_multiple_records_fail_closed_for_single_record_extraction() -> None:
    with pytest.raises(CorrelationAcceptanceError, match="exactly one"):
        require_single_autotask_item({"data": {"items": [{"id": 1}, {"id": 2}]}})
    with pytest.raises(CorrelationAcceptanceError, match="exactly one"):
        require_single_it_glue_item({"data": {"data": [{"id": "1"}, {"id": "2"}]}})
