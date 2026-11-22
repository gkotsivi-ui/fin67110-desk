"""A model call that failed on the way: one rule for the agent team and the worksheet (model_calls.py).

On 2026-11-22 the audit built each provider's errors and ran them through the two copies of the rule. Neither
tried a rate limit (429) again. The team's copy read only `status_code`, so Google's "model is overloaded" (its
errors carry `code`) ended a run at once; the worksheet's copy read it. A stalled call had no time limit on an
Anthropic or a Google model. The errors here are made up: each has the name and the fields a provider's has.
"""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import equity_research_agent_team as team
import model_calls
from desk_sources import skill


def error(name, **fields):
    made = type(name, (Exception,), {})(name)
    for key, value in fields.items():
        setattr(made, key, value)
    return made


class WhatIsTriedOnceMore(unittest.TestCase):
    def test_rate_limits_and_server_errors_of_every_provider(self):
        cases = [(error("RateLimitError", status_code=429), "rate limit"),           # Anthropic, OpenAI
                 (error("ClientError", code=429), "rate limit"),                      # Google: the status is in `code`
                 (error("ServerError", code=503), "dropped"),                         # Google: the model is overloaded
                 (error("APIStatusError", status_code=529), "dropped"),               # Anthropic: overloaded
                 (error("HTTPError", response=SimpleNamespace(status_code=503)), "dropped"),  # requests
                 (error("HTTPError", response=SimpleNamespace(status_code=429)), "rate limit"),
                 (error("ReadTimeout"), "dropped"), (ConnectionResetError(10054, "closed"), "dropped"), (TimeoutError(), "dropped")]
        for made, expected in cases:
            with self.subTest(error=type(made).__name__, fields=vars(made)):
                self.assertEqual(model_calls.retry_reason(made), expected)

    def test_a_refusal_is_never_asked_again(self):
        for made in (error("BadRequestError", status_code=400), error("AuthenticationError", status_code=401),
                     error("NotFoundError", status_code=404), error("ClientError", code=400),
                     error("APIError", code="insufficient_quota"), ValueError("Role did not read assigned files")):
            with self.subTest(error=type(made).__name__):
                self.assertIsNone(model_calls.retry_reason(made))

    def test_the_cause_inside_a_wrapped_error_is_read(self):
        outer = RuntimeError("the flow failed")
        outer.__cause__ = error("ClientError", code=429)
        self.assertEqual(model_calls.retry_reason(outer), "rate limit")

    def test_the_team_and_the_worksheet_use_this_one_rule(self):
        worksheet = skill("spinoff-worksheet")
        made = error("ServerError", code=503)
        self.assertTrue(team.dropped_connection(made))
        self.assertTrue(worksheet.dropped_connection(made))
        self.assertIs(team.dropped_connection, model_calls.dropped_connection)
        self.assertEqual(worksheet.dropped_connection.__code__, model_calls.dropped_connection.__code__)


class TheTimeLimit(unittest.TestCase):
    def test_a_call_that_stalls_raises_and_one_that_answers_returns(self):
        self.assertEqual(model_calls.within_time_limit(lambda: "answer", 5, "A role"), "answer")
        with self.assertRaisesRegex(TimeoutError, "A role: the model did not answer"):
            model_calls.within_time_limit(lambda: time.sleep(5), 0.05, "A role")
        self.assertEqual(model_calls.retry_reason(TimeoutError()), "dropped")

    def test_an_error_inside_the_call_comes_out_as_itself(self):
        def refuse():
            raise error("BadRequestError", status_code=400)
        with self.assertRaises(Exception) as caught:
            model_calls.within_time_limit(refuse, 5, "A role")
        self.assertEqual(type(caught.exception).__name__, "BadRequestError")


class TheTeamsRoleCall(unittest.TestCase):
    def call(self, *replies):
        folder = Path(tempfile.mkdtemp())
        rt = team.Runtime.__new__(team.Runtime)
        rt.set_output_dir(folder)
        rt.role_call_counts, rt.skill_files, rt.output_hook, rt.llm = {}, [], None, object()
        rt.instructions = lambda name: "Answer in JSON."
        with patch.object(team, "Agent"), patch.object(team, "Task"), patch.object(team, "Crew") as crew, \
                patch.object(team, "RETRY_WAIT_SECONDS", 0), patch.object(team, "RATE_LIMIT_WAIT_SECONDS", 0):
            crew.return_value.kickoff.side_effect = list(replies)
            output = rt.role_call("Legacy Financial", "legacy.md", {"task": "Answer.", "context": {}, "expected_output": "JSON"})
        return output, crew.return_value.kickoff.call_count, folder

    def test_googles_overloaded_answer_is_tried_once_more(self):
        output, calls, _ = self.call(error("ServerError", code=503), SimpleNamespace(raw='{"draft": "ok"}'))
        self.assertEqual((output, calls), ({"draft": "ok"}, 2))

    def test_a_rate_limit_is_tried_once_more_and_recorded_as_one(self):
        output, calls, folder = self.call(error("RateLimitError", status_code=429), SimpleNamespace(raw='{"draft": "ok"}'))
        self.assertEqual((output, calls), ({"draft": "ok"}, 2))
        record = json.loads((folder / "nodes/Legacy_Financial_1/dropped_connections.json").read_text(encoding="utf-8"))
        self.assertEqual([r["reason"] for r in record], ["rate limit"])


class TheTeamsSettings(unittest.TestCase):
    def test_a_missing_model_is_named_and_no_other_model_is_taken(self):
        with patch.dict("os.environ", {"API_KEY": "a-made-up-key", "MODEL": ""}), patch.object(team, "load_dotenv"), patch.object(team, "LLM") as llm:
            with self.assertRaisesRegex(ValueError, "MODEL is missing or empty in .env"):
                team.Runtime()
        llm.assert_not_called()

    def test_each_request_gets_a_time_limit(self):
        with patch.dict("os.environ", {"API_KEY": "a-made-up-key", "MODEL": "anthropic/a-made-up-model"}), patch.object(team, "load_dotenv"), patch.object(team, "LLM") as llm:
            team.Runtime()
        self.assertEqual(llm.call_args.kwargs["timeout"], model_calls.REQUEST_TIME_LIMIT_SECONDS)


class TheWorksheetsCall(unittest.TestCase):
    ENV = {"MODEL": "anthropic/claude-made-up", "API_KEY": "the-team-key", "ANTHROPIC_API_KEY": "a-key-left-in-the-shell"}

    def setUp(self):
        self.worksheet = skill("spinoff-worksheet")

    def answer(self, status, body):
        response = Mock()
        response.status_code, response.text = status, json.dumps(body)
        response.json.return_value = body
        return response

    def test_it_sends_the_teams_key_and_no_other(self):
        good = self.answer(200, {"content": [{"type": "text", "text": json.dumps({"judgment": "Supported.", "next_filing_trigger": "Watch."})}]})
        with patch.dict("os.environ", self.ENV), patch("requests.post", return_value=good) as post:
            self.worksheet.judge_once("A persona", {})
        self.assertEqual(post.call_args.kwargs["headers"]["x-api-key"], "the-team-key")

    def test_a_refusal_says_what_the_provider_said_and_is_saved(self):
        refused = self.answer(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "a made-up cause"}})
        saved = []
        with patch.dict("os.environ", self.ENV), patch("requests.post", return_value=refused) as post:
            with self.assertRaisesRegex(Exception, "400 from the model provider: a made-up cause"):
                self.worksheet.judge_once("A persona", {}, record_response=saved.append)
        self.assertEqual((post.call_count, saved[0]["status"]), (1, 400))

    def test_a_rate_limit_is_tried_once_more(self):
        limited = self.answer(429, {"type": "error", "error": {"message": "slow down"}})
        good = self.answer(200, {"content": [{"type": "text", "text": json.dumps({"judgment": "Supported.", "next_filing_trigger": "Watch."})}]})
        with patch.dict("os.environ", self.ENV), patch.object(self.worksheet, "RATE_LIMIT_WAIT_SECONDS", 0), patch("requests.post", side_effect=[limited, good]) as post:
            self.assertEqual(self.worksheet.judge_once("A persona", {})["judgment"], "Supported.")
        self.assertEqual(post.call_count, 2)


class AReplyWithWindowsLineEnds(unittest.TestCase):
    def test_a_drafts_line_ends_are_made_one_kind_before_anything_is_saved(self):
        from desk_claims import parse_response
        reply = json.dumps({"claims": [], "draft": "== 1. OVERVIEW ==\r\nA line.\r\nInsight: another line.\r"})
        draft = parse_response(reply, "Research Analyst")["draft"]
        self.assertEqual(draft, "== 1. OVERVIEW ==\nA line.\nInsight: another line.\n")
        saved = Path(tempfile.mkdtemp()) / "draft.md"
        saved.write_text(draft, encoding="utf-8")
        self.assertEqual(saved.read_text(encoding="utf-8"), draft)  # what the hook compares


if __name__ == "__main__":
    unittest.main()
