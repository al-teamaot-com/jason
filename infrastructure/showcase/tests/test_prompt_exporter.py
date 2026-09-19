from __future__ import annotations
import importlib.util, json
from pathlib import Path


def load_exporter():
    path=Path(__file__).resolve().parents[1]/"prompt_exporter.py"
    spec=importlib.util.spec_from_file_location("jason_prompt_exporter",path)
    module=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module); return module


def test_registry_is_nonempty_hash_valid_and_secret_safe():
    module=load_exporter(); payload=module._load_registry(); prompts=payload["prompts"]
    assert len(prompts) >= 10
    assert len({p["prompt_id"] for p in prompts}) == len(prompts)
    assert all(module._hash_matches(p) == 1 for p in prompts)
    metrics=module.render_metrics()
    assert f"jason_ai_prompt_registry_entries {len(prompts)}" in metrics
    assert "jason_ai_prompt_invocation_telemetry_available 0" in metrics
    assert 'jason_ai_prompt_exporter_build_info{version="1"} 1' in metrics
    for p in prompts:
        assert f'prompt_id="{p["prompt_id"]}"' in metrics
        assert p["content_sha256"] not in metrics
    source_text="\n".join(module._source_prompt_text(p["source_path"],p["source_symbol"]) or "" for p in prompts)
    assert source_text
    assert source_text not in metrics


def test_hash_mismatch_fails_closed(tmp_path):
    module=load_exporter(); payload=module._load_registry(); payload["prompts"][0]["content_sha256"]="0"*64
    path=tmp_path/"registry.json"; path.write_text(json.dumps(payload),encoding="utf-8")
    metrics=module.render_metrics(registry_path=path)
    pid=payload["prompts"][0]["prompt_id"]
    assert f'jason_ai_prompt_source_hash_match{{prompt_id="{pid}"}} 0' in metrics
