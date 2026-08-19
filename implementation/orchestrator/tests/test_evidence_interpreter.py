from __future__ import annotations

import pytest

from orchestrator.evidence_interpreter import (
    EvidenceReasoningPlan,
    EvidenceVerificationError,
    EvidenceVerifier,
)
from orchestrator.evidence_sanitization import REDACTED


def evidence_bundle():
    return {
        "request": {
            "resource_selector": {"hostname": "AOT-50107"},
            "requested_facts": ["LAN IP"],
        },
        "sections": {
            "device": {
                "status": "available",
                "provenance": {
                    "provider": "datto_rmm",
                    "method": "GET",
                    "path": "/api/v2/device/example",
                },
                "payload": {
                    "hostname": "AOT-50107",
                    "intIpAddress": "192.0.2.25",
                    "lastLoggedInUser": r"AzureAD\ExampleUser",
                    "emptyValue": "",
                    "secretValue": REDACTED,
                    "nested": {
                        "a/b": "escaped-pointer-value",
                    },
                },
            }
        },
        "references": {
            "windows_release_health": {
                "provenance": {
                    "source": "microsoft",
                    "status": "authoritative",
                },
                "payload": {
                    "build_family": "26200",
                    "release": "25H2",
                },
            }
        },
    }


def test_direct_plan_dereferences_actual_evidence_value():
    verifier = EvidenceVerifier()
    plan = EvidenceReasoningPlan(
        answer_type="direct",
        evidence_paths=("/sections/device/payload/intIpAddress",),
    )

    result = verifier.verify(plan=plan, evidence_bundle=evidence_bundle())

    assert result.answer_type == "direct"
    assert result.evidence[0].value == "192.0.2.25"
    assert result.evidence[0].provenance["provider"] == "datto_rmm"
    assert result.evidence[0].provenance["method"] == "GET"


def test_unavailable_plan_returns_no_claimed_evidence():
    verifier = EvidenceVerifier()

    result = verifier.verify(
        plan=EvidenceReasoningPlan(answer_type="unavailable"),
        evidence_bundle=evidence_bundle(),
    )

    assert result.answer_type == "unavailable"
    assert result.evidence == ()


def test_path_outside_governed_evidence_roots_fails_closed():
    verifier = EvidenceVerifier()
    plan = EvidenceReasoningPlan(
        answer_type="direct",
        evidence_paths=("/request/resource_selector/hostname",),
    )

    with pytest.raises(EvidenceVerificationError, match="outside governed"):
        verifier.verify(plan=plan, evidence_bundle=evidence_bundle())


def test_metadata_path_inside_evidence_root_fails_closed():
    bundle = evidence_bundle()
    bundle["sections"]["device"]["selector"] = {"hostname": "poison-value"}
    verifier = EvidenceVerifier()
    plan = EvidenceReasoningPlan(
        answer_type="direct",
        evidence_paths=("/sections/device/selector/hostname",),
    )

    with pytest.raises(EvidenceVerificationError, match="orchestration metadata"):
        verifier.verify(plan=plan, evidence_bundle=bundle)


def test_redacted_and_empty_values_cannot_be_asserted():
    verifier = EvidenceVerifier()

    for path in (
        "/sections/device/payload/secretValue",
        "/sections/device/payload/emptyValue",
    ):
        plan = EvidenceReasoningPlan(
            answer_type="direct",
            evidence_paths=(path,),
        )
        with pytest.raises(EvidenceVerificationError, match="unavailable or redacted"):
            verifier.verify(plan=plan, evidence_bundle=evidence_bundle())


def test_missing_path_cannot_be_asserted():
    verifier = EvidenceVerifier()
    plan = EvidenceReasoningPlan(
        answer_type="direct",
        evidence_paths=("/sections/device/payload/doesNotExist",),
    )

    with pytest.raises(EvidenceVerificationError, match="does not exist"):
        verifier.verify(plan=plan, evidence_bundle=evidence_bundle())


def test_unapproved_derivation_fails_closed_before_fact_assembly():
    verifier = EvidenceVerifier()
    plan = EvidenceReasoningPlan(
        answer_type="derived",
        evidence_paths=("/sections/device/payload/hostname",),
        derivation_required="windows_release_from_build",
    )

    with pytest.raises(EvidenceVerificationError, match="not approved"):
        verifier.verify(plan=plan, evidence_bundle=evidence_bundle())


def test_approved_derivation_can_select_provider_and_reference_evidence():
    verifier = EvidenceVerifier(
        approved_derivations=("windows_release_from_build",)
    )
    plan = EvidenceReasoningPlan(
        answer_type="derived",
        evidence_paths=(
            "/sections/device/payload/hostname",
            "/references/windows_release_health/payload/build_family",
            "/references/windows_release_health/payload/release",
        ),
        derivation_required="windows_release_from_build",
    )

    result = verifier.verify(plan=plan, evidence_bundle=evidence_bundle())

    assert result.answer_type == "derived"
    assert result.derivation_required == "windows_release_from_build"
    assert [item.value for item in result.evidence] == [
        "AOT-50107",
        "26200",
        "25H2",
    ]


def test_catalog_exposes_paths_not_raw_operational_values():
    verifier = EvidenceVerifier()

    catalog = verifier.catalog(evidence_bundle())

    paths = {entry["path"] for entry in catalog}
    assert "/sections/device/payload/intIpAddress" in paths
    assert "/sections/device/provenance/provider" not in paths
    assert "/request/resource_selector/hostname" not in paths
    assert all("value" not in entry for entry in catalog)
    assert "192.0.2.25" not in repr(catalog)
    assert r"AzureAD\ExampleUser" not in repr(catalog)


def test_rfc6901_escaped_pointer_tokens_are_dereferenced():
    verifier = EvidenceVerifier()
    plan = EvidenceReasoningPlan(
        answer_type="direct",
        evidence_paths=("/sections/device/payload/nested/a~1b",),
    )

    result = verifier.verify(plan=plan, evidence_bundle=evidence_bundle())

    assert result.evidence[0].value == "escaped-pointer-value"


def test_reasoning_plan_rejects_values_disguised_as_invalid_paths():
    with pytest.raises(ValueError, match="absolute JSON pointers"):
        EvidenceReasoningPlan(
            answer_type="direct",
            evidence_paths=("192.0.2.25",),
        )


def test_unavailable_plan_cannot_smuggle_evidence_paths():
    with pytest.raises(ValueError, match="cannot claim evidence"):
        EvidenceReasoningPlan(
            answer_type="unavailable",
            evidence_paths=("/sections/device/payload/hostname",),
        )
