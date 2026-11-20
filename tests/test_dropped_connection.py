"""A model call whose connection drops is made once more; nothing else is retried.

On 2026-11-19 a practice run on Lowe's lost its connection to Anthropic five minutes into the Verifier's call,
and the whole run stopped with no report. The roles run through CrewAI here; Agent, Task and Crew are stubbed.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import equity_research_agent_team as team

ENVELOPE = {"task": "Answer.", "context": {}, "expected_output": "JSON"}


class APIConnectionError(Exception):
    """The name the Anthropic and OpenAI SDKs give a dropped connection."""


def runtime(folder):
    rt = team.Runtime.__new__(team.Runtime)
    rt.set_output_dir(Path(folder))
    rt.role_call_counts, rt.skill_files, rt.output_hook, rt.llm = {}, [], None, object()
    rt.instructions = lambda name: "Answer in JSON."
    return rt


class DroppedConnectionTests(unittest.TestCase):
    def call(self, *replies):
        folder = tempfile.mkdtemp()
        with patch.object(team, "Agent"), patch.object(team, "Task"), patch.object(team, "Crew") as crew, \
                patch.object(team, "RETRY_WAIT_SECONDS", 0):
            crew.return_value.kickoff.side_effect = list(replies)
            try:
                return runtime(folder).role_call("Legacy Financial", "legacy.md", ENVELOPE), crew, Path(folder)
            except Exception as error:
                return error, crew, Path(folder)

    def test_a_dropped_connection_is_tried_once_more(self):
        output, crew, folder = self.call(APIConnectionError("Connection error."), SimpleNamespace(raw='{"draft": "ok"}'))
        self.assertEqual(output, {"draft": "ok"})
        self.assertEqual(crew.return_value.kickoff.call_count, 2)
        record = json.loads((folder / "nodes/Legacy_Financial_1/dropped_connections.json").read_text(encoding="utf-8"))
        self.assertEqual([r["error"] for r in record], ["APIConnectionError: Connection error."])

    def test_a_second_drop_stops_the_run(self):
        error, crew, _ = self.call(ConnectionResetError(10054, "forcibly closed"), ConnectionResetError(10054, "again"))
        self.assertIsInstance(error, ConnectionResetError)
        self.assertEqual(crew.return_value.kickoff.call_count, 2)

    def test_any_other_error_is_not_retried(self):
        error, crew, _ = self.call(ValueError("Role did not read assigned files"))
        self.assertIsInstance(error, ValueError)
        self.assertEqual(crew.return_value.kickoff.call_count, 1)

    def test_what_counts_as_a_reply_that_never_came(self):
        wrapped = RuntimeError("Flow failed")
        wrapped.__cause__ = APIConnectionError("Connection error.")
        server = Exception("Overloaded")
        server.status_code = 529
        refused = Exception("Bad request")
        refused.status_code = 400
        for error, expected in ((APIConnectionError("x"), True), (ConnectionResetError(), True), (TimeoutError(), True),
                                (wrapped, True), (server, True), (refused, False), (ValueError("x"), False)):
            with self.subTest(error=repr(error)):
                self.assertEqual(team.dropped_connection(error), expected)


if __name__ == "__main__":
    unittest.main()
