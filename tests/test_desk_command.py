"""Offline tests of the one command: the order of the parts, the one run folder, the stop, the hook and the replay.

The real graph runs on the saved example, with a made-up model, made-up hand-written files and no network.
Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import desk  # noqa: E402
import hook  # noqa: E402
import lab03_app as app  # noqa: E402
from test_desk import GOOD_ANALYSIS, advisor, research  # noqa: E402
from test_team import FakeModel, OfflineTeam, offline_desk, reader  # noqa: E402
from test_worksheet import GOOD_REPLY, METHOD, bars, years  # noqa: E402

STARTED = datetime(2026, 9, 24, 17, 0, 0).astimezone()


class DeskTeam(OfflineTeam):
    """The real graph on the saved example. Its steps save into the command's run folder what the real steps save."""

    def steps(self, state: Any) -> dict[str, Any]:
        run_dir = Path(state["run_dir"])
        for file in self.desk.outdir.iterdir():
            if file.is_file():
                shutil.copy(file, run_dir / file.name)
        self.desk.outdir = run_dir
        facts = json.loads((run_dir / "facts.json").read_text(encoding="utf-8"))
        facts.update(company="Example Corp", worksheet={
            "net_income": {"tag": "NetIncomeLoss", "unit": "USD", "years": years([1000e6, 900e6, 800e6])},
            "depreciation": {"tag": "DepreciationDepletionAndAmortization", "unit": "USD", "years": years([200e6, 190e6, 180e6])},
            "capex": {"tag": "PaymentsToAcquirePropertyPlantAndEquipment", "unit": "USD", "years": years([300e6, 290e6, 280e6])},
            "diluted_shares": {"tag": "WeightedAverageNumberOfDilutedSharesOutstanding", "unit": "shares", "years": years([400e6], "shares")},
        })
        (run_dir / "facts.json").write_text(json.dumps(facts), encoding="utf-8")
        note = "$50.00, the close of 2026-09-23, the last close before 2026-09-24 16:05:00 ET, when the release was accepted, from a test"
        (run_dir / "price.json").write_text(json.dumps({"price": 50.0, "note": note}), encoding="utf-8")
        return super().steps(state)


class DeskCase(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.output = self.home / "output"
        (self.home / "worksheet.json").write_text(json.dumps(METHOD), encoding="utf-8")
        (self.home / "persona.md").write_text("A made-up persona for the tests.\n", encoding="utf-8")
        files = {"WORKSHEET_FILE": str(self.home / "worksheet.json"), "PERSONA_FILE": str(self.home / "persona.md")}
        patcher = mock.patch.dict(os.environ, files)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_desk(self, target: str = "exm", replies: dict[str, Any] | None = None, seek: Any = None) -> tuple[int, str, str, FakeModel]:
        good = {"Research Analyst": research, "Financial Analyst": lambda p: GOOD_ANALYSIS, "Investment Advisor": advisor,
                "Verifier (reader)": reader, "Verifier (line check)": lambda p: {"checks": []}, "Worksheet (persona)": lambda p: dict(GOOD_REPLY)}
        model = FakeModel({**good, **(replies or {})})
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = desk.run(target, lambda: DeskTeam(model, offline_desk()), model, {"peers": [], "price": None, "filed": None}, STARTED,
                            [target], seek=seek, bars=bars, output=self.output)
        return code, out.getvalue(), err.getvalue(), model

    def folder(self) -> Path:
        folders = sorted(self.output.iterdir())
        self.assertEqual(len(folders), 1, "one command, one run folder")
        return folders[0]


class OneCommand(DeskCase):
    def test_the_parts_run_in_the_fixed_order_through_one_run_folder(self) -> None:
        code, printed, errors, _ = self.run_desk()
        self.assertEqual((code, errors), (0, ""))
        parts = [name for name in re.findall(r"^=== (.+) ===$", printed, re.M) if name in desk.ORDER]
        self.assertEqual(parts, desk.ORDER[1:])  # every part but the seeker, which nobody asked for
        self.assertIn("Order: " + " -> ".join(desk.ORDER[1:]), printed)
        folder = self.folder()
        self.assertEqual(folder.name, "EXM_20260924_170000")  # the ticker, and the date and time the command started
        for name in ("pick.json", "facts.json", "price.json", "report.md", "verified_report.md", "verification.json", "worksheet.md", "view.json",
                     "worksheet_file.json", "final_report.md", "desk.json"):
            self.assertTrue((folder / name).is_file(), name)
        self.assertIn("Done: the hook refused nothing.", printed)
        self.assertIn(f"Final report: {folder / 'final_report.md'}", printed)

    def test_each_part_prints_its_seconds_on_its_last_line(self) -> None:
        _, printed, _, _ = self.run_desk()
        lines = printed.splitlines()
        for part in desk.ORDER[1:]:
            start = lines.index(f"=== {part} ===")
            later = [i for i, line in enumerate(lines) if i > start and line.startswith("=== ") and line[4:-4] in desk.ORDER]
            end = later[0] if later else next(i for i, line in enumerate(lines) if line.startswith("Run folder:"))
            last = [line for line in lines[start:end] if line.strip()][-1]
            self.assertRegex(last, rf"^{re.escape(part)}: \d+\.\d seconds$")
        saved = json.loads((self.folder() / "desk.json").read_text(encoding="utf-8"))
        self.assertEqual([p["part"] for p in saved["parts"]], desk.ORDER[1:])
        self.assertTrue(all(isinstance(p["seconds"], float) for p in saved["parts"]))

    def test_the_final_report_is_the_verified_report_with_the_view_under_it(self) -> None:
        self.run_desk()
        folder = self.folder()
        final = (folder / "final_report.md").read_text(encoding="utf-8").splitlines()
        verified = (folder / "verified_report.md").read_text(encoding="utf-8").splitlines()
        sheet = (folder / "worksheet.md").read_text(encoding="utf-8").splitlines()
        cut = final.index(hook.VIEW_HEADING)
        self.assertEqual(final[0], verified[0])  # the first line names the filings; no part read another
        self.assertTrue(final[0].startswith("Filings read:"))
        self.assertEqual([line for line in final[:cut] if line.strip()], [line for line in verified if line.strip()])
        self.assertEqual(final[cut + 2:], sheet)
        self.assertIn("- View: the company is worth less than the price.", sheet)
        self.assertEqual(final[-1], "Any remaining errors are my own.")  # the course's closing lines end the report

    def test_a_name_the_seeker_never_saw_is_not_applicable_and_the_rest_runs(self) -> None:
        code, _, _, _ = self.run_desk()
        sheet = (self.folder() / "worksheet.md").read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("## Facts of the spinoff\n- Not applicable.", sheet)
        self.assertIn("- Low case, per share: $20.00 [computed: 8,000.0 / 400.0]", sheet)

    def test_the_order_is_the_same_on_two_runs_and_no_model_chose_it(self) -> None:
        first = re.findall(r"^=== (.+) ===$", self.run_desk()[1], re.M)
        shutil.rmtree(self.output)
        _, printed, _, model = self.run_desk()
        self.assertEqual(re.findall(r"^=== (.+) ===$", printed, re.M), first)
        # The model answered the roles and the persona. Nothing asked it what to run.
        self.assertLessEqual(set(model.roles), {"Research Analyst", "Financial Analyst", "Investment Advisor", "Verifier (reader)", "Verifier (line check)", "Worksheet (persona)"})
        self.assertEqual(model.roles.count("Worksheet (persona)"), 1)  # one model call for the judgment

    def test_the_seeker_runs_first_only_when_it_is_asked_for(self) -> None:
        calls: list[str] = []
        _, printed, _, _ = self.run_desk(seek=lambda: calls.append("ran") or "ran")
        self.assertEqual(calls, ["ran"])
        self.assertEqual([n for n in re.findall(r"^=== (.+) ===$", printed, re.M) if n in desk.ORDER], desk.ORDER)


class Stops(DeskCase):
    def test_a_part_that_fails_stops_the_command_names_itself_and_keeps_the_folder(self) -> None:
        os.environ["WORKSHEET_FILE"] = str(self.home / "no_such_file.json")
        code, printed, errors, _ = self.run_desk()
        self.assertEqual(code, 1)
        self.assertIn("The desk stopped at this part: Worksheet: The worksheet file is missing", errors)
        self.assertIn("A team member writes it by hand; no AI writes it.", errors)
        folder = self.folder()
        self.assertIn(f"The run folder is kept: {folder}", errors)
        self.assertTrue((folder / "verified_report.md").is_file())  # what ran before the stop is kept
        self.assertFalse((folder / "final_report.md").exists())
        self.assertNotIn("=== Final report ===", printed)  # no part runs after the one that failed
        saved = json.loads((folder / "desk.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["parts"][-1]["part"], saved["parts"][-1]["outcome"]), ("Worksheet", "failed"))

    def test_a_role_that_stops_stops_the_desk_at_the_agent_team(self) -> None:
        def fails(packet: dict[str, Any]) -> dict[str, Any]:
            raise app.RoleError("Financial Analyst did not return JSON (stop reason max_tokens).")
        code, printed, errors, _ = self.run_desk(replies={"Financial Analyst": fails})
        self.assertEqual(code, 1)
        self.assertIn("Financial Analyst stopped: Financial Analyst did not return JSON", errors)
        self.assertIn("The desk stopped at this part: Agent team", errors)
        self.assertTrue(list((self.folder() / "nodes").glob("*_stopped.json")))
        self.assertNotIn("=== Worksheet ===", printed)

    def test_the_screen_with_no_report_of_the_seeker_stops_at_the_pick(self) -> None:
        with mock.patch.object(desk, "SEEKER_REPORTS", self.home / "no_reports"):
            code, _, errors, _ = self.run_desk(target="screen")
        self.assertEqual(code, 1)
        self.assertIn("The desk stopped at this part: Pick: the seeker has written no report", errors)

    def test_the_screen_takes_the_top_name_of_the_latest_report(self) -> None:
        reports = self.home / "reports"
        reports.mkdir()
        (reports / "screen_20260901_090000.json").write_text(json.dumps({"in_window": [{"ticker": "OLD"}]}), encoding="utf-8")
        (reports / "screen_20260923_090000.json").write_text(json.dumps({"in_window": [{"ticker": "exm"}, {"ticker": "TWO"}]}), encoding="utf-8")
        with mock.patch.object(desk, "SEEKER_REPORTS", reports):
            code, printed, _, _ = self.run_desk(target="screen")
        self.assertEqual(code, 0)
        self.assertIn("EXM, from the top of the seeker's report screen_20260923_090000.json.", printed)
        self.assertEqual(json.loads((self.folder() / "pick.json").read_text(encoding="utf-8"))["ticker"], "EXM")

    def test_a_refusal_of_the_hook_does_not_stop_the_parts_and_the_command_ends_not_done(self) -> None:
        # The persona quotes a number that the worksheet prints, but names a deciding line; then one amount is changed
        # in the saved verified report's marks before the worksheet runs: here the Verifier's own count says "wrong".
        def reader_with_a_wrong_number(packet: dict[str, Any]) -> dict[str, Any]:
            read = reader(packet)
            read["numbers"][0]["number"] = "$999,999.0M"  # not the revenue fact: the Verifier marks it wrong
            return read
        code, printed, errors, _ = self.run_desk(replies={"Verifier (reader)": reader_with_a_wrong_number})
        self.assertEqual(code, 2)
        self.assertIn("refused: line 1, the Verifier marked 1 number(s) wrong or unsupported", printed)
        self.assertIn("=== Worksheet ===", printed)  # the parts after the refusal still ran
        self.assertIn("Not done: the hook refused", errors)
        self.assertTrue((self.folder() / "final_report.md").is_file())


class Replay(DeskCase):
    def replay(self, folder: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = desk.replay(folder)
        return code, out.getvalue(), err.getvalue()

    def test_the_replay_gives_the_same_report_fetches_nothing_and_writes_nothing(self) -> None:
        self.run_desk()
        folder = self.folder()
        before = {p.name: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        code, printed, errors = self.replay(folder)
        self.assertEqual((code, errors), (0, ""))
        self.assertIn("The replay gives the same final report: yes. Nothing was fetched.", printed)
        self.assertEqual(re.findall(r"^=== (.+) ===$", printed, re.M), desk.ORDER[1:])
        self.assertEqual({p.name: p.read_bytes() for p in folder.rglob("*") if p.is_file()}, before)

    def test_inside_the_replay_a_connection_is_an_error(self) -> None:
        with desk.no_network():
            with self.assertRaises(RuntimeError):
                socket.create_connection(("127.0.0.1", 9), timeout=1)
        self.assertIsNot(socket.create_connection, None)

    def test_the_replay_refuses_a_saved_output_that_was_changed(self) -> None:
        self.run_desk()
        folder = self.folder()
        sheet = folder / "worksheet.md"
        sheet.write_text(sheet.read_text(encoding="utf-8").replace("$8,000.0M", "$8,001.0M", 1), encoding="utf-8")
        code, printed, errors = self.replay(folder)
        self.assertEqual(code, 2)
        self.assertIn("$8,001.0M is not what its arithmetic gives", printed)
        self.assertIn("The replay gives the same final report: NO.", printed)
        self.assertIn("Not done: the hook refused", errors)

    def test_a_seeded_copy_of_the_final_report_is_refused_by_line(self) -> None:
        self.run_desk()
        folder = self.folder()
        lines = (folder / "final_report.md").read_text(encoding="utf-8").splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("| 1 | Total revenue"))
        seeded = lines[:index] + [lines[index].replace("$303,154.0M", "$303,155.0M")] + lines[index + 1:]
        copy = self.home / "seeded_final_report.md"
        copy.write_text("\n".join(seeded) + "\n", encoding="utf-8")
        found = hook.check(copy, folder)
        self.assertEqual(found, [(index + 1, "$303,155.0M is not in the verified report (the saved line holds $303,154.0M)")])

    def test_a_folder_that_is_not_a_finished_run_says_what_is_missing(self) -> None:
        code, _, errors = self.replay(self.home)
        self.assertEqual(code, 1)
        self.assertIn("is not a finished run of the desk", errors)


class NoCompanyNamed(unittest.TestCase):
    def test_the_desk_code_names_no_company(self) -> None:
        for name in ("desk.py", "hook.py", "worksheet.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT|CSCO|NVDA)\b", source), name)


if __name__ == "__main__":
    unittest.main()
