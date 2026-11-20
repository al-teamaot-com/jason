import json
import unittest
from dataclasses import replace
from implementation.shared_sessions.companion_protocol import CompanionFrame,FrameReplayGuard

class CompanionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.f=CompanionFrame(1,'propose','tenant','client','claw2-uid','session','msg-1',1,'a'*64,{'classification':'read_only'})

    def test_exact_roundtrip_and_replay(self):
        frame=CompanionFrame.parse(self.f.encode())
        guard=FrameReplayGuard()
        self.assertTrue(guard.accept(frame,authenticated_tenant='tenant',authenticated_device='claw2-uid'))
        self.assertFalse(guard.accept(frame,authenticated_tenant='tenant',authenticated_device='claw2-uid'))
        next_frame=replace(frame,message_id='msg-2',sequence=2)
        self.assertFalse(FrameReplayGuard().accept(next_frame,authenticated_tenant='another',authenticated_device='claw2-uid'))
        self.assertTrue(guard.accept(next_frame,authenticated_tenant='tenant',authenticated_device='claw2-uid'))
        self.assertFalse(guard.accept(replace(next_frame,message_id='msg-3',sequence=1),authenticated_tenant='tenant',authenticated_device='claw2-uid'))

    def test_unknown_fields_and_raw_command_rejected(self):
        original=json.loads(self.f.encode())
        for patch in ({'unknown':1},{'sequence':True},{'version':False},{'payload':{'command':'Get-Process'}},
                      {'payload':{'secret':'password'}},{'command_digest':'bogus'}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                CompanionFrame.parse(json.dumps(original|patch).encode())

    def test_size_limit_and_malformed(self):
        for raw in (b'',b'not json',b'{' + b'a'*65536):
            with self.assertRaises(ValueError):
                CompanionFrame.parse(raw)
