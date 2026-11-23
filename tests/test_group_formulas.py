"""The group desk's calculations (equity_research_desk.Desk.compile_facts and step5) on made-up company facts.

No network and no model: company facts are a made-up payload, the close is a stand-in.

On 2026-11-22 the audit changed each formula on purpose (operating margin to net income over revenue, average
equity to year-end equity, free cash flow to a sum, and more) and the 202 tests of the time still passed: the
tests of the formulas were tests of the base desk (lab02_desk.py), and no test ran the group desk's step 5. Each
test here fails on its own changed formula. As in a real 10-K, last year's amount stands twice in the facts: in
this year's filing, as its comparative column, and in last year's own filing.
"""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import equity_research_desk
from equity_research_desk import Desk

END, PRIOR_END, START, PRIOR_START = "2026-01-31", "2025-01-31", "2025-02-01", "2024-02-01"
ACCN, PRIOR_ACCN = "0000000000-26-000001", "0000000000-25-000001"


def row(value, end=END, start=None, fy=2025, accn=ACCN, form="10-K", filed="2026-03-20"):
    out = {"val": value, "end": end, "accn": accn, "fy": fy, "fp": "FY", "form": form, "filed": filed}
    if start:
        out["start"] = start
    return out


def year(current, prior, unit="USD"):
    return {"units": {unit: [row(current, start=START), row(prior, PRIOR_END, PRIOR_START),
                             row(prior, PRIOR_END, PRIOR_START, 2024, PRIOR_ACCN, filed="2025-03-20")]}}


def instant(current, prior):
    return {"units": {"USD": [row(current), row(prior, PRIOR_END), row(prior, PRIOR_END, None, 2024, PRIOR_ACCN, filed="2025-03-20")]}}


def company(**changes):
    """A made-up filer. A change of None removes the tag."""
    gaap = {
        "Revenues": year(1000, 800),
        "RevenueFromContractWithCustomerExcludingAssessedTax": year(950, 700),   # one part of revenue, never the total
        "OperatingIncomeLoss": year(150, 100),
        "ProfitLoss": year(100, 70),                                             # consolidated, with the minority's share
        "NetIncomeLoss": year(90, 60),                                           # the parent's
        "EarningsPerShareDiluted": year(4.0, 3.0, "USD/shares"),
        "EarningsPerShareBasic": year(5.0, 3.5, "USD/shares"),
        "StockholdersEquity": instant(500, 400),
        "LongTermDebtNoncurrent": instant(200, 180),
        "LongTermDebtCurrent": instant(50, 20),
        "NetCashProvidedByUsedInOperatingActivities": year(120, 110),
        "PaymentsToAcquirePropertyPlantAndEquipment": year(30, 25),
    }
    # The fourth quarter alone, in the same 10-K with the same period end: never an annual amount.
    gaap["Revenues"]["units"]["USD"].insert(0, row(300, start="2025-11-01"))
    for tag, value in changes.items():
        if value is None:
            gaap.pop(tag, None)
        else:
            gaap[tag] = value
    return {"facts": {"us-gaap": gaap}}


def metrics(payload, price=50.0):
    desk = Desk.__new__(Desk)
    desk.ticker, desk.company, desk.cik = "EXMP", "Example Co", "0000000000"
    desk.facts, desk.report_period, _ = desk.compile_facts(payload)
    desk.filings = {"10-K": object()}
    desk.market_evidence = {"effective_filed_eastern": "2026-03-20T16:05:00-04:00"}
    close = {"close": price, "source": "made-up close", "close_time": "2026-03-20T16:00:00-04:00"}
    with tempfile.TemporaryDirectory() as folder, \
            mock.patch.object(equity_research_desk, "last_close_before", return_value=close), \
            contextlib.redirect_stdout(io.StringIO()):
        desk.output_dir = Path(folder)
        desk.step5()
    return {name: item["value"] for name, item in desk.computed_metrics.items()}


class GroupDeskFormulas(unittest.TestCase):
    def test_revenue_growth_is_over_last_years_revenue(self):
        self.assertAlmostEqual(metrics(company())["revenue_growth"], 25.0)           # (1000 - 800) / 800

    def test_operating_margin_is_operating_income_over_revenue(self):
        self.assertAlmostEqual(metrics(company())["operating_margin"], 15.0)         # 150 / 1000

    def test_return_on_equity_uses_the_parents_income_and_average_equity(self):
        self.assertAlmostEqual(metrics(company())["return_on_average_equity"], 20.0)  # 90 / ((500 + 400) / 2)

    def test_debt_to_equity_adds_the_current_portion_and_uses_year_end_equity(self):
        self.assertAlmostEqual(metrics(company())["debt_to_equity"], 0.5)            # (200 + 50) / 500

    def test_free_cash_flow_subtracts_capital_spending(self):
        self.assertAlmostEqual(metrics(company())["free_cash_flow"], 90)             # 120 - 30

    def test_price_to_earnings_uses_diluted_earnings_per_share(self):
        self.assertAlmostEqual(metrics(company())["pe"], 12.5)                       # 50 / 4.0

    def test_noncurrent_debt_alone_gives_no_ratio(self):
        self.assertIsNone(metrics(company(LongTermDebtCurrent=None))["debt_to_equity"])

    def test_a_pair_from_two_filings_gives_no_ratio(self):
        other = {"units": {"USD": [row(50, accn="0000000000-26-000009")]}}
        self.assertIsNone(metrics(company(LongTermDebtCurrent=other))["debt_to_equity"])

    def test_a_fact_missing_this_year_is_not_replaced_by_last_years(self):
        only_prior = {"units": {"USD": [row(110, PRIOR_END, PRIOR_START, 2024, PRIOR_ACCN, filed="2025-03-20")]}}
        self.assertIsNone(metrics(company(NetCashProvidedByUsedInOperatingActivities=only_prior))["free_cash_flow"])

    def test_a_quarterly_report_never_supplies_an_annual_fact(self):
        quarterly = {"units": {"USD": [row(999, form="10-Q"), row(400, PRIOR_END, None, 2024, PRIOR_ACCN, filed="2025-03-20")]}}
        self.assertIsNone(metrics(company(StockholdersEquity=quarterly))["debt_to_equity"])

    def test_the_parents_income_is_consolidated_less_the_minoritys_share(self):
        nci = year(10, 10)
        facts, _, _ = Desk.__new__(Desk).compile_facts(company(NetIncomeLoss=None, NetIncomeLossAttributableToNonredeemableNoncontrollingInterest=nci))
        self.assertEqual(facts["net_income_attributable_to_parent"]["value"], 90)   # 100 - 10


if __name__ == "__main__":
    unittest.main()
