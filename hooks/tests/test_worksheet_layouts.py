"""Statement and cover-page layouts the hook must read as the worksheet's parser does.

The layouts copy Lowe's and Walmart's 10-Ks (read on 2026-11-20): Lowe's "Statements of Earnings" with a "% Sales"
figure after each amount and "OUTSTANDING AT 3/19/2026" above its share count; Walmart's "Fiscal Years Ended
January 31," above columns of years and "N / shares of common stock outstanding as of ...". The amounts are the
filings' own where a test checks them.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worksheet_format import WorksheetFormat

LOWES = ["Consolidated Statements of Earnings", "(In millions, except per share and percentage data)", "Fiscal Years Ended",
         "January 30, 2026", "January 31, 2025", "February 2, 2024", "Current Earnings", "Amount", "% Sales", "Amount", "% Sales",
         "Amount", "% Sales", "Net sales", "$", "86,286", "100.00", "%", "$", "83,674", "100.00", "%", "$", "86,377", "100.00", "%",
         "Net earnings", "$", "6,654", "7.71", "$", "6,957", "8.31", "$", "7,726", "8.94"]
WALMART = ["Consolidated Statements of Income", "Fiscal Years Ended January 31,", "(Amounts in millions, except per share data)",
           "2026", "2025", "2024", "Revenues:", "Net sales", "$", "706,413", "$", "674,538", "$", "642,637",
           "Consolidated net income attributable to Walmart", "$", "21,893", "$", "19,436", "$", "15,511"]


class Layouts(unittest.TestCase):
    def check(self, filing, citation):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run = Path(tmp.name)
        (run / "10-K.txt").write_text("\n".join(filing), encoding="utf-8")
        audit = WorksheetFormat(run, run, run / "w.md", "")
        audit.read_sources(1, citation)
        return audit

    def test_lowes_earnings_statement_with_percentages_of_sales(self):
        line = LOWES.index("Net earnings") + 1
        good = self.check(LOWES, f"[10-K.txt:L{line}] section Consolidated Statements of Earnings; year ended 2025-01-31; units 1e+06; Net earnings = 6.957e+09")
        self.assertEqual((good.errors, [s["value"] for s in good.sources.values()]), ({}, [6957000000]))
        wrong = self.check(LOWES, f"[10-K.txt:L{line}] section Consolidated Statements of Earnings; year ended 2025-01-31; units 1e+06; Net earnings = 8.31e+06")
        self.assertTrue(wrong.errors)

    def test_walmart_years_under_one_month_and_day(self):
        line = WALMART.index("Consolidated net income attributable to Walmart") + 1
        good = self.check(WALMART, f"[10-K.txt:L{line}] section Consolidated Statements of Income; year ended 2026-01-31; units 1e+06; "
                                   "Consolidated net income attributable to Walmart = 2.1893e+10")
        self.assertEqual(good.errors, {})
        wrong = self.check(WALMART, f"[10-K.txt:L{line}] section Consolidated Statements of Income; year ended 2026-01-30; units 1e+06; "
                                    "Consolidated net income attributable to Walmart = 2.1893e+10")
        self.assertTrue(wrong.errors)

    def test_walmart_count_before_its_dated_line(self):
        filing = ["The registrant had", "7,972,402,501", "shares of common stock outstanding as of March 11, 2026."]
        cite = "[10-K.txt:L3] section Cover page; as of 2026-03-11; quote: shares of common stock outstanding as of March 11, 2026.; shares: "
        self.assertEqual(self.check(filing, cite + "7,972,402,501").errors, {})
        self.assertTrue(self.check(filing, cite + "7,972,402,502").errors)

    def test_lowes_count_under_its_dated_heading(self):
        filing = ["CLASS", "OUTSTANDING AT 3/19/2026", "Common Stock, $0.50 par value", "560,063,429"]
        self.assertEqual(self.check(filing, "[10-K.txt:L2] section Cover page; as of 2026-03-19; quote: OUTSTANDING AT 3/19/2026; shares: 560,063,429").errors, {})
        self.assertTrue(self.check(filing, "[10-K.txt:L2] section Cover page; as of 2026-03-18; quote: OUTSTANDING AT 3/19/2026; shares: 560,063,429").errors)


if __name__ == "__main__":
    unittest.main()
