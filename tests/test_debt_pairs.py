"""Claim 7's debt: the balance sheet's two lines as one pair, never the total tag, never short-term borrowings.

The amounts are the ones Lowe's and Walmart filed in their latest 10-Ks (read from SEC company facts on
2026-11-20). docs/decision-log.md, entry 9, gives the rule; on 2026-11-20 the joined desk had lost it.
"""
import unittest

from equity_research_desk import DEBT_TOTAL, Desk

END, PRIOR_END = "2026-01-30", "2025-01-31"
ACCN = "0000000000-26-000001"


def fact(value, end=END, accn=ACCN, start=None, fy=2025):
    row = {"val": value, "end": end, "accn": accn, "fy": fy, "fp": "FY", "form": "10-K", "filed": "2026-03-20"}
    if start:
        row["start"] = start
    return row


def company(**tags):
    """A company-facts payload with annual revenue, equity, and the given instant facts (tag=(current, prior))."""
    gaap = {"Revenues": {"units": {"USD": [fact(86e9, start="2025-02-01"), fact(83e9, PRIOR_END, start="2024-02-03", fy=2024)]}},
            "StockholdersEquity": {"units": {"USD": [fact(-9.917e9), fact(-14.231e9, PRIOR_END, fy=2024)]}}}
    for tag, (current, prior) in tags.items():
        rows = [fact(current)] + ([fact(prior, PRIOR_END, fy=2024)] if prior is not None else [])
        gaap[tag] = {"units": {"USD": rows}}
    return {"facts": {"us-gaap": gaap}}


def debt(payload):
    facts, _, _ = Desk.__new__(Desk).compile_facts(payload)
    return facts["long_term_debt"], facts["current_portion_of_long_term_debt"]


class DebtPairs(unittest.TestCase):
    def test_lowes_reads_its_balance_sheet_pair_not_the_total_tag(self):
        noncurrent, current = debt(company(LongTermDebt=(39_819e6, None),
                                           LongTermDebtAndCapitalLeaseObligations=(37_490e6, 32_901e6),
                                           LongTermDebtAndCapitalLeaseObligationsCurrent=(2_431e6, 2_586e6)))
        self.assertEqual((noncurrent["tag"], current["tag"]),
                         ("LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent"))
        self.assertEqual(noncurrent["value"] + current["value"], 39_921e6)
        self.assertEqual(noncurrent["debt_basis"], "pair")
        self.assertIn("excluding current maturities", noncurrent["label"])

    def test_walmart_reads_its_pair_and_never_adds_short_term_borrowings(self):
        noncurrent, current = debt(company(LongTermDebt=(38_166e6, 35_999e6), LongTermDebtNoncurrent=(34_624e6, 33_401e6),
                                           LongTermDebtCurrent=(3_542e6, 2_598e6), ShortTermBorrowings=(6_596e6, 3_068e6)))
        self.assertEqual((noncurrent["tag"], current["tag"]), ("LongTermDebtNoncurrent", "LongTermDebtCurrent"))
        self.assertEqual(noncurrent["value"] + current["value"], 38_166e6)

    def test_the_total_tag_shows_only_that_there_is_no_current_portion(self):
        noncurrent, current = debt(company(LongTermDebt=(5_000e6, None), LongTermDebtNoncurrent=(5_000e6, None)))
        self.assertEqual((noncurrent["debt_basis"], current["value"]), ("no current portion", None))
        self.assertIn(DEBT_TOTAL, noncurrent["note"])

    def test_a_total_tag_alone_establishes_nothing(self):
        noncurrent, current = debt(company(LongTermDebt=(39_819e6, None)))
        self.assertNotIn("debt_basis", noncurrent)
        self.assertIsNone(noncurrent["value"])

    def test_two_lines_from_different_pairs_are_not_a_pair(self):
        noncurrent, current = debt(company(LongTermDebtNoncurrent=(34_624e6, None),
                                           LongTermDebtAndCapitalLeaseObligationsCurrent=(2_431e6, None)))
        self.assertNotIn("debt_basis", noncurrent)


if __name__ == "__main__":
    unittest.main()
