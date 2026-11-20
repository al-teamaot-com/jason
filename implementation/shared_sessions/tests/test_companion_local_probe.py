import unittest
from unittest.mock import MagicMock,patch
from hashlib import sha256
from implementation.shared_sessions.companion_local_probe import Claw2LocalProbe,CLAW2_DATTO_UID
from implementation.shared_sessions.command_catalog import get_reviewed_command
from implementation.shared_sessions.grants import GrantScope

class LocalProbeTests(unittest.TestCase):
    def setUp(self):
        self.grant=MagicMock()
        self.grant.consume.return_value=True
        self.scope=GrantScope('aot','aot','13eda165-08e0-ec79-026a-985b37e2eb9e','tech','ticket','companion',
                              get_reviewed_command('powershell.version').digest)

    @patch('implementation.shared_sessions.companion_local_probe.subprocess.run')
    def test_disabled_by_default(self,run):
        result=Claw2LocalProbe(grant_verifier=self.grant).execute_reviewed_test(
            scope=self.scope,token='x',command_id='powershell.version')
        self.assertFalse(result.attempted)
        run.assert_not_called()
        self.grant.consume.assert_not_called()

    @patch('implementation.shared_sessions.companion_local_probe.subprocess.run')
    @patch('implementation.shared_sessions.companion_local_probe.socket.gethostname',return_value='Claw2-PC')
    def test_exact_target_and_grant_only(self,host,run):
        run.return_value=MagicMock(stdout=b'7.5',stderr=b'',returncode=0)
        probe=Claw2LocalProbe(grant_verifier=self.grant,enabled=True)
        result=probe.execute_reviewed_test(scope=self.scope,token='grant',command_id='powershell.version')
        self.assertTrue(result.completed)
        self.assertEqual(result.stdout,'7.5')
        self.assertEqual(run.call_args.kwargs['timeout'],10)
        self.assertEqual(run.call_args.args[0][-1],get_reviewed_command('powershell.version').script)
        self.assertNotIn('shell',run.call_args.kwargs)

    @patch('implementation.shared_sessions.companion_local_probe.subprocess.run')
    @patch('implementation.shared_sessions.companion_local_probe.socket.gethostname',return_value='jason-prod')
    def test_never_run_on_wrong_host(self,host,run):
        result=Claw2LocalProbe(grant_verifier=self.grant,enabled=True).execute_reviewed_test(
            scope=self.scope,token='x',command_id='powershell.version')
        self.assertFalse(result.attempted)
        run.assert_not_called()

    @patch('implementation.shared_sessions.companion_local_probe.subprocess.run')
    @patch('implementation.shared_sessions.companion_local_probe.socket.gethostname',return_value='Claw2-PC')
    def test_unknown_or_wrong_digest_and_denied_grant(self,host,run):
        probe=Claw2LocalProbe(grant_verifier=self.grant,enabled=True)
        for name in ('Remove-Item','host.identity'):
            self.assertFalse(probe.execute_reviewed_test(scope=self.scope,token='x',command_id=name).attempted)
        self.grant.consume.return_value=False
        self.assertFalse(probe.execute_reviewed_test(scope=self.scope,token='x',command_id='powershell.version').attempted)
        run.assert_not_called()
