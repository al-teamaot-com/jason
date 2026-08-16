from __future__ import annotations

import json

from orchestrator.authoritative_derivations import (
    AuthoritativeDerivationRegistry,
    WINDOWS_RELEASE_FROM_BUILD,
)
from orchestrator.evidence_interpreter import EvidenceVerifier
from orchestrator.generic_evidence_reasoning import (
    GenericStructuredEvidenceReasoner,
    GovernedEvidenceInterpreter,
    build_reasoning_evidence_catalog,
)


class FakeStructuredClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete(self, *, system, user, schema, max_output_tokens=160):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
            }
        )
        return dict(self.result)


def bundle():
    return {
        "request": {
            "resource_selector": {"hostname": "AOT-EXAMPLE"},
        },
        "sections": {
            "device": {
                "provenance": {"provider": "example_provider", "method": "GET"},
                "payload": {
                    "operatingSystem": "Microsoft Windows 11 Pro 10.0.26200",
                    "credential": "super-secret-should-never-reach-model",
                    "arbitraryNewProviderField": "new-value-never-added-to-a-vocabulary",
                },
            },
            "software": {
                "provenance": {"provider": "example_provider", "method": "GET"},
                "payload": [
                    {"name": "Example Browser", "version": "7.8.9"},
                    {"name": "Example Overlay Network", "version": "1.2.3"},
                ],
            },
        },
        "references": {
            "windows_release_health": {
                "provenance": {"source": "authoritative-example"},
                "payload": {
                    "rows": [
                        {"build_family": "26200", "release": "25H2"},
                    ]
                },
            }
        },
    }


def test_reasoning_catalog_contains_sanitized_semantic_previews():
    verifier = EvidenceVerifier()
    from orchestrator.evidence_sanitization import sanitize_evidence_tree

    sanitized = sanitize_evidence_tree(bundle())
    catalog = build_reasoning_evidence_catalog(
        verifier=verifier,
        sanitized_evidence_bundle=sanitized,
    )

    by_path = {item["path"]: item for item in catalog}
    assert by_path["/sections/software/payload/0/name"]["preview"] == "Example Browser"
    assert by_path["/sections/software/payload/1/name"]["preview"] == "Example Overlay Network"
    assert by_path["/sections/device/payload/arbitraryNewProviderField"]["preview"] == (
        "new-value-never-added-to-a-vocabulary"
    )
    assert "preview" not in by_path["/sections/device/payload/credential"]
    assert "/request/resource_selector/hostname" not in by_path
    assert "super-secret-should-never-reach-model" not in repr(catalog)


def test_generic_reasoner_can_select_previously_unmodeled_evidence_path():
    path = "/sections/device/payload/arbitraryNewProviderField"
    client = FakeStructuredClient(
        {
            "answer_type": "direct",
            "evidence_paths": [path],
        }
    )
    reasoner = GenericStructuredEvidenceReasoner(client=client)
    verifier = EvidenceVerifier()
    from orchestrator.evidence_sanitization import sanitize_evidence_tree

    sanitized = sanitize_evidence_tree(bundle())
    catalog = build_reasoning_evidence_catalog(
        verifier=verifier,
        sanitized_evidence_bundle=sanitized,
    )
    plan = reasoner.reason(
        question="What is the arbitrary new provider field?",
        evidence_catalog=catalog,
    )
    verified = verifier.verify(plan=plan, evidence_bundle=sanitized)

    assert verified.evidence[0].path == path
    assert verified.evidence[0].value == "new-value-never-added-to-a-vocabulary"
    call = client.calls[0]
    payload = json.loads(call["user"])
    assert payload["question"] == "What is the arbitrary new provider field?"
    assert path in call["schema"]["properties"]["evidence_paths"]["items"]["enum"]


def test_interpreter_sanitizes_before_model_and_dereferences_same_sanitized_bundle():
    path = "/sections/software/payload/0/version"
    client = FakeStructuredClient(
        {
            "answer_type": "direct",
            "evidence_paths": [path],
        }
    )
    reasoner = GenericStructuredEvidenceReasoner(client=client)
    verifier = EvidenceVerifier()
    interpreter = GovernedEvidenceInterpreter(
        reasoner=reasoner,
        verifier=verifier,
        derivations=AuthoritativeDerivationRegistry(),
    )

    result = interpreter.interpret(
        question="What version of Example Browser is installed?",
        evidence_bundle=bundle(),
    )

    assert result.verified.evidence[0].value == "7.8.9"
    assert result.sanitized_evidence_bundle["sections"]["device"]["payload"][
        "credential"
    ] == "[REDACTED]"
    assert "super-secret-should-never-reach-model" not in client.calls[0]["user"]


def test_unavailable_is_a_successful_abstention_not_an_execution_failure():
    client = FakeStructuredClient(
        {
            "answer_type": "unavailable",
            "evidence_paths": [],
        }
    )
    reasoner = GenericStructuredEvidenceReasoner(client=client)
    interpreter = GovernedEvidenceInterpreter(
        reasoner=reasoner,
        verifier=EvidenceVerifier(),
        derivations=AuthoritativeDerivationRegistry(),
    )

    result = interpreter.interpret(
        question="What fact is not represented in this evidence?",
        evidence_bundle=bundle(),
    )

    assert result.plan.answer_type == "unavailable"
    assert result.verified.answer_type == "unavailable"
    assert result.verified.evidence == ()
    assert result.derived is None


def test_approved_derivation_uses_provider_and_authoritative_reference_paths():
    paths = [
        "/sections/device/payload/operatingSystem",
        "/references/windows_release_health/payload/rows/0/build_family",
        "/references/windows_release_health/payload/rows/0/release",
    ]
    client = FakeStructuredClient(
        {
            "answer_type": "derived",
            "evidence_paths": paths,
            "derivation_required": WINDOWS_RELEASE_FROM_BUILD,
        }
    )
    reasoner = GenericStructuredEvidenceReasoner(
        client=client,
        approved_derivations=(WINDOWS_RELEASE_FROM_BUILD,),
    )
    verifier = EvidenceVerifier(
        approved_derivations=(WINDOWS_RELEASE_FROM_BUILD,)
    )
    interpreter = GovernedEvidenceInterpreter(
        reasoner=reasoner,
        verifier=verifier,
        derivations=AuthoritativeDerivationRegistry(),
    )

    result = interpreter.interpret(
        question="What Windows release is this workstation running?",
        evidence_bundle=bundle(),
    )

    assert result.derived is not None
    assert result.derived.value == "Windows 11 Pro 25H2"
    assert result.derived.source_paths == tuple(paths)


def test_reasoner_prompt_contains_no_workstation_fact_mapping_vocabulary():
    client = FakeStructuredClient(
        {
            "answer_type": "unavailable",
            "evidence_paths": [],
        }
    )
    reasoner = GenericStructuredEvidenceReasoner(client=client)
    reasoner.reason(
        question="A deliberately generic question",
        evidence_catalog=(
            {"path": "/sections/example/payload/x", "type": "string", "preview": "y"},
        ),
    )

    system = client.calls[0]["system"].casefold()
    for provider_or_fact_hint in (
        "datto",
        "intipaddress",
        "lastloggedinuser",
        "bitlocker",
        "reboot",
        "virus scan",
        "chrome",
        "zerotier",
    ):
        assert provider_or_fact_hint not in system
