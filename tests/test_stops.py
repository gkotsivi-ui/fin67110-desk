"""Offline tests of a run that stops: a connection to the model that is cut, and the record a stopped run keeps.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import anthropic  # noqa: E402
import requests  # noqa: E402

import lab03_app as app  # noqa: E402
import team  # noqa: E402
from test_desk import GOOD_ANALYSIS, advisor, research  # noqa: E402
from test_setup import ANTHROPIC, GOOGLE, FakeResponse  # noqa: E402
from test_team import FakeModel, OfflineTeam, offline_desk, reader  # noqa: E402


class TransportError(Exception):
    """Made up. It has the family name that the HTTP library gives its connection errors."""


class ReadError(TransportError):
    pass


def cut_connection() -> Exception:
    """The errors a cut connection leaves: one from the operating system, wrapped in one from the HTTP library."""
    try:
        try:
            raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
        except ConnectionResetError as exc:
            raise ReadError("the connection was closed") from exc
    except ReadError as exc:
        return exc


REPLY = SimpleNamespace(stop_reason="end_turn", model="claude-test-1", usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                        content=[SimpleNamespace(type="text", text='{"answer": 42}')])
GEMINI_REPLY = {"candidates": [{"content": {"parts": [{"text": '{"answer": 42}'}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}, "modelVersion": "gemini-test-1"}


class FakeStream:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def get_final_message(self) -> Any:
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeClient:
    """Stands in for the Anthropic client: each call to stream() gives the next outcome, a reply or an error."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.beta = self.messages = self

    def stream(self, **request: Any) -> FakeStream:
        self.calls += 1
        return FakeStream(self.outcomes.pop(0))


def model_with(outcomes: list[Any]) -> tuple[app.Model, FakeClient]:
    model = app.Model(ANTHROPIC, app.DEFAULT_MODEL, "medium")
    model.client = FakeClient(outcomes)
    return model, model.client


def ask(model: app.Model) -> tuple[Any, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        return model.ask("Verifier (reader)", "Reply with JSON.", {"task": "test"}), out.getvalue()


class LostConnection(unittest.TestCase):
    """A connection that is cut while a reply is being read. On 2026-11-13 it ended a live run with a traceback."""

    def test_a_network_failure_is_known_by_its_family_or_by_its_cause(self) -> None:
        caused = RuntimeError("wrapped")
        caused.__cause__ = ConnectionAbortedError("aborted")
        for exc in (ReadError("cut"), cut_connection(), TimeoutError("timed out"), caused):
            self.assertTrue(app.lost_connection(exc), repr(exc))
        for exc in (ValueError("a bug"), KeyError("k"), FileNotFoundError("no such file"), app.RoleError("not JSON")):
            self.assertFalse(app.lost_connection(exc), repr(exc))

    def test_a_cut_connection_is_the_desks_own_message(self) -> None:
        model, _ = model_with([cut_connection()])
        with self.assertRaises(app.ConnectionLost) as caught:
            model.send("Reply with JSON.", {"task": "test"})
        self.assertIsInstance(caught.exception, app.RoleError)  # so the run stops as it does for every role error
        self.assertIsInstance(caught.exception.__cause__, ReadError)  # the first error is kept as the cause
        for words in ("connection to the Anthropic API was lost", "ReadError", "run again"):
            self.assertIn(words, str(caught.exception))

    def test_an_error_that_is_no_network_failure_keeps_its_own_name(self) -> None:
        model, _ = model_with([ValueError("a bug in the desk")])
        with self.assertRaises(ValueError):
            model.send("Reply with JSON.", {"task": "test"})

    def test_a_cut_connection_gets_one_more_try(self) -> None:
        model, client = model_with([cut_connection(), REPLY])
        data, printed = ask(model)
        self.assertEqual(data, {"answer": 42})
        self.assertEqual(client.calls, 2)
        self.assertIn("once more", printed)

    def test_two_cut_connections_stop_the_role(self) -> None:
        model, client = model_with([cut_connection(), cut_connection(), REPLY])
        with self.assertRaises(app.ConnectionLost):
            ask(model)
        self.assertEqual(client.calls, 2)  # one more try, never a third

    def test_a_failure_to_connect_is_not_tried_again(self) -> None:
        # The Anthropic library has tried again by itself before it reports that it cannot connect.
        cannot_connect = anthropic.APIConnectionError.__new__(anthropic.APIConnectionError)
        model, client = model_with([cannot_connect, REPLY])
        with self.assertRaises(app.RoleError) as caught:
            ask(model)
        self.assertNotIsInstance(caught.exception, app.ConnectionLost)
        self.assertIn("Could not reach the Anthropic API", str(caught.exception))
        self.assertEqual(client.calls, 1)

    def test_a_gemini_call_gets_one_more_try_too(self) -> None:
        model = app.Model(GOOGLE, app.GEMINI_MODEL, "medium")
        replies = [requests.ConnectionError("cut"), FakeResponse(200, GEMINI_REPLY)]
        with mock.patch.object(app.requests, "post", side_effect=replies) as post:
            data, printed = ask(model)
        self.assertEqual(data, {"answer": 42})
        self.assertEqual(post.call_count, 2)
        self.assertIn("once more", printed)
        with mock.patch.object(app.requests, "post", side_effect=[requests.ConnectionError("cut"), requests.Timeout("slow")]) as post:
            with self.assertRaises(app.RoleError) as caught:
                ask(model)
        self.assertIn("Could not reach the Gemini API", str(caught.exception))
        self.assertEqual(post.call_count, 2)


class StopRecord(unittest.TestCase):
    """A run that stops says which part stopped and why, keeps its folder, and records the stop in it."""

    def stop(self, replies: dict[str, Any]) -> tuple[int, str, Path]:
        """Run the real graph on the saved example with one failing part; then what the program does at a stop."""
        desk = offline_desk()
        good = {"Research Analyst": research, "Financial Analyst": lambda p: GOOD_ANALYSIS, "Investment Advisor": advisor,
                "Verifier (reader)": reader, "Verifier (line check)": lambda p: {"checks": []}}
        the_team = OfflineTeam(FakeModel({**good, **replies}), desk)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                the_team.graph().invoke({"ticker": "EXM", "peers": [], "price": None, "run_dir": str(desk.outdir)}, {"recursion_limit": 40})
            except Exception as exc:  # noqa: BLE001 - the program catches every error at this point
                code = team.stopped(the_team, desk.outdir, exc)
            else:
                self.fail("the run did not stop")
        return code, err.getvalue(), desk.outdir

    @staticmethod
    def records(folder: Path) -> list[str]:
        return sorted(p.name for p in (folder / "nodes").glob("*.json"))

    @staticmethod
    def fails_with(exc: Exception) -> Any:
        def reply(packet: dict[str, Any]) -> dict[str, Any]:
            raise exc
        return reply

    def test_a_stop_in_the_verifier_is_recorded_and_says_how_to_go_on(self) -> None:
        lost = app.ConnectionLost("The connection to the Anthropic API was lost while the reply was being read (ReadError). Check the network and run again.")
        code, printed, folder = self.stop({"Verifier (reader)": self.fails_with(lost)})
        self.assertEqual(code, 1)
        self.assertIn("Verifier stopped: The connection to the Anthropic API was lost", printed)
        self.assertEqual(self.records(folder)[-1], "06_verifier_stopped.json")  # numbered after the five parts that ran
        self.assertIn("06_verifier_stopped.json", printed)
        record = json.loads((folder / "nodes" / "06_verifier_stopped.json").read_text(encoding="utf-8"))
        self.assertEqual(record["node"], "Verifier")
        stop = record["stopped"]
        self.assertIn("ConnectionLost: The connection to the Anthropic API was lost", stop["error"])
        self.assertRegex(stop["time"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")
        self.assertIn("report.md", stop["files_saved"])
        self.assertTrue(any(place.startswith("team.py:") for place in stop["where"]), stop["where"])
        # The report was written before the stop, so the run can go on from the saved folder.
        self.assertTrue((folder / "report.md").exists())
        self.assertFalse((folder / "verified_report.md").exists())
        self.assertIn("--verify-only", printed)
        self.assertNotIn("Traceback", printed)

    def test_an_error_nobody_expected_is_recorded_with_its_causes_and_no_traceback_is_printed(self) -> None:
        code, printed, folder = self.stop({"Verifier (reader)": self.fails_with(cut_connection())})
        self.assertEqual(code, 1)
        self.assertIn("Verifier stopped: an error the desk did not expect, ReadError", printed)
        self.assertNotIn("Traceback", printed)
        stop = json.loads((folder / "nodes" / "06_verifier_stopped.json").read_text(encoding="utf-8"))["stopped"]
        self.assertIn("ReadError", stop["error"])
        self.assertTrue(any("ConnectionResetError" in cause for cause in stop["causes"]), stop["causes"])
        self.assertTrue(any("Traceback" in line for line in stop["traceback"]))  # kept in the folder, not on the screen

    def test_a_stop_in_an_analyst_names_the_analyst(self) -> None:
        not_json = app.RoleError("Financial Analyst did not return JSON (stop reason max_tokens).")
        code, printed, folder = self.stop({"Financial Analyst": self.fails_with(not_json)})
        self.assertEqual(code, 1)
        self.assertIn("Financial Analyst stopped: Financial Analyst did not return JSON", printed)
        self.assertEqual(self.records(folder), ["01_steps.json", "02_research_analyst.json", "03_financial_analyst_stopped.json"])
        self.assertNotIn("--verify-only", printed)  # there is no report to verify yet
        stop = json.loads((folder / "nodes" / "03_financial_analyst_stopped.json").read_text(encoding="utf-8"))["stopped"]
        self.assertNotIn("traceback", stop)  # an error the desk expects needs none

    def test_a_failed_sec_request_keeps_its_words(self) -> None:
        desk = offline_desk()
        the_team = OfflineTeam(FakeModel({}), desk)
        the_team.current = "steps"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = team.stopped(the_team, desk.outdir, requests.ConnectionError("no route to host"))
        self.assertEqual(code, 1)
        self.assertIn("The steps stopped: SEC request failed: no route to host", err.getvalue())
        self.assertEqual(self.records(desk.outdir), ["01_steps_stopped.json"])

    def test_a_stop_before_the_first_part_is_the_runs_own(self) -> None:
        desk = offline_desk()
        the_team = OfflineTeam(FakeModel({}), desk)  # no part has started
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = team.stopped(the_team, desk.outdir, RuntimeError("the graph could not be built"))
        self.assertEqual(code, 1)
        self.assertIn("The run stopped: the graph could not be built", err.getvalue())
        self.assertEqual(self.records(desk.outdir), ["01_run_stopped.json"])
        self.assertEqual(json.loads((desk.outdir / "nodes" / "01_run_stopped.json").read_text(encoding="utf-8"))["node"], "The run")

    def test_the_record_names_no_folder_of_the_person_who_ran_the_desk(self) -> None:
        home, desk_folder = Path.home(), ROOT
        seeded = RuntimeError(f"cannot read {home / 'private' / 'notes.txt'} or {desk_folder / 'output' / 'x.txt'}")
        _, _, folder = self.stop({"Verifier (reader)": self.fails_with(seeded)})
        text = (folder / "nodes" / "06_verifier_stopped.json").read_text(encoding="utf-8")
        for place in (home, desk_folder):
            for written in (str(place), str(place).replace("\\", "\\\\"), place.as_posix()):
                self.assertNotIn(written.lower(), text.lower())
        stop = json.loads(text)["stopped"]
        self.assertIn("notes.txt", stop["error"])  # the rest of the message is kept
        for place in stop["where"]:
            self.assertRegex(place, r"^[\w.]+:\d+ in \w+$")  # a file of the desk, a line and a function, and no folder

    def test_the_stop_code_names_no_company(self) -> None:
        source = (ROOT / "tests" / "test_stops.py").read_text(encoding="utf-8") + (ROOT / "team.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT|CSCO)\b", source.replace("(COST|WMT|TGT|BJ|AAPL|MSFT|CSCO)", "")))


if __name__ == "__main__":
    unittest.main()
