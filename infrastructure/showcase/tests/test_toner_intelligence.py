import importlib.util
import unittest
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODULE = Path(__file__).parents[2] / 'toner-intelligence' / 'toner_intelligence.py'
spec = importlib.util.spec_from_file_location('toner_intelligence', MODULE)
ti = importlib.util.module_from_spec(spec); sys.modules[spec.name]=ti; spec.loader.exec_module(ti)


def r(day, level):
    return ti.Reading(datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=day), level)


class TonerIntelligenceTests(unittest.TestCase):
    def test_detects_probable_replacement(self):
        events = ti.detect_replacements([r(0,12),r(1,8),r(2,4),r(3,100)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].confidence, 'high')

    def test_does_not_call_midlevel_jump_replacement(self):
        self.assertEqual(ti.detect_replacements([r(0,48),r(1,100)]), [])

    def test_ship_today_from_depletion_forecast(self):
        readings=[r(i,20-2*i) for i in range(8)]
        result=ti.forecast(readings)
        self.assertEqual(result.action,'ship_today')
        self.assertTrue(2.5 <= result.days_remaining <= 3.5)

    def test_customer_seasonality_changes_decision(self):
        readings=[r(i,23-i) for i in range(8)]
        self.assertEqual(ti.forecast(readings,0.5).action,'watch')
        self.assertEqual(ti.forecast(readings,4.0).action,'ship_today')

    def test_current_telemetry(self):
        self.assertEqual(ti.classify_telemetry(0,0,0.1)[0], 'current')

    def test_one_missed_run_is_stale(self):
        self.assertEqual(ti.classify_telemetry(1,1,1.2)[0], 'stale')

    def test_two_missed_runs_is_not_reporting(self):
        self.assertEqual(ti.classify_telemetry(2,2,2.2)[0], 'not_reporting')

    def test_long_missing_wins(self):
        self.assertEqual(ti.classify_telemetry(1,1,8.0)[0], 'long_term_missing')

    def test_toner_can_be_stale_while_device_is_current(self):
        self.assertEqual(ti.classify_telemetry(0,1,1.0)[0], 'toner_stale')

    def test_stale_telemetry_blocks_shipping_recommendation(self):
        action, reason = ti.apply_safety_gates('ship_today','projected depletion','stale','device missed latest run','Company A','TK-1')
        self.assertEqual(action, 'needs_review')
        self.assertIn('missed', reason)

    def test_missing_customer_blocks_shipping_recommendation(self):
        action, _ = ti.apply_safety_gates('ship_today','projected depletion','current','ok','','TK-1')
        self.assertEqual(action, 'needs_review')


if __name__ == '__main__':
    unittest.main()
