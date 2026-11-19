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
import desk  # noqa: E402


class FormTests(unittest.TestCase):
    def test_local_final_report_requires_complete_pipeline_status(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            run = root / 'runs/practice/EXM'
            run.mkdir(parents=True)
            final = run / 'final_report.md'
            final.write_text('# Final report\n')
            intermediate = run / 'verified_report.md'
            intermediate.write_text('# Intermediate\n')
            state = run / 'desk_run.json'
            with mock.patch.object(page, 'ROOT', root), mock.patch.object(page, 'OUTPUT', root / 'output'):
                state.write_text(json.dumps({'status': 'failed', 'final_report': final.name}))
                self.assertIsNone(page.safe_report(str(final)))
                self.assertIsNone(page.safe_report(str(intermediate)))
                state.write_text(json.dumps({'status': 'complete', 'final_report': final.name}))
                self.assertEqual(page.safe_report(str(final)), final)

    def test_run_uses_only_this_repositorys_pipeline(self) -> None:
        process = mock.Mock(stdout=iter([]))
        with mock.patch.object(page.subprocess, "Popen", return_value=process) as popen, \
             mock.patch.object(page.threading, "Thread"):
            page.Run(["EXM"])
        self.assertEqual(popen.call_args.args[0], [sys.executable, "-u", str(ROOT / "desk.py"), "EXM"])
        self.assertEqual(popen.call_args.kwargs["cwd"], ROOT)

    def test_other_repository_reports_and_reviews_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "verified_report.md"
            path.write_text("# External report\n")
            self.assertIsNone(page.safe_report(str(path)))
            with self.assertRaises(ValueError):
                page.review_folder(folder)

    def test_the_page_lists_the_graphs_nodes_in_order(self) -> None:
        self.assertEqual(page.NODES, ["inputs", "seeker", "pick", "team", "worksheet", "final report"])

    def test_the_form_becomes_local_pipeline_arguments(self) -> None:
        args, problem = page.arguments({"ticker": " exm ", "peers": "peer, oth", "refresh_screen": "2026-01-01", "filed": "2026-10-06T21:13:15"})
        self.assertEqual((args, problem), (["EXM", "--peers", "PEER", "OTH", "--refresh-screen", "2026-01-01", "--filed", "2026-10-06T21:13:15"], ""))
        self.assertEqual(page.arguments({"ticker": "EXM"}), (["EXM"], ""))

    def test_a_bad_form_says_what_is_wrong(self) -> None:
        for body, words in (({"ticker": ""}, "Type a ticker"), ({"ticker": "EXM; rm"}, "Type a ticker"),
                            ({"ticker": "EXM", "peers": "A,B C"}, "Peers are tickers"), ({"ticker": "EXM", "refresh_screen": "2026-02-30"}, "YYYY-MM-DD"),
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
        self.assertIn("Run the group desk", text)
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

    def test_setup_uses_local_configuration_check(self) -> None:
        done = mock.Mock(returncode=0, stdout="ok local setup\n")
        with mock.patch.object(page.subprocess, "run", return_value=done) as run:
            status, _ = self.ask("GET", "/setup")
        self.assertEqual(status, 200)
        self.assertEqual(run.call_args.args[0][1], str(ROOT / "check_pipeline.py"))
        self.assertEqual(run.call_args.kwargs["cwd"], ROOT)


if __name__ == "__main__":
    unittest.main()
