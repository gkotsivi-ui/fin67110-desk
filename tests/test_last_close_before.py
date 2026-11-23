"""closes_reader.last_close_before on made-up closes: the most recent close strictly before the filing time.

Proposed by the mutation audit of 2026-11-22. No network: daily_closes is a stand-in.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import closes_reader as c

ROWS = [{'date': day, 'close': price, 'close_time': day + 'T16:00:00-05:00', 'source': 'made up'}
        for day, price in (('2026-01-05', 10.0), ('2026-01-06', 11.0), ('2026-01-07', 12.0))]


def close(filed, keep_window=True):
    def fetch(ticker, start, end, **kwargs):
        kept = [row for row in ROWS if not keep_window or start <= row['date'] <= end]
        return kept or c.NOT_AVAILABLE
    with patch.object(c, 'daily_closes', side_effect=fetch):
        return c.last_close_before('ZZZ', filed)


class LastCloseBefore(unittest.TestCase):
    def test_the_most_recent_close_not_the_oldest(self):
        self.assertEqual(close('2026-01-07T12:00:00')['close'], 11.0)

    def test_a_filing_after_the_close_uses_that_days_close(self):
        self.assertEqual(close('2026-01-06T16:05:00')['close'], 11.0)

    def test_a_filing_at_the_close_does_not_use_that_days_close(self):
        self.assertEqual(close('2026-01-06T16:00:00')['close'], 10.0)

    def test_a_close_at_the_filing_instant_is_refused_even_when_the_reader_returns_it(self):
        self.assertEqual(close('2026-01-06T16:00:00', keep_window=False)['close'], 10.0)

    def test_no_close_before_the_filing_is_not_available(self):
        self.assertEqual(close('2026-01-05T09:00:00'), c.NOT_AVAILABLE)


if __name__ == '__main__':
    unittest.main()
