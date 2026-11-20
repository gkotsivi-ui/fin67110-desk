"""Exercise the review's HTTP contract on an isolated local server and temporary repository."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import page
from error_review_evaluation import put


class ReviewPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "runs/practice/EXM"
        self.run.mkdir(parents=True)
        put(self.run, "facts.json", {"company": "Example", "ticker": "EXM", "facts": {}})
        put(self.run, "report.md", "# Example\nPartner's check:\n")
        put(self.run, "run.log", "ValueError: <script>alert('x')</script>\n")
        for name, value in [("ROOT", self.root), ("OUTPUT", self.root / "output"), ("RUN", None), ("REVIEW_JOB", None)]:
            p = patch.object(page, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), page.Page)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def ask(self, method, path, body=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        text = response.read().decode()
        code = response.status
        conn.close()
        return code, text

    def test_saved_run_review_shows_groups_evidence_and_both_downloads(self):
        code, _ = self.ask("POST", "/review", {"folder": "runs/practice/EXM", "record_number": 1})
        self.assertEqual(code, 202)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, text = self.ask("GET", "/review/status")
            state = json.loads(text)
            if state["done"]:
                break
            time.sleep(.02)
        self.assertFalse(state["error"])
        self.assertTrue(state["result"]["findings"])
        for kind in ("human", "ai"):
            code, text = self.ask("GET", "/review/download?kind=" + kind)
            self.assertEqual(code, 200)
            self.assertIn("## Confirmed errors", text)
            self.assertIn("## Unconfirmed errors", text)
            self.assertIn("run/run.log:1", text)
        self.assertEqual(self.ask("GET", "/review/download?kind=../../.env")[0], 404)
        _, text = self.ask("GET", "/")
        self.assertIn("Review a saved run", text)
        # Evidence uses textContent, so untrusted filing/model markup cannot execute.
        self.assertIn("p.textContent = ref.path", text)

    def test_invalid_paths_and_foreign_origin_cannot_start_review(self):
        with patch.object(page, "ReviewJob") as job:
            for path in ("../outside", ".env", "runs/live", ""):
                self.assertEqual(self.ask("POST", "/review", {"folder": path})[0], 400)
            self.assertEqual(self.ask("POST", "/review", {"folder": "runs/practice/EXM"}, "https://foreign.example")[0], 403)
            job.assert_not_called()

    def test_active_run_is_not_stopped_or_reviewed(self):
        class Active:
            done = False
        with patch.object(page, "RUN", Active()), patch.object(page, "ReviewJob") as job:
            self.assertEqual(self.ask("POST", "/review", {"folder": "runs/practice/EXM"})[0], 409)
            job.assert_not_called()

    def test_symlink_run_outside_allowed_folders_is_rejected(self):
        outside = self.root / "private"
        outside.mkdir()
        try:
            (self.root / "runs/practice/link").symlink_to(outside)
        except OSError as error:  # Windows: administrator rights or Developer Mode
            self.skipTest(f"this account cannot create a symlink: {error}")
        with self.assertRaises(ValueError):
            page.review_folder("runs/practice/link")
