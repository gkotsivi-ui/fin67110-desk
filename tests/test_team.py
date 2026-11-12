"""Offline tests of the agent team and the Verifier: no network and no model key.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import team  # noqa: E402
import verifier  # noqa: E402
from lab03_app import StrategyManager  # noqa: E402
from test_desk import (  # noqa: E402
    CURRENT,
    GOOD_ANALYSIS,
    LAST_YEAR_END,
    NONCURRENT,
    YEAR_END,
    advisor,
    desk_after_steps_4_and_5,
    example_desk,
    fact,
    research,
)

TEN_K_LINES = ("Net income increased 14% to $9,226, $20.76 per diluted share, compared to $8,099.\n"
               "Total revenue | 303,154 | 275,235 | 254,453\nDiluted | $20.76 | $18.21 | $16.56\n")
RELEASE_LINES = "Total revenue | 95,723 | 86,156 | 303,154 | 275,235\n"
FACTS = {"ticker": "EXM", "facts": {
    "revenue": {"tag": "Revenues", "label": "Revenues", "unit": "USD",
                "current": {"start": "2025-09-01", "end": "2026-08-30", "val": 303154e6}, "prior": {"start": "2024-09-02", "end": "2025-08-31", "val": 275235e6}},
    "diluted_eps": {"tag": "EarningsPerShareDiluted", "label": "EPS", "unit": "USD/shares",
                    "current": {"start": "2025-09-01", "end": "2026-08-30", "val": 20.76}, "prior": {"start": "2024-09-02", "end": "2025-08-31", "val": 18.21}},
}}
REPORT = [
    "Filings read: 10-K 0000000001-26-000003",
    "Run time: test",
    "Partner's check: ",
    "## 1. Overview",
    "| 5 | Diluted EPS, GAAP | $21.76 | 10-K per-share line: Diluted \\| $21.76 \\| $18.21 \\| $16.56 |",
    "- Total revenue was **$303,154.0 million** (us-gaap:Revenues, 2025-09-01 to 2026-08-30).",
    "- Revenue growth was **14.14%** = 303,154.0 / 275,235.0 - 1.",
    "- Price: $992.13, the close of 2026-10-27.",
    '- The quarter\'s total revenue was 95,723 (release line: "Total revenue | 95,723 | 86,156").',
    "- Margins were strong at 12.3%.",
    "## 5. Investment Recommendation",
    "**Recommendation: Hold.**",
    "The thesis says revenue might reach 999,999.",
]
READ = {"numbers": [
    {"line": 5, "number": "$21.76", "what": "diluted EPS", "scale": "per_share", "fact": "diluted_eps", "source": {"type": "line", "document": "10-K", "line": "Diluted | $21.76 | $18.21 | $16.56"}},
    {"line": 6, "number": "$303,154.0", "what": "total revenue", "scale": "millions", "fact": "revenue", "source": {"type": "xbrl", "tag": "us-gaap:Revenues", "period_end": "2026-08-30"}},
    {"line": 7, "number": "14.14%", "what": "revenue growth", "scale": "percent", "source": {"type": "ratio", "arithmetic": "303,154.0 / 275,235.0 - 1"}},
    {"line": 8, "number": "$992.13", "what": "price", "scale": "per_share", "source": {"type": "price"}},
    {"line": 9, "number": "95,723", "what": "quarter revenue", "scale": "millions", "source": {"type": "line", "document": "release", "line": "Total revenue | 95,723 | 86,156"}},
    {"line": 10, "number": "12.3%", "what": "margin", "scale": "percent", "source": {"type": "none"}},
    {"line": 13, "number": "999,999", "what": "a thesis number", "scale": "millions", "source": {"type": "none"}},
]}


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


def saved_run(report: list[str], ten_k: str = TEN_K_LINES, facts: dict[str, Any] = FACTS) -> Path:
    folder = Path(tempfile.mkdtemp())
    (folder / "10K_test.txt").write_text(ten_k, encoding="utf-8")
    (folder / "8K_test.txt").write_text(RELEASE_LINES, encoding="utf-8")
    (folder / "facts.json").write_text(json.dumps(facts), encoding="utf-8")
    (folder / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return folder


class VerifierTests(unittest.TestCase):
    def verify(self) -> tuple[dict[str, Any], Path]:
        folder = saved_run(REPORT)
        model = FakeModel({"Verifier (reader)": lambda p: READ, "Verifier (line check)": lambda p: {"checks": [{"id": i["id"], "states_it": True} for i in p["context"]["items"]]}})
        with contextlib.redirect_stdout(io.StringIO()):
            result = verifier.verify_run(folder, model)
        return {r["line"]: r for r in result["records"]}, folder

    def test_the_seeded_eps_is_wrong_and_corrected_from_the_10k_line(self) -> None:
        marks, _ = self.verify()
        self.assertEqual(marks[5]["mark"], "wrong")
        self.assertEqual(marks[5]["correction"], "$20.76")
        self.assertIn("Diluted | $20.76 | $18.21 | $16.56", marks[5]["real"])

    def test_an_invented_growth_rate_is_recomputed(self) -> None:
        marks, _ = self.verify()
        self.assertEqual((marks[7]["mark"], marks[7]["correction"]), ("wrong", "10.14%"))

    def test_correct_unsupported_and_unchecked_numbers(self) -> None:
        marks, _ = self.verify()
        self.assertEqual(marks[6]["mark"], "correct")  # the tag and period equal the facts file
        self.assertEqual(marks[9]["mark"], "correct")  # the line is in the release, and the model says it states the number
        self.assertEqual(marks[10]["mark"], "unsupported")  # no source
        self.assertEqual(marks[8]["mark"], "not checked")  # a price is not a filing figure

    def test_the_thesis_is_skipped_and_the_marks_sit_under_the_first_line(self) -> None:
        marks, folder = self.verify()
        self.assertNotIn(13, marks)
        lines = (folder / "verified_report.md").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], REPORT[0])
        self.assertEqual(lines[2], "## Verifier's marks")
        self.assertTrue(any(line.startswith(REPORT[4]) and "[Verifier: $21.76 is wrong" in line for line in lines))

    def test_a_restated_number_carries_its_source_but_a_fabricated_quote_does_not(self) -> None:
        report = REPORT[:4] + [
            "- Revenue growth was **10.14%** = 303,154.0 / 275,235.0 - 1.",
            "- In short, revenue grew 10.14% and EPS reached $20.76.",
            '- The 10-K says "Revenue grew 10.14% to a record" (10-K).',
        ]
        read = {"numbers": [
            {"line": 5, "number": "10.14%", "scale": "percent", "source": {"type": "ratio", "arithmetic": "303,154.0 / 275,235.0 - 1"}},
            {"line": 6, "number": "10.14%", "scale": "percent", "source": {"type": "none"}},
            {"line": 6, "number": "$20.76", "scale": "per_share", "fact": "diluted_eps", "source": {"type": "none"}},
            {"line": 7, "number": "10.14%", "scale": "percent", "source": {"type": "line", "document": "10-K", "line": "Revenue grew 10.14% to a record"}},
        ]}
        model = FakeModel({"Verifier (reader)": lambda p: read, "Verifier (line check)": lambda p: {"checks": []}})
        with contextlib.redirect_stdout(io.StringIO()):
            records = verifier.verify_run(saved_run(report), model)["records"]
        marks = [(r["line"], r["number"], r["mark"]) for r in records]
        self.assertEqual(marks, [(5, "10.14%", "correct"), (6, "10.14%", "correct"), (6, "$20.76", "unsupported"), (7, "10.14%", "unsupported")])

    def test_a_ratio_is_recomputed_from_its_numbers_not_its_names(self) -> None:
        self.assertAlmostEqual(verifier.recompute("(quarter_eps - 0.15) / quarter_eps_prior - 1 = (6.75 - 0.15) / 5.87 - 1"), 6.60 / 5.87 - 1)
        self.assertAlmostEqual(verifier.recompute("992.13 / 20.76 (price / diluted EPS)"), 992.13 / 20.76)
        self.assertAlmostEqual(verifier.recompute("303,154.0 / 275,235.0 - 1 ($ millions)"), 303154.0 / 275235.0 - 1)
        self.assertIsNone(verifier.recompute("net_income / revenue"))

    def test_a_second_verification_never_overwrites_the_first(self) -> None:
        _, folder = self.verify()
        model = FakeModel({"Verifier (reader)": lambda p: READ, "Verifier (line check)": lambda p: {"checks": []}})
        with contextlib.redirect_stdout(io.StringIO()):
            verifier.verify_run(folder, model)
        self.assertEqual(len(list(folder.glob("verified_report*.md"))), 2)


def marks_of(report: list[str], read: list[dict[str, Any]], line_check: Any = None, **saved: Any) -> list[dict[str, Any]]:
    """The Verifier's records for a made-up report, with a stand-in for each of its two model calls."""
    says_yes = lambda p: {"checks": [{"id": i["id"], "states_it": True} for i in p["context"]["items"]]}  # noqa: E731
    model = FakeModel({"Verifier (reader)": lambda p: {"numbers": read}, "Verifier (line check)": line_check or says_yes})
    with contextlib.redirect_stdout(io.StringIO()):
        return verifier.verify_run(saved_run(REPORT[:4] + report, **saved), model)["records"]


def ratio(line: int, number: str, arithmetic: str, scale: str = "percent") -> dict[str, Any]:
    return {"line": line, "number": number, "scale": scale, "source": {"type": "ratio", "arithmetic": arithmetic}}


class FalseFlagTests(unittest.TestCase):
    """Three kinds of correct number that the Verifier marked wrong or unsupported on a real run on 2026-11-11.
    A verifier that flags correct numbers costs as much as one that misses wrong ones. Made-up numbers."""

    FALL = "960.0 / 1,000.0 - 1"  # -4.00%
    MARGINS = dict(FACTS, facts=dict(FACTS["facts"], operating_income={
        "tag": "OperatingIncomeLoss", "label": "Operating income", "unit": "USD",
        "current": {"start": "2025-09-01", "end": "2026-08-30", "val": 11685e6}, "prior": {"start": "2024-09-02", "end": "2025-08-31", "val": 10383e6}}))
    CHANGE = "operating_income / revenue - operating_income_prior / revenue_prior"  # 3.8545% - 3.7724% = 0.0821 points

    def test_a_decline_written_as_a_positive_number(self) -> None:
        report = ["- As a result, free cash flow fell 4.00% and stayed below net income.",
                  "- Free cash flow was 4.00% lower.",
                  "- A decline of 4.00% in free cash flow.",
                  "- Free cash flow changed by -4.00%."]
        records = marks_of(report, [ratio(n, "-4.00%" if n == 8 else "4.00%", self.FALL) for n in (5, 6, 7, 8)])
        self.assertEqual([r["mark"] for r in records], ["correct"] * 4)
        self.assertIn("decline", records[0]["code"])

    def test_a_rise_that_was_a_fall_is_still_wrong(self) -> None:
        # The words directly beside the number must say that it is a decline. A level is not a decline:
        # "narrowed to 4.00%" gives a level, and a level of -4.00% written as 4.00% is an error.
        report = ["- Free cash flow grew 4.00%.",
                  "- Revenue grew 4.00% while costs fell.",
                  "- Costs fell, and free cash flow grew 4.00%.",
                  "- The margin narrowed to 4.00%."]
        records = marks_of(report, [ratio(n, "4.00%", self.FALL) for n in (5, 6, 7, 8)])
        self.assertEqual([(r["mark"], r["correction"]) for r in records], [("wrong", "-4.00%")] * 4)

    def test_the_words_beside_a_number_that_say_it_is_a_decline(self) -> None:
        for line in ("fell 4.00%", "fell by about 4.00%", "a decrease of 4.00%", "down 4.00%", "was 4.00% lower", "a 4.00% decline", "fell $4.00 million"):
            self.assertTrue(verifier.says_decline(line, "4.00"), line)
        for line in ("grew 4.00%", "narrowed to 4.00%", "down from 4.00%", "fell 14.00%", "costs fell and it rose 4.00%"):
            self.assertFalse(verifier.says_decline(line, "4.00"), line)

    def test_arithmetic_that_names_saved_facts_is_redone_from_the_facts_file(self) -> None:
        report = [f"| Operating margin | +0.08 margin points (0.0008 = {self.CHANGE}) |",
                  "- Revenue rose by $27,919.0 million (revenue - revenue_prior).",
                  "- Revenue grew 10.14% (revenue / revenue_prior - 1, in $ millions).",
                  "- The operating margin widened by 0.08 points."]
        read = [ratio(5, "+0.08", self.CHANGE, "ratio"), ratio(5, "0.0008", self.CHANGE, "ratio"),
                ratio(6, "$27,919.0", "revenue - revenue_prior", "millions"),
                ratio(7, "10.14%", "revenue / revenue_prior - 1, in $ millions"),
                {"line": 8, "number": "0.08", "scale": "ratio", "source": {"type": "none"}}]
        records = marks_of(report, read, facts=self.MARGINS)
        self.assertEqual([r["mark"] for r in records], ["correct"] * 5)
        self.assertIn("from the saved facts", records[0]["code"])
        self.assertIn("restates line 5", records[4]["code"])

    def test_a_wrong_result_of_named_arithmetic_is_corrected_from_the_facts_file(self) -> None:
        records = marks_of(["- Revenue rose by $28,919.0 million (revenue - revenue_prior)."],
                           [ratio(5, "$28,919.0", "revenue - revenue_prior", "millions")])
        self.assertEqual((records[0]["mark"], records[0]["correction"]), ("wrong", "27,919.0"))

    def test_a_name_that_is_not_a_saved_fact_is_not_redone(self) -> None:
        records = marks_of(["- EPS grew 15.0% (quarter_eps / quarter_eps_prior - 1)."], [ratio(5, "15.0%", "quarter_eps / quarter_eps_prior - 1")])
        self.assertEqual(records[0]["mark"], "unsupported")
        self.assertIsNone(verifier.recompute_named("__import__('os').getcwd()", {"revenue": 1.0}))

    def test_less_than_stays_with_its_figure_for_the_line_check(self) -> None:
        ten_k = TEN_K_LINES + "Large customers were approximately 6% of total revenue compared with less than 2% a year earlier.\n"
        report =['Insight: Large customers were about 6% of revenue, up from less than 2%. (10-K: "Large customers were approximately 6% of total revenue compared with less than 2% a year earlier.")']
        source = {"type": "line", "document": "10-K", "line": "Large customers were approximately 6% of total revenue compared with less than 2% a year earlier."}
        asked: list[str] = []

        def strict(packet: dict[str, Any]) -> dict[str, Any]:
            """A model that says a line states "2%" only when the question keeps the words "less than"."""
            asked.extend(i["number"] for i in packet["context"]["items"])
            return {"checks": [{"id": i["id"], "states_it": i["number"] in ("about 6%", "less than 2%")} for i in packet["context"]["items"]]}

        records = marks_of(report, [{"line": 5, "number": "6%", "scale": "percent", "source": source},
                                    {"line": 5, "number": "2%", "scale": "percent", "source": source}], strict, ten_k=ten_k)
        self.assertEqual(asked, ["about 6%", "less than 2%"])
        self.assertEqual([r["mark"] for r in records], ["correct", "correct"])
        self.assertEqual(verifier.qualified("2%", "It rose 2% to less than 20%."), "2%")


def offline_desk() -> Any:
    folder = Path(tempfile.mkdtemp())
    desk = example_desk(folder)
    # The Verifier reads the run folder the way the steps save it.
    (folder / "10K_test.txt").write_text((folder / "10K.txt").read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "8K_test.txt").write_text((folder / "8K.txt").read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "facts.json").write_text(json.dumps({"ticker": desk.ticker, "facts": desk.fact_rows}), encoding="utf-8")
    (folder / "peer_facts.json").write_text(json.dumps(desk.peers), encoding="utf-8")
    return desk


class OfflineTeam(team.Team):
    """The real graph, with steps that use a saved example instead of EDGAR."""

    def __init__(self, model: Any, desk: Any) -> None:
        super().__init__({"user_agent": "", "prices_key": "", "run_time": datetime.now().astimezone(), "tools": "Claude Code"}, model)
        self.desk = desk

    def steps(self, state: team.TeamState) -> dict[str, Any]:
        self.starting("steps")
        manager = StrategyManager(self.desk, self.model, None, "none", self.settings["run_time"], "Claude Code")
        self.save(state, "steps", {}, {})
        return {"desk": self.desk, "manager": manager, "price": None, "more": team.more_ratios(self.desk), "outputs": {},
                "runs": {a: 0 for a in team.ANALYSTS}, "feedback": {}, "sent_back": [], "calculator": []}


def reader(packet: dict[str, Any]) -> dict[str, Any]:
    """Reads the revenue row of the compiled report's core-figures table."""
    for line in packet["context"]["report_lines"]:
        if line["text"].startswith("| 1 | Total revenue"):
            return {"numbers": [{"line": line["line"], "number": "$303,154.0M", "scale": "millions", "fact": "revenue", "what": "total revenue",
                                 "source": {"type": "xbrl", "tag": "us-gaap:Revenues", "period_end": "2026-08-30"}}]}
    return {"numbers": []}


class GraphTests(unittest.TestCase):
    def run_team(self, financial: Any) -> tuple[list[str], Path, FakeModel]:
        desk = offline_desk()
        model = FakeModel({"Research Analyst": research, "Financial Analyst": financial, "Investment Advisor": advisor,
                           "Verifier (reader)": reader, "Verifier (line check)": lambda p: {"checks": []}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            final = OfflineTeam(model, desk).graph().invoke({"ticker": "EXM", "peers": [], "price": None, "run_dir": str(desk.outdir)}, {"recursion_limit": 40})
        printed = re.findall(r"^=== (.+) ===$", out.getvalue(), re.M)
        self.assertTrue(Path(final["verified_path"]).exists())
        return printed, desk.outdir, model

    def test_the_nodes_run_in_the_fixed_order_and_the_verifier_runs(self) -> None:
        printed, folder, _ = self.run_team(lambda p: GOOD_ANALYSIS)
        self.assertEqual(printed, ["The steps", "Research Analyst", "Financial Analyst", "Investment Advisor", "Strategy Manager", "Verifier"])
        self.assertEqual([p.name.split("_", 1)[1] for p in sorted((folder / "nodes").glob("*.json"))],
                         ["steps.json", "research_analyst.json", "financial_analyst.json", "investment_advisor.json", "strategy_manager.json", "verifier.json"])
        self.assertIn("**correct**", (folder / "verified_report.md").read_text(encoding="utf-8"))

    def test_a_failing_part_goes_back_once_and_no_role_runs_three_times(self) -> None:
        # Only the Financial Analyst errs: it keeps the 10.14% the Investment Advisor cites.
        bad = dict(GOOD_ANALYSIS, statement_analysis="Revenue was about $303.2 billion, up 10.14% = 303,154.0 / 275,235.0 - 1.")
        replies = iter([bad, bad])
        printed, _, model = self.run_team(lambda p: next(replies))
        self.assertEqual(printed, ["The steps", "Research Analyst", "Financial Analyst", "Investment Advisor", "Strategy Manager",
                                   "Financial Analyst", "Strategy Manager", "Verifier"])
        self.assertEqual(model.roles.count("Financial Analyst"), 2)


class PriorYearDebtTests(unittest.TestCase):
    """The extra ratios the desk computes for the Financial Analyst, on made-up facts."""

    def prior_year(self, debt: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        desk, _ = desk_after_steps_4_and_5(debt)
        return [r for r in team.more_ratios(desk) if r["name"] == "Debt to equity, prior year"]

    def test_the_prior_year_ratio_uses_the_prior_years_two_parts(self) -> None:
        ratios = self.prior_year({
            NONCURRENT: [fact(None, LAST_YEAR_END, 4000e6), fact(None, YEAR_END, 5000e6)],
            CURRENT: [fact(None, LAST_YEAR_END, 50e6), fact(None, YEAR_END, 100e6)],
        })
        self.assertEqual([(r["shown"], r["arithmetic"]) for r in ratios], [("0.225", "(4,000.0 + 50.0) / 18,000.0")])

    def test_no_prior_year_ratio_when_a_part_is_missing(self) -> None:
        self.assertEqual(self.prior_year({NONCURRENT: [fact(None, LAST_YEAR_END, 4000e6), fact(None, YEAR_END, 5000e6)],
                                          CURRENT: [fact(None, YEAR_END, 100e6)]}), [])


class SkipTests(unittest.TestCase):
    def test_every_path_to_the_end_runs_the_verifier(self) -> None:
        edges = OfflineTeam(FakeModel({}), None).graph().get_graph().edges
        into_end = {e.source for e in edges if e.target == "__end__"}
        self.assertEqual(into_end, {"verifier"})
        self.assertIn(("strategy_manager", "verifier"), {(e.source, e.target) for e in edges})

    def test_no_option_turns_the_verifier_off(self) -> None:
        options = re.findall(r'add_argument\("(--[\w-]+)"', (ROOT / "team.py").read_text(encoding="utf-8"))
        self.assertEqual(options, ["--peers", "--price", "--filed", "--verify-only"])

    def test_the_team_code_names_no_company(self) -> None:
        for name in ("team.py", "verifier.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT)\b", source), name)
            self.assertIsNone(re.search(r"costco|walmart|target corp|wholesale club|apple inc|microsoft", source, re.I), name)


if __name__ == "__main__":
    unittest.main()
