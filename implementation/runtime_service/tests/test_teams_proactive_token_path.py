from pathlib import Path

from jason_runtime.composition import RuntimeSettings
from jason_runtime import teams_message_send, autonomous_completion_notification


EXPECTED = Path("/run/jason-secrets/teams-proactive-gateway/token")
LEGACY = "/run/jason-secrets/teams-proactive/token"


def test_runtime_settings_default_to_active_gateway_token_mount(monkeypatch):
    monkeypatch.delenv("JASON_TEAMS_PROACTIVE_TOKEN_FILE", raising=False)
    settings = RuntimeSettings.from_env()
    assert settings.teams_proactive_token_file == EXPECTED


def test_all_runtime_teams_sender_defaults_use_same_gateway_token_mount():
    composition_source = Path(
        "implementation/runtime_service/src/jason_runtime/composition.py"
    ).read_text(encoding="utf-8")
    governed_source = Path(
        "implementation/runtime_service/src/jason_runtime/teams_message_send.py"
    ).read_text(encoding="utf-8")
    completion_source = Path(
        "implementation/runtime_service/src/jason_runtime/autonomous_completion_notification.py"
    ).read_text(encoding="utf-8")

    for source in (composition_source, governed_source, completion_source):
        assert str(EXPECTED) in source
        assert LEGACY not in source


def test_environment_override_remains_supported(monkeypatch, tmp_path):
    override = tmp_path / "alternate-token"
    monkeypatch.setenv("JASON_TEAMS_PROACTIVE_TOKEN_FILE", str(override))
    settings = RuntimeSettings.from_env()
    assert settings.teams_proactive_token_file == override
