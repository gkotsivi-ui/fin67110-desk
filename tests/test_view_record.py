"""Synthetic prediction records: code time, explicit window, and immutable first view."""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest


class ViewRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        (self.run / 'filing_time.json').write_text(json.dumps({
            'edgar_accepted': '2026-11-25 17:00:00',
            'effective_filed_eastern': '2026-11-25T17:00:00-05:00'}),encoding='utf-8')

    def test_explicit_prediction_and_actual_save_time(self):
        from view_record import freeze_view
        now = datetime.fromisoformat('2026-11-27T12:00:00-05:00')
        saved = freeze_view(self.run, 'EXM', 'more than the price', clock=lambda: now)
        self.assertEqual(saved['direction'], 'up')
        self.assertEqual(saved['time'], now.isoformat())
        self.assertEqual(saved['view_time'], saved['time'])
        self.assertEqual(saved['filing_time'], '2026-11-25T17:00:00-05:00')
        self.assertEqual(saved['reaction_window']['first_close_after_filing_time'], '2026-11-27T13:00:00-05:00')
        self.assertEqual(saved['reaction_window']['baseline_close_time'], '2026-11-25T16:00:00-05:00')

    def test_first_prediction_content_and_file_time_never_change(self):
        from view_record import freeze_view
        first = datetime.fromisoformat('2026-11-26T09:00:00-05:00')
        a = freeze_view(self.run, 'EXM', 'down', clock=lambda: first)
        path = self.run / 'view.json'
        before = path.read_bytes(), path.stat().st_mtime_ns
        b = freeze_view(self.run, 'EXM', 'up', clock=lambda: datetime.now().astimezone())
        self.assertEqual(a, b)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_missing_filing_is_not_computed_and_never_guessed(self):
        from view_record import freeze_view
        (self.run / 'filing_time.json').unlink()
        saved = freeze_view(self.run, 'EXM', 'up')
        self.assertEqual(saved['direction'], 'not computed')
        self.assertIsNone(saved['filing_time'])
        self.assertTrue(saved['time'])

    def test_override_does_not_replace_actual_filing_acceptance(self):
        from view_record import freeze_view
        (self.run / 'filing_time.json').write_text(json.dumps({
            'edgar_accepted': '2026-11-25 17:00:00',
            'effective_filed_eastern': '2026-11-26T12:00:00-05:00',
            'filed_override': '2026-11-26T12:00:00'}),encoding='utf-8')
        saved = freeze_view(self.run, 'EXM', 'flat')
        self.assertEqual(saved['filing_time'], '2026-11-25T17:00:00-05:00')

    def test_no_backfill_for_historical_worksheet(self):
        from view_record import freeze_view
        (self.run / 'Spinoff worksheet, previous.json').write_text(json.dumps({'view': {'direction': 'not computed'}}), encoding='utf-8')
        self.assertIsNone(freeze_view(self.run, 'EXM', 'up'))
        self.assertFalse((self.run / 'view.json').exists())

    def test_clock_requires_a_utc_offset(self):
        from view_record import freeze_view
        with self.assertRaises(ValueError):
            freeze_view(self.run, 'EXM', 'up', clock=lambda: datetime(2026, 11, 26))
