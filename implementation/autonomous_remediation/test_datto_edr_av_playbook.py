from .datto_edr_av_playbook import (
    ApprovalClass,
    ExecutionObservation,
    HealthObservation,
    PlaybookRun,
    PlaybookState,
    RepairStep,
    escalation_payload,
    internal_ticket_note,
    metrics_payload,
    next_action,
    verification_action,
)


def run() -> PlaybookRun:
    return PlaybookRun(
        run_id="run-1",
        ticket_id="T1",
        device_id="AOT-50282",
        organization_id="ORG1",
        client_id="CLIENT1",
    )


def test_healthy_stops_immediately():
    r = run()
    action = next_action(r, HealthObservation(status="Healthy"))
    assert action is None
    assert r.state == PlaybookState.HEALTHY


def test_missing_edr_uses_maintenance_then_reinstall():
    r = run()
    h = HealthObservation(status="Unhealthy", hunt_agent_installed=False, av_present=True, av_healthy=True)
    action = next_action(r, h)
    assert action.step == RepairStep.EDR_MAINTENANCE
    r.record_job(action)
    action = next_action(r, h)
    assert action.step == RepairStep.EDR_FORCE_REINSTALL


def test_av_force_update_is_single_governed_command():
    r = run()
    h = HealthObservation(
        status="Unhealthy",
        hunt_agent_installed=True,
        hunt_agent_running=True,
        edr_current=True,
        av_present=False,
    )
    action = next_action(r, h)
    assert action.step == RepairStep.AV_FORCE_UPDATE
    assert action.approval_class == ApprovalClass.STANDING_SAFE


def test_hung_av_update_schedules_reboot_and_never_redispatches_same_step():
    r = run()
    h = HealthObservation(
        status="Unhealthy",
        hunt_agent_installed=True,
        hunt_agent_running=True,
        edr_current=True,
        av_present=False,
    )
    action = next_action(r, h)
    r.record_job(action)
    r.record_execution(
        action,
        ExecutionObservation(
            terminal=False,
            provider_status="Running",
            job_id="J1",
            stdout_observed=False,
        ),
    )
    action2 = next_action(r, h)
    assert action2.step == RepairStep.SCHEDULED_REBOOT
    assert action2.approval_class == ApprovalClass.APPROVAL_REQUIRED
    assert r.state == PlaybookState.AWAITING_APPROVAL
    assert action2.schedule_local == "02:30"
    assert action2.resume_local == "03:30"
    r.record_job(action2)
    assert r.state == PlaybookState.AWAITING_SCHEDULED_REBOOT


def test_post_reboot_allows_one_more_av_update_then_clean_recovery():
    r = run()
    h = HealthObservation(
        status="Unhealthy",
        hunt_agent_installed=True,
        hunt_agent_running=True,
        edr_current=True,
        av_present=False,
    )
    a1 = next_action(r, h)
    r.record_job(a1)
    r.force_update_pending_reboot = True
    reboot = next_action(r, h)
    r.record_job(reboot)
    r.force_update_pending_reboot = False
    a2 = next_action(r, h)
    assert a2.step == RepairStep.POST_REBOOT_AV_FORCE_UPDATE
    r.record_job(a2)
    a3 = next_action(r, h)
    assert a3.step == RepairStep.CLEAN_UNINSTALL
    assert a3.approval_class == ApprovalClass.POLICY_GATED


def test_clean_recovery_sequence_is_bounded():
    r = run()
    h = HealthObservation(
        status="Unhealthy",
        hunt_agent_installed=False,
        hunt_agent_running=False,
        edr_current=False,
        av_present=False,
    )
    # Exhaust ordinary EDR and AV repair.
    for step in (RepairStep.EDR_MAINTENANCE, RepairStep.EDR_FORCE_REINSTALL, RepairStep.AV_FORCE_UPDATE):
        r.attempted_steps.add(step)
        r.attempt_order.append(step)
    clean = next_action(r, h)
    assert clean.step == RepairStep.CLEAN_UNINSTALL
    r.record_job(clean)
    recovery_reboot = next_action(r, h)
    assert recovery_reboot.step == RepairStep.RECOVERY_REBOOT
    assert recovery_reboot.approval_class == ApprovalClass.APPROVAL_REQUIRED
    assert r.state == PlaybookState.AWAITING_APPROVAL
    r.record_job(recovery_reboot)
    assert r.state == PlaybookState.AWAITING_SCHEDULED_REBOOT
    maintenance = next_action(r, h)
    assert maintenance.step == RepairStep.RECOVERY_MAINTENANCE
    r.record_job(maintenance)
    reinstall = next_action(r, h)
    assert reinstall.step == RepairStep.RECOVERY_FORCE_REINSTALL


def test_provider_success_is_not_health():
    r = run()
    h = HealthObservation(status="Unhealthy", hunt_agent_installed=False)
    action = next_action(r, h)
    r.record_job(action)
    r.record_execution(
        action,
        ExecutionObservation(terminal=True, provider_status="Completed", job_id="J2"),
    )
    assert r.state != PlaybookState.HEALTHY
    verify = verification_action(r)
    assert verify.operation.startswith("Check Datto EDR/AV Status")


def test_read_failure_does_not_create_permission_to_redispatch():
    r = run()
    h = HealthObservation(status="Unhealthy", hunt_agent_installed=False)
    action = next_action(r, h)
    r.record_job(action)
    r.record_execution(
        action,
        ExecutionObservation(
            terminal=False,
            provider_status="Unknown",
            job_id="J3",
            read_failed=True,
        ),
    )
    assert action.idempotency_key in r.completed_job_keys


def test_notes_are_concise_and_metrics_are_stable():
    r = run()
    r.record_health(HealthObservation(status="Healthy", edr_version="3.5.1"))
    note = internal_ticket_note(r)
    assert "Status=Healthy" in note
    assert len(note) < 250
    metrics = metrics_payload(r)
    assert metrics["healthy"] is True
    assert metrics["playbook"].startswith("Jason - Datto EDR/AV")


def test_escalation_payload_contains_required_evidence_fields():
    r = run()
    r.provider_job_ids.append("J9")
    r.record_health(
        HealthObservation(
            status="Unhealthy",
            edr_version="3.0",
            hunt_agent_path=r"C:\\Program Files\\Infocyte\\Agent\\agent.exe",
            hunt_agent_running=False,
            av_present=False,
            security_center_healthy=False,
        )
    )
    r.escalate("test")
    payload = escalation_payload(r)
    assert payload["device_id"] == "AOT-50282"
    assert payload["provider_job_ids"] == ("J9",)
    assert payload["reasons"] == ("test",)
