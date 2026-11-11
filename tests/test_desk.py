"""Offline tests of the desk's rules: no network and no model key.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lab03_app as app  # noqa: E402
from lab02_desk import Desk, html_to_text, is_annual, numbers_in  # noqa: E402


def fact(start: str | None, end: str, val: float, unit: str = "USD") -> dict[str, Any]:
    entry: dict[str, Any] = {"end": end, "val": val, "accn": "0000000001-26-000001", "fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-10-07", "unit": unit}
    if start:
        entry["start"] = start
    return entry


class TextTests(unittest.TestCase):
    def test_table_row_keeps_cells_apart(self) -> None:
        html = "<table><tr><td>Total revenue</td><td>$</td><td>95,723</td><td>(1.2</td><td>)</td></tr></table>"
        self.assertEqual(html_to_text(html), "Total revenue | $95,723 | (1.2)")

    def test_a_label_wrapped_in_a_div_stays_with_its_numbers(self) -> None:
        html = "<table><tr><td><div>Total net sales </div><div>(1)</div></td><td>109,417</td><td>94,036</td></tr></table>"
        self.assertEqual(html_to_text(html), "Total net sales (1) | 109,417 | 94,036")

    def test_a_layout_table_keeps_its_paragraphs(self) -> None:
        html = "<table><tr><td><p>Item 7. Management's Discussion</p><p>Sales rose.</p></td></tr></table>"
        self.assertEqual(html_to_text(html), "Item 7. Management's Discussion\nSales rose.")

    def test_line_breaks_in_the_html_source_are_spaces(self) -> None:
        html = "<table>\n <tr>\n  <td><p>Total revenue</p></td>\n  <td><p>92,279</p></td>\n  <td><p>77,673</p></td>\n </tr>\n</table>"
        self.assertEqual(html_to_text(html), "Total revenue | 92,279 | 77,673")

    def test_step6_reads_the_income_statement_before_a_reconciliation_table(self) -> None:
        folder = Path(tempfile.mkdtemp())
        (folder / "8K.txt").write_text("\n".join([
            "Diluted earnings per share | $4.92 | $(0.03) | $4.89 | $3.72",
            "INCOME STATEMENTS",
            "Three Months Ended September 30, | 2026 | 2025",
            "Total revenue | 92,279 | 77,673",
            "Earnings per share:",
            "Diluted | $4.92 | $3.72",
        ]), encoding="utf-8")
        desk = Desk("Test Agent test@example.com", folder)
        desk.selected = {"8-K": {"saved_text": str(folder / "8K.txt")}}
        with contextlib.redirect_stdout(io.StringIO()):
            desk.step6()
        self.assertEqual((desk.quarter["revenue"], desk.quarter["revenue_prior"]), (92279.0, 77673.0))
        self.assertEqual((desk.quarter["eps"], desk.quarter["eps_prior"]), (4.92, 3.72))

    def test_numbers_in_a_row(self) -> None:
        self.assertEqual(numbers_in("Diluted | $6.75 | $5.87 | 9.1% | $(0.40)"), [6.75, 5.87, -0.40])

    def test_full_years_only(self) -> None:
        self.assertTrue(is_annual(fact("2025-09-01", "2026-08-30", 1)))  # 52 weeks
        self.assertTrue(is_annual(fact("2022-08-29", "2023-09-03", 1)))  # 53 weeks
        self.assertFalse(is_annual(fact("2026-05-11", "2026-08-30", 1)))  # a 16-week quarter
        self.assertTrue(is_annual(fact(None, "2026-08-30", 1)))  # a balance-sheet instant


class TagRuleTests(unittest.TestCase):
    """The tag trap from the Week 2 page, on made-up numbers."""

    def setUp(self) -> None:
        self.desk = Desk("Test Agent test@example.com", Path(tempfile.mkdtemp()))

    def test_newest_year_wins_when_the_filer_changed_tags(self) -> None:
        facts = {
            "Revenues": {"label": "Revenues", "units": {"USD": [fact("2024-09-02", "2025-08-31", 275)]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"label": "Contract revenue", "units": {"USD": [
                fact("2024-09-02", "2025-08-31", 275),
                fact("2025-09-01", "2026-08-30", 303),
                fact("2026-05-11", "2026-08-30", 95),
            ]}},
        }
        chosen = self.desk.choose_fact(facts, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"], "revenue")
        self.assertEqual(chosen["tag"], "RevenueFromContractWithCustomerExcludingAssessedTax")
        self.assertEqual(chosen["current"]["val"], 303)  # the full year, not the quarter that ends the same day
        self.assertEqual(chosen["prior"]["val"], 275)

    def test_a_tie_goes_to_total_revenues(self) -> None:
        facts = {
            "Revenues": {"label": "Revenues", "units": {"USD": [fact("2025-02-01", "2026-01-31", 713)]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"label": "Net sales", "units": {"USD": [fact("2025-02-01", "2026-01-31", 706)]}},
        }
        chosen = self.desk.choose_fact(facts, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"], "revenue")
        self.assertEqual((chosen["tag"], chosen["current"]["val"]), ("Revenues", 713))


class ManagerRuleTests(unittest.TestCase):
    def test_a_quote_must_appear_word_for_word(self) -> None:
        source = app.normalize("Net sales for the quarter increased 11.2 percent, to $93.9 billion.\nThe Company operates 939 warehouses.")
        self.assertTrue(app.quote_found("Net sales for the quarter increased 11.2 percent, to $93.9 billion.", source))
        self.assertTrue(app.quote_found("the company  operates 939 warehouses", source))
        self.assertFalse(app.quote_found("Net sales for the quarter increased 12 percent", source))

    def test_numbers_must_trace_to_the_context(self) -> None:
        known = app.number_keys('{"value": "$303,154.0 million", "growth": "10.14%"}')
        self.assertEqual(app.untraced("Revenue was $303,154 million in fiscal 2026, up 10.14%.", known), [])
        self.assertEqual(app.untraced("Revenue was $303.2 billion.", known), ["303.2"])

    def test_the_calculator_runs_arithmetic_only(self) -> None:
        self.assertAlmostEqual(app.calculate("net_income / revenue", {"net_income": 9.0, "revenue": 300.0}), 0.03)
        with self.assertRaises(ValueError):
            app.calculate("__import__('os').getcwd()", {"revenue": 1.0})

    def test_a_json_reply_inside_a_code_fence(self) -> None:
        self.assertEqual(app.parse_json('```json\n{"recommendation": "Hold"}\n```'), {"recommendation": "Hold"})


class FakeModel:
    """Stands in for the model: each role's reply comes from a function of the packet it receives."""

    model = "fake-model"

    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.exchanges: list[dict[str, Any]] = []
        self.roles: list[str] = []

    def ask(self, role: str, instructions: str, packet: dict[str, Any]) -> dict[str, Any]:
        self.roles.append(role)
        self.exchanges.append({"role": role, "sent": packet})
        return self.replies[role](packet)


TEN_K = """Item 1. | Business | 3
Item 1A. | Risk Factors | 9
Item 1—Business
The Company operates 939 warehouses in 14 countries.
Members pay an annual fee to shop in the warehouses.
Item 1A—Risk Factors
Competition is intense.
Item 7—Management's Discussion and Analysis
Net sales increased 10 percent, driven by traffic and new warehouses.
The Company plans to open 30 new warehouses next year.
Item 7A—Quantitative and Qualitative Disclosures About Market Risk
"""
RELEASE = """Net income for the quarter was $2.998 billion, $6.75 per diluted share.
Total revenue | 95,723 | 86,156
Diluted | $6.75 | $5.87
"""


def example_desk(folder: Path) -> Desk:
    (folder / "10K.txt").write_text(TEN_K, encoding="utf-8")
    (folder / "8K.txt").write_text(RELEASE, encoding="utf-8")
    desk = Desk("Test Agent test@example.com", folder)
    desk.company, desk.ticker, desk.cik = "Example Corp", "EXM", "0000000001"
    filing = {"accepted_index": "2026-10-06 21:13:15", "acceptanceDateTime": ""}
    desk.selected = {
        "10-K": dict(filing, accessionNumber="0000000001-26-000003", reportDate="2026-08-30", saved_text=str(folder / "10K.txt")),
        "10-Q": dict(filing, accessionNumber="0000000001-26-000002", reportDate="2026-05-10"),
        "8-K": dict(filing, accessionNumber="0000000001-26-000004", reportDate="2026-09-24", exhibit99_1="ex991.htm", saved_text=str(folder / "8K.txt")),
    }

    def item(tag: str, current: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
        return {"tag": tag, "label": tag, "unit": current["unit"], "current": current, "prior": prior}

    desk.fact_rows = {
        "revenue": item("Revenues", fact("2025-09-01", "2026-08-30", 303154e6), fact("2024-09-02", "2025-08-31", 275235e6)),
        "operating_income": item("OperatingIncomeLoss", fact("2025-09-01", "2026-08-30", 11685e6), fact("2024-09-02", "2025-08-31", 10383e6)),
        "diluted_eps": item("EarningsPerShareDiluted", fact("2025-09-01", "2026-08-30", 20.76, "USD/shares"), fact("2024-09-02", "2025-08-31", 18.21, "USD/shares")),
    }
    desk.ratios = [
        {"name": "Revenue growth", "value": 0.1014, "shown": "10.14%", "arithmetic": "303,154.0 / 275,235.0 - 1"},
        {"name": "Operating margin", "value": 0.0385, "shown": "3.85%", "arithmetic": "11,685.0 / 303,154.0"},
    ]
    desk.quarter = {
        "revenue_line": "Total revenue | 95,723 | 86,156", "revenue": 95723.0, "revenue_prior": 86156.0, "revenue_growth": 0.1110,
        "eps_line": "Diluted | $6.75 | $5.87", "eps": 6.75, "eps_prior": 5.87, "revenue_headers": [], "eps_heading": None, "sentence": None,
    }
    peer_item = {"tag": "Revenues", "current": {"val": 713163e6}}
    desk.peers = [{
        "company": "Peer Inc", "ticker": "PEER", "fiscal_year_end": "2026-01-31", "ten_k": "0000000002-26-000001",
        "facts": {"revenue": peer_item, "operating_income": {"tag": "OperatingIncomeLoss", "current": {"val": 29825e6}}}, "operating_margin": 0.0418,
    }]
    return desk


def research(packet: dict[str, Any]) -> dict[str, Any]:
    claim = {"claim": "The company operates 939 warehouses.", "quote": "The Company operates 939 warehouses in 14 countries.", "source": "10-K Item 1"}
    plan = {"claim": "The company plans 30 new warehouses next year.", "quote": "The Company plans to open 30 new warehouses next year.", "source": "10-K Item 7"}
    insight = {"claim": "The company operates 939 warehouses in 14 countries.", "source": "10-K Item 1", "line": "The Company operates 939 warehouses in 14 countries."}
    return {"overview": [claim], "business_model": [claim], "competitive_position": [claim], "catalysts": [plan], "recent_developments": [plan], "insight": insight}


GOOD_ANALYSIS = {
    "calculator_requests": [],
    "statement_analysis": "Total revenue was $303,154.0 million (us-gaap:Revenues, 10-K), up 10.14% = 303,154.0 / 275,235.0 - 1.",
    "latest_quarter": "The quarter's total revenue was 95,723, up 11.10% on 86,156; GAAP diluted EPS was $6.75 (release line).",
    "peer_comparison": "| Company | Operating margin |\n|---|---|\n| EXM | 3.85% |\n| PEER | 4.18% |",
    "valuation": "No price was given, so there is no P/E; the operating margin is 3.85% on total revenue.",
    "definitions": ["Total revenue, not net sales."],
    "insight": {"claim": "The operating margin was 3.85% = 11,685.0 / 303,154.0.", "source": "10-K, computed in code",
                "line": "us-gaap:OperatingIncomeLoss, 2025-09-01 to 2026-08-30"},
}


def advisor(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "recommendation": "Hold",
        "deciding_number": {"label": "Revenue growth", "value": "10.14%", "source": "Financial Analyst, 10-K"},
        "thesis": "Revenue grew 10.14% on total revenue, but the operating margin of 3.85% is below the peer's 4.18%, so the case is balanced.",
        "what_would_change_it": "A margin above the peer's.",
        "strategic_recommendations": ["Watch the quarter's growth of 11.10%."],
        "insight": {"claim": "The company runs 939 warehouses at an operating margin of 3.85%.", "source": "10-K Item 1",
                    "line": "The Company operates 939 warehouses in 14 countries."},
    }


class StrategyManagerTests(unittest.TestCase):
    def manager(self, replies: dict[str, Any]) -> tuple[app.StrategyManager, FakeModel]:
        folder = Path(tempfile.mkdtemp())
        model = FakeModel(replies)
        return app.StrategyManager(example_desk(folder), model, None, "none", app.datetime.now().astimezone(), "Claude Code"), model

    def test_a_clean_run_compiles_five_parts(self) -> None:
        manager, model = self.manager({"Research Analyst": research, "Financial Analyst": lambda p: GOOD_ANALYSIS, "Investment Advisor": advisor})
        report = manager.run().read_text(encoding="utf-8").splitlines()
        self.assertTrue(report[0].startswith("Filings read: 10-K 0000000001-26-000003"))
        self.assertTrue(report[1].startswith("Run time: "))
        for number, part in enumerate(app.PARTS, 1):
            self.assertIn(f"## {number}. {part}", report)
        self.assertEqual(model.roles, ["Research Analyst", "Financial Analyst", "Investment Advisor"])
        self.assertIn("- Parts sent back once: none", report)
        self.assertTrue((manager.desk.outdir / "audit.md").exists())

    def test_a_number_the_desk_never_gave_is_sent_back_once(self) -> None:
        replies = iter([dict(GOOD_ANALYSIS, statement_analysis="Revenue was about $303.2 billion, up roughly 10%."), GOOD_ANALYSIS])
        manager, model = self.manager({"Research Analyst": research, "Financial Analyst": lambda p: next(replies), "Investment Advisor": advisor})
        manager.run()
        self.assertEqual(model.roles.count("Financial Analyst"), 2)
        self.assertIn("303.2", " ".join(model.exchanges[2]["sent"]["manager_feedback"]))


class NoCompanyNamedInCodeTests(unittest.TestCase):
    def test_the_desk_code_names_no_company(self) -> None:
        for name in ("lab02_desk.py", "lab03_app.py", "prices.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL)\b", source), name)
            self.assertIsNone(re.search(r"costco|walmart|target corp|wholesale club|apple inc", source, re.I), name)


if __name__ == "__main__":
    unittest.main()
