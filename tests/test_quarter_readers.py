"""Step 6 states a quarter's figure only when the table says which column is which.

On 2026-11-22 the audit ran made-up release tables through step 6 and it printed a wrong figure for six of eight:
a loss in parentheses made it read the year-ago EPS as the quarter's, three dated columns made it read the prior
quarter, two change columns gave a growth of 900%, a row "Revenue from services" was read as total revenue, and
an abbreviated month stopped the run. A wrong claim fails the audit and a missing one does not, so a reader now
refuses a row whose amounts do not line up with the period columns. Every table and amount here is made up.
"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from desk_role_contracts import core_claims_table
from equity_research_desk import Desk, Filing, read_quarter_table, read_quarter_token_table, row_amounts


def html(rows, above="Condensed Consolidated Statements of Income (in millions, except per share data)"):
    cells = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<html><body><p>{above}</p><table>{cells}</table></body></html>"


def quarter(*pages):
    """What step 6 saves for a release made of these tables, with no network."""
    desk = Desk.__new__(Desk)
    desk.filings = {"8-K": Filing("8-K", "0000000000-26-000001", "2026-11-20", "x.htm", release_url="https://www.sec.gov/x.htm"),
                    "10-Q": Filing("10-Q", "0000000000-26-000002", "2026-11-01", "q.htm")}
    body = "".join(page.replace("<html><body>", "").replace("</body></html>", "") for page in pages)
    desk.get = lambda url: SimpleNamespace(content=f"<html><body>{body}</body></html>".encode("utf-8"))
    desk.facts, desk.computed_metrics, desk.quarter_results, desk.company_facts, desk.cik = {}, {}, {}, {"facts": {}}, "1"
    with contextlib.redirect_stdout(io.StringIO()):
        desk.step6()
    return desk


def figures(desk):
    q = desk.quarter_results
    return q["total_revenue"], q["prior_year_total_revenue"], q["diluted_eps"]


TOKENS = [["", "Q3'26", "Q3'25"], ["Revenue", "100", "90"], ["Diluted EPS", "1.00", "0.90"]]
DATED = [["", "Three Months Ended"], ["", "September 30, 2026", "September 30, 2025"],
         ["Total revenue", "100", "90"], ["Diluted earnings per share", "1.00", "0.90"]]


class RowAmounts(unittest.TestCase):
    def test_a_loss_keeps_its_sign_and_its_column(self):
        self.assertEqual(row_amounts(["$", "(0.12)", "$", "0.34"]), ["-0.12", "0.34"])
        self.assertEqual(row_amounts(["$", "(0.12", ")", "$", "0.34"]), ["-0.12", "0.34"])
        self.assertEqual(row_amounts(["-0.12", "0.34"]), ["-0.12", "0.34"])
        self.assertEqual(row_amounts(["−0.12", "0.34"]), ["-0.12", "0.34"])

    def test_a_dash_is_an_empty_amount_in_its_column(self):
        self.assertEqual(row_amounts(["—", "0.34"]), [None, "0.34"])

    def test_a_percentage_is_not_an_amount(self):
        self.assertEqual(row_amounts(["188,835", "179,496", "5.2", "%", "(19.5", "%)", "100.00 %"]), ["188,835", "179,496"])


class TheQuarterIsTheRightColumn(unittest.TestCase):
    def test_plain_tables_are_read(self):
        self.assertEqual(figures(quarter(html(TOKENS))), (100.0, 90.0, 1.0))
        self.assertEqual(figures(quarter(html(DATED))), (100.0, 90.0, 1.0))

    def test_a_loss_in_parentheses_is_the_quarters_loss_not_last_years_profit(self):
        for cells in (["(0.12)", "0.34"], ["-0.12", "0.34"], ["$", "(0.12", ")", "$", "0.34"]):
            with self.subTest(cells=cells):
                desk = quarter(html(TOKENS[:2] + [["Diluted EPS", *cells]]))
                self.assertEqual(figures(desk), (100.0, 90.0, -0.12))
                self.assertIn("0.12", desk.quarter_results["diluted_eps_source"])

    def test_a_loss_under_three_months_ended_with_a_gaap_row(self):
        rows = [["", "Three Months Ended September 30,"], ["", "2026", "2025"], ["Revenue", "100", "90"],
                ["Diluted earnings per share"], ["GAAP", "$", "(0.12", ")", "$", "0.34"], ["Adjusted", "$", "0.05", "$", "0.40"]]
        self.assertEqual(figures(quarter(html(rows))), (100.0, 90.0, -0.12))

    def test_three_dated_columns_are_compared_as_dates(self):
        rows = [["", "Three Months Ended"], ["", "June 30, 2026", "September 30, 2026", "September 30, 2025"],
                ["Total revenue", "95", "100", "90"], ["Diluted earnings per share", "0.95", "1.00", "0.90"]]
        self.assertEqual(figures(quarter(html(rows))), (100.0, 90.0, 1.0))

    def test_the_latest_year_printed_twice_is_not_read(self):
        rows = [["", "Three Months Ended"], ["", "2026", "2026", "2025"],
                ["Total revenue", "95", "100", "90"], ["Diluted earnings per share", "0.95", "1.00", "0.90"]]
        self.assertIsNone(read_quarter_table(rows))

    def test_change_columns_are_not_amounts_of_a_period(self):
        rows = DATED[:2] + [["Total revenue", "100", "90", "10", "11.1"], ["Diluted earnings per share", "1.00", "0.90", "0.10", "11.1"]]
        self.assertIsNone(read_quarter_table(rows))
        self.assertEqual(figures(quarter(html(rows))), (None, None, None))

    def test_an_amount_and_its_percentage_of_sales_only_under_a_header_that_says_so(self):
        rows = [["", "Three Months Ended"], ["", "September 30, 2026", "September 30, 2025"], ["", "Amount", "% Sales", "Amount", "% Sales"],
                ["Net sales", "100", "100.00", "90", "100.00"], ["Diluted earnings per common share", "1.00", "0.90"]]
        found = read_quarter_table(rows)
        self.assertEqual((found["revenue"], found["prior_revenue"], found["eps"]), ("100", "90", "1.00"))

    def test_one_kind_of_revenue_is_not_total_revenue(self):
        rows = [["", "Three Months Ended September 30,"], ["", "2026", "2025"], ["Revenue from services", "40", "35"],
                ["Total revenue", "100", "90"], ["Diluted earnings per share"], ["GAAP", "1.00", "0.90"]]
        self.assertEqual(figures(quarter(html(rows))), (100.0, 90.0, 1.0))

    def test_eps_from_continuing_operations_is_not_the_quarters_eps(self):
        rows = DATED[:3] + [["Diluted earnings per share from continuing operations", "1.00", "0.90"], ["Diluted earnings per share", "0.80", "0.90"]]
        self.assertEqual(figures(quarter(html(rows)))[2], 0.8)
        self.assertEqual(figures(quarter(html(rows[:4]))), (None, None, None))

    def test_the_quarter_is_the_three_month_group_wherever_it_stands(self):
        rows = [["", "Nine Months Ended", "Three Months Ended"], ["", "September 30, 2026", "September 30, 2025", "September 30, 2026", "September 30, 2025"],
                ["Total revenue", "300", "270", "100", "90"], ["Diluted earnings per share", "3.00", "2.70", "1.00", "0.90"]]
        self.assertEqual(figures(quarter(html(rows))), (100.0, 90.0, 1.0))

    def test_weeks_with_an_abbreviated_month_are_read_and_never_stop_the_run(self):
        rows = [["", "12 Weeks Ended", "36 Weeks Ended"], ["", "Aug 30, 2026", "Aug 31, 2025", "Aug 30, 2026", "Aug 31, 2025"],
                ["Total revenue", "100", "90", "300", "270"], ["Net income per common share:"], ["Diluted", "1.00", "0.90", "3.00", "2.70"]]
        self.assertEqual(figures(quarter(html(rows))), (100.0, 90.0, 1.0))

    def test_a_token_printed_twice_does_not_say_which_column_is_gaap(self):
        rows = [["", "Q3'26", "Q3'25", "Q3'26", "Q3'25"], ["Revenue", "100", "90", "100", "90"], ["Diluted EPS", "1.00", "0.90", "1.40", "1.10"]]
        self.assertIsNone(read_quarter_token_table(rows))

    def test_a_non_gaap_table_is_not_the_income_statement(self):
        adjusted = html([["", "Q3'26", "Q3'25"], ["Revenue", "100", "90"], ["Diluted EPS", "1.40", "1.10"]], above="Reconciliation of GAAP to Non-GAAP results")
        self.assertEqual(figures(quarter(adjusted)), (None, None, None))
        self.assertEqual(figures(quarter(adjusted, html(TOKENS))), (100.0, 90.0, 1.0))

    def test_a_diluted_row_under_an_adjusted_heading_is_not_gaap(self):
        rows = DATED[:3] + [["Adjusted net income per share:"], ["Diluted", "1.40", "1.10"]]
        self.assertIsNone(read_quarter_table(rows))

    def test_growth_needs_a_positive_base(self):
        desk = quarter(html(DATED[:2] + [["Total revenue", "100", "—"], ["Diluted earnings per share", "1.00", "0.90"]]))
        self.assertNotIn("quarter_revenue_growth", desk.computed_metrics)
        self.assertEqual(figures(desk), (100.0, None, 1.0))


class TheTextFallback(unittest.TestCase):
    def test_a_loss_after_the_label_is_not_skipped_for_the_next_number(self):
        page = "<html><body><p>NET INCOME PER COMMON SHARE</p><p>Diluted</p><p>(0.12)</p><p>0.34</p></body></html>"
        self.assertIsNone(quarter(page).quarter_results["diluted_eps"])

    def test_it_states_no_unit_it_did_not_read(self):
        page = "<html><body><p>Total revenue</p><p>18,517</p></body></html>"
        self.assertFalse(any("in millions" in line for line in quarter(page).quarter_results["results"]))


class TheClaimsTablePrintsWhatTheReleasePrints(unittest.TestCase):
    def table(self, rows):
        desk = quarter(html(rows))
        run = Path(tempfile.mkdtemp())
        (run / "facts.json").write_text(json.dumps({"facts": {}}), encoding="utf-8")
        (run / "calculated_facts.json").write_text(json.dumps({"metrics": desk.computed_metrics, "quarter_results": desk.quarter_results}), encoding="utf-8")
        return core_claims_table(run)

    def test_a_revenue_in_billions_keeps_its_decimal_and_its_unit(self):
        table = self.table([["(in billions)", "Q3'26", "Q3'25"], ["Revenue", "18.5", "16.2"], ["Diluted EPS", "1.00", "0.90"]])
        self.assertIn("| 18.5 (USD billions), as the release table prints it |", table)

    def test_a_loss_per_share_is_printed_as_a_loss(self):
        table = self.table(TOKENS[:2] + [["Diluted EPS", "(0.12)", "0.34"]])
        self.assertIn("| -$0.12 |", table)


if __name__ == "__main__":
    unittest.main()
