from __future__ import annotations

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / 'openclaw_ed25519_rotation_proof.py'
spec = importlib.util.spec_from_file_location('openclaw_rotation_proof', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_active_key_ids_returns_only_active_records(tmp_path: Path) -> None:
    registry = tmp_path / 'registry.json'
    registry.write_text(
        json.dumps(
            {
                'version': 1,
                'keys': [
                    {'key_id': 'old', 'status': 'revoked'},
                    {'key_id': 'new', 'status': 'active'},
                    {'key_id': 'legacy'},
                ],
            }
        ),
        encoding='utf-8',
    )

    assert module.active_key_ids(registry) == ['legacy', 'new']


def test_test_envelope_binds_machine_identity_and_synthetic_capability() -> None:
    envelope = module.test_envelope('openclaw-gateway-2')

    assert envelope['key_id'] == 'openclaw-gateway-2'
    assert envelope['capability'] == 'jason.synthetic.health'
    assert envelope['requested_mode'] == 'observe'
    assert envelope['arguments']['rotation_proof'] is True
    assert envelope['principal']['principal_id'] == 'svc-openclaw-gateway'
    assert envelope['principal']['organization_id'] == 'aot'


def recursive_canonicalize(value):
    if isinstance(value, list):
        return [recursive_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {
            key: recursive_canonicalize(value[key])
            for key in sorted(value)
        }
    return value


def test_node_recursive_canonical_json_matches_transport_shape() -> None:
    envelope = module.test_envelope('openclaw-gateway-2')
    envelope['signature'] = 'ignored'

    body = {
        key: value
        for key, value in envelope.items()
        if key != 'signature'
    }

    node_equivalent = json.dumps(
        recursive_canonicalize(body),
        separators=(',', ':'),
        ensure_ascii=False,
    )

    python_transport_equivalent = json.dumps(
        body,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    )

    assert node_equivalent == python_transport_equivalent
