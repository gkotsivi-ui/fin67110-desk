"""Offline tests of the release reader: made-up earnings releases in the layouts that real ones use.

Each layout below was seen in a real release on 2026-11-11; the names and the numbers are made up.
Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import release  # noqa: E402
from release import amounts_in, read_quarter  # noqa: E402

HEADING = "UNAUDITED CONSOLIDATED CONDENSED STATEMENTS OF OPERATIONS"
TWO_PERIODS = "Three Months Ended | Nine Months Ended"
FOUR_DATES = "(In millions, except per share amounts) | July 26, 2026 | July 27, 2025 | July 26, 2026 | July 27, 2025"
PER_SHARE_ROWS = [
    "Earnings per share:",
    "Basic | $3.19 | $2.24 | $9.28 | $6.33",
    "Diluted | $3.17 | $2.22 | $9.22 | $6.29",
    "Weighted average number of shares:",
    "Basic | 78 | 80 | 75 | 82",
    "Diluted | 79 | 81 | 76 | 83",
]
# An outlook table above the statement, with a "Total revenue" row of its own: a midpoint and a range.
OUTLOOK = ["Business Outlook", "Total revenue | $1,250 | +/- | $50", "Non-GAAP diluted EPS | $3.40 | +/- | $0.20"]
STATEMENT = [HEADING, TWO_PERIODS, FOUR_DATES, "Revenue | $1,115 | $902 | $3,037 | $2,568", "Cost of products sold | 529 | 440 | 1,469 | 1,225",
             "Gross profit | 586 | 462 | 1,568 | 1,343", "Net income | $250 | $180 | $700 | $520", *PER_SHARE_ROWS]
BALANCE_SHEET = ["UNAUDITED CONSOLIDATED CONDENSED BALANCE SHEETS", "Total revenue | 9 | 9"]


def statement(header: list[str], rows: list[str]) -> list[str]:
    return [HEADING, *header, *rows]


class TheIncomeStatement(unittest.TestCase):
    def test_an_outlook_table_is_not_the_income_statement(self) -> None:
        # Found on a real release on 2026-11-11: the desk read guidance as the quarter's revenue.
        q = read_quarter(["Example Corp reports third quarter results", *OUTLOOK, *STATEMENT, *BALANCE_SHEET])
        self.assertEqual((q["revenue"], q["revenue_prior"]), (1115.0, 902.0))
        self.assertAlmostEqual(q["revenue_growth"], 1115 / 902 - 1)
        self.assertEqual((q["revenue_shown"], q["revenue_prior_shown"]), ("1,115", "902"))
        self.assertEqual((q["period"], q["prior_period"], q["units"]), ("July 26, 2026", "July 27, 2025", "millions"))
        self.assertEqual((q["eps"], q["eps_prior"], q["eps_shown"]), (3.17, 2.22, "$3.17"))
        self.assertEqual((q["revenue_line"], q["eps_line"], q["eps_heading"]),
                         ("Revenue | $1,115 | $902 | $3,037 | $2,568", "Diluted | $3.17 | $2.22 | $9.22 | $6.29", "Earnings per share:"))
        self.assertEqual(q["revenue_headers"], [HEADING, TWO_PERIODS, FOUR_DATES])
        self.assertEqual(q["why"], {})

    def test_a_release_with_no_income_statement_states_nothing(self) -> None:
        q = read_quarter(["Example Corp reports results", *OUTLOOK, "Revenue grew in the quarter."])
        self.assertIsNone(q.get("revenue"))
        self.assertEqual(set(q["why"]), {"revenue", "growth", "eps"})
        self.assertIn("no income statement", q["why"]["revenue"])

    def test_an_adjusted_statement_is_not_the_income_statement(self) -> None:
        adjusted = ["NON-GAAP ADJUSTED STATEMENTS OF OPERATIONS", TWO_PERIODS, FOUR_DATES, "Revenue | $1,200 | $950 | $3,100 | $2,600",
                    "Earnings per share:", "Diluted | $4.00 | $3.00 | $11.00 | $8.00"]
        q = read_quarter([*adjusted, *STATEMENT])
        self.assertEqual((q["revenue"], q["eps"]), (1115.0, 3.17))

    def test_a_line_that_only_names_the_statement_is_not_the_statement(self) -> None:
        contents = ["Consolidated Statements of Operations", "Consolidated Balance Sheets", "Consolidated Statements of Cash Flows",
                    "(1) Refer to the Consolidated Statements of Operations herein."]
        q = read_quarter([*contents, *STATEMENT])
        self.assertEqual(q["revenue"], 1115.0)

    def test_the_total_row_when_revenue_has_parts(self) -> None:
        rows = ["Net revenue:", "Products | $900 | $700 | $2,400 | $1,900", "Services | 215 | 202 | 637 | 668",
                "Total net revenue | 1,115 | 902 | 3,037 | 2,568", "Cost of net revenue:", "Total cost of net revenue | 529 | 440 | 1,469 | 1,225"]
        q = read_quarter(statement([TWO_PERIODS, FOUR_DATES], rows + PER_SHARE_ROWS))
        self.assertEqual((q["revenue_line"], q["revenue"]), ("Total net revenue | 1,115 | 902 | 3,037 | 2,568", 1115.0))

    def test_one_kind_of_revenue_and_a_selling_cost_are_not_total_revenue(self) -> None:
        rows = ["Product revenue | $900 | $700 | $2,400 | $1,900", "Sales and marketing | 215 | 202 | 637 | 668"]
        q = read_quarter(statement([TWO_PERIODS, FOUR_DATES], rows + PER_SHARE_ROWS))
        self.assertIsNone(q.get("revenue"))
        self.assertIn("no income statement", q["why"]["revenue"])


class TheColumns(unittest.TestCase):
    """A column is chosen by its date, never by its position."""

    def read(self, header: list[str], revenue: str, per_share: str = "Diluted | $1.00 | $0.90 | $0.80") -> dict:
        return read_quarter(statement(header, [revenue, "Earnings per share:", per_share]))

    def test_this_quarter_then_last_quarter_then_last_years_quarter(self) -> None:
        q = self.read(["Three Months Ended", "October 25, 2026 | July 26, 2026 | October 26, 2025"], "Revenue | 500 | 480 | 400")
        self.assertEqual((q["revenue"], q["revenue_prior"], q["prior_period"]), (500.0, 400.0, "October 26, 2025"))
        self.assertEqual((q["eps"], q["eps_prior"]), (1.00, 0.80))

    def test_last_year_in_the_first_column(self) -> None:
        q = self.read(["Three Months Ended September 30,", "2025 | 2026"], "Revenue | 400 | 500", "Diluted | $0.80 | $1.00")
        self.assertEqual((q["revenue"], q["revenue_prior"], q["period"], q["prior_period"]), (500.0, 400.0, "2026", "2025"))
        self.assertEqual((q["eps"], q["eps_prior"]), (1.00, 0.80))

    def test_years_alone_under_the_periods(self) -> None:
        header = ["(In millions, except per share amounts)", "(Unaudited)", "Three Months Ended September 30, | Nine Months Ended September 30,", "2026 | 2025 | 2026 | 2025"]
        q = self.read(header, "Revenue | $646 | $512 | $1,817 | $1,410", "Diluted | $3.83 | $1.05 | $20.44 | $14.62")
        self.assertEqual((q["revenue"], q["revenue_prior"], q["eps"], q["eps_prior"]), (646.0, 512.0, 3.83, 1.05))

    def test_the_years_beside_the_period_on_one_line(self) -> None:
        q = self.read(["Three Months Ended September 30, | 2026 | 2025"], "Total revenue | 92,279 | 77,673", "Diluted | $4.92 | $3.72")
        self.assertEqual((q["revenue"], q["revenue_prior"]), (92279.0, 77673.0))

    def test_a_quarter_of_53_weeks_beside_one_of_52(self) -> None:
        q = self.read(["First Quarters Ended", "October 3, 2026 | September 27, 2025"], "Net revenues | $253,153 | $225,209", "Diluted net earnings (loss) per share | $0.21 | $(0.21)")
        self.assertEqual((q["revenue"], q["revenue_prior"], q["eps"], q["eps_prior"]), (253153.0, 225209.0, 0.21, -0.21))

    def test_a_change_column_in_percent_is_not_a_figure(self) -> None:
        header = ["Three Months Ended | Six Months Ended", "July 31, 2026 | August 1, 2025 | Change | July 31, 2026 | August 1, 2025 | Change"]
        q = self.read(header, "Total net revenue | 46,971 | 29,776 | 58% | 90,813 | 53,154 | 71%", "Diluted | $6.34 | $1.70 | 273% | $11.58 | $3.07 | 277%")
        self.assertEqual((q["revenue"], q["revenue_prior"], q["eps"], q["eps_prior"]), (46971.0, 29776.0, 6.34, 1.70))

    def test_no_column_for_last_years_quarter(self) -> None:
        q = self.read(["Three Months Ended", "October 25, 2026 | July 26, 2026"], "Revenue | 500 | 480", "Diluted | $1.00 | $0.90")
        self.assertEqual((q["revenue"], q["eps"]), (500.0, 1.00))
        self.assertIsNone(q.get("revenue_growth"))
        self.assertIsNone(q.get("eps_prior"))
        self.assertIn("one year before", q["why"]["growth"])

    def test_a_statement_whose_first_period_is_not_a_quarter(self) -> None:
        for header in (["Year Ended December 31,", "2026 | 2025"], ["Nine Months Ended | Three Months Ended", "July 26, 2026 | July 27, 2025 | July 26, 2026 | July 27, 2025"],
                       ["52 Weeks Ended", "August 30, 2026 | August 31, 2025"]):
            q = read_quarter(statement(header, ["Revenue | 500 | 400" + (" | 500 | 400" if len(header[1]) > 40 else "")]))
            self.assertIsNone(q.get("revenue"), header)
            self.assertIn("not a quarter", q["why"]["revenue"])

    def test_the_weeks_of_a_quarter(self) -> None:
        for weeks in ("12 Weeks Ended", "16 Weeks Ended", "Thirteen Weeks Ended"):
            self.assertEqual(self.read([weeks, "August 30, 2026 | August 31, 2025"], "Total revenue | 500 | 400", "Diluted | $1.00 | $0.80")["revenue"], 500.0, weeks)

    def test_a_header_that_names_no_period_or_gives_no_dates(self) -> None:
        self.assertIn("does not name its periods", self.read(["2026 | 2025"], "Revenue | 500 | 400")["why"]["revenue"])
        self.assertIn("one date for each column", self.read(["Three Months Ended"], "Revenue | 500 | 400")["why"]["revenue"])

    def test_figures_and_dates_that_do_not_line_up(self) -> None:
        q = self.read(["Three Months Ended", "October 25, 2026 | October 26, 2025"], "Revenue | 500 | 480 | 400")
        self.assertIsNone(q.get("revenue"))
        q = self.read(["Three Months Ended", "October 25, 2026 | October 26, 2025"], "Revenue | 500 | 400", "Diluted | $1.00")
        self.assertEqual(q["revenue"], 500.0)
        self.assertIn("one figure for each column", q["why"]["eps"])

    def test_the_units_come_from_the_statements_header(self) -> None:
        dates = "October 3, 2026 | September 27, 2025"
        self.assertEqual(self.read(["(unaudited, in thousands, except share and per share amounts)", "Three Months Ended", dates], "Revenue | $ 344,441 | $ 287,900")["units"], "thousands")
        self.assertEqual(self.read(["Three Months Ended", dates], "Revenue | 500 | 400")["units"], "")


class DilutedEps(unittest.TestCase):
    HEADER = [TWO_PERIODS, FOUR_DATES]
    REVENUE = "Revenue | $727 | $703 | $2,217 | $2,108"

    def eps(self, rows: list[str]) -> dict:
        return read_quarter(statement(self.HEADER, [self.REVENUE, *rows]))

    def test_eps_for_the_whole_company_not_for_continuing_operations(self) -> None:
        # Found on a real release on 2026-11-11: the desk read the continuing-operations row as the quarter's EPS.
        q = self.eps(["Diluted earnings (loss) per share from continuing operations | $0.14 | $0.49 | $0.88 | $(5.05)",
                      "Diluted earnings (loss) per share from discontinued operations | (0.06) | 0.36 | (0.11) | 0.43",
                      "Diluted earnings (loss) per share attributable to common shareholders | $0.08 | $0.85 | $0.77 | $(4.62)"])
        self.assertEqual((q["eps"], q["eps_prior"], q["eps_shown"]), (0.08, 0.85, "$0.08"))

    def test_only_a_continuing_operations_row_states_nothing(self) -> None:
        q = self.eps(["Diluted earnings per share from continuing operations | $0.14 | $0.49 | $0.88 | $0.95"])
        self.assertIsNone(q.get("eps"))
        self.assertIn("continuing", q["why"]["eps"])
        self.assertEqual(q["revenue"], 727.0)

    def test_a_heading_for_continuing_operations_above_a_plain_row(self) -> None:
        q = self.eps(["Income per share from continuing operations:", "Diluted | $0.14 | $0.49 | $0.88 | $0.95",
                      "Net income per share:", "Diluted | $0.08 | $0.85 | $0.77 | $0.90"])
        self.assertEqual(q["eps"], 0.08)

    def test_a_row_that_ends_with_the_word_diluted_and_a_loss(self) -> None:
        q = self.eps(["Net loss per share attributable to common stockholders, diluted | $(1.27) | $(0.22) | $(3.80) | $(1.87)"])
        self.assertEqual((q["eps"], q["eps_prior"], q["eps_shown"], q["eps_prior_shown"]), (-1.27, -0.22, "$(1.27)", "$(0.22)"))

    def test_a_space_between_the_dollar_sign_and_the_figure(self) -> None:
        q = self.eps(["(Loss) earnings per share:", "Basic | $ (0.04) | $ (0.31) | $ 0.75 | $ (0.51)", "Diluted | $ (0.04) | $ (0.31) | $ 0.73 | $ (0.51)",
                      "Weighted-average shares used in computing (loss) earnings per share:", "Diluted | 118,312,116 | 120,598,219 | 122,305,404 | 120,753,102"])
        self.assertEqual((q["eps"], q["eps_prior"], q["eps_shown"]), (-0.04, -0.31, "$(0.04)"))

    def test_a_count_of_shares_is_not_eps(self) -> None:
        q = self.eps(["Shares used in per-share calculation:", "Diluted | 3,970 | 4,005 | 3,990 | 4,010",
                      "Weighted-average diluted shares | 39.70 | 40.05 | 39.90 | 40.10"])
        self.assertIsNone(q.get("eps"))
        self.assertIn("no diluted EPS row", q["why"]["eps"])

    def test_an_adjusted_eps_row_outside_the_statement_is_not_read(self) -> None:
        lines = ["Adjusted diluted earnings per share | $9.99 | $8.88 | $7.77 | $6.66", *statement(self.HEADER, [self.REVENUE]),
                 "RECONCILIATION OF GAAP TO NON-GAAP RESULTS", "Non-GAAP diluted earnings per share | $9.99 | $8.88 | $7.77 | $6.66"]
        self.assertIsNone(read_quarter(lines).get("eps"))


class Figures(unittest.TestCase):
    def test_figures_as_printed_and_as_numbers(self) -> None:
        row = "A label | $ 344,441 | $ (0.04) | (1.2) | -3.5 | 9.1% | — | (5)% | $6.75"
        self.assertEqual(amounts_in(row), [("$ 344,441", 344441.0), ("$ (0.04)", -0.04), ("(1.2)", -1.2), ("-3.5", -3.5), ("$6.75", 6.75)])
        self.assertEqual(release.numbers_in("Diluted | $6.75 | $5.87 | 9.1% | $(0.40)"), [6.75, 5.87, -0.40])
        self.assertEqual((release.as_printed("$ (0.04)"), release.per_share("0.97"), release.per_share("(0.06)")), ("$(0.04)", "$0.97", "$(0.06)"))

    def test_the_dates_of_a_header_line(self) -> None:
        self.assertEqual(release.dates_in("(in millions) | Oct. 3, 2026 | September 27, 2025 | Change"), [(2026, 10, 3), (2025, 9, 27)])
        self.assertEqual(release.dates_in("Three Months Ended September 30, | 2026 | 2025"), [(2026, 0, 0), (2025, 0, 0)])
        self.assertEqual(release.dates_in("Products | $2,026 | 1,999.5 | FY2026"), [])

    def test_the_code_names_no_company(self) -> None:
        source = (ROOT / "release.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT|CSCO|AMAT|META|DELL)\b", source))


if __name__ == "__main__":
    unittest.main()
