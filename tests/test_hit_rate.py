import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from hit_rate import close_window, row_for, stamp


class HitRateTests(unittest.TestCase):
    def test_group_worksheet_schema_is_scored_without_changing_view(self):
        run, _, _, _ = self.run_case("2026-11-27T12:00:00-05:00", offline=True)
        path = run / 'view.json'
        view = json.loads(path.read_text())
        view['view_time'] = view.pop('time')
        view['direction'] = 'more than the price'
        path.write_text(json.dumps(view))
        before = path.read_bytes()
        rows = [(datetime(2026, 11, 25).date(), 100), (datetime(2026, 11, 27).date(), 110)]
        with patch('hit_rate.closes.read', return_value=(rows, 'synthetic source')):
            fields, score = row_for(run, stamp('2026-11-30T17:00:00-05:00'))
        self.assertTrue(score)
        self.assertEqual(fields[3], 'up')
        self.assertEqual(before, path.read_bytes())
    def test_holiday_early_close_and_weekend(self):
        before, after = close_window(stamp("2026-11-25T17:00:00-05:00"))
        self.assertEqual(before.isoformat(), "2026-11-25T21:00:00+00:00")
        self.assertEqual(after.isoformat(), "2026-11-27T18:00:00+00:00")
        _, after = close_window(stamp("2026-11-27T13:00:00-05:00"))
        self.assertEqual(after.date().isoformat(), "2026-11-30")

    def test_requires_timezone(self):
        with self.assertRaises(ValueError):
            stamp("2026-11-25T17:00:00")

    def run_case(self, time, direction="up", offline=False, now="2026-11-30T17:00:00-05:00"):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        run = Path(folder.name)
        view = {"ticker": "ZZZZ", "filing_time": "2026-11-25T17:00:00-05:00",
                "time": time, "direction": direction}
        original = json.dumps(view).encode()
        (run / "view.json").write_bytes(original)
        prices = [(datetime(2026, 11, 25).date(), 100), (datetime(2026, 11, 27).date(), 110)]
        with patch("hit_rate.closes.read", return_value=(prices, "synthetic test")) as reader:
            fields, score = row_for(run, stamp(now), offline)
        self.assertEqual((run / "view.json").read_bytes(), original)
        return run, fields, score, reader

    def test_agreement_and_idempotent_reaction(self):
        run, fields, score, _ = self.run_case("2026-11-27T12:00:00-05:00")
        self.assertTrue(score)
        self.assertEqual(fields[4], "+10.0000% (up)")
        saved = (run / "reaction.json").read_bytes()
        with patch("hit_rate.closes.read", side_effect=AssertionError("must reuse saved reaction")):
            row_for(run, stamp("2026-12-01T17:00:00-05:00"))
        self.assertEqual((run / "reaction.json").read_bytes(), saved)

    def test_after_is_excluded(self):
        _, fields, score, _ = self.run_case("2026-11-27T13:00:01-05:00")
        self.assertEqual(fields[-1], "after")
        self.assertIsNone(score)

    def test_equal_time_is_not_after_and_wrong_direction_disagrees(self):
        _, fields, score, _ = self.run_case("2026-11-27T13:00:00-05:00", "down")
        self.assertEqual(fields[-1], "")
        self.assertFalse(score)

    def test_not_computed_is_excluded(self):
        _, _, score, _ = self.run_case(None, "not computed")
        self.assertIsNone(score)

    def test_future_close_and_offline_do_not_fetch(self):
        for offline, now in [(True, "2026-11-30T17:00:00-05:00"), (False, "2026-11-27T12:00:00-05:00")]:
            run, _, score, reader = self.run_case("2026-11-26T12:00:00-05:00", offline=offline, now=now)
            reader.assert_not_called()
            self.assertIsNone(score)
            self.assertFalse((run / "reaction.json").exists())

    def test_missing_session_price_does_not_substitute_later_day(self):
        run, _, _, _ = self.run_case(None, "not computed", offline=True)
        with patch("hit_rate.closes.read", return_value=([], "")):
            _, score = row_for(run, stamp("2026-11-30T17:00:00-05:00"))
        self.assertIsNone(score)
        self.assertFalse((run / "reaction.json").exists())
