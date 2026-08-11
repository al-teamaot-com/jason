from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_runtime_compose_has_no_host_published_port_and_preserves_network_separation():
    compose = (_repo_root() / "infrastructure/jason-runtime/compose.yaml").read_text(encoding="utf-8")

    assert "ports:" not in compose
    assert 'user: "1000:1000"' in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "name: openclaw_default" in compose
    assert "name: jason-core" in compose
    assert "name: jason-observability" in compose
    assert "/var/lib/jason/openclaw/trusted-keys:/var/lib/jason/openclaw/trusted-keys:ro" in compose


def test_runtime_image_drops_to_host_state_owner_uid_and_uses_internal_entrypoint():
    dockerfile = (_repo_root() / "infrastructure/jason-runtime/Dockerfile").read_text(encoding="utf-8")

    assert "USER 1000:1000" in dockerfile
    assert 'CMD ["python", "-m", "jason_runtime.main"]' in dockerfile
