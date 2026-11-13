"""Offline tests of the setup: how .env is read, the key checks, and the Gemini and OpenAI paths against made-up replies.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lab03_app as app  # noqa: E402
from lab02_desk import api_key_problem, is_placeholder, load_dotenv, no_env_message, provider_of, user_agent_problem  # noqa: E402

GOOGLE = "AIza" + "x" * 35
ANTHROPIC = "sk-ant-api03-" + "x" * 40
OPENAI = "sk-proj-" + "x" * 40
ENV = Path(".env")


class FakeResponse:
    """The parts of a requests.Response that the Gemini path reads."""

    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status_code = status
        self.body = body
        self.text = json.dumps(body)

    def json(self) -> dict[str, Any]:
        return self.body


class EnvFile(unittest.TestCase):
    def read(self, data: bytes) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_bytes(data)
            return load_dotenv(path)

    def test_utf16_as_windows_powershell_writes_it(self) -> None:
        values = self.read("API_KEY=AIzaTEST\r\nSEC_USER_AGENT=A Student a@purdue.edu\r\n".encode("utf-16"))
        self.assertEqual(values, {"API_KEY": "AIzaTEST", "SEC_USER_AGENT": "A Student a@purdue.edu"})

    def test_bom_quotes_export_and_comments(self) -> None:
        values = self.read('﻿# a comment\nexport API_KEY="sk-ant-TEST"\nMODEL = gemini/gemini-3.5-flash-lite\n'.encode("utf-8"))
        self.assertEqual(values, {"API_KEY": "sk-ant-TEST", "MODEL": "gemini/gemini-3.5-flash-lite"})

    def test_example_values_count_as_missing(self) -> None:
        example = load_dotenv(ROOT / ".env.example")
        for name in ("SEC_USER_AGENT", "API_KEY", "FINANCIAL_DATASETS_API_KEY"):
            self.assertTrue(is_placeholder(example[name]), name)
        self.assertFalse(is_placeholder("A Student a@purdue.edu"))

    def test_the_example_names_the_default_model_of_each_provider(self) -> None:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        for model in (app.DEFAULT_MODEL, app.GEMINI_MODEL, app.OPENAI_MODEL):
            self.assertIn(model, text)


class KeyChecks(unittest.TestCase):
    def test_providers(self) -> None:
        self.assertEqual([provider_of(k) for k in (ANTHROPIC, GOOGLE, OPENAI, "abc")], ["anthropic", "google", "openai", ""])

    def test_a_key_of_each_provider_passes(self) -> None:
        for key in (ANTHROPIC, GOOGLE, OPENAI):
            self.assertIsNone(api_key_problem(key, ENV), key[:8])

    def test_a_key_of_no_provider_says_which_keys_work(self) -> None:
        message = api_key_problem("abc" + "x" * 40, ENV)
        for words in ("not a key this desk can use", "sk-ant-", "AIza", "sk-", "OpenAI", "lab02_desk.py) need no model key"):
            self.assertIn(words, message)

    def test_set_keys_takes_a_key_of_each_provider(self) -> None:
        import set_keys

        check = dict((name, check) for name, _, check in set_keys.KEYS)["API_KEY"]
        for key in (ANTHROPIC, GOOGLE, OPENAI):
            self.assertIsNone(check(key), key[:8])
        self.assertIsNotNone(check("abc"))

    def test_example_key_and_no_env_file(self) -> None:
        self.assertIn("still the example", api_key_problem("", ENV))
        self.assertIn("still the example", api_key_problem("sk-paste-your-key-here", ENV))  # a prefix alone is not a key
        with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
            self.assertIn("There is no .env file", api_key_problem("", None))
            (Path(tmp) / ".env.txt").write_text("API_KEY=x\n", encoding="utf-8")
            self.assertIn("Rename it to .env", no_env_message())

    def test_user_agent_needs_a_name_and_an_email(self) -> None:
        self.assertIsNone(user_agent_problem("A Student a@purdue.edu", ENV))
        for agent in ("Your Name your.email@purdue.edu", "A Student", ""):
            self.assertIn("needs your own name and email", user_agent_problem(agent, ENV), agent)


class GeminiPath(unittest.TestCase):
    REPLY = {
        "candidates": [{"content": {"parts": [{"text": "a thought", "thought": True}, {"text": '{"answer": 42}'}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30, "thoughtsTokenCount": 12},
        "modelVersion": "gemini-3.8-flash-001",
    }

    def ask(self, model: app.Model, response: FakeResponse) -> tuple[dict[str, Any], mock.MagicMock]:
        with mock.patch.object(app.requests, "post", return_value=response) as post, contextlib.redirect_stdout(io.StringIO()):
            return model.ask("Research Analyst", "Reply with JSON.", {"task": "test"}), post

    def test_the_key_picks_the_model(self) -> None:
        self.assertEqual(app.Model(GOOGLE, app.DEFAULT_MODEL, "medium").model, app.GEMINI_MODEL)
        self.assertEqual(app.Model(GOOGLE, "gemini/gemini-3.5-flash-lite", "medium").model, "gemini-3.5-flash-lite")
        self.assertEqual(app.Model(ANTHROPIC, "gemini-3.8-flash", "medium").model, app.DEFAULT_MODEL)
        self.assertEqual(app.Model(ANTHROPIC, "claude-sonnet-5-5", "medium").model, "claude-sonnet-5-5")
        # An OpenAI key: MODEL when it names an OpenAI model, else the default for OpenAI.
        self.assertEqual(app.Model(OPENAI, app.DEFAULT_MODEL, "medium").model, app.OPENAI_MODEL)
        self.assertEqual(app.Model(OPENAI, "gemini-3.8-flash", "medium").model, app.OPENAI_MODEL)
        self.assertEqual(app.Model(OPENAI, "openai/gpt-x-test", "medium").model, "gpt-x-test")
        # A model of OpenAI does not apply to another provider's key.
        self.assertEqual(app.Model(GOOGLE, "gpt-x-test", "medium").model, app.GEMINI_MODEL)
        self.assertEqual(app.Model(ANTHROPIC, "gpt-x-test", "medium").model, app.DEFAULT_MODEL)
        self.assertEqual([app.Model(key, "", "medium").vendor for key in (ANTHROPIC, GOOGLE, OPENAI)], ["Anthropic", "Google", "OpenAI"])

    def test_a_reply_is_read_as_an_anthropic_message_is(self) -> None:
        model = app.Model(GOOGLE, app.GEMINI_MODEL, "medium")
        data, post = self.ask(model, FakeResponse(200, self.REPLY))
        self.assertEqual(data, {"answer": 42})
        url = post.call_args.args[0]
        self.assertTrue(url.endswith(f"/models/{app.GEMINI_MODEL}:generateContent"))
        self.assertNotIn(GOOGLE, url)
        self.assertEqual(post.call_args.kwargs["headers"], {"x-goog-api-key": GOOGLE})
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(sent["systemInstruction"]["parts"][0]["text"], "Reply with JSON.")
        self.assertEqual(model.exchanges[0]["served_by"], "gemini-3.8-flash-001")
        self.assertEqual(model.exchanges[0]["usage"], {"input_tokens": 120, "output_tokens": 42})

    def test_a_bad_key_stops_with_what_to_do(self) -> None:
        error = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}
        with self.assertRaises(app.RoleError) as caught:
            self.ask(app.Model(GOOGLE, app.GEMINI_MODEL, "medium"), FakeResponse(400, error))
        self.assertIn("rejected API_KEY", str(caught.exception))

    def test_a_blocked_reply_is_a_refusal(self) -> None:
        reply = {"candidates": [{"content": {"parts": []}, "finishReason": "SAFETY"}]}
        with self.assertRaises(app.RoleError) as caught:
            self.ask(app.Model(GOOGLE, app.GEMINI_MODEL, "medium"), FakeResponse(200, reply))
        self.assertIn("declined", str(caught.exception))


class EmptyResponse(FakeResponse):
    """A reply with no body, as OpenAI's API gives for a request with no key."""

    def __init__(self, status: int) -> None:
        super().__init__(status, {})
        self.text = ""

    def json(self) -> dict[str, Any]:
        raise ValueError("no JSON in the body")


class OpenAIPath(unittest.TestCase):
    """The OpenAI path against made-up replies in the shape of OpenAI's Responses API. No test calls OpenAI."""

    REPLY = {
        "id": "resp_test", "status": "completed", "model": "gpt-x-test-2026-01-01",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "role": "assistant", "status": "completed",
             "content": [{"type": "output_text", "text": '{"answer": 42}', "annotations": []}]},
        ],
        "usage": {"input_tokens": 120, "output_tokens": 42},
    }

    def ask(self, response: FakeResponse) -> tuple[dict[str, Any], mock.MagicMock, app.Model]:
        model = app.Model(OPENAI, "gpt-x-test", "medium")
        with mock.patch.object(app.requests, "post", return_value=response) as post, contextlib.redirect_stdout(io.StringIO()):
            return model.ask("Research Analyst", "Reply with JSON.", {"task": "test"}), post, model

    def refused(self, response: FakeResponse) -> str:
        with self.assertRaises(app.RoleError) as caught:
            self.ask(response)
        return str(caught.exception)

    def test_a_reply_is_read_as_an_anthropic_message_is(self) -> None:
        data, post, model = self.ask(FakeResponse(200, self.REPLY))
        self.assertEqual(data, {"answer": 42})
        self.assertEqual(post.call_args.args[0], "https://api.openai.com/v1/responses")
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": f"Bearer {OPENAI}"})  # the key goes in a header, never in the URL
        sent = post.call_args.kwargs["json"]
        self.assertEqual((sent["model"], sent["instructions"], sent["store"]), ("gpt-x-test", "Reply with JSON.", False))
        self.assertEqual(json.loads(sent["input"]), {"task": "test"})
        self.assertEqual(model.exchanges[0]["served_by"], "gpt-x-test-2026-01-01")
        self.assertEqual(model.exchanges[0]["usage"], {"input_tokens": 120, "output_tokens": 42})

    def test_the_text_is_found_wherever_the_message_stands(self) -> None:
        reply = dict(self.REPLY, output=list(reversed(self.REPLY["output"])), usage={"prompt_tokens": 7, "completion_tokens": 5})
        data, _, model = self.ask(FakeResponse(200, reply))
        self.assertEqual(data, {"answer": 42})
        self.assertEqual(model.exchanges[0]["usage"], {"input_tokens": 7, "output_tokens": 5})

    def test_a_bad_key_stops_with_what_to_do(self) -> None:
        error = {"error": {"message": "Incorrect API key provided.", "type": "invalid_request_error", "param": None, "code": "invalid_api_key"}}
        # OpenAI's own message can show the key, whole or with stars in the middle. The desk's message shows neither.
        starred = f"{OPENAI[:8]}{'*' * 30}{OPENAI[-4:]}"
        shown = {"error": {"message": f"Incorrect API key provided: {starred}. The key sent was {OPENAI}.", "code": "invalid_api_key"}}
        for response in (FakeResponse(401, error), EmptyResponse(401), FakeResponse(401, shown)):
            message = self.refused(response)
            self.assertIn("rejected API_KEY", message)
            for part in (OPENAI, starred, OPENAI[-4:] + "."):
                self.assertNotIn(part, message)

    def test_a_model_the_key_cannot_use(self) -> None:
        error = {"error": {"message": "The model `gpt-x-test` does not exist or you do not have access to it.", "type": "invalid_request_error", "code": "model_not_found"}}
        for status in (404, 400):
            self.assertIn("Set MODEL in .env", self.refused(FakeResponse(status, error)))

    def test_no_credit_is_not_the_same_as_too_many_requests(self) -> None:
        quota = {"error": {"message": "You exceeded your current quota.", "type": "insufficient_quota", "code": "insufficient_quota"}}
        rate = {"error": {"message": "Rate limit reached.", "type": "requests", "code": "rate_limit_exceeded"}}
        self.assertIn("credit", self.refused(FakeResponse(429, quota)))
        self.assertIn("Wait a minute", self.refused(FakeResponse(429, rate)))

    def test_a_refusal_and_an_empty_reply(self) -> None:
        refusal = dict(self.REPLY, output=[{"type": "message", "content": [{"type": "refusal", "refusal": "I cannot help with that."}]}])
        self.assertIn("declined", self.refused(FakeResponse(200, refusal)))
        self.assertIn("declined", self.refused(FakeResponse(200, dict(self.REPLY, status="incomplete", incomplete_details={"reason": "content_filter"}, output=[]))))
        self.assertIn("no text", self.refused(FakeResponse(200, dict(self.REPLY, output=[]))))

    def test_a_reply_cut_off_at_the_token_limit_says_so(self) -> None:
        cut = dict(self.REPLY, status="incomplete", incomplete_details={"reason": "max_output_tokens"},
                   output=[{"type": "message", "content": [{"type": "output_text", "text": '{"answer": 4'}]}])
        self.assertIn("stop reason max_tokens", self.refused(FakeResponse(200, cut)))

    def test_the_desk_code_names_no_openai_model_but_its_default(self) -> None:
        source = (ROOT / "lab03_app.py").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"\bgpt-[\w.-]+", source)), {app.OPENAI_MODEL})


class CheckEnvOffline(unittest.TestCase):
    """check_env.py --offline, run in a folder that holds a made-up .env. It makes no network call."""

    SETTINGS = ("SEC_USER_AGENT", "API_KEY", "ANTHROPIC_API_KEY", "MODEL", "LSEG_APP_KEY", "CLOSES_FILE", "FINANCIAL_DATASETS_API_KEY")

    def check(self, key: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".env").write_text(f"SEC_USER_AGENT=A Student a@purdue.edu\nAPI_KEY={key}\n", encoding="utf-8")
            # The settings of the person who runs the tests stay out of the check.
            env = {name: value for name, value in os.environ.items() if name not in self.SETTINGS}
            done = subprocess.run([sys.executable, str(ROOT / "check_env.py"), "--offline"], cwd=tmp, env=env,
                                  capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        return done.stdout + done.stderr

    def test_it_names_the_provider_and_the_model_and_prints_no_key(self) -> None:
        for key, kind, model in ((ANTHROPIC, "an Anthropic key", app.DEFAULT_MODEL), (GOOGLE, "a Google AI Studio key", app.GEMINI_MODEL),
                                 (OPENAI, "an OpenAI key", app.OPENAI_MODEL)):
            printed = self.check(key)
            line = next((text for text in printed.splitlines() if "API_KEY:" in text), printed)
            self.assertTrue(line.startswith("ok"), line)
            self.assertIn(f"API_KEY: {kind}", line)
            self.assertIn(f"the roles will run on {model}", line)
            self.assertNotIn(key, printed)

    def test_a_key_of_no_provider_is_a_fix(self) -> None:
        printed = self.check("abc" + "x" * 40)
        self.assertIn("FIX   API_KEY in", printed)
        self.assertIn("not a key this desk can use", printed)


class NoCompanyNamedInSetupCode(unittest.TestCase):
    def test_the_setup_code_names_no_company(self) -> None:
        for name in ("check_env.py", "set_keys.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT)\b", source), name)
            self.assertIsNone(re.search(r"costco|walmart|target corp|wholesale club|apple inc|microsoft", source, re.I), name)


if __name__ == "__main__":
    unittest.main()
