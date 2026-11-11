"""Offline tests of Lab 05's Insight lines: the two Strategy Manager checks, the report, and the Verifier.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lab03_app as app  # noqa: E402
import verifier  # noqa: E402
from test_desk import GOOD_ANALYSIS, FakeModel, advisor, example_desk, research  # noqa: E402

RELEASE = """EX-99.1 2 ex991.htm EX-99.1 Document
Exhibit 99.1
Press Release
EXAMPLE CORP REPORTS FOURTH QUARTER RESULTS
CITY, State, September 24, 2026 - Example Corp today announced its operating results for the 16-week fourth quarter.
Net sales for the quarter increased 11.2 percent, to $93.9 billion, from $84.4 billion last year.
"""


class FirstParagraphTests(unittest.TestCase):
    def test_the_exhibit_header_is_left_out(self) -> None:
        text = app.first_paragraph(RELEASE)
        self.assertTrue(text.startswith("EXAMPLE CORP REPORTS"))
        self.assertIn("$93.9 billion", text)

    def test_it_stops_near_1000_characters(self) -> None:
        release = "Headline\n" + "\n".join(f"Paragraph {i} " + "x" * 300 for i in range(10))
        self.assertLess(len(app.first_paragraph(release)), 1400)

    def test_a_figure_in_other_units_is_the_same_figure(self) -> None:
        paragraph = app.first_paragraph(RELEASE)
        self.assertTrue(app.only_restates("Net sales rose 11.2% to $93,873 million.", paragraph))
        self.assertFalse(app.only_restates("Membership fees reached $1,850 million.", paragraph))
        self.assertFalse(app.only_restates("Net sales rose 11.2% while fees reached $1,850 million.", paragraph))
        self.assertFalse(app.only_restates("The company has 939 warehouses in 14 countries.", paragraph))
        # A rounder figure may be another measure: membership fees up 11% is not net sales up 11.2 percent.
        self.assertFalse(app.only_restates("Membership fee revenue increased 11% in 2026.", paragraph))
        self.assertTrue(app.only_restates("Net sales increased 11.2 percent in the quarter.", paragraph))

    def test_years_days_and_week_counts_are_not_figures(self) -> None:
        self.assertEqual(app.figures("In the 16 weeks to August 30, 2026"), [])


class InsightCheckTests(unittest.TestCase):
    def run_manager(self, financial: Any) -> tuple[list[str], FakeModel]:
        model = FakeModel({"Research Analyst": research, "Financial Analyst": financial, "Investment Advisor": advisor})
        manager = app.StrategyManager(example_desk(Path(tempfile.mkdtemp())), model, None, "none", app.datetime.now().astimezone(), "Claude Code")
        with contextlib.redirect_stdout(io.StringIO()):
            path = manager.run()
        return path.read_text(encoding="utf-8").splitlines(), model

    def test_three_insight_lines_reach_the_report(self) -> None:
        report, model = self.run_manager(lambda p: GOOD_ANALYSIS)
        insights = [line for line in report if line.startswith("Insight:")]
        self.assertEqual(len(insights), 3)
        self.assertTrue(insights[0].endswith('(Research Analyst; 10-K Item 1: "The Company operates 939 warehouses in 14 countries.")'))
        self.assertIn("- Insight lines, one from each analyst: 3 of 3", report)
        self.assertIn("- Parts sent back once: none", report)
        # Each role is told what the first paragraph says, so that it can say something else.
        self.assertIn(app.FIRST_PARAGRAPH, model.exchanges[0]["sent"]["context"])
        self.assertEqual(list(model.exchanges[2]["sent"]["expected_output"])[-1], "insight")

    def test_a_part_without_an_insight_goes_back_once(self) -> None:
        missing = {k: v for k, v in GOOD_ANALYSIS.items() if k != "insight"}
        replies = iter([missing, GOOD_ANALYSIS])
        _, model = self.run_manager(lambda p: next(replies))
        self.assertEqual(model.roles.count("Financial Analyst"), 2)
        self.assertTrue(any(f.startswith("insight: missing") for f in model.exchanges[2]["sent"]["manager_feedback"]))

    def test_an_insight_that_restates_the_first_paragraph_goes_back_once(self) -> None:
        headline = dict(GOOD_ANALYSIS, insight={"claim": "The quarter's diluted EPS was $6.75.", "source": "Earnings release", "line": "Diluted | $6.75 | $5.87"})
        replies = iter([headline, headline])
        report, model = self.run_manager(lambda p: next(replies))
        self.assertEqual(model.roles.count("Financial Analyst"), 2)
        self.assertTrue(any("only restates" in f for f in model.exchanges[2]["sent"]["manager_feedback"]))
        self.assertTrue(any(line.startswith("- Still open after the send-back, Financial Analyst: insight: the claim only restates") for line in report))

    def test_an_insight_line_must_be_in_the_filings(self) -> None:
        made_up = dict(GOOD_ANALYSIS, insight={"claim": "Fees grew 7.31%.", "source": "Earnings release", "line": "Membership fees grew 7.31%"})
        replies = iter([made_up, GOOD_ANALYSIS])
        _, model = self.run_manager(lambda p: next(replies))
        feedback = " ".join(model.exchanges[2]["sent"]["manager_feedback"])
        self.assertIn("not in the filings word for word", feedback)
        self.assertIn("7.31", feedback)


class VerifierInsightTests(unittest.TestCase):
    def test_the_verifier_reads_every_insight_line(self) -> None:
        lines = ["Filings read", "Run time", "Partner's check", "## 5. Investment Recommendation", "**Recommendation: Hold.**",
                 "The thesis says 999.", 'Insight: The margin was 3.85% (Investment Advisor; 10-K: "Operating income | 11,685")']
        kept = [number for number, _ in verifier.lines_to_check(lines)]
        self.assertEqual(kept, [5, 7])


if __name__ == "__main__":
    unittest.main()
