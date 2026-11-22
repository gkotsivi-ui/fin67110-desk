"""The group desk's eight annual claims belong to the 10-K it names, and compare two years of that one filing.

On 2026-11-22 the audit found two gaps in equity_research_desk.py. First, nothing checked that SEC's company
facts were those of the 10-K on the report's first line: the base desk has had that rule since 2026-11-12
(lab02_desk.py, decision log F8), and the group desk, copied from another desk, never got it. Second, last
year's figure came from last year's 10-K, where the audit checklist computes growth "from the two years in the
same filing": the comparative column of the 10-K the desk read. Every amount, date and accession here is made up.
"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from desk_role_contracts import core_claims_table
from equity_research_desk import Desk, Filing

THIS_10K, LAST_10K = "0000000001-26-000010", "0000000001-25-000009"
END, PRIOR_END = "2026-06-30", "2025-06-30"


def row(value, end, accn, start=None, fy=2026):
    fact = {"val": value, "end": end, "accn": accn, "fy": fy, "fp": "FY", "form": "10-K", "filed": "2026-08-15" if accn == THIS_10K else "2025-08-15"}
    if start:
        fact["start"] = start
    return fact


def company(revenue_rows, equity_rows=(), tag="Revenues"):
    gaap = {tag: {"units": {"USD": list(revenue_rows)}}}
    if equity_rows:
        gaap["StockholdersEquity"] = {"units": {"USD": list(equity_rows)}}
    return {"facts": {"us-gaap": gaap}}


def duration(value, end, accn, fy=2026):
    start = f"{int(end[:4]) - 1}-07-01"
    return row(value, end, accn, start=start, fy=fy)


RESTATED = company(
    # Last year's revenue was 90 when first reported, and this year's 10-K restates it to 80.
    [duration(100, END, THIS_10K), duration(80, PRIOR_END, THIS_10K), duration(90, PRIOR_END, LAST_10K, fy=2025)],
    [row(50, END, THIS_10K), row(40, PRIOR_END, THIS_10K), row(44, PRIOR_END, LAST_10K, fy=2025)])


def desk(ten_k_year_end=END):
    d = Desk.__new__(Desk)
    d.ticker, d.company, d.cik, d.price, d.price_source, d.market_evidence = "ZZZZ", "A made-up company", "1", None, "not available", {}
    d.filings = {"10-K": Filing("10-K", THIS_10K, "2026-08-15", "k.htm", report_date=ten_k_year_end)} if ten_k_year_end is not None else {}
    d.facts, d.computed_metrics, d.quarter_results, d.submissions, d.annual_problem = {}, {}, {}, {"sicDescription": ""}, ""
    return d


def read(payload, ten_k_year_end=END):
    d = desk(ten_k_year_end)
    with contextlib.redirect_stdout(io.StringIO()):
        d.print_facts(payload, "ZZZZ")
    return d


class ThePriorYearIsTheSameFilingsComparative(unittest.TestCase):
    def test_a_restated_prior_year_is_read_from_the_10k_the_desk_read(self):
        facts = read(RESTATED).facts
        self.assertEqual((facts["revenue"]["value"], facts["revenue"]["prior_value"], facts["revenue"]["prior_filing"]), (100, 80, THIS_10K))
        self.assertEqual((facts["stockholders_equity"]["prior_value"], facts["stockholders_equity"]["prior_filing"]), (40, THIS_10K))

    def test_no_comparative_in_the_filing_states_no_prior_year(self):
        payload = company([duration(100, END, THIS_10K), duration(90, PRIOR_END, LAST_10K, fy=2025)])
        revenue = read(payload).facts["revenue"]
        self.assertEqual((revenue["value"], revenue["prior_value"], revenue["prior_filing"]), (100, None, None))

    def test_a_53_week_year_is_still_the_year_before(self):
        payload = company([row(100, "2026-01-30", THIS_10K, start="2025-02-01"), row(90, "2025-01-31", THIS_10K, start="2024-02-03")])
        self.assertEqual(read(payload, "2026-01-30").facts["revenue"]["prior_value"], 90)

    def test_a_period_two_years_back_is_not_the_prior_year(self):
        payload = company([duration(100, END, THIS_10K), duration(70, "2024-06-30", THIS_10K)])
        self.assertIsNone(read(payload).facts["revenue"]["prior_value"])


class TheFactsAreTheChosenTenKs(unittest.TestCase):
    def test_the_10ks_own_year_states_the_facts(self):
        d = read(RESTATED)
        self.assertEqual((d.annual_problem, d.report_period, d.facts["revenue"]["value"]), ("", END, 100))

    def test_facts_that_stop_a_year_before_the_10k_are_not_stated(self):
        d = read(RESTATED, "2027-06-30")
        self.assertIn("2026-06-30", d.annual_problem)
        self.assertIn("2027-06-30", d.annual_problem)
        self.assertTrue(all(item["value"] is None and item["prior_value"] is None for item in d.facts.values()))
        self.assertEqual(d.report_period, "2027-06-30")

    def test_a_cover_date_a_few_days_from_the_year_end_is_the_same_year(self):
        self.assertEqual(read(RESTATED, "2026-06-27").annual_problem, "")

    def test_no_revenue_fact_states_no_annual_fact_and_does_not_stop(self):
        d = read(company([duration(100, END, THIS_10K)], tag="SomeOtherRevenueTag"))
        self.assertIn("no full-year revenue", d.annual_problem)
        self.assertIsNone(d.facts["revenue"]["value"])

    def test_without_a_chosen_10k_the_facts_are_read_as_before(self):
        self.assertEqual(read(RESTATED, None).facts["revenue"]["value"], 100)

    def test_the_ratios_are_not_computed_from_another_years_facts_and_the_table_says_why(self):
        d = read(RESTATED, "2027-06-30")
        with contextlib.redirect_stdout(io.StringIO()):
            d.output_dir = Path(tempfile.mkdtemp())
            d.step5()
            d.save_facts()
        self.assertTrue(all(metric["value"] is None for metric in d.computed_metrics.values()))
        (d.output_dir / "calculated_facts.json").write_text(json.dumps({"metrics": d.computed_metrics, "quarter_results": {}}), encoding="utf-8")
        table = core_claims_table(d.output_dir)
        self.assertIn("| 1 | Total revenue, fiscal year ended not established | not established by code | the XBRL company facts end their latest fiscal year on 2026-06-30", table)
        self.assertIn("| 2 | Revenue growth versus the prior year | not established by code | the XBRL company facts end", table)

    def test_a_peer_with_no_revenue_fact_does_not_stop_the_run(self):
        d = desk()
        facts, end, fy = d.compile_facts(company([duration(100, END, THIS_10K)], tag="SomeOtherRevenueTag"))
        self.assertIsNone(facts["revenue"]["value"])


class GrowthUsesTheRestatedBase(unittest.TestCase):
    def test_growth_and_average_equity_use_the_same_filing(self):
        d = read(RESTATED)
        d.facts["net_income_attributable_to_parent"].update(value=9, tag="NetIncomeLoss", filing=THIS_10K, period_end=END)
        with contextlib.redirect_stdout(io.StringIO()):
            d.output_dir = Path(tempfile.mkdtemp())
            d.step5()
        self.assertAlmostEqual(d.computed_metrics["revenue_growth"]["value"], 25.0)           # (100 - 80) / 80
        self.assertAlmostEqual(d.computed_metrics["return_on_average_equity"]["value"], 20.0)  # 9 / ((50 + 40) / 2)


if __name__ == "__main__":
    unittest.main()
