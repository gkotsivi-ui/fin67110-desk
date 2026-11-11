"""Offline tests of the setup: how .env is read, the key checks, and the Gemini path against a fake reply.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import io
import json
import re
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


class KeyChecks(unittest.TestCase):
    def test_providers(self) -> None:
        self.assertEqual([provider_of(k) for k in (ANTHROPIC, GOOGLE, OPENAI, "abc")], ["anthropic", "google", "openai", ""])

    def test_anthropic_and_google_keys_pass(self) -> None:
        self.assertIsNone(api_key_problem(ANTHROPIC, ENV))
        self.assertIsNone(api_key_problem(GOOGLE, ENV))

    def test_an_openai_key_says_which_keys_work(self) -> None:
        message = api_key_problem(OPENAI, ENV)
        for words in ("an OpenAI key", "sk-ant-", "AIza", "lab02_desk.py) need no model key"):
            self.assertIn(words, message)

    def test_example_key_and_no_env_file(self) -> None:
        self.assertIn("still the example", api_key_problem("", ENV))
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


class NoCompanyNamedInSetupCode(unittest.TestCase):
    def test_the_setup_code_names_no_company(self) -> None:
        for name in ("check_env.py", "set_keys.py"):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT)\b", source), name)
            self.assertIsNone(re.search(r"costco|walmart|target corp|wholesale club|apple inc|microsoft", source, re.I), name)


if __name__ == "__main__":
    unittest.main()
