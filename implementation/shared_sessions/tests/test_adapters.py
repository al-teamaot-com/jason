import unittest
from implementation.shared_sessions.adapters import AdapterCapabilities, AdapterRegistry

class AdapterRegistryTests(unittest.TestCase):
    def make(self, **kw):
        fields = dict(transport_id='ssh', target_kind='network-switch',
                      supported_session_modes=frozenset({'guided'}),
                      supports_live_input=False, supports_output_stream=True,
                      supports_cancel=True, execution_identity='governed-service',
                      max_output_bytes=32768, session_expiry_seconds=300)
        fields.update(kw)
        return AdapterCapabilities(**fields)

    def test_registry_is_explicit_not_implicit_authority(self):
        registry = AdapterRegistry()
        with self.assertRaises(ValueError):
            registry.lookup('ssh')
        descriptor = self.make()
        registry.register(descriptor)
        self.assertEqual(registry.lookup('ssh'), descriptor)
        with self.assertRaises(ValueError):
            registry.register(descriptor)
        self.assertFalse(hasattr(registry, 'execute'))

    def test_untrusted_or_invalid_descriptors_rejected(self):
        for kwargs in ({'transport_id':'unreviewed'}, {'execution_identity':''},
                       {'supported_session_modes':frozenset({'unknown'})},
                       {'session_expiry_seconds':3601}, {'max_output_bytes':-1},
                       {'supports_cancel':1}, {'target_kind':''}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.make(**kwargs)
