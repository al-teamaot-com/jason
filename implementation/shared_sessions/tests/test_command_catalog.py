import unittest
from hashlib import sha256
from implementation.shared_sessions.command_catalog import get_reviewed_command

class ReviewedCommandsTests(unittest.TestCase):
    def test_known_diagnostics_bounded(self):
        for name in ('powershell.version','host.identity','host.os','host.utc'):
            cmd = get_reviewed_command(name)
            self.assertEqual(cmd.classification,'read_only')
            self.assertTrue(0 < cmd.max_runtime_seconds <= 10)
            self.assertTrue(0 < cmd.max_output_bytes <= 4096)
            self.assertEqual(cmd.digest,sha256(cmd.script.encode()).hexdigest())

    def test_injection_and_unreviewed_commands_denied(self):
        for name in ('pwsh -Command echo', 'host.utc; rm -rf /', 'powershell.version;Get-Process', None, 3, '', 'Get-Service'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                get_reviewed_command(name)
