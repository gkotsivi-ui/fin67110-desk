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

    # 2026-11-23: layouts from Workday's, NVIDIA's, Analog Devices', Dell's, Dollar Tree's and HP Inc.'s filings, which the
    # worksheet's statements.py now reads. Workday's and NVIDIA's amounts are their 10-Ks'.
    def test_workdays_month_and_day_before_its_years(self):
        workday = ["CONSOLIDATED STATEMENTS OF CASH FLOWS", "(in millions)", "Year Ended January 31,", "2026", "2025", "2024",
                   "Net income", "$", "693", "$", "526", "$", "1,381", "Capital expenditures", "(162)", "(269)", "(232)"]
        line = workday.index("Capital expenditures") + 1
        cite = f"[10-K.txt:L{line}] section CONSOLIDATED STATEMENTS OF CASH FLOWS; year ended 2025-01-31; units 1e+06; Capital expenditures = -2.69e+08; spending = -(-2.69e+08) = 2.69e+08"
        self.assertEqual(self.check(workday, cite).errors, {})
        self.assertTrue(self.check(workday, cite.replace("-2.69e+08", "-1.62e+08")).errors)

    def test_nvidias_abbreviated_months(self):
        nvidia = ["Consolidated Statements of Income", "(In millions, except per share data)", "Year Ended", "Jan 25, 2026", "Jan 26, 2025",
                  "Jan 28, 2024", "Net income", "$", "120,067", "$", "72,880", "$", "29,760"]
        cite = "[10-K.txt:L7] section Consolidated Statements of Income; year ended 2025-01-26; units 1e+06; Net income = 7.288e+10"
        self.assertEqual(self.check(nvidia, cite).errors, {})
        self.assertTrue(self.check(nvidia, cite.replace("2025-01-26", "2025-01-25")).errors)

    def test_amounts_in_bare_thousands(self):
        adi = ["Consolidated Statements of Cash Flows", "Years ended November 1, 2025, November 2, 2024 and October 28, 2023", "(thousands)",
               "2025", "2024", "2023", "Depreciation and amortization", "$", "800,000", "$", "700,000", "$", "600,000"]
        cite = "[10-K.txt:L7] section Consolidated Statements of Cash Flows; year ended 2025-11-01; units 1000; Depreciation and amortization = 8e+08"
        self.assertEqual(self.check(adi, cite).errors, {})
        self.assertTrue(self.check(adi, cite.replace("units 1000", "units 1").replace("8e+08", "800000")).errors)

    def test_dells_total_on_its_dated_line(self):
        filing = ["As of September 1, 2026, there were 635,812,750 shares of the registrant’s common stock outstanding, consisting of",
                  "354,000,000", "outstanding shares of Class C Common Stock,"]
        cite = ("[10-K.txt:L1] section Cover page; as of 2026-09-01; quote: As of September 1, 2026, there were 635,812,750 shares of the "
                "registrant’s common stock outstanding, consisting of; shares: ")
        self.assertEqual(self.check(filing, cite + "635,812,750").errors, {})
        self.assertTrue(self.check(filing, cite + "354,000,000").errors)

    def test_count_on_the_line_after_the_dated_line(self):
        dollar_tree = ["As of August 25, 2026, there were", "187,630,299", "shares of the registrant’s common stock outstanding."]
        cite = "[10-K.txt:L1] section Cover page; as of 2026-08-25; quote: As of August 25, 2026, there were; shares: "
        self.assertEqual(self.check(dollar_tree, cite + "187,630,299").errors, {})
        self.assertTrue(self.check(dollar_tree, cite + "187,630,298").errors)
        hp = ["The number of shares of HP Inc. common stock outstanding as of August 19, 2026 was", "901,790,969"]
        cite = ("[10-K.txt:L1] section Cover page; as of 2026-08-19; quote: The number of shares of HP Inc. common stock outstanding as of "
                "August 19, 2026 was; shares: 901,790,969")
        self.assertEqual(self.check(hp, cite).errors, {})
        self.assertTrue(self.check(hp, cite.replace("as of 2026-08-19", "as of 2026-08-20")).errors)

    def test_the_hook_and_the_worksheet_read_the_same_column_dates(self):
        import importlib.util
        path = Path(__file__).resolve().parents[2] / "skills" / "spinoff-worksheet" / "scripts" / "statements.py"
        spec = importlib.util.spec_from_file_location("statements_for_hook_test", path)
        statements = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(statements)
        from worksheet_format import column_dates
        for intro in ("Fiscal Years Ended January 31, (Amounts in millions) 2026 2025 2024", "(in millions) Year Ended January 31, 2026 2025 2024",
                      "(In millions) Year Ended Jan 25, 2026 Jan 26, 2025 Jan 28, 2024", "Years Ended December 31, 2025, 2024 and 2023",
                      "Years ended November 1, 2025, November 2, 2024 and October 28, 2023", "Fiscal Year Ended January 30, 2026 January 31, 2025 February 2, 2024",
                      "(In millions, except per share data)", "Sept. 30, 2025 Sept. 30, 2024"):
            self.assertEqual(column_dates(intro), statements.period_dates(intro), intro)


if __name__ == "__main__":
    unittest.main()
