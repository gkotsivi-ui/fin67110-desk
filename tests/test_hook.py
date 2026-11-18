"""Offline tests of the hook: every number in a saved output has its support, or the hook refuses and names the line.

Made-up data; no network, no key, no model. Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import hook  # noqa: E402
from test_worksheet import saved_run, sheet  # noqa: E402

REPORT = [
    "Filings read: 10-K 0000000001-26-000003 (fiscal year ended 2026-08-30); 8-K 0000000001-26-000004",
    "",
    "## Verifier's marks",
    "| 1 | 9 | $1,000.0M | Net income | **correct** |",
    "",
    "# Example Corp (EXM): equity research report",
    "- Net income was **$1,000.0 million** (us-gaap:NetIncomeLoss, 2025-09-01 to 2026-08-30).",
    "- Revenue of the quarter was 95,723 (release line: \"Total revenue | 95,723 | 86,156\").",
]


def clean_run() -> tuple[Path, list[str]]:
    """A made-up run folder with a worksheet that the worksheet code wrote, and its lines."""
    folder = saved_run()
    _, text, _ = sheet(folder)
    return folder, text.splitlines()


def refusals(lines: list[str], folder: Path, name: str = "copy.md") -> list[tuple[int, str]]:
    """What the hook says about these lines, saved as a copy beside the run's own files."""
    copy = folder / name
    copy.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hook.check(copy, folder)


def seeded(lines: list[str], starts: str, old: str, new: str) -> tuple[list[str], int]:
    """The lines with one amount changed on the line that starts with `starts`, and that line's number."""
    index = next(i for i, line in enumerate(lines) if line.startswith(starts))
    assert old in lines[index], (old, lines[index])
    return lines[:index] + [lines[index].replace(old, new, 1)] + lines[index + 1:], index + 1


class WorksheetNumbers(unittest.TestCase):
    def test_a_clean_worksheet_is_silent(self) -> None:
        folder, _ = clean_run()
        self.assertEqual(hook.check(folder / "worksheet.md"), [])

    def test_one_amount_changed_by_one_is_refused_by_line_whatever_its_source(self) -> None:
        cases = [
            ("- Net income, fiscal year ended 2026-08-30", "$1,000.0M", "$1,001.0M", "is not in facts.json under NetIncomeLoss, 2025-09-01 to 2026-08-30 (the facts file holds 1,000.0)"),
            ("- Owner cash flow, fiscal year ended 2026-08-30", "$900.0M", "$901.0M", "is not what its arithmetic gives: 1,000.0 + 200.0 - 300.0 = 900.0"),
            ("- Rate of the low case", "10.00%", "11.00%", "is not the value of low_rate in the worksheet file (0.1)"),
            ("- Price:", "$50.00", "$51.00", "is not the close in price.json (50.00)"),
            ("- Median daily dollar volume", "$100.0M", "$101.0M", "is not in liquidity.json (100.0)"),
            ("- Revenue of the quarter", "95,723 [", "95,724 [", "is not in the line it quotes from 8K_2026-09-24_release.txt"),
            ("- The number that decides it", "150.00% [", "151.00% [", "is not the number on the worksheet line \"Price against the low case\" (150.00%)"),
            ("- The client's purchase size", "$100,000", "$100,001", "is not the value of purchase_size in the worksheet file (100000)"),
        ]
        for starts, old, new, why in cases:
            folder, lines = clean_run()
            changed, number = seeded(lines, starts, old, new)
            found = refusals(changed, folder)
            self.assertTrue(found, starts)
            self.assertEqual(found[0][0], number, starts)  # the first refusal names the seeded line
            self.assertIn(why, found[0][1], starts)

    def test_a_quote_that_the_filing_does_not_hold_is_refused(self) -> None:
        folder, lines = clean_run()
        changed, number = seeded(lines, "- Diluted EPS of the quarter", "Diluted | $6.75 | $5.87", "Diluted | $6.75 | $5.97")
        found = refusals(changed, folder)
        self.assertEqual(found[0][0], number)
        self.assertIn("claims a line that is not in 8K_2026-09-24_release.txt", found[0][1])

    def test_a_number_with_no_source_is_refused(self) -> None:
        folder, lines = clean_run()
        index = lines.index("## Value range")
        found = refusals(lines[:index + 1] + ["- Growth I expect next year: 12%"] + lines[index + 1:], folder)
        self.assertEqual(found, [(index + 2, "12% has no source")])

    def test_arithmetic_on_a_number_nobody_printed_is_refused(self) -> None:
        folder, lines = clean_run()
        index = lines.index("## Value range")
        extra = "- A case of my own: $9,999.0M [computed: 999.9 / 0.1]"
        found = refusals(lines[:index + 1] + [extra] + lines[index + 1:], folder)
        self.assertEqual(found, [(index + 2, "$9,999.0M is computed from 999.9, which no checked line above prints")])

    def test_the_judgment_may_quote_a_printed_number_and_no_other(self) -> None:
        folder, lines = clean_run()
        index = next(i for i, line in enumerate(lines) if line.startswith("## Why it may be cheap"))
        self.assertIn("150.00%", lines[index + 1])  # the persona quoted a printed number, and the clean worksheet passed
        changed = lines[:index + 1] + [lines[index + 1] + " Owner cash flow will grow 12% next year."] + lines[index + 2:]
        self.assertEqual(refusals(changed, folder), [(index + 2, "12% is not printed on a line of the worksheet that has a source")])

    def test_two_numbers_on_one_line_need_two_sources(self) -> None:
        folder, lines = clean_run()
        changed, number = seeded(lines, "- Rate of the mid case", "5.00%", "5.00% and 7.00%")
        found = refusals(changed, folder)
        self.assertEqual(found[0][0], number)
        self.assertIn("states 2 numbers", found[0][1])

    def test_dates_times_accession_numbers_and_forms_are_names_not_claims(self) -> None:
        folder, lines = clean_run()
        index = lines.index("## Not known")
        named = "- The release is 8-K 0000000001-26-000004, Exhibit 99.1, Item 2.02, accepted 2026-09-24 16:05:00, for the quarter ended August 30, 2026."
        self.assertEqual(refusals(lines[:index + 1] + [named] + lines[index + 1:], folder), [])


class ReportNumbers(unittest.TestCase):
    """The agent team's report: the text the Verifier marked, with none of its marks wrong or unsupported."""

    def run_with_report(self, wrong: int = 0, marks: bool = True) -> Path:
        folder, _ = clean_run()
        (folder / "verified_report.md").write_text("\n".join(REPORT) + "\n", encoding="utf-8")
        if marks:
            counts = {"correct": 2 - wrong, "wrong": wrong, "unsupported": 0, "not checked": 0}
            (folder / "verification.json").write_text(json.dumps({"counts": counts, "records": []}), encoding="utf-8")
        return folder

    def final(self, folder: Path) -> list[str]:
        return REPORT + ["", hook.VIEW_HEADING, ""] + (folder / "worksheet.md").read_text(encoding="utf-8").splitlines()

    def test_the_verified_report_and_the_final_report_are_silent(self) -> None:
        folder = self.run_with_report()
        self.assertEqual(hook.check(folder / "verified_report.md"), [])
        self.assertEqual(refusals(self.final(folder), folder, "final_report.md"), [])

    def test_an_amount_changed_in_the_teams_part_is_refused_by_line(self) -> None:
        folder = self.run_with_report()
        changed, number = seeded(self.final(folder), "- Net income was", "$1,000.0 million", "$1,001.0 million")
        self.assertEqual(refusals(changed, folder), [(number, "$1,001.0 is not in the verified report (the saved line holds $1,000.0)")])

    def test_an_amount_changed_in_the_view_is_refused_at_its_line_in_the_final_report(self) -> None:
        folder = self.run_with_report()
        changed, number = seeded(self.final(folder), "- Low case, per share", "$20.00", "$21.00")
        found = refusals(changed, folder)
        self.assertEqual(found[0][0], number)
        self.assertGreater(number, len(REPORT))
        self.assertIn("is not what its arithmetic gives", found[0][1])

    def test_a_mark_of_the_verifier_that_is_wrong_refuses_the_report(self) -> None:
        folder = self.run_with_report(wrong=1)
        found = hook.check(folder / "verified_report.md")
        self.assertEqual(len(found), 1)
        self.assertIn("the Verifier marked 1 number(s) wrong or unsupported", found[0][1])

    def test_a_report_without_the_verifiers_marks_is_refused(self) -> None:
        folder = self.run_with_report(marks=False)
        self.assertIn("holds no marks of the Verifier", hook.check(folder / "verified_report.md")[0][1])

    def test_a_first_line_may_name_more_filings_and_no_fewer(self) -> None:
        folder = self.run_with_report()
        more = [REPORT[0] + "; Form 10 0000000009-26-000001"] + REPORT[1:]
        self.assertEqual(refusals(more, folder), [])
        fewer = ["Filings read: 10-K 0000000001-26-000003"] + REPORT[1:]
        self.assertEqual(refusals(fewer, folder)[0], (1, "the first line does not begin with the verified report's list of filings"))


class TheCommand(unittest.TestCase):
    def run_hook(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["hook.py", *args]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = hook.main()
        return code, out.getvalue(), err.getvalue()

    def test_silence_and_zero_on_a_clean_output_two_and_the_line_on_a_seeded_copy(self) -> None:
        folder, lines = clean_run()
        self.assertEqual(self.run_hook(str(folder / "worksheet.md")), (0, "", ""))
        changed, number = seeded(lines, "- Low case, value", "$8,000.0M", "$8,001.0M")
        copy = folder.parent / "seeded_copy.md"
        copy.write_text("\n".join(changed) + "\n", encoding="utf-8")
        code, out, err = self.run_hook(str(copy), "--run", str(folder))
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith(f"refused: line {number}, $8,001.0M is not what its arithmetic gives: 800.0 / 0.1 = 8,000.0"), err)

    def test_the_newest_output_of_the_newest_run_is_what_an_agents_hook_checks(self) -> None:
        folder, _ = clean_run()
        self.assertEqual(hook.latest(folder.parent), folder / "worksheet.md")
        (folder / "final_report.md").write_text("Filings read: none\n", encoding="utf-8")
        self.assertEqual(hook.latest(folder.parent), folder / "final_report.md")  # the final report, when the run has one
        self.assertIsNone(hook.latest(folder.parent / "no_such_folder"))

    def test_the_hook_calls_no_model_and_fetches_nothing(self) -> None:
        source = (ROOT / "hook.py").read_text(encoding="utf-8")
        for name in ("lab03_app", "anthropic", "requests", "urllib", "Model("):
            self.assertNotIn(name, source)
        self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT|CSCO|NVDA)\b", source))


if __name__ == "__main__":
    unittest.main()
