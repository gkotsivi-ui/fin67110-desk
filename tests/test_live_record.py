"""Offline tests of the live record: made-up report lines, made-up times and a made-up git repository.

No test reads .env or asks SEC EDGAR.
Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import live_record as live  # noqa: E402

ET = live.eastern()
# A made-up first line, in the shape the desk prints it.
FIRST_LINE = (
    "Filings read: 10-K 0000000001-26-000010 (fiscal year ended 2026-06-30, accepted 2026-08-20 16:30:00 ET); "
    "10-Q 0000000001-26-000007 (quarter ended 2026-03-31, accepted 2026-05-05 16:30:00 ET); "
    "8-K 0000000001-26-000020 (Item 2.02 earnings release, Exhibit 99.1 ex991release.htm, accepted 2026-11-12 16:07:06 ET); "
    "XBRL company facts, CIK 0000000001"
)


def at(text: str) -> datetime:
    return datetime.strptime(text, live.STAMP).replace(tzinfo=ET)


class FirstLine(unittest.TestCase):
    def test_the_first_line_names_the_release(self) -> None:
        named = live.release_named(FIRST_LINE)
        self.assertEqual(named, {"accession": "0000000001-26-000020", "cik": "0000000001", "exhibit": "ex991release.htm", "accepted": "2026-11-12 16:07:06"})

    def test_the_8k_is_not_the_10k(self) -> None:
        # The 10-K and the 10-Q come first on the line; the release is the 8-K.
        self.assertNotEqual(live.release_named(FIRST_LINE)["accession"], "0000000001-26-000010")

    def test_a_line_that_names_no_8k(self) -> None:
        self.assertIsNone(live.release_named("# A report with no filings line"))
        self.assertIsNone(live.release_named("Filings read: 10-K 0000000001-26-000010; XBRL company facts, CIK 0000000001"))

    def test_a_time_that_is_not_eastern_is_not_taken(self) -> None:
        line = FIRST_LINE.replace("accepted 2026-11-12 16:07:06 ET);", "accepted 2026-11-12T21:07:06.000Z UTC);")
        self.assertEqual(live.release_named(line)["accepted"], "")


class Window(unittest.TestCase):
    accepted = at("2026-11-12 16:07:06")
    now = at("2026-11-12 18:00:00")

    def test_the_edges_of_the_24_hours(self) -> None:
        self.assertEqual(live.judge(self.accepted, self.accepted, self.now), "yes")
        self.assertEqual(live.judge(self.accepted, at("2026-11-13 16:07:06"), self.now), "yes")
        self.assertEqual(live.judge(self.accepted, at("2026-11-13 16:07:07"), self.now), "NO: late")

    def test_a_commit_before_the_release_is_not_a_live_report(self) -> None:
        self.assertTrue(live.judge(self.accepted, at("2026-11-12 16:07:05"), self.now).startswith("NO"))

    def test_a_report_not_committed_yet_shows_the_time_left(self) -> None:
        self.assertEqual(live.judge(self.accepted, None, self.now), "not committed yet; 22.1 hours left")
        self.assertTrue(live.judge(self.accepted, None, at("2026-11-13 16:07:07")).startswith("NO"))

    def test_the_weeks_run_monday_to_sunday(self) -> None:
        self.assertEqual(live.week_of(date(2026, 11, 9)), "Week 4")
        self.assertEqual(live.week_of(date(2026, 11, 15)), "Week 4")
        self.assertEqual(live.week_of(date(2026, 11, 16)), "Week 5")
        self.assertEqual(live.week_of(date(2026, 12, 6)), "Week 7")
        self.assertEqual(live.week_of(date(2026, 12, 7)), "outside Weeks 4 to 7")
        for first, last in live.WEEKS.values():
            self.assertEqual((first.weekday(), last.weekday(), (last - first).days), (0, 6, 6))

    def test_a_commit_time_is_read_in_eastern_time(self) -> None:
        winter = datetime.fromisoformat("2026-11-13T02:10:00+00:00").astimezone(ET)
        summer = datetime.fromisoformat("2026-07-01T02:10:00+00:00").astimezone(ET)
        self.assertEqual(f"{winter:{live.STAMP}}", "2026-11-12 21:10:00")
        self.assertEqual(f"{summer:{live.STAMP}}", "2026-06-30 22:10:00")


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class FromGit(unittest.TestCase):
    """A made-up repository with one live run, committed at a time the test chooses."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.run_folder = self.root / "runs" / "live" / "EXM_20261112_163000"
        self.run_folder.mkdir(parents=True)
        self.git("init", "-q")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str, when: str = "2026-11-12T12:00:00-05:00") -> None:
        who = {"GIT_AUTHOR_NAME": "A Student", "GIT_AUTHOR_EMAIL": "a.student@example.edu", "GIT_COMMITTER_NAME": "A Student",
               "GIT_COMMITTER_EMAIL": "a.student@example.edu", "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.root, check=True, capture_output=True, env={**os.environ, **who})

    def commit(self, name: str, text: str, when: str) -> None:
        (self.run_folder / name).write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"Add {name}", when=when)

    def test_the_commit_that_first_added_the_report(self) -> None:
        self.commit("verified_report.md", FIRST_LINE + "\n", "2026-11-12T19:30:00-05:00")
        self.commit("notes.md", "a later commit\n", "2026-11-14T09:00:00-05:00")
        commit, when = live.first_commit(self.run_folder / "verified_report.md", self.root)
        self.assertEqual(len(commit), 40)
        self.assertEqual(f"{when.astimezone(ET):{live.STAMP}}", "2026-11-12 19:30:00")

    def test_a_report_that_is_not_committed(self) -> None:
        (self.run_folder / "verified_report.md").write_text(FIRST_LINE + "\n", encoding="utf-8")
        self.assertIsNone(live.first_commit(self.run_folder / "verified_report.md", self.root))

    def test_one_row_inside_its_window(self) -> None:
        self.commit("verified_report.md", FIRST_LINE + "\n", "2026-11-12T19:30:00-05:00")
        row = live.read_run(self.run_folder, None, at("2026-11-14 09:00:00"), self.root)
        self.assertEqual((row["ticker"], row["week"], row["inside"], row["problem"]), ("EXM", "Week 4", "yes", ""))
        self.assertEqual(live.hours(row["committed_at"] - row["accepted_at"]), "3.4 hours")
        self.assertFalse(live.late(row))

    def test_one_row_that_is_late(self) -> None:
        self.commit("verified_report.md", FIRST_LINE + "\n", "2026-11-13T16:10:00-05:00")
        row = live.read_run(self.run_folder, None, at("2026-11-14 09:00:00"), self.root)
        self.assertEqual(row["inside"], "NO: late")
        self.assertTrue(live.late(row))

    def test_the_verified_report_is_read_before_the_report(self) -> None:
        self.commit("report.md", "no filings line\n", "2026-11-12T19:00:00-05:00")
        self.commit("verified_report.md", FIRST_LINE + "\n", "2026-11-12T19:30:00-05:00")
        row = live.read_run(self.run_folder, None, at("2026-11-14 09:00:00"), self.root)
        self.assertEqual(row["report"], "runs/live/EXM_20261112_163000/verified_report.md")

    def test_a_folder_the_program_cannot_read_is_a_problem(self) -> None:
        row = live.read_run(self.run_folder, None, at("2026-11-14 09:00:00"), self.root)
        self.assertIn("no report", row["problem"])
        self.commit("report.md", "no filings line\n", "2026-11-12T19:00:00-05:00")
        row = live.read_run(self.run_folder, None, at("2026-11-14 09:00:00"), self.root)
        self.assertIn("names no 8-K", row["problem"])
        self.assertTrue(live.late(row))


class Table(unittest.TestCase):
    def row(self, week: str, inside: str, accepted: str, hours_after: float) -> dict:
        when = at(accepted)
        return {"ticker": "EXM", "folder": "EXM_x", "problem": "", "inside": inside, "week": week, "accession": "0000000001-26-000020",
                "cik": "0000000001", "exhibit": "ex991release.htm", "accepted_at": when, "deadline": when + live.WINDOW,
                "commit": "a" * 40, "committed_at": when + timedelta(hours=hours_after), "accepted_from": "EDGAR index page"}

    def test_the_table_counts_each_week_once(self) -> None:
        rows = [self.row("Week 4", "yes", "2026-11-12 16:07:06", 3), self.row("Week 4", "yes", "2026-11-12 16:03:00", 4),
                self.row("Week 5", "NO: late", "2026-11-18 16:20:00", 30)]
        text = live.render(rows, at("2026-11-20 10:00:00"), offline=False, tools="A Tool")
        self.assertIn("Weeks with a report inside its window: 1 of 4 (Week 4). The top tier needs 3.", text)
        self.assertIn("https://www.sec.gov/Archives/edgar/data/1/000000000126000020/ex991release.htm", text)
        self.assertEqual(text.count("| EXM |"), 3)

    def test_no_report_yet_and_the_three_lines_at_the_end(self) -> None:
        text = live.render([], at("2026-11-11 10:00:00"), offline=True, tools="A Tool")
        self.assertIn("No live report yet.", text)
        self.assertEqual(text.rstrip().split("\n\n")[-3:], [
            "This is a learning exercise, not financial advice.",
            "AI assistance: A Tool. I verified the sources myself; the judgments are mine.",
            "Any remaining errors are my own.",
        ])

    def test_the_code_names_no_company(self) -> None:
        source = (ROOT / "live_record.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT|CSCO|AMAT)\b", source))


if __name__ == "__main__":
    unittest.main()
