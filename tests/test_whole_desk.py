"""The whole desk, one run, with nothing real outside it: made-up SEC pages, a stand-in closes reader, and a
scripted model in place of the provider.

Every part runs as desk.py runs it: the settings check, the seven data steps on SEC pages, the five roles through
CrewAI with their file reads, the claims ledger, the Verifier, the worksheet and its hook, the final report, the
replay, and the check of what a live run would make public. Until 2026-11-22 no test ran the parts together; each
practice run found the next problem, and the last runs before the audit stopped for lack of model credit before
they reached a report. The company, its filings, its prices and every amount are made up.
"""
from contextlib import redirect_stdout
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

import requests

import check_pipeline
import check_public
import desk
import equity_research_agent_team as team
from desk_parts import Parts
from desk_role_contracts import report_catalog
from desk_rules import FOOTER_FIRST, FOOTER_LAST
from desk_stub_llm import StubLLM, tool_call
from portable import local_sockets_only

CIK, TICKER = "0000999999", "ZZZZ"
TEN_K, TEN_Q, EIGHT_K = "0000999999-26-000010", "0000999999-26-000020", "0000999999-26-000030"
END, PRIOR_END = "2026-08-30", "2025-08-31"
STARTED = datetime.fromisoformat("2026-11-17T09:12:13.123456-05:00")
SALES_LINE = "Net sales increased 11.2 percent, to $93.9 billion."


def page(*lines, table=None):
    rows = "" if table is None else "<table>" + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in table) + "</table>"
    return "<html><body>" + "".join(f"<p>{line}</p>" for line in lines) + rows + "</body></html>"


def index(accepted, files):
    rows = "".join(f"<tr><td>{n}</td><td>a document</td><td><a href='/x/{name}'>{name}</a></td><td>{kind}</td><td>1</td></tr>" for n, (kind, name) in enumerate(files, 1))
    return f"<html><body><div>Accepted</div><div>{accepted}</div><table>{rows}</table></body></html>"


def folder(accession):
    return f"https://www.sec.gov/Archives/edgar/data/999999/{accession.replace('-', '')}"


def fact(value, end, start=None):
    row = {"val": value, "end": end, "accn": TEN_K, "fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-10-10"}
    return {**row, "start": start} if start else row


def two_years(now, before, unit="USD", duration=True):
    rows = [fact(now, END, "2025-09-01" if duration else None), fact(before, PRIOR_END, "2024-09-02" if duration else None)]
    return {"units": {unit: rows}}


def third_year(item, value):
    """The same fact for the year before last: a 10-K's income and cash flow statements print three years, and the
    worksheet uses a statement row only when the company's XBRL facts hold it for that year (2026-11-25)."""
    item["units"]["USD"].append(fact(value, "2024-09-01", "2023-09-04"))
    return item


YEARS = ["Years ended", "August 30, 2026", "August 31, 2025", "September 1, 2024"]
ANNUAL = page(
    "The number of shares outstanding of the registrant’s common stock as of September 29, 2026, was", "10,000,000", ".",
    "Item 1. Business", "Made Up Stores sells made-up goods to members.", SALES_LINE,
    "Item 2. Properties", "The company owns its stores.",
    "Item 7. Management's Discussion and Analysis", "Results improved in the year.",
    "Item 8. Financial Statements",
    "CONSOLIDATED STATEMENTS OF INCOME", "(amounts in millions)", *YEARS, "NET INCOME", "$", "100", "90", "80",
    "CONSOLIDATED STATEMENTS OF CASH FLOWS", "(amounts in millions)", *YEARS, "Net income", "$", "100", "90", "80",
    "Depreciation and amortization", "20", "25", "30", "Additions to property and equipment", "(30)", "(25)", "(20)")
RELEASE = page("Made Up Stores reports third quarter results", "Condensed Consolidated Statements of Income (in millions, except per share data)",
               table=[["", "Three Months Ended"], ["", "November 1, 2026", "November 2, 2025"],
                      ["Total revenue", "300", "250"], ["Diluted earnings per share", "2.50", "2.00"]])
FACTS = {"facts": {"us-gaap": {
    "Revenues": two_years(1000e6, 800e6), "OperatingIncomeLoss": two_years(150e6, 100e6), "NetIncomeLoss": third_year(two_years(100e6, 90e6), 80e6),
    "EarningsPerShareDiluted": two_years(10.0, 9.0, "USD/shares"), "StockholdersEquity": two_years(500e6, 400e6, duration=False),
    "LongTermDebtNoncurrent": two_years(200e6, 180e6, duration=False), "LongTermDebtCurrent": two_years(50e6, 20e6, duration=False),
    "NetCashProvidedByUsedInOperatingActivities": two_years(120e6, 110e6), "PaymentsToAcquirePropertyPlantAndEquipment": third_year(two_years(30e6, 25e6), 20e6),
    "DepreciationDepletionAndAmortization": third_year(two_years(20e6, 25e6), 30e6)}}}
FILINGS = [("8-K", EIGHT_K, "2026-11-16", "", "eightk.htm", "2.02,9.01"), ("10-K", TEN_K, "2026-10-10", END, "tenk.htm", ""),
           ("10-Q", TEN_Q, "2026-06-20", "2026-05-10", "tenq.htm", "")]
KEYS = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument", "items")
SEC = {
    "https://www.sec.gov/files/company_tickers.json": {"0": {"cik_str": 999999, "ticker": TICKER, "title": "Made Up Stores"}},
    f"https://data.sec.gov/submissions/CIK{CIK}.json": {"sicDescription": "Retail", "filings": {"files": [], "recent": {key: [row[i] for row in FILINGS] for i, key in enumerate(KEYS)}}},
    f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json": FACTS,
    f"{folder(TEN_K)}/{TEN_K}-index.html": index("2026-10-10 16:10:00", [("10-K", "tenk.htm")]),
    f"{folder(TEN_Q)}/{TEN_Q}-index.html": index("2026-06-20 16:10:00", [("10-Q", "tenq.htm")]),
    f"{folder(EIGHT_K)}/{EIGHT_K}-index.html": index("2026-11-16 16:05:00", [("8-K", "eightk.htm"), ("EX-99.1", "release.htm")]),
    f"{folder(TEN_K)}/tenk.htm": ANNUAL, f"{folder(TEN_Q)}/tenq.htm": page("A made-up quarterly report."), f"{folder(EIGHT_K)}/release.htm": RELEASE,
}
SETTINGS = {"SEC_USER_AGENT": "Pat Example pat.example@school.example", "API_KEY": "sk-ant-made-up-0123456789", "MODEL": "anthropic/a-made-up-model"}


def sec(url, **kwargs):
    """The made-up SEC EDGAR. A page the test did not make is a page the desk should not have asked for."""
    if url not in SEC:
        raise AssertionError("The desk asked SEC EDGAR for a page the test did not make: " + url)
    answer = requests.Response()
    answer.status_code = 200
    answer._content = (SEC[url] if isinstance(SEC[url], str) else json.dumps(SEC[url])).encode("utf-8")
    assert kwargs["headers"]["User-Agent"] == SETTINGS["SEC_USER_AGENT"]
    return answer


def closes():
    rows, day = [], (STARTED - timedelta(days=1)).date()
    while len(rows) < 60:
        if day.weekday() < 5:
            rows.append({"date": day.isoformat(), "close": 50.0, "volume": 100000.0, "currency": "USD",
                         "source": "LSEG TR.PriceClose (ZZZZ.O)", "volume_source": "LSEG TR.Volume (ZZZZ.O)"})
        day -= timedelta(days=1)
    return sorted(rows, key=lambda row: row["date"])


class ScriptedModel:
    """What a model would answer, role by role: read every assigned file, then one JSON reply that the checks accept."""

    def __init__(self, run_folder):
        self.run_folder, self.asked = run_folder, []

    def line(self, name, text):
        return (self.run_folder() / name).read_text(encoding="utf-8").splitlines().index(text) + 1

    def reply(self, role):
        draft = lambda who: f"nodes/{who}_1/draft.md"
        if role == "Research Analyst":
            return {"claims": [{"id": "c1", "file": "10-K.txt", "line": self.line("10-K.txt", SALES_LINE), "quote": SALES_LINE, "value": "$93.9 billion"}],
                    "draft": "== 1. OVERVIEW ==\nNet sales reached {c1}.\nGrowth is supported by sales of {c1}.\nInsight: Sales of {c1} support the business."}
        if role == "Financial Analyst":
            return {"claims": [{"id": "c1", "computed": "free_cash_flow"}],
                    "draft": "== 2. CASH ==\nFree cash flow was {c1}.\nInsight: Spending leaves free cash flow of {c1}."}
        if role == "Investment Advisor":
            return {"claims": [{"id": "c1", "from": "Financial Analyst", "claim": "c1"}],
                    "draft": "== 3. RATING ==\nHold. Free cash flow of {c1} supports caution.\nInsight: Protection remains from {c1}."}
        if role == "Strategy Manager":
            research = draft("Research_Analyst")
            return {"claims": [], "failures": [], "sections": {
                "Overview": {"file": research, "start": 2, "end": 2}, "Market Positioning and Growth Outlook": {"file": research, "start": 3, "end": 3},
                "Future Developments and Strategic Recommendations": {"file": research, "start": 4, "end": 4},
                "Valuation Insights": {"file": draft("Financial_Analyst"), "start": 2, "end": 3},
                "Investment Recommendation": {"file": draft("Investment_Advisor"), "start": 2, "end": 3}}}
        return {"claims": [], "checks": [{"target": item["target"], "status": "correct", "correction": "",
                                         "reason": "The saved evidence supports the meaning and the period."} for item in report_catalog(self.run_folder())]}

    def __call__(self, messages, response_model=None):
        text = "\n".join(str(m.get("content", "")) if isinstance(m, dict) else str(m) for m in messages)
        role = next(name for name in ("Research Analyst", "Financial Analyst", "Investment Advisor", "Strategy Manager", "Verifier") if f"You are {name}" in text)
        assigned = list(dict.fromkeys(re.findall(r'\\?"file\\?":\s*\\?"([^"\\]+)\\?",\s*\\?"sha256', text)))
        read = re.findall(r'Action Input:\s*\{"file":\s*"([^"]+)"\}', text)
        todo = [name for name in assigned if name not in read]
        self.asked.append((role, todo[0] if todo else "answer"))
        return tool_call("read_assigned_file", {"file": todo[0]}) if todo else "Final Answer: " + json.dumps(self.reply(role))


class WholeDesk(unittest.TestCase):
    def test_one_run_from_the_ticker_to_the_final_report(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        rows = closes()
        model = ScriptedModel(lambda: runner.run)
        judged = {"judgment": "The supplied earnings support the cash flow measure.", "next_filing_trigger": "Read the next cash flow statement.",
                  "insight": "Capital spending uses cash [fact:capital_spending]."}

        class ScriptedParts(Parts):
            def team(self, ticker, started, output_hook):
                with patch.object(team, "LLM", lambda **settings: StubLLM(emit_events=False, responder=model)), patch.object(team, "load_dotenv"), \
                        patch("equity_research_desk.load_dotenv"):
                    return super().team(ticker, started, output_hook)

            def worksheet(self, started, output_hook):
                class Clock(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return started
                with patch.object(self.worksheet_module, "judge_once", return_value=judged), patch("view_record.datetime", Clock):
                    return super().worksheet(started, output_hook)

        options = desk.parser().parse_args([TICKER, "--runs-root", str(root)])
        with patch.dict("os.environ", SETTINGS), patch.object(desk, "dotenv_values", return_value=SETTINGS), \
                patch.object(check_pipeline, "read_settings", return_value=SETTINGS), \
                patch("closes_reader.last_close_before", return_value=dict(rows[-1], ticker=TICKER, close_time=rows[-1]["date"] + "T16:00:00-05:00")), \
                patch("closes_reader.daily_closes_and_volumes", return_value=rows), \
                redirect_stdout(io.StringIO()) as printed, local_sockets_only():
            runner = desk.DeskRun(options, parts_factory=ScriptedParts, clock=STARTED)
            runner.sources.transport = sec
            final = runner.execute()
            replayed = desk.replay(runner.run)

        state = json.loads((runner.run / "desk_run.json").read_text(encoding="utf-8"))
        self.assertEqual((state["status"], [part["name"] for part in state["parts"]], {part["status"] for part in state["parts"]}),
                         ("complete", ["inputs", "seeker", "pick", "team", "worksheet", "final report"], {"PASS"}))
        self.assertEqual(replayed, final)
        self.assertEqual([role for role, what in model.asked if what == "answer"],
                         ["Research Analyst", "Financial Analyst", "Investment Advisor", "Strategy Manager", "Verifier"])
        text = final.read_text(encoding="utf-8")
        lines = text.splitlines()

        # The first line names the three filings, the release by its exhibit, its Accepted time and the CIK.
        self.assertIn(f"8-K {EIGHT_K} (Item 2.02 earnings release, Exhibit 99.1 release.htm, accepted 2026-11-16 16:05:00 ET)", lines[0])
        self.assertIn(f"10-K {TEN_K} (fiscal year ended {END}", lines[0])
        self.assertIn(f"CIK {CIK}", lines[0])

        # The eleven core claims, read and computed in code from the made-up facts and the made-up release.
        claims = {line.split(" | ")[1]: line.split(" | ")[2] for line in lines if re.match(r"\| \d+ \| ", line)}
        self.assertEqual(claims, {
            f"Total revenue, fiscal year ended {END}": "$1 billion", "Revenue growth versus the prior year": "25.00%",
            "Operating income": "$150 million", "Operating margin (operating income / total revenue)": "15.00%",
            "Net income attributable to the company": "$100 million", "Diluted EPS, GAAP": "$10",
            "Return on average equity": "22.22%", "Debt to equity (long-term debt with its current portion)": "0.500",
            "Free cash flow (cash from operations - additions to property and equipment)": "$90 million",
            "Latest quarter's revenue": "300 (USD millions), as the release table prints it",
            "Quarter growth versus the same quarter last year": "20.00%", "Latest quarter's diluted EPS, GAAP": "$2.50"})

        # The roles' text holds only numbers that code rendered from a claim, each with its citation.
        self.assertIn(f"Net sales reached $93.9 billion [10-K.txt:L{model.line('10-K.txt', SALES_LINE)}].", text)
        self.assertIn("Hold. Free cash flow of $90 million [saved calculated_facts.json#/metrics/free_cash_flow", text)
        self.assertIn("| correct |", text)

        # The worksheet's view and its liquidity result are in the report; the licensed rows are not.
        self.assertIn("## Worksheet view and evidence", text)
        self.assertIn("Can you buy it: ", text)
        self.assertNotIn("Liquidity day |", text)
        self.assertTrue(list((runner.run / "sources/licensed").glob("*liquidity rows.json")))

        # The framework recorded no trace of the run to offer for upload (model_calls.framework_sends_nothing):
        # when it does, it notes a first execution in this file.
        self.assertFalse((runner.run / "framework/.crewai_user.json").exists())

        # The course's three lines end it.
        closing = [line for line in lines if line.strip()][-3:]
        self.assertEqual((closing[0], closing[2]), (FOOTER_FIRST, FOOTER_LAST))
        self.assertIn("anthropic/a-made-up-model", closing[1])

        # What a live run would commit holds no key, no list of closes and no home path.
        public = [p.relative_to(runner.run).as_posix() for p in runner.run.rglob("*") if p.is_file() and not desk.kept_out_of_the_record(p.relative_to(runner.run))]
        self.assertEqual(check_public.problems(runner.run, public, check_public.env_secrets(root / "no-such-file")), [])
        self.assertNotIn(SETTINGS["API_KEY"], "".join((runner.run / name).read_text(encoding="utf-8", errors="replace") for name in public))
        self.assertIn("Final report: ", printed.getvalue())

        # A clone of a live run has no licensed rows. Its replay stands on the check the run made with them,
        # and since 2026-11-25 it says so; with the rows in the folder it says nothing of the kind.
        self.assertNotIn("are not in this folder", printed.getvalue())
        clone = root / "clone"
        shutil.copytree(runner.run, clone)
        shutil.rmtree(clone / "sources/licensed")
        with redirect_stdout(io.StringIO()) as said:
            desk.replay(clone)
        self.assertIn("licensed data and are not in this folder", said.getvalue())
        self.assertNotIn("trying once more", printed.getvalue())  # no call was made twice
        self.assertNotIn("left out", printed.getvalue())           # and no claim or line was dropped after repairs


if __name__ == "__main__":
    unittest.main()
