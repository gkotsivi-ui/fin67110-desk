"""Offline tests of the page: the form's checks, the report paths it serves, and who may start a run.

No test starts a run of the agent team. Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import page  # noqa: E402
import team  # noqa: E402


class FormTests(unittest.TestCase):
    def test_the_page_lists_the_graphs_nodes_in_order(self) -> None:
        self.assertEqual(page.NODES, [team.NAMES[node] for node in team.ORDER])

    def test_the_form_becomes_team_py_arguments(self) -> None:
        args, problem = page.arguments({"ticker": " exm ", "peers": "peer, oth", "price": "$1,004.75", "filed": "2026-10-06T21:13:15"})
        self.assertEqual((args, problem), (["EXM", "--peers", "PEER,OTH", "--price", "1004.75", "--filed", "2026-10-06T21:13:15"], ""))
        self.assertEqual(page.arguments({"ticker": "EXM"}), (["EXM"], ""))

    def test_a_bad_form_says_what_is_wrong(self) -> None:
        for body, words in (({"ticker": ""}, "Type a ticker"), ({"ticker": "EXM; rm"}, "Type a ticker"),
                            ({"ticker": "EXM", "peers": "A,B C"}, "Peers are tickers"), ({"ticker": "EXM", "price": "ten"}, "a number"),
                            ({"ticker": "EXM", "filed": "2026-10-06 21:13"}, "YYYY-MM-DDTHH:MM:SS")):
            args, problem = page.arguments(body)
            self.assertEqual(args, [])
            self.assertIn(words, problem)

    def test_only_markdown_files_in_the_output_folder_are_served(self) -> None:
        saved = next(page.OUTPUT.glob("*/verified_report*.md"), None)
        if saved is not None:
            self.assertEqual(page.safe_report(saved.relative_to(ROOT).as_posix()), saved.resolve())
        for path in ("README.md", "output/../README.md", "../outside.md", ".env", "output", "page.py"):
            self.assertIsNone(page.safe_report(path), path)


class ServerTests(unittest.TestCase):
    """The page on a free port of this computer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), page.Page)
        cls.server.daemon_threads = True
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def ask(self, method: str, path: str, body: str | None = None, headers: dict[str, str] | None = None) -> tuple[int, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(method, path, body=body, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
        answer = connection.getresponse()
        text = answer.read().decode("utf-8")
        connection.close()
        return answer.status, text

    def test_the_page_and_its_saved_runs(self) -> None:
        status, text = self.ask("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Run the agent team", text)
        self.assertIn(json.dumps(page.NODES), text)
        status, text = self.ask("GET", "/runs")
        self.assertEqual(status, 200)
        self.assertIsInstance(json.loads(text), list)

    def test_a_report_renders_with_its_text_escaped(self) -> None:
        # A fresh clone has no output folder yet: practice runs are not committed.
        page.OUTPUT.mkdir(exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=page.OUTPUT))
        try:
            (folder / "verified_report.md").write_text("# A report\n\n| # | Mark |\n|---|---|\n| 1 | **wrong** |\n\n<script>bad()</script>\n", encoding="utf-8")
            status, text = self.ask("GET", f"/report?path=output/{folder.name}/verified_report.md")
        finally:
            for file in folder.iterdir():
                file.unlink()
            folder.rmdir()
        self.assertEqual(status, 200)
        self.assertIn("<td><strong>wrong</strong></td>", text)
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_another_website_cannot_start_a_run(self) -> None:
        body = json.dumps({"ticker": "EXM"})
        with mock.patch.object(page, "Run") as run:
            self.assertEqual(self.ask("POST", "/run", body, {"Content-Type": "text/plain"})[0], 415)
            self.assertEqual(self.ask("POST", "/run", body, {"Content-Type": "application/json", "Origin": "http://example.com"})[0], 403)
            self.assertEqual(self.ask("GET", "/", headers={"Host": "attacker.example:80"})[0], 403)
            run.assert_not_called()

    def test_a_bad_form_starts_nothing(self) -> None:
        with mock.patch.object(page, "Run") as run:
            status, text = self.ask("POST", "/run", json.dumps({"ticker": ""}), {"Content-Type": "application/json"})
            run.assert_not_called()
        self.assertEqual(status, 400)
        self.assertIn("Type a ticker", json.loads(text)["error"])


if __name__ == "__main__":
    unittest.main()
