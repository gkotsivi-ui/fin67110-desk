"""Rules that two programs share are read the same way by both.

Found by the audit of 2026-11-22, each on made-up files:
- hit_rate.py did not read final_report.md, the group desk's report, and passed no CIK for a first line without one;
- the hit-rate table reads its closes through the base desk's reader, which named its file CLOSES_FILE while
  .env.example gives LSEG_CLOSES_FILE;
- with LSEG_APP_KEY set, the base desk's price step imported python-dotenv, which requirements.txt did not list,
  and stopped with a traceback;
- a verified report with no "Filings read:" line got a second, unreadable form of that line;
- step 6 held a rule written for one company's release;
- a .env saved as UTF-16 stopped the group desk with a traceback.
"""
import builtins
import contextlib
import io
import json
from datetime import date, datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import check_pipeline
import closes
import hit_rate
from desk_hook import Hook
from desk_sources import Sources
from equity_research_desk import Desk, Filing

LINE = "Filings read: 8-K 0000012345-26-000002 (Item 2.02 earnings release, Exhibit 99.1 r.htm, accepted 2026-11-10 16:05:00 ET)"
NOW = datetime.fromisoformat("2026-11-20T12:00:00-05:00")


class TheHitRateReadsWhatTheLiveRecordReads(unittest.TestCase):
    def run_folder(self, report_name, first_line):
        folder = Path(tempfile.mkdtemp())
        (folder / report_name).write_text(first_line + "\nA report.\n", encoding="utf-8")
        (folder / "facts.json").write_text(json.dumps({"ticker": "ZZZZ", "cik": "0000012345"}), encoding="utf-8")
        return folder

    def test_the_group_desks_final_report_gives_the_filing_time(self):
        folder = self.run_folder("final_report.md", LINE + "; XBRL company facts, CIK 0000012345")
        fields, _ = hit_rate.row_for(folder, NOW, offline=True)
        self.assertEqual(fields[1], "2026-11-10T16:05:00-05:00")

    def test_a_first_line_without_a_cik_uses_the_runs_own(self):
        folder = self.run_folder("verified_report.md", LINE)
        fields, _ = hit_rate.row_for(folder, NOW, offline=True)
        self.assertEqual(fields[1], "2026-11-10T16:05:00-05:00")


class TheClosesFileHasOneNameThatWorks(unittest.TestCase):
    def test_the_name_the_example_gives_is_read(self):
        folder = Path(tempfile.mkdtemp())
        rows = folder / "closes.csv"  # a made-up file in a temporary folder, outside the repository
        rows.write_text("ticker,date,close\nZZZZ,2026-11-10,10.5\nZZZZ,2026-11-11,11.0\n", encoding="utf-8")
        for name in ("LSEG_CLOSES_FILE", "CLOSES_FILE"):
            with self.subTest(name=name), patch.object(closes, "setting", lambda asked, name=name: str(rows) if asked == name else ""):
                found, source = closes.read("ZZZZ", date(2026, 11, 10), date(2026, 11, 11))
                self.assertEqual(found, [(date(2026, 11, 10), 10.5), (date(2026, 11, 11), 11.0)])
                self.assertIn(name, source)


class TheBaseDesksPriceStepWithoutDotenv(unittest.TestCase):
    def test_it_goes_on_without_a_price_and_says_what_to_install(self):
        real = builtins.__import__

        def no_dotenv(name, *args, **kwargs):
            if name == "dotenv":
                raise ModuleNotFoundError("No module named 'dotenv'")
            return real(name, *args, **kwargs)
        said = io.StringIO()
        with patch.object(builtins, "__import__", no_dotenv), contextlib.redirect_stderr(said):
            self.assertEqual(closes.worker_closes("ZZZZ", date(2026, 11, 10), date(2026, 11, 11)), ([], ""))
        self.assertIn("python-dotenv", said.getvalue())

    def test_the_base_requirements_list_it(self):
        listed = (Path(closes.__file__).with_name("requirements.txt")).read_text(encoding="utf-8")
        self.assertIn("python-dotenv==", listed)


class OneWriterOfTheFirstLine(unittest.TestCase):
    def test_a_verified_report_without_the_line_makes_no_final_report(self):
        run = Path(tempfile.mkdtemp())
        (run / "verified_report.md").write_text("A report with no first line of filings.\n", encoding="utf-8")
        (run / "worksheet.md").write_text("A worksheet.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, 'no "Filings read:" first line'):
            Hook(run, Sources(run, "")).compose(run / "verified_report.md", run / "worksheet.md")
        self.assertFalse(hasattr(Sources, "filing_line"))


class NoRuleForOneCompany(unittest.TestCase):
    def test_a_sentence_of_one_filers_release_makes_no_metric(self):
        page = ("<html><body><p>Results include a non-recurring benefit of $0.10 per diluted share.</p>"
                "<p>Condensed Consolidated Statements of Income</p><table><tr><td></td><td>Q1'27</td><td>Q1'26</td></tr>"
                "<tr><td>Revenue</td><td>100</td><td>90</td></tr><tr><td>Diluted EPS</td><td>1.00</td><td>0.90</td></tr></table></body></html>")
        desk = Desk.__new__(Desk)
        desk.filings = {"8-K": Filing("8-K", "0000000000-26-000001", "2026-11-20", "x.htm", release_url="https://www.sec.gov/x.htm"),
                        "10-Q": Filing("10-Q", "0000000000-26-000002", "2026-11-01", "q.htm")}
        desk.get = lambda url: SimpleNamespace(content=page.encode("utf-8"))
        desk.facts = {"diluted_eps": {"value": 2.0, "tag": "EarningsPerShareDiluted", "period_end": "2026-06-30", "filing": "0000000000-26-000003"}}
        desk.computed_metrics, desk.quarter_results, desk.company_facts, desk.cik = {}, {}, {"facts": {}}, "1"
        with contextlib.redirect_stdout(io.StringIO()):
            desk.step6()
        names = " ".join([*desk.computed_metrics, *desk.quarter_results])
        self.assertNotRegex(names, "refund|q4|nonrecurring")
        self.assertEqual(sorted(desk.computed_metrics), ["quarter_revenue_growth"])


class TheErrorReviewsModel(unittest.TestCase):
    def test_a_model_written_with_its_provider_is_the_model_used(self):
        import lab03_app
        self.assertEqual(lab03_app.model_for("anthropic", "anthropic/claude-made-up-9"), "claude-made-up-9")
        self.assertEqual(lab03_app.model_for("anthropic", "claude-made-up-9"), "claude-made-up-9")
        self.assertEqual(lab03_app.model_for("google", "gemini/gemini-made-up"), "gemini-made-up")

    def test_an_openai_key_or_model_is_refused_and_never_sent_elsewhere(self):
        import desk_error_review
        import lab02_desk
        for settings in ({"API_KEY": "sk-proj-made-up-0123456789", "MODEL": "openai/a-model"}, {"API_KEY": "sk-ant-made-up-0123456789", "MODEL": "openai/a-model"}):
            with self.subTest(settings=settings), patch.object(lab02_desk, "load_dotenv", return_value=settings), \
                    patch.dict("os.environ", {"API_KEY": "", "MODEL": ""}):
                with self.assertRaisesRegex(ValueError, "Anthropic or a Google model"):
                    desk_error_review.configured_model()


class ASettingsFileWindowsWrote(unittest.TestCase):
    def test_utf_16_is_named_as_the_problem(self):
        root = Path(tempfile.mkdtemp())
        (root / ".env").write_text("SEC_USER_AGENT=Pat Example pat.example@school.example\n", encoding="utf-16")
        with self.assertRaisesRegex(ValueError, "not saved as UTF-8"):
            check_pipeline.read_settings(root)


if __name__ == "__main__":
    unittest.main()
