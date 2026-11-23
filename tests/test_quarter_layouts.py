"""Release income statements as filers lay them out, through step 6 of the group desk.

On 2026-11-22 an independent review of the audit's commit ran a battery of made-up statements through step 6. It
found a count of shares published as GAAP diluted EPS ("$204": the rows "Basic" and "Diluted" under "Shares used in
computing net income per share:"), a non-GAAP statement read as the GAAP one when its title was a row of its own
table or a section inside it, a unit taken from one row's label ("shares in thousands") for the whole table, a
text fallback that stated the first amount after a label, whatever its column, and a regression of the audit
itself: a GAAP statement was skipped whenever a paragraph above it said "outlook", "guidance" or "non-GAAP",
which the paragraph before a release's statements usually does. Every company, table and amount here is made up.
"""
import contextlib
import io
from types import SimpleNamespace
import unittest

from equity_research_desk import Desk, Filing, read_quarter_table, read_quarter_token_table, row_amounts


def t(rows):
    return "<table>" + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows) + "</table>"


def p(*lines):
    return "".join(f"<p>{line}</p>" for line in lines)


TITLE = p("MADE UP CORP", "CONDENSED CONSOLIDATED STATEMENTS OF INCOME", "(In millions, except per share data)", "(Unaudited)")
CONTACT = p("Investor contact: Pat Example", "investors@madeup.example", "555-0100", "Tables follow")


def money4(label, a, b, c, d):
    return [label, "$", a, "", "$", b, "", "$", c, "", "$", d, ""]


def plain4(label, a, b, c, d):
    return [label, a, "", b, "", c, "", d, ""]


THREE = [["", "Three Months Ended September 30,"], ["", "2026", "", "2025", ""]]
THREE_AND_NINE = [["", "Three Months Ended September 30,", "Nine Months Ended September 30,"], ["", "2026", "", "2025", "", "2026", "", "2025", ""]]
REVENUE = ["Revenue", "$", "1,000", "", "$", "900", ""]
EPS = ["Diluted earnings per share", "$", "0.98", "", "$", "0.75", ""]
BODY = [money4("Revenue", "1,000", "900", "2,900", "2,600"), plain4("Cost of revenue", "400", "380", "1,200", "1,100"),
        money4("Net income", "200", "150", "590", "470"), ["Earnings per share:"],
        money4("Basic", "1.02", "0.77", "3.00", "2.40"), money4("Diluted", "0.98", "0.75", "2.90", "2.30"),
        ["Weighted average shares outstanding:"], plain4("Basic", "196", "195", "196", "195"), plain4("Diluted", "204", "200", "204", "200")]
RIGHT = (1000.0, 900.0, 0.98)
NOTHING = (None, None, None)


def quarter(body):
    """What step 6 saves for a release with this body, with no network."""
    desk = Desk.__new__(Desk)
    desk.filings = {"8-K": Filing("8-K", "0000000000-26-000001", "2026-11-20", "x.htm", release_url="https://www.sec.gov/x.htm"),
                    "10-Q": Filing("10-Q", "0000000000-26-000002", "2026-11-01", "q.htm")}
    desk.get = lambda url: SimpleNamespace(content=f"<html><body>{body}</body></html>".encode("utf-8"))
    desk.facts, desk.computed_metrics, desk.quarter_results, desk.company_facts, desk.cik = {}, {}, {}, {"facts": {}}, "1"
    with contextlib.redirect_stdout(io.StringIO()):
        desk.step6()
    return desk.quarter_results


def figures(body):
    q = quarter(body)
    return q["total_revenue"], q["prior_year_total_revenue"], q["diluted_eps"]


class OrdinaryStatements(unittest.TestCase):
    def test_three_and_nine_months_with_eps_under_a_heading(self):
        self.assertEqual(figures(CONTACT + TITLE + t(THREE_AND_NINE + BODY)), RIGHT)

    def test_the_nine_month_group_first(self):
        rows = [["", "Nine Months Ended September 30,", "Three Months Ended September 30,"], ["", "2026", "", "2025", "", "2026", "", "2025", ""],
                money4("Revenue", "2,900", "2,600", "1,000", "900"), ["Earnings per share:"], money4("Diluted", "2.90", "2.30", "0.98", "0.75")]
        self.assertEqual(figures(CONTACT + TITLE + t(rows)), RIGHT)

    def test_the_older_year_first(self):
        rows = [["", "Three Months Ended September 30,"], ["", "2025", "", "2026", ""],
                ["Revenue", "$", "900", "", "$", "1,000", ""], ["Diluted earnings per share", "$", "0.75", "", "$", "0.98", ""]]
        self.assertEqual(figures(CONTACT + TITLE + t(rows)), RIGHT)

    def test_a_fourth_quarter_beside_the_year(self):
        head = [["", "Three Months Ended December 31,", "Year Ended December 31,"], ["", "2026", "", "2025", "", "2026", "", "2025", ""]]
        self.assertEqual(figures(CONTACT + TITLE + t(head + BODY)), RIGHT)

    def test_weeks_and_dates(self):
        rows = [["", "Thirteen Weeks Ended", "Thirty-Nine Weeks Ended"], ["", "October 31, 2026", "November 1, 2025", "October 31, 2026", "November 1, 2025"],
                ["Net sales", "1,000", "900", "2,900", "2,600"], ["Diluted earnings per share", "0.98", "0.75", "2.90", "2.30"]]
        self.assertEqual(figures(CONTACT + TITLE + t(rows)), RIGHT)

    def test_a_loss_under_net_loss_per_share(self):
        rows = THREE + [REVENUE, ["Net loss per share:"], ["Basic", "$", "(0.12", ")", "$", "0.34", ""], ["Diluted", "$", "(0.12", ")", "$", "0.33", ""]]
        self.assertEqual(figures(CONTACT + TITLE + t(rows)), (1000.0, 900.0, -0.12))

    def test_total_net_revenue_before_net_sales(self):
        rows = THREE + [["Net sales", "$", "950", "", "$", "860", ""], ["Financing revenue", "50", "", "40", ""], ["Total net revenue", "1,000", "", "900", ""], EPS]
        self.assertEqual(figures(CONTACT + TITLE + t(rows)), RIGHT)

    def test_the_label_that_ends_with_diluted(self):
        for basic, diluted in (("Earnings per share - basic", "Earnings per share - diluted"), ("Net income per share - basic", "Net income per share - diluted"),
                               ("Earnings per share (basic)", "Earnings per share (diluted)"), ("Net income per common share, basic", "Net income per common share, diluted")):
            with self.subTest(label=diluted):
                rows = THREE + [REVENUE, [basic, "$", "1.02", "", "$", "0.77", ""], [diluted, "$", "0.98", "", "$", "0.75", ""]]
                self.assertEqual(figures(CONTACT + TITLE + t(rows)), RIGHT)


class ACountOfSharesIsNotEarningsPerShare(unittest.TestCase):
    def test_share_counts_under_a_heading_that_says_per_share(self):
        for heading in ("Shares used in computing net income per share:", "Weighted average shares used to compute net income per share:",
                        "Weighted-average common shares outstanding used in per share computation:"):
            with self.subTest(heading=heading):
                rows = THREE + [REVENUE, [heading], ["Basic", "196", "", "195", ""], ["Diluted", "204", "", "200", ""],
                                ["Net income per share:"], ["Basic", "$", "1.02", "", "$", "0.77", ""], ["Diluted", "$", "0.98", "", "$", "0.75", ""]]
                self.assertEqual(figures(CONTACT + TITLE + t(rows)), RIGHT)

    def test_share_counts_after_the_per_share_rows(self):
        rows = THREE_AND_NINE + [money4("Revenue", "1,000", "900", "2,900", "2,600"), money4("Net income per share - basic", "1.02", "0.77", "3.00", "2.40"),
                                 money4("Net income per share - diluted", "0.98", "0.75", "2.90", "2.30"),
                                 ["Shares used in computing net income per share:"], plain4("Basic", "196", "195", "196", "195"), plain4("Diluted", "204", "200", "204", "200")]
        self.assertEqual(figures(CONTACT + TITLE + t(rows)), RIGHT)

    def test_only_share_counts_state_no_eps(self):
        rows = THREE + [REVENUE, ["Shares used in computing net income per share:"], ["Basic", "196", "", "195", ""], ["Diluted", "204", "", "200", ""]]
        self.assertIsNone(quarter(CONTACT + TITLE + t(rows))["diluted_eps"])


class ANonGaapStatementIsNotTheStatement(unittest.TestCase):
    GAAP = TITLE + t(THREE + [REVENUE, EPS])

    def test_its_title_is_a_row_of_its_own_table(self):
        other = t([["SUPPLEMENTAL NON-GAAP CONSOLIDATED STATEMENTS OF INCOME"]] + THREE + [REVENUE, ["Diluted earnings per share", "$", "1.31", "", "$", "1.05", ""]])
        self.assertEqual(figures(CONTACT + p("MADE UP CORP") + other + self.GAAP), RIGHT)
        self.assertEqual(figures(CONTACT + p("MADE UP CORP") + other), NOTHING)

    def test_a_non_gaap_section_inside_the_table(self):
        tokens = [["", "Q3'26", "Q3'25"], ["Non-GAAP"], ["Revenue", "1,000", "900"], ["Diluted EPS", "1.31", "1.05"],
                  ["GAAP"], ["Revenue", "1,000", "900"], ["Diluted EPS", "0.98", "0.75"]]
        self.assertEqual(figures(CONTACT + p("Financial highlights") + t(tokens)), RIGHT)
        self.assertEqual(figures(CONTACT + p("Financial highlights") + t(tokens[:4])), NOTHING)
        dated = THREE + [REVENUE, ["Non-GAAP measures:"], ["Diluted earnings per share", "$", "1.31", "", "$", "1.05", ""]]
        self.assertIsNone(quarter(CONTACT + TITLE + t(dated))["diluted_eps"])

    def test_a_per_share_heading_does_not_end_the_non_gaap_section(self):
        rows = THREE + [REVENUE, ["Adjusted results:"], ["Earnings per share:"], ["Diluted", "$", "1.31", "", "$", "1.05", ""]]
        self.assertIsNone(quarter(CONTACT + TITLE + t(rows))["diluted_eps"])


class AParagraphAboveIsNotTheTablesTitle(unittest.TestCase):
    """The regression: the paragraph before a release's statements speaks of outlook, guidance and non-GAAP measures."""
    SAFE_HARBOR = p("Forward-looking statements: this release holds statements about our outlook and guidance, which are forecasts and may differ from results.")
    NOTE = p("We also report adjusted measures. A reconciliation of each non-GAAP measure to GAAP follows the statements.")

    def test_a_safe_harbor_paragraph_then_the_title_lines(self):
        body = self.SAFE_HARBOR + p("CONDENSED CONSOLIDATED STATEMENTS OF INCOME", "(In millions, except per share data)", "(Unaudited)") + t(THREE_AND_NINE + BODY)
        self.assertEqual(figures(body), RIGHT)
        self.assertEqual(quarter(body)["revenue_unit"], "USD millions")

    def test_a_paragraph_then_a_table_that_holds_its_own_title(self):
        table = t([["MADE UP CORP"], ["CONDENSED CONSOLIDATED STATEMENTS OF INCOME"], ["(In millions, except per share data)"]] + THREE_AND_NINE + BODY)
        self.assertEqual(figures(self.NOTE + table), RIGHT)
        self.assertEqual(quarter(self.NOTE + table)["revenue_unit"], "USD millions")

    def test_a_title_above_still_names_a_table_that_is_not_the_statement(self):
        for title in ("Reconciliation of GAAP to Non-GAAP Results", "RECONCILIATION OF GAAP NET INCOME AND DILUTED EARNINGS PER SHARE TO NON-GAAP ADJUSTED NET INCOME AND ADJUSTED DILUTED EARNINGS PER SHARE",
                      "Fiscal 2027 Outlook", "Non-GAAP results follow:"):
            with self.subTest(title=title):
                self.assertEqual(figures(CONTACT + p(title) + t(THREE + [REVENUE, EPS])), NOTHING)


class TheUnitIsTheStatements(unittest.TestCase):
    def test_one_rows_own_unit_is_not_the_tables(self):
        rows = THREE + [REVENUE, EPS, ["Weighted average diluted shares (in thousands)", "204,000", "", "200,000", ""]]
        self.assertEqual(quarter(CONTACT + TITLE + t(rows))["revenue_unit"], "USD millions")

    def test_the_unit_in_the_first_cell_of_the_row_of_years(self):
        # One real release prints "(Amounts in millions, except per share data)" beside its years. The first form
        # of the rule above ended the title rows before the row of years and lost that unit; a replay of the pages
        # a practice run saved showed it.
        rows = [["", "Three Months Ended", "Nine Months Ended"], ["", "October 31,", "October 31,"],
                ["(Amounts in millions, except per share data)", "2026", "2025", "2026", "2025"],
                ["Total revenues", "1,000", "900", "2,900", "2,600"], ["Diluted earnings per share", "0.98", "0.75", "2.90", "2.30"],
                ["Weighted average diluted shares (in thousands)", "204,000", "200,000", "204,000", "200,000"]]
        q = quarter(CONTACT + t(rows))
        self.assertEqual((q["total_revenue"], q["prior_year_total_revenue"], q["diluted_eps"], q["revenue_unit"]), (1000.0, 900.0, 0.98, "USD millions"))

    def test_thousands_above_the_table(self):
        title = p("MADE UP CORP", "CONSOLIDATED STATEMENTS OF OPERATIONS", "(In thousands, except per share data)", "(Unaudited)")
        rows = THREE + [["Total revenues", "$", "1,000,000", "", "$", "900,000", ""], ["Diluted net income per share", "$", "0.98", "", "$", "0.75", ""]]
        q = quarter(CONTACT + title + t(rows))
        self.assertEqual((q["total_revenue"], q["revenue_unit"], q["diluted_eps"]), (1000000.0, "USD thousands", 0.98))


class NoFigureFromTextTheDeskCannotPlace(unittest.TestCase):
    """A table no reader can read gives no claim. The text fallback stated the first amount after the label."""
    def test_the_first_amount_after_a_label_is_not_the_quarters(self):
        older_first = [["", "Three Months Ended September 30,"], ["", "2025", "", "2026", ""], ["Total sales", "$", "900", "", "$", "1,000", ""],
                       ["Diluted net income per common share", "$", "0.75", "", "$", "0.98", ""]]
        nine_first = [["", "Nine Months Ended September 30,", "Three Months Ended September 30,"], ["", "2026", "", "2025", "", "2026", "", "2025", ""],
                      money4("Total sales", "2,900", "2,600", "1,000", "900"), money4("Diluted net income per common share", "2.90", "2.30", "0.98", "0.75")]
        for rows in (older_first, nine_first):
            q = quarter(CONTACT + TITLE + t(rows))
            self.assertIsNone(q["diluted_eps"])
            self.assertFalse(any("(quarterly" in line for line in q["results"]), q["results"])


class WhenInDoubtNothing(unittest.TestCase):
    def test_layouts_the_desk_may_refuse_but_never_misreads(self):
        change = [["", "Three Months Ended September 30,", ""], ["", "2026", "", "2025", "", "% Change", ""],
                  ["Revenue", "$", "1,000", "", "$", "900", "", "11.1", ""], ["Diluted earnings per share", "$", "0.98", "", "$", "0.75", "", "30.7", ""]]
        three_columns = [["", "Three Months Ended", "Year Ended"], ["", "December 31, 2026", "September 30, 2026", "December 31, 2025", "December 31, 2026", "December 31, 2025"],
                         ["Revenue", "1,000", "960", "900", "3,900", "3,500"], ["Diluted earnings per share", "0.98", "0.90", "0.75", "3.80", "3.05"]]
        for rows in (change, three_columns):
            self.assertIn(figures(CONTACT + TITLE + t(rows)), (RIGHT, NOTHING))
        split = t(THREE + [REVENUE]) + t([["Earnings per share:"], ["Basic", "$", "1.02", "", "$", "0.77", ""], ["Diluted", "$", "0.98", "", "$", "0.75", ""]])
        self.assertIn(figures(CONTACT + TITLE + split), (RIGHT, NOTHING))


class APercentageIsNotAnAmount(unittest.TestCase):
    """A change column. The audit's first row reader knew a percentage by a next cell that starts with "%". A
    negative change is printed "(5" then ")%": the "(5" counted as an amount, the row then held one amount too
    many and was dropped, and the next row that fitted was published in its place (a part of revenue for total
    revenues; a count of shares for EPS). The code before the audit read these tables."""
    def test_a_negative_change_split_over_two_cells(self):
        self.assertEqual(row_amounts(["1,000", "1,010", "(1", ")%"]), ["1,000", "1,010"])
        self.assertEqual(row_amounts(["0.98", "1.03", "(5", ") %"]), ["0.98", "1.03"])
        self.assertEqual(row_amounts(["0.98", "1.03", "(5)%"]), ["0.98", "1.03"])
        rows = [["", "Three Months Ended", "", ""], ["", "October 30, 2026", "October 31, 2025", "% Change"],
                ["Net sales", "950", "900", "6", "%"], ["Total revenues", "1,000", "1,010", "(1", ")%"],
                ["Net income per share:"], ["Diluted", "0.98", "1.03", "(5", ")%"],
                ["Shares used in computing net income per share:"], ["Diluted", "204", "200", "2", "%"]]
        self.assertEqual(figures(CONTACT + TITLE + t(rows)), (1000.0, 1010.0, 0.98))

    def test_two_change_columns_do_not_pair_each_amount_with_a_percentage(self):
        rows = [["", "Three Months Ended", "", "", ""], ["", "October 30, 2026", "October 31, 2025", "% Change", "% Change in Constant Currency"],
                ["Total revenues", "1,000", "900", "11.1", "12.3"], ["Diluted earnings per share", "0.98", "0.88", "11.4", "12.0"]]
        self.assertIn(figures(CONTACT + TITLE + t(rows)), (RIGHT, (1000.0, 900.0, 0.98), NOTHING))   # never a prior year of 11.1

    def test_an_amount_and_its_percentage_of_sales_are_still_paired(self):
        rows = [["", "Three Months Ended", "", "", ""], ["", "October 30, 2026", "% Sales", "October 31, 2025", "% Sales"],
                ["Net sales", "1,000", "100.00", "900", "100.00"], ["Diluted earnings per common share", "0.98", "", "0.75", ""]]
        self.assertEqual(figures(CONTACT + TITLE + t(rows))[:2], (1000.0, 900.0))


class TheTitleWhereverItStands(unittest.TestCase):
    OTHER = THREE + [REVENUE, ["Diluted earnings per share", "$", "1.31", "", "$", "1.05", ""]]
    GAAP = TITLE + t(THREE + [REVENUE, EPS])

    def test_a_non_gaap_title_five_lines_above_its_table(self):
        title = p("Non-GAAP Condensed Consolidated Statements of Income", "MADE UP CORP", "(In millions, except per share data)", "(Unaudited)", "Quarter ended September 30, 2026")
        self.assertEqual(figures(CONTACT + title + t(self.OTHER)), NOTHING)
        self.assertEqual(figures(CONTACT + title + t(self.OTHER) + self.GAAP), RIGHT)

    def test_a_title_split_by_bold_and_footnote_tags(self):
        title = "<p><b>Non-GAAP</b> Condensed Consolidated Statements of Income</p><p>(In <b>millions</b>, except per share data)<sup>(1)</sup></p><p>(Unaudited)</p>"
        self.assertEqual(figures(CONTACT + title + t(self.OTHER)), NOTHING)
        gaap = "<p>Condensed Consolidated <b>Statements</b> of Income</p><p>(In <b>millions</b>, except per share data)<sup>(1)</sup></p><p>(Unaudited)</p>"
        q = quarter(CONTACT + gaap + t(THREE + [REVENUE, EPS]))
        self.assertEqual((q["total_revenue"], q["diluted_eps"], q["revenue_unit"]), (1000.0, 0.98, "USD millions"))

    def test_amounts_adjusted_for_a_stock_split_are_not_adjusted_results(self):
        title = p("MADE UP CORP", "Condensed Consolidated Statements of Income",
                  "(In millions, except per share data; share and per share amounts adjusted for the four-for-one stock split)")
        self.assertEqual(figures(CONTACT + title + t(THREE + [REVENUE, EPS])), RIGHT)

    def test_the_footnote_of_the_table_before_is_not_this_tables_title(self):
        before = t([["Segment", "Q3"], ["Stores", "700"]]) + p("(1) Adjusted operating income is defined in the tables at the end of this release.")
        title = p("MADE UP CORP", "Condensed Consolidated Statements of Income (in millions, unaudited)")
        q = quarter(before + title + t(THREE + [REVENUE, EPS]))
        self.assertEqual((q["total_revenue"], q["prior_year_total_revenue"], q["diluted_eps"], q["revenue_unit"]), (1000.0, 900.0, 0.98, "USD millions"))


class LossesAndColumnsTheReviewAskedAbout(unittest.TestCase):
    def test_a_loss_per_share_on_one_line(self):
        for label in ("Diluted net loss per share", "Net loss per share - diluted", "Diluted earnings (loss) per share", "Diluted net income (loss) per common share"):
            with self.subTest(label=label):
                q = quarter(CONTACT + TITLE + t(THREE + [REVENUE, [label, "$", "(0.12", ")", "$", "0.33", ""]]))
                self.assertEqual(q["diluted_eps"], -0.12)
                self.assertTrue(any("-$0.12" in line for line in q["results"]), q["results"])   # the printed line keeps the sign

    def test_the_latest_date_printed_twice_is_not_read(self):
        rows = [["", "Three Months Ended"], ["", "September 30, 2026", "September 30, 2026", "September 30, 2025"],
                ["Total revenue", "100", "140", "90"], ["Diluted earnings per share", "1.00", "1.40", "0.90"]]
        self.assertIsNone(read_quarter_table(rows))

    def test_a_token_row_with_an_amount_too_many_is_not_read(self):
        rows = [["", "Q3'26", "Q3'25"], ["Revenue", "100", "90", "11"], ["Diluted EPS", "1.00", "0.90"]]
        self.assertIsNone(read_quarter_token_table(rows))


if __name__ == "__main__":
    unittest.main()
