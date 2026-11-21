"""Step 6's general reader of a release's quarter table (read_quarter_table).

The rows copy the shape of Lowe's and Walmart's third-quarter releases (read from SEC EDGAR on 2026-11-20), where
the earlier strategies found no quarter at all, and Cisco's "Net income per share:" heading with its Diluted row.
The quarter's revenue and diluted EPS are the releases' own; some other amounts (nine-month columns, Walmart's net
sales row) are made up for the shape.
"""
import unittest

from equity_research_desk import read_quarter_table, table_unit

LOWES = [
    ["", "Three Months Ended", "Nine Months Ended"],
    ["", "October 30, 2026", "October 31, 2025", "October 30, 2026", "October 31, 2025"],
    ["Current Earnings", "Amount", "% Sales", "Amount", "% Sales", "Amount", "% Sales", "Amount", "% Sales"],
    ["Net sales", "$", "22,756", "100.00 %", "$", "20,813", "100.00", "%", "$", "71,790", "100.00", "%", "$", "65,701", "100.00 %"],
    ["Gross margin", "7,497", "32.95", "7,116", "34.19", "23,617", "32.90", "22,204", "33.80"],
    ["Diluted earnings per common share (1)", "$", "2.98", "$", "2.88", "$", "10.13", "$", "9.93"],
]
WALMART = [
    ["", "Three Months Ended October 31,", "Nine Months Ended October 31,"],
    ["(Amounts in millions, except per share data)", "2026", "2025", "Percent Change", "2026", "2025", "Percent Change"],
    ["Revenues:"],
    ["Net sales", "$", "186,960", "$", "177,840", "5.1", "%", "$", "548,744", "$", "517,571", "6.0", "%"],
    ["Total revenues", "188,835", "179,496", "5.2", "%", "554,523", "522,507", "6.1", "%"],
    ["Net income per common share:"],
    ["Basic net income per common share attributable to Walmart", "$", "0.62", "$", "0.77", "(19.5", "%)", "$", "2.09", "$", "2.21", "(5.4", "%)"],
    ["Diluted net income per common share attributable to Walmart", "0.62", "0.77", "(19.5", "%)", "2.09", "2.20", "(5.0", "%)"],
]
CISCO = [
    ["", "Three Months Ended"],
    ["", "October 24, 2026", "October 25, 2025"],
    ["Total revenue", "18,517", "14,883"],
    ["Net income per share:"],
    ["Basic", "$", "1.15", "$", "0.72"],
    ["Diluted", "$", "1.14", "$", "0.72"],
]


class QuarterTable(unittest.TestCase):
    def test_lowes_dated_columns_with_percentages_of_sales(self):
        found = read_quarter_table(LOWES)
        self.assertEqual((found["revenue"], found["prior_revenue"], found["eps"]), ("22,756", "20,813", "2.98"))
        self.assertEqual((found["revenue_label"], found["latest"], found["prior"]), ("Net sales", "October 30, 2026", "October 31, 2025"))

    def test_walmart_years_under_merged_headers_prefer_total_revenues(self):
        found = read_quarter_table(WALMART)
        self.assertEqual((found["revenue"], found["prior_revenue"], found["eps"]), ("188,835", "179,496", "0.62"))
        self.assertEqual(found["revenue_label"], "Total revenues")
        self.assertTrue(found["eps_label"].startswith("Diluted"))

    def test_cisco_diluted_under_its_per_share_heading(self):
        found = read_quarter_table(CISCO)
        self.assertEqual((found["revenue"], found["prior_revenue"], found["eps"]), ("18,517", "14,883", "1.14"))

    def test_an_adjusted_eps_is_never_taken(self):
        rows = CISCO[:3] + [["Adjusted diluted EPS", "$", "1.40", "$", "1.00"]]
        self.assertIsNone(read_quarter_table(rows))

    def test_a_table_without_a_three_month_period_is_not_read(self):
        self.assertIsNone(read_quarter_table([["", "Year Ended"], ["", "2026", "2025"], ["Total revenue", "1", "2"]]))


def first_table(html: str):
    from bs4 import BeautifulSoup
    table = BeautifulSoup(html, "html.parser").find("table")
    return table, [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])] for row in table.find_all("tr")]


class TableUnit(unittest.TestCase):
    """The unit of a release table: its own cells first, then the lines printed just above it (Lowe's)."""

    def test_the_unit_printed_above_the_table(self):
        html = ("<p>LOWE'S COMPANIES, INC.</p><p>Consolidated Statements of Current and Retained Earnings (Unaudited)</p>"
                "<p>In Millions, Except Per Share and Percentage Data</p><table><tr><td>Net sales</td><td>22,756</td></tr></table>")
        self.assertEqual(table_unit(*first_table(html)), "USD millions")

    def test_the_tables_own_cell_comes_first(self):
        html = "<p>In Millions</p><table><tr><td>(Amounts in thousands)</td></tr><tr><td>Revenue</td><td>9</td></tr></table>"
        self.assertEqual(table_unit(*first_table(html)), "USD thousands")

    def test_no_unit_anywhere_says_so(self):
        self.assertEqual(table_unit(*first_table("<p>Results</p><table><tr><td>Revenue</td><td>9</td></tr></table>")), "USD as shown")

    def test_an_earlier_tables_unit_is_not_borrowed(self):
        from bs4 import BeautifulSoup
        html = ("<p>In Millions</p><table><tr><td>Cash</td><td>1</td></tr></table>"
                "<p>Store count</p><table><tr><td>Stores</td><td>1,749</td></tr></table>")
        table = BeautifulSoup(html, "html.parser").find_all("table")[1]
        self.assertEqual(table_unit(table, [["Stores", "1,749"]]), "USD as shown")


if __name__ == "__main__":
    unittest.main()
