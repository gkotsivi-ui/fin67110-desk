"""The setup check and the run's first step refuse settings that cannot work, and SEC EDGAR is asked again.

On 2026-11-22 the audit ran check_pipeline.py on the README's own example lines and it printed three "ok" lines.
It also passed an Anthropic key with an OpenAI model, and a model with no provider. A run then stopped at its
first model call, after the seeker, the pick and the seven data steps. One 429 or 503 from SEC EDGAR, or one
dropped connection, among a run's forty to a hundred requests ended the run. Every key, name and page is made up.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

import check_pipeline
import desk_sources
from desk_sources import Sources

GOOD = {"SEC_USER_AGENT": "Pat Example pat.example@school.example", "API_KEY": "sk-ant-made-up-0123456789", "MODEL": "anthropic/a-model"}


class TheRequiredSettings(unittest.TestCase):
    def problems(self, **changed):
        return check_pipeline.settings_problems({**GOOD, **changed})

    def test_good_settings_of_each_provider_pass(self):
        self.assertEqual(self.problems(), [])
        self.assertEqual(self.problems(API_KEY="AIzaMadeUp0123456789", MODEL="gemini/a-model"), [])
        self.assertEqual(self.problems(API_KEY="sk-proj-made-up-0123456789", MODEL="openai/a-model"), [])

    def test_the_readmes_example_lines_do_not_pass(self):
        found = self.problems(SEC_USER_AGENT="Your Name your.email@university.edu", API_KEY="your model key", MODEL="anthropic/claude-opus-5-5")
        self.assertEqual(len(found), 2)
        self.assertIn("SEC_USER_AGENT", found[0])
        self.assertIn("API_KEY", found[1])

    def test_blank_settings_are_each_named(self):
        found = self.problems(SEC_USER_AGENT="", API_KEY="", MODEL="")
        self.assertEqual([line.split()[0] for line in found], ["SEC_USER_AGENT", "API_KEY", "MODEL"])

    def test_a_name_with_no_email_does_not_pass(self):
        self.assertIn("name and email", self.problems(SEC_USER_AGENT="Pat Example")[0])

    def test_a_key_of_one_provider_and_a_model_of_another_do_not_pass(self):
        for key, model in (("sk-ant-made-up-0123456789", "openai/a-model"), ("AIzaMadeUp0123456789", "anthropic/a-model"),
                           ("sk-proj-made-up-0123456789", "gemini/a-model"), ("sk-proj-made-up-0123456789", "anthropic/a-model")):
            with self.subTest(model=model):
                found = self.problems(API_KEY=key, MODEL=model)
                self.assertEqual(len(found), 1)
                self.assertIn("two providers", found[0])
                self.assertNotIn(key, found[0])

    def test_a_model_with_no_provider_does_not_pass(self):
        self.assertIn("must start with its provider", self.problems(MODEL="a-model")[0])

    def test_a_server_of_your_own_follows_no_providers_form(self):
        self.assertEqual(self.problems(MODEL="a-local-model", API_KEY="any-key-at-all", LLM_BASE_URL="http://127.0.0.1:1234/v1"), [])

    def test_the_run_checks_the_settings_before_any_other_step(self):
        from desk_parts import Parts
        parts = Parts.__new__(Parts)
        with patch.object(check_pipeline, "read_settings", return_value={**GOOD, "MODEL": "openai/a-model"}):
            with self.assertRaisesRegex(ValueError, "The settings are not ready.*two providers"):
                parts.validate_setup()


class Answer:
    def __init__(self, status, content=b"a page", headers=None):
        self.status_code, self.content, self.headers = status, content, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


class SecEdgarIsAskedAgain(unittest.TestCase):
    URL = "https://www.sec.gov/files/a-made-up-page.json"

    def fetch(self, *answers):
        asked = []

        def transport(url, **kwargs):
            asked.append(kwargs["headers"]["User-Agent"])
            answer = answers[len(asked) - 1]
            if isinstance(answer, Exception):
                raise answer
            return answer
        sources = Sources(Path(tempfile.mkdtemp()), "Pat Example pat.example@school.example", transport=transport)
        with patch.object(desk_sources, "SEC_WAITS", (0, 0)), patch.object(desk_sources, "SEC_SPACING", 0):
            try:
                return sources.response(self.URL).content, asked
            except Exception as error:
                return error, asked

    def test_a_busy_answer_and_a_dropped_connection_are_asked_again(self):
        for first in (Answer(503), Answer(429, headers={"Retry-After": "0"}), requests.ConnectionError("dropped"), requests.Timeout("slow")):
            with self.subTest(first=getattr(first, "status_code", type(first).__name__)):
                content, asked = self.fetch(first, Answer(200))
                self.assertEqual((content, len(asked)), (b"a page", 2))
                self.assertEqual(set(asked), {"Pat Example pat.example@school.example"})

    def test_three_requests_for_one_page_and_no_more(self):
        error, asked = self.fetch(Answer(503), Answer(503), Answer(503), Answer(200))
        self.assertIsInstance(error, requests.HTTPError)
        self.assertEqual(len(asked), 3)

    def test_a_page_that_is_not_there_is_not_asked_for_again(self):
        error, asked = self.fetch(Answer(404), Answer(200))
        self.assertIsInstance(error, requests.HTTPError)
        self.assertEqual(len(asked), 1)

    def test_a_refusal_says_what_to_fix(self):
        error, asked = self.fetch(Answer(403), Answer(200))
        self.assertIn("SEC_USER_AGENT in .env must hold your own name and email", str(error))
        self.assertEqual(len(asked), 1)

    def test_no_name_and_email_asks_nothing(self):
        sources = Sources(Path(tempfile.mkdtemp()), "", transport=lambda *a, **k: self.fail("a request was made"))
        with self.assertRaisesRegex(ValueError, "SEC_USER_AGENT is missing"):
            sources.response(self.URL)


if __name__ == "__main__":
    unittest.main()
