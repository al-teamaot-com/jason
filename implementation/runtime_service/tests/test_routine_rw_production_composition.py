"""Source-only MCP/runtime composition acceptance without live credentials.

This is an isolated preproduction test: it creates temporary sqlite stores
and fake, inert AppRole files. No provider network calls or real writes.
"""
from jason_runtime.composition import build_runtime_application
from jason_runtime.routine_rw_registration import (
    ENTRA_USER_CREATE, IT_GLUE_NOTES,
)

from test_composition import _settings


def _runtime(tmp_path):
    return build_runtime_application(_settings(tmp_path))


def _capability_statuses(runtime):
    return {
        item.capability_name: item.lifecycle_status.value
        for item in runtime.capabilities.list_all()
        if item.capability_name in (ENTRA_USER_CREATE, IT_GLUE_NOTES)
    }


def _set_fake_bootstrap(monkeypatch, tmp_path, prefix):
    for field in ("ROLE_ID", "SECRET_ID"):
        p=tmp_path/(prefix+"-"+field.lower())
        p.write_text("synthetic-preproduction-not-a-credential")
        p.chmod(0o600)
        monkeypatch.setenv(
            "JASON_"+prefix+"_OPENBAO_"+field+"_PATH",
            str(p),
        )


def test_runtime_boots_default_off_with_both_writes_inactive(tmp_path, monkeypatch):
    monkeypatch.delenv("JASON_IT_GLUE_ROUTINE_RW_PROFILE", raising=False)
    monkeypatch.delenv("JASON_ENTRA_STANDARD_USER_CREATE_PROFILE", raising=False)
    application=_runtime(tmp_path)
    assert application.dispatch(
        method="GET", path="/healthz", headers={}, body=b"",
    ).status_code==200
    assert _capability_statuses(application)=={
        IT_GLUE_NOTES:"building", ENTRA_USER_CREATE:"building",
    }
    existing=set(application.governed_orchestrator._invoker.registered_capabilities())
    assert IT_GLUE_NOTES not in existing
    assert ENTRA_USER_CREATE not in existing
    assert "service.ticket.update" in existing


def test_profiles_without_bootstraps_stay_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("JASON_IT_GLUE_ROUTINE_RW_PROFILE", "configuration-notes-v1")
    monkeypatch.setenv("JASON_ENTRA_STANDARD_USER_CREATE_PROFILE", "cloud-user-v1")
    for prefix in ("IT_GLUE_RW", "ENTRA_USER_CREATE", "ENTRA_ONBOARDING_PASSWORD"):
        for field in ("ROLE_ID","SECRET_ID"):
            monkeypatch.setenv(
                "JASON_"+prefix+"_OPENBAO_"+field+"_PATH",
                str(tmp_path/"does-not-exist"),
            )
    application=_runtime(tmp_path)
    assert _capability_statuses(application)=={
        IT_GLUE_NOTES:"building", ENTRA_USER_CREATE:"building",
    }
    existing=set(application.governed_orchestrator._invoker.registered_capabilities())
    assert IT_GLUE_NOTES not in existing
    assert ENTRA_USER_CREATE not in existing


def test_synthetic_bootstrap_registers_exact_two_named_invokers(tmp_path, monkeypatch):
    monkeypatch.setenv("JASON_IT_GLUE_ROUTINE_RW_PROFILE", "configuration-notes-v1")
    monkeypatch.setenv("JASON_ENTRA_STANDARD_USER_CREATE_PROFILE", "cloud-user-v1")
    for prefix in ("IT_GLUE_RW", "ENTRA_USER_CREATE", "ENTRA_ONBOARDING_PASSWORD"):
        _set_fake_bootstrap(monkeypatch,tmp_path,prefix)
    application=_runtime(tmp_path)
    assert _capability_statuses(application)=={
        IT_GLUE_NOTES:"active", ENTRA_USER_CREATE:"active",
    }
    inv=application.governed_orchestrator._invoker.snapshot()
    assert IT_GLUE_NOTES in inv
    assert ENTRA_USER_CREATE in inv
    it=inv[IT_GLUE_NOTES]
    en=inv[ENTRA_USER_CREATE]
    assert set(it.connectors)=={"it_glue_configuration_note_update"}
    assert set(en.connectors)=={"microsoft_graph_standard_user_create"}
    assert set(it.provider_capability_map.values())=={"it_glue.configuration.update"}
    assert set(en.provider_capability_map.values())=={ENTRA_USER_CREATE}
    assert application.dispatch(
        method="GET",path="/healthz",headers={},body=b"",
    ).status_code==200


def test_missing_onboarding_password_pair_blocks_entra_only(tmp_path,monkeypatch):
    monkeypatch.setenv("JASON_IT_GLUE_ROUTINE_RW_PROFILE", "configuration-notes-v1")
    monkeypatch.setenv("JASON_ENTRA_STANDARD_USER_CREATE_PROFILE", "cloud-user-v1")
    for prefix in ("IT_GLUE_RW","ENTRA_USER_CREATE"):
        _set_fake_bootstrap(monkeypatch,tmp_path,prefix)
    for field in ("ROLE_ID","SECRET_ID"):
        monkeypatch.setenv(
            "JASON_ENTRA_ONBOARDING_PASSWORD_OPENBAO_"+field+"_PATH",
            str(tmp_path/"missing-onboarding-credential"),
        )
    application=_runtime(tmp_path)
    assert _capability_statuses(application)=={
        IT_GLUE_NOTES:"active", ENTRA_USER_CREATE:"building",
    }
    enabled=set(application.governed_orchestrator._invoker.registered_capabilities())
    assert IT_GLUE_NOTES in enabled
    assert ENTRA_USER_CREATE not in enabled
