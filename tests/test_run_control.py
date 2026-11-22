"""A run that stops says so, can be finished, and is not taken for a finished one.

Found by the audit of 2026-11-22, each on made-up parts:
- the group desk's final report had no course footer;
- a failure in the worksheet, whose model call is the last of a run, threw away a finished team report: there
  was no way to resume;
- a final report that failed its check kept the name final_report.md;
- Ctrl+C left desk_run.json at "running" for good, with no part named;
- live_record.py read the report of a failed or killed run as a live report;
- three saved files of a run held the member's home-folder path.
"""
from contextlib import redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import desk
import live_record
from desk_hook import Hook, HookFailure
from desk_rules import FOOTER_FIRST, FOOTER_LAST
from portable import local_sockets_only
from test_joined_desk import ACC, FakeParts


class RunControl(unittest.TestCase):
    def setUp(self):
        identity = patch.object(desk, "dotenv_values", return_value={"SEC_USER_AGENT": "Synthetic offline test identity", "MODEL": "anthropic/a-made-up-model"})
        identity.start()
        self.addCleanup(identity.stop)
        # The settings come from the stand-in above, whatever this terminal or an earlier test left in the environment.
        environment = patch.dict("os.environ", {"MODEL": "", "AI_TOOLS": "", "SEC_USER_AGENT": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        FakeParts.calls, FakeParts.failure = [], None
        self.options = desk.parser().parse_args(["ZZZZ", "--runs-root", str(self.root)])
        self.started = datetime.fromisoformat("2026-11-17T09:12:13.123456-05:00")

    def run_desk(self, parts=FakeParts, hook=Hook):
        runner = desk.DeskRun(self.options, parts_factory=parts, clock=self.started, hook_factory=hook)
        error = None
        with redirect_stdout(io.StringIO()), local_sockets_only():
            try:
                runner.execute()
            except BaseException as caught:  # a stop by hand is not an Exception
                error = caught
        return runner, error

    def state(self, runner):
        return json.loads((runner.run / "desk_run.json").read_text(encoding="utf-8"))


class TheFinalReport(RunControl):
    def test_it_ends_with_the_courses_three_lines_and_names_the_tools(self):
        runner, _ = self.run_desk()
        lines = [line for line in (runner.run / "final_report.md").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(lines[-3], FOOTER_FIRST)
        self.assertEqual(lines[-2], "AI assistance: Claude Code and OpenAI Codex (the desk's code); anthropic/a-made-up-model "
                                    "(the roles and the worksheet's judgment). I verified the sources myself; the judgments are mine.")
        self.assertEqual(lines[-1], FOOTER_LAST)
        self.assertEqual(sum(line == FOOTER_FIRST for line in lines), 1)

    def test_a_replay_on_another_computer_writes_the_same_footer(self):
        runner, _ = self.run_desk()
        with patch.object(desk, "dotenv_values", return_value={}), patch.dict("os.environ", {"MODEL": "", "AI_TOOLS": ""}), redirect_stdout(io.StringIO()):
            self.assertEqual(desk.replay(runner.run), runner.run / "final_report.md")

    def test_a_final_report_that_fails_its_check_does_not_keep_the_name(self):
        class RejectsTheFinalReport(Hook):
            def check(self, phase, paths, **kwargs):
                if phase == "final report":
                    raise HookFailure("an invented failure of the final check")
                return super().check(phase, paths, **kwargs)
        runner, error = self.run_desk(hook=RejectsTheFinalReport)
        self.assertIsInstance(error, HookFailure)
        self.assertFalse((runner.run / "final_report.md").exists())
        self.assertTrue((runner.run / "final_report.rejected.md").exists())
        self.assertEqual(self.state(runner)["failed_part"], "final report")


class AStoppedRun(RunControl):
    def test_ctrl_c_names_the_part_and_is_not_left_running(self):
        class StoppedInTheTeam(FakeParts):
            def team(self, ticker, started, output_hook):
                raise KeyboardInterrupt()
        runner, error = self.run_desk(parts=StoppedInTheTeam)
        self.assertIsInstance(error, KeyboardInterrupt)
        state = self.state(runner)
        self.assertEqual((state["status"], state["failed_part"]), ("stopped", "team"))
        self.assertEqual(state["parts"][-1]["status"], "STOPPED")
        self.assertEqual(json.loads((runner.run / "view.json").read_text(encoding="utf-8"))["direction"], "not computed")

    def test_the_command_ends_with_130_and_names_the_folder(self):
        class StoppedInTheTeam(FakeParts):
            def team(self, ticker, started, output_hook):
                raise KeyboardInterrupt()
        out = io.StringIO()
        real = desk.DeskRun
        with patch.object(desk, "DeskRun", lambda options: real(self.options, parts_factory=StoppedInTheTeam, clock=self.started)), \
                redirect_stdout(out), patch("sys.stderr", io.StringIO()):
            self.assertEqual(desk.main(["ZZZZ"]), 130)
        self.assertIn("Saved run: ", out.getvalue())

    def test_a_killed_run_still_says_which_part_it_was_in(self):
        seen = {}

        class LooksAtTheState(FakeParts):
            def team(self, ticker, started, output_hook):
                seen.update(json.loads((self.run / "desk_run.json").read_text(encoding="utf-8")))
                return super().team(ticker, started, output_hook)
        self.run_desk(parts=LooksAtTheState)
        self.assertEqual((seen["status"], seen["current_part"]), ("running", "team"))


class Resume(RunControl):
    def failed_in_the_worksheet(self):
        FakeParts.failure = "worksheet"
        runner, error = self.run_desk()
        self.assertIsInstance(error, ValueError)
        FakeParts.failure, FakeParts.calls = None, []
        return runner

    def test_a_run_that_stopped_in_its_worksheet_is_finished_without_the_team(self):
        stopped = self.failed_in_the_worksheet()
        with redirect_stdout(io.StringIO()), local_sockets_only():
            runner = desk.resume(stopped.run, parts_factory=FakeParts)
            final = runner.finish(runner.run / "verified_report.md")
        self.assertEqual(FakeParts.calls, ["worksheet"])                       # no seeker, no pick, no team
        self.assertEqual(final, stopped.run / "final_report.md")
        state = self.state(runner)
        self.assertEqual((state["status"], state["started_at"]), ("complete", self.started.isoformat()))
        self.assertNotIn("failed_part", state)
        self.assertEqual(state["resumed"][0]["from_part"], "worksheet")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(desk.replay(runner.run), final)

    def test_the_view_of_a_stopped_run_is_not_made_again(self):
        stopped = self.failed_in_the_worksheet()
        frozen = (stopped.run / "view.json").read_bytes()
        self.assertEqual(json.loads(frozen)["direction"], "not computed")
        self.assertTrue(stopped.run.joinpath("view.json").exists())
        # The stand-in worksheet writes view.json itself; the real one keeps the first saved view (view_record.py).
        self.assertEqual(json.loads(frozen)["ticker"], "ZZZZ")

    def test_a_run_that_stopped_before_its_team_report_is_run_again(self):
        FakeParts.failure = "team"
        runner, _ = self.run_desk()
        with self.assertRaisesRegex(ValueError, 'stopped in "team". Run the desk again'):
            desk.resume(runner.run, parts_factory=FakeParts)

    def test_a_complete_run_has_nothing_to_resume(self):
        runner, _ = self.run_desk()
        with self.assertRaisesRegex(ValueError, "nothing to resume"):
            desk.resume(runner.run, parts_factory=FakeParts)

    def test_a_file_changed_after_the_stop_refuses_the_resume(self):
        stopped = self.failed_in_the_worksheet()
        report = stopped.run / "verified_report.md"
        report.write_text(report.read_text(encoding="utf-8").replace("$100", "$101"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after it stopped: verified_report.md"):
            desk.resume(stopped.run, parts_factory=FakeParts)

    def test_the_command_says_how_to_resume(self):
        FakeParts.failure = "worksheet"
        out = io.StringIO()
        real = desk.DeskRun
        with patch.object(desk, "DeskRun", lambda options: real(self.options, parts_factory=FakeParts, clock=self.started)), \
                redirect_stdout(out), patch("sys.stderr", io.StringIO()), local_sockets_only():
            self.assertEqual(desk.main(["ZZZZ"]), 1)
        self.assertIn(" desk.py --resume ", out.getvalue())

    def test_the_resume_line_names_the_python_that_ran_the_desk(self):
        # Until 2026-11-22 the line said "python" and the folder's whole path. On a member's computer "python" is
        # not the desk's environment, and the command then stops on a package it cannot find.
        run = desk.ROOT / "runs" / "practice" / "ZZZZ_made_up"
        with patch.object(desk.sys, "executable", str(desk.ROOT / ".venv-desk" / "Scripts" / "python.exe")):
            self.assertEqual(desk.resume_line(run), str(Path(".venv-desk", "Scripts", "python.exe"))
                             + ' desk.py --resume "' + str(Path("runs", "practice", "ZZZZ_made_up")) + '"')
        with patch.object(desk.sys, "executable", str(Path(self.tmp.name) / "elsewhere" / "python.exe")):
            self.assertTrue(desk.resume_line(run).startswith("python desk.py --resume "))
        # A run folder outside the repository (a test's, here) keeps its whole path.
        self.assertIn(str(self.root / "ZZZZ"), desk.resume_line(self.root / "ZZZZ"))

    def test_a_run_stopped_by_hand_in_its_worksheet_says_how_to_resume(self):
        class StoppedInTheWorksheet(FakeParts):
            def worksheet(self, started, output_hook):
                raise KeyboardInterrupt()
        out = io.StringIO()
        real = desk.DeskRun
        with patch.object(desk, "DeskRun", lambda options: real(self.options, parts_factory=StoppedInTheWorksheet, clock=self.started)), \
                redirect_stdout(out), patch("sys.stderr", io.StringIO()), local_sockets_only():
            self.assertEqual(desk.main(["ZZZZ"]), 130)
        self.assertIn(" desk.py --resume ", out.getvalue())

    def test_a_run_stopped_in_its_team_is_not_told_to_resume(self):
        FakeParts.failure = "team"
        out = io.StringIO()
        real = desk.DeskRun
        with patch.object(desk, "DeskRun", lambda options: real(self.options, parts_factory=FakeParts, clock=self.started)), \
                redirect_stdout(out), patch("sys.stderr", io.StringIO()), local_sockets_only():
            self.assertEqual(desk.main(["ZZZZ"]), 1)
        self.assertNotIn("--resume", out.getvalue())


class TheLiveRecordReadsTheRunsState(unittest.TestCase):
    LINE = f"Filings read: 8-K 0000012345-26-000002 (Item 2.02 earnings release, Exhibit 99.1 r.htm, accepted 2026-11-24 16:05:00 ET); XBRL company facts, CIK 0000012345\n"

    def folder(self, state, *reports):
        root = Path(tempfile.mkdtemp())
        folder = root / "runs" / "live" / "ZZZZ_2026-11-24_17-00-00.000000"
        folder.mkdir(parents=True)
        if state is not None:
            (folder / "desk_run.json").write_text(json.dumps(state), encoding="utf-8")
        for name in reports:
            (folder / name).write_text(self.LINE + "\nA report.\n", encoding="utf-8")
        now = datetime.fromisoformat("2026-11-24T18:00:00-05:00")
        return live_record.read_run(folder, None, now, root)

    def test_a_complete_run_is_read_from_its_final_report(self):
        row = self.folder({"status": "complete"}, "final_report.md", "verified_report.md", "report.md")
        self.assertEqual((row["problem"], row["note"], row["report"]), ("", "", "runs/live/ZZZZ_2026-11-24_17-00-00.000000/final_report.md"))

    def test_a_run_that_failed_in_its_team_holds_no_live_report(self):
        for state in ({"status": "failed", "failed_part": "team"}, {"status": "running", "current_part": "team"}, {"status": "stopped", "failed_part": "pick"}):
            with self.subTest(state=state):
                row = self.folder(state, "report.md", "verified_report.md")
                self.assertIn("did not finish", row["problem"])
                self.assertTrue(live_record.late(row))

    def test_a_run_that_stopped_in_its_worksheet_is_shown_by_its_verified_report_with_a_note(self):
        row = self.folder({"status": "failed", "failed_part": "worksheet"}, "verified_report.md", "report.md", "final_report.rejected.md")
        self.assertEqual(row["problem"], "")
        self.assertTrue(row["report"].endswith("/verified_report.md"))
        self.assertIn('stopped in the part "worksheet"', row["note"])
        text = live_record.render([row], datetime.fromisoformat("2026-11-24T18:00:00-05:00"), True, "Claude Code")
        self.assertIn("Runs that did not finish:", text)

    def test_a_base_desk_run_has_no_state_and_is_read_as_before(self):
        row = self.folder(None, "verified_report.md", "report.md")
        self.assertEqual((row["problem"], row["note"]), ("", ""))


class NoHomeFolderInARunsFiles(unittest.TestCase):
    def test_the_saved_fields_hold_file_names(self):
        import ast
        source = (Path(__file__).resolve().parents[1] / "equity_research_agent_team.py").read_text(encoding="utf-8")
        for field in ('"verified_report": str(', "'verified_report':str(", '"report": str('):
            self.assertNotIn(field, source)
        ast.parse(source)
        from desk_sources import skill
        worksheet = skill("spinoff-worksheet")
        folder = Path(tempfile.mkdtemp())
        rules = folder / "rules.json"
        rules.write_text(json.dumps({"facts": {}}), encoding="utf-8")
        self.assertEqual(worksheet.load_worksheet(rules)["worksheet_source"], "rules.json")



class TheTicker(unittest.TestCase):
    """Only a ticker-shaped word starts a run: it becomes a folder's name and part of SEC addresses. No test
    held the pattern until 2026-11-22."""
    def test_a_word_that_is_no_ticker_starts_nothing(self):
        for word in ("1ABC", "AB CD", "../X", "A" * 17, "AB$", "AB/CD", "Ａ"):
            with self.subTest(word=word), patch.object(desk, "DeskRun", side_effect=AssertionError("a run was started")), \
                    patch("sys.stderr", io.StringIO()) as said:
                self.assertEqual(desk.main([word]), 1)
                self.assertIn("Invalid ticker", said.getvalue())

    def test_a_ticker_with_a_dot_or_a_dash_starts_a_run_in_capitals(self):
        for word in ("BRK.B", "BF-B", "zzzz"):
            started = []

            class Started:
                def __init__(self, options):
                    started.append(options.selector)

                def execute(self):
                    pass
            with self.subTest(word=word), patch.object(desk, "DeskRun", Started):
                self.assertEqual(desk.main([word]), 0)
                self.assertEqual(started, [word.upper()])


if __name__ == "__main__":
    unittest.main()
