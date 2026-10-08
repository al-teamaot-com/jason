from jason_runtime.vulscan_non_kb import analyze_non_kb_vulscan, render_non_kb_assessment


def test_third_party_cve_correlates_installed_software():
    assessment = analyze_non_kb_vulscan(
        "Adobe Acrobat vulnerable version CVE-2026-12345 https://www.adobe.com/security/advisory",
        [{"name": "Adobe Acrobat", "version": "24.001"}],
    )
    assert assessment.classification == "third_party_or_runtime_vulnerability"
    assert assessment.cves == ("CVE-2026-12345",)
    assert assessment.matched_software
    assert assessment.confidence in {"moderate", "high"}
    assert "software_update_or_upgrade" in render_non_kb_assessment(assessment)


def test_protocol_finding_classifies_without_mutation_authority():
    assessment = analyze_non_kb_vulscan(
        "SMBv1 protocol is enabled and exposed service is reachable.",
        [],
    )
    assert assessment.classification == "service_or_protocol_exposure"
    assert assessment.remediation_kind == "service_protocol_or_firewall_change"
    rendered = render_non_kb_assessment(assessment)
    assert "No endpoint modification is authorized" in rendered


def test_false_positive_candidate_stays_read_only():
    assessment = analyze_non_kb_vulscan(
        "Scanner notes likely false positive / detection artifact; verify applicability.",
        [],
    )
    assert assessment.classification == "false_positive_candidate"
    assert assessment.remediation_kind == "validate_scanner_evidence"
