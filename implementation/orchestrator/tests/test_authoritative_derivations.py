from __future__ import annotations

import pytest

from orchestrator.authoritative_derivations import (
    AuthoritativeDerivationError,
    AuthoritativeDerivationRegistry,
    WINDOWS_RELEASE_FROM_BUILD,
)
from orchestrator.evidence_interpreter import (
    EvidenceReasoningPlan,
    EvidenceVerifier,
)


def bundle(*, provider_os: str = "Microsoft Windows 11 Pro 10.0.26200"):
    return {
        "sections": {
            "device": {
                "provenance": {
                    "provider": "datto_rmm",
                    "method": "GET",
                },
                "payload": {
                    "operatingSystem": provider_os,
                },
            }
        },
        "references": {
            "windows_release_health": {
                "provenance": {
                    "source": "Microsoft Windows release health",
                    "status": "authoritative",
                },
                "payload": {
                    "rows": [
                        {"build_family": "26100", "release": "24H2"},
                        {"build_family": "26200", "release": "25H2"},
                    ]
                },
            }
        },
    }


def verified_selection(evidence):
    verifier = EvidenceVerifier(
        approved_derivations=(WINDOWS_RELEASE_FROM_BUILD,)
    )
    plan = EvidenceReasoningPlan(
        answer_type="derived",
        evidence_paths=(
            "/sections/device/payload/operatingSystem",
            "/references/windows_release_health/payload/rows/1/build_family",
            "/references/windows_release_health/payload/rows/1/release",
        ),
        derivation_required=WINDOWS_RELEASE_FROM_BUILD,
    )
    return verifier.verify(plan=plan, evidence_bundle=evidence)


def test_windows_build_26200_derives_windows_11_pro_25h2():
    selection = verified_selection(bundle())

    result = AuthoritativeDerivationRegistry().derive(selection)

    assert result.value == "Windows 11 Pro 25H2"
    assert result.derivation == WINDOWS_RELEASE_FROM_BUILD
    assert result.source_paths == (
        "/sections/device/payload/operatingSystem",
        "/references/windows_release_health/payload/rows/1/build_family",
        "/references/windows_release_health/payload/rows/1/release",
    )


def test_derivation_uses_reference_evidence_not_an_internal_build_table():
    evidence = bundle()
    evidence["references"]["windows_release_health"]["payload"]["rows"][1][
        "release"
    ] = "26H1"
    selection = verified_selection(evidence)

    result = AuthoritativeDerivationRegistry().derive(selection)

    assert result.value == "Windows 11 Pro 26H1"


def test_mismatched_reference_build_fails_closed():
    evidence = bundle()
    evidence["references"]["windows_release_health"]["payload"]["rows"][1][
        "build_family"
    ] = "28000"
    selection = verified_selection(evidence)

    with pytest.raises(AuthoritativeDerivationError, match="no authoritative"):
        AuthoritativeDerivationRegistry().derive(selection)


def test_non_windows_provider_value_cannot_be_derived():
    selection = verified_selection(bundle(provider_os="Ubuntu 24.04 LTS"))

    with pytest.raises(AuthoritativeDerivationError, match="no Windows build"):
        AuthoritativeDerivationRegistry().derive(selection)
