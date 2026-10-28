"""Acceptance cases for provider-neutral least-disruptive execution policy."""
from .least_disruptive_policy import (
    Impact, RemediationGateResult, action_fingerprint, applies_to_remediation,
    assess_remediation, classify_impact,
)


EVIDENCE = ["corr_mcp_drmm12345", "evidence://rmm/endpoint/c220"]


def assessment(**changes):
    value = {
        "decision": "recommend",
        "target_id": "pc7",
        "problem": "Printer queue is blocked because Print Spooler has stopped.",
        "evidence_refs": EVIDENCE,
        "expected_improvement": "Restore printing while leaving active user sessions intact.",
        "verification": "Read Print Spooler status and attempt a test print to validate.",
        "narrower_options": [],
    }
    value.update(changes)
    return value


def test_restart_print_spooler_is_better_than_host_reboot_with_exact_technician_approval():
    service = assess_remediation(
        capability="automation.component.execute",
        arguments={"device_uid": "pc7", "variables": {"usrinput": "Restart-Service Spooler"}},
        component_name="Run Ad Hoc Command (PowerShell 2-5) [WIN]",
        review=assessment(), explicit_technician_approval=True,
    )
    assert service.impact is Impact.SERVICE_INTERRUPTION
    assert service.may_proceed_to_authority
    assert service.reasons == ()


def test_reboot_blocked_if_spooler_repair_is_still_viable_even_after_approval():
    decision = assess_remediation(
        capability="automation.component.execute",
        arguments={"device_uid": "pc7", "variables": {"usrinput": "Restart-Computer"}},
        review=assessment(narrower_options=[{
            "action": "Restart Print Spooler service",
            "disposition": "viable", "evidence_refs": EVIDENCE,
        }]), explicit_technician_approval=True,
    )
    assert decision.impact is Impact.HOST_DISRUPTION
    assert not decision.may_proceed_to_authority
    assert "LESS_DISRUPTIVE_EFFECTIVE_ACTION_AVAILABLE" in decision.reasons


def test_reboot_blocked_without_narrower_action_review_even_with_approval():
    decision = assess_remediation(
        capability="endpoint.reboot.schedule", arguments={"device_uid": "pc7"},
        review=assessment(), explicit_technician_approval=True,
    )
    assert not decision.may_proceed_to_authority
    assert "HOST_DISRUPTION_REQUIRES_NARROWER_OPTIONS_REVIEW" in decision.reasons
    assert "PRINT_SERVICE_REPAIR_NOT_RULED_OUT" in decision.reasons


def test_reboot_only_allowed_if_narrower_spooler_repair_failed_with_evidence():
    decision = assess_remediation(
        capability="endpoint.reboot.schedule", arguments={"device_uid": "pc7"},
        review=assessment(narrower_options=[{
            "action": "Restart Print Spooler service",
            "disposition": "attempted_failed",
            "evidence_refs": ["evidence://job/restart-spooler-failed"],
        }]), explicit_technician_approval=True,
    )
    assert decision.may_proceed_to_authority


def test_reboot_still_requires_exact_technician_authorization():
    decision = assess_remediation(
        capability="endpoint.reboot.schedule", arguments={"device_uid": "pc7"},
        review=assessment(narrower_options=[{
            "action": "Restart Print Spooler service",
            "disposition": "attempted_failed",
            "evidence_refs": EVIDENCE,
        }]), explicit_technician_approval=False,
    )
    assert not decision.may_proceed_to_authority
    assert "EXPLICIT_DISRUPTION_APPROVAL_REQUIRED" in decision.reasons


def test_negative_jason_judgment_refuses_even_if_technician_approved():
    decision = assess_remediation(
        capability="endpoint.security.scan.start", arguments={"resource_id": "pc7", "scan_type": "full"},
        review=assessment(decision="do_not_run"), explicit_technician_approval=True,
    )
    assert not decision.may_proceed_to_authority
    assert "REMEDIATION_NOT_RECOMMENDED_BY_JASON" in decision.reasons


def test_missing_expected_benefit_or_verification_refuses_action():
    for value in (assessment(expected_improvement=""),
                  assessment(verification=""), assessment(evidence_refs=[]), None):
        decision = assess_remediation(
            capability="endpoint.security.scan.start", arguments={"resource_id": "pc7"},
            review=value, explicit_technician_approval=True,
        )
        assert not decision.may_proceed_to_authority


def test_urgent_edr_isolation_justified_when_narrower_measures_ruled_out_with_evidence():
    decision = assess_remediation(
        capability="endpoint.security.isolate", arguments={"resource_id": "infected-pc"},
        review=assessment(
            target_id="infected-pc",
            problem="Confirmed active malicious command and control on the affected endpoint.",
            expected_improvement="Prevent malicious lateral network propagation immediately.",
            verification="Read EDR isolation status and correlated network alerts.",
            narrower_options=[{
                "action": "Block malicious process only on the affected endpoint",
                "disposition": "not_applicable", "evidence_refs": EVIDENCE,
            }],
        ), explicit_technician_approval=True,
    )
    assert decision.impact is Impact.HOST_DISRUPTION
    assert decision.may_proceed_to_authority


def test_backup_operation_and_dnsfilter_change_need_benefit_and_verification():
    for capability, args in (
        ("backup.job.start", {"asset_id": "backup-one"}),
        ("dnsfilter.policy.update", {"policy_id": "policy-7"}),
    ):
        assert applies_to_remediation(capability)
        result = assess_remediation(
            capability=capability, arguments=args,
            review=assessment(
                target_id=("backup-one" if capability.startswith("backup.") else "policy-7"),
                problem="Monitoring detected a specific service issue requiring correction.",
                expected_improvement="Correct the observed service issue with a narrowly scoped change.",
                verification="Read the same provider's status and confirm the error clears.",
            ),
            explicit_technician_approval=True,
        )
        assert result.impact is (
            Impact.TARGETED if capability.startswith("backup.") else Impact.SERVICE_INTERRUPTION
        )
        assert result.may_proceed_to_authority


def test_open_end_administrative_ticket_updates_are_not_remediation_commands():
    for capability in ("service.ticket.note.create", "service.ticket.update",
                       "communication.teams.message.send", "service.quote.create"):
        assert not applies_to_remediation(capability)


def test_action_binding_changes_with_target_payload_or_capability():
    original = action_fingerprint("endpoint.security.scan.start", {"resource_id": "pc7", "scan_type": "quick"})
    assert original != action_fingerprint("endpoint.security.scan.start", {"resource_id": "pc8", "scan_type": "quick"})
    assert original != action_fingerprint("endpoint.security.scan.start", {"resource_id": "pc7", "scan_type": "full"})
    assert original != action_fingerprint("backup.job.start", {"resource_id": "pc7", "scan_type": "quick"})


def test_unknown_narrower_disposition_is_fail_closed():
    decision = assess_remediation(
        capability="endpoint.security.scan.start", arguments={"resource_id": "pc7"},
        review=assessment(narrower_options=[{"action": "Try targeted service repair", "disposition": "unknown"}]),
    )
    assert not decision.may_proceed_to_authority
    assert "REMEDIATION_ALTERNATIVE_UNRESOLVED" in decision.reasons


def test_component_cannot_hide_disruption_with_an_innocent_name():
    result = classify_impact(
        "automation.component.execute", {"variables": {"usrinput": "Restart-Computer -Force"}},
        component_name="diagnostic component",
    )
    assert result is Impact.HOST_DISRUPTION


def test_authored_impact_hint_cannot_override_server_classification():
    result = assess_remediation(
        capability="endpoint.reboot.schedule", arguments={"device_uid": "pc7"},
        review=assessment(impact="targeted"), explicit_technician_approval=False,
    )
    assert result.impact is Impact.HOST_DISRUPTION
    assert not result.may_proceed_to_authority


def test_action_review_cannot_be_reused_on_another_endpoint():
    result = assess_remediation(
        capability="endpoint.security.scan.start", arguments={"resource_id":"another-pc"},
        review=assessment(target_id="pc7"), explicit_technician_approval=True,
    )
    assert not result.may_proceed_to_authority
    assert "REMEDIATION_TARGET_SCOPE_MISMATCH" in result.reasons


def test_unclassified_component_requires_explicit_approval_because_disruption_is_uncertain():
    result = assess_remediation(
        capability="automation.component.execute", arguments={"device_uid": "pc7"},
        review=assessment(), explicit_technician_approval=False,
        component_name="Maintenance Utility",
    )
    assert result.impact is Impact.SERVICE_INTERRUPTION
    assert "EXPLICIT_DISRUPTION_APPROVAL_REQUIRED" in result.reasons


def test_network_and_identity_disruption_require_exact_approval():
    for capability, params, target in (
        ("network.adapter.disable", {"device_uid": "pc7"}, "pc7"),
        ("identity.user.disable", {"resource_id": "user-42"}, "user-42"),
        ("backup.asset.restore", {"asset_id": "asset-1"}, "asset-1"),
    ):
        decision = assess_remediation(
            capability=capability, arguments=params, review=assessment(target_id=target),
            explicit_technician_approval=False,
        )
        assert not decision.may_proceed_to_authority
        assert "EXPLICIT_DISRUPTION_APPROVAL_REQUIRED" in decision.reasons
