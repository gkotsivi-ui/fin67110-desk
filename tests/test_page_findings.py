"""What the page serves, shows and starts, on made-up reports. No desk run and no network.

On 2026-11-22 the audit sent the page made-up reports and requests, and each test here failed: a report's link
could be a script, its image was fetched from any host, "2*3*4" was shown as 234, a table row with a cell too
many lost its last cells, a report that was not UTF-8 closed the connection, a network path reached the file
system, a draft that never passed the audit was served, a crashed setup check read as "passed", a second page
shared the first one's port on Windows, the form took a time that does not exist, Stop said it had stopped a
run that had ended, another website's GET started the setup check, a JSON null became the ticker NONE, and
deeply nested JSON got no answer. The reports and run folders are made in a temporary folder that stands in for
the repository, so the tests write nothing into it.
"""
from __future__ import annotations

import errno
import http.client
import json
import ntpath
import os
import re
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import page


class FakeProcess:
    def __init__(self):
        self.stdout = iter(()); self.terminated = 0
    def wait(self): return 0
    def terminate(self): self.terminated += 1


class Findings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        root = Path(cls.folder.name).resolve()
        (root / "output").mkdir()
        (root / "runs" / "practice").mkdir(parents=True)
        cls.patches = [mock.patch.object(page, "ROOT", root), mock.patch.object(page, "OUTPUT", root / "output")]
        for patch in cls.patches:
            patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), page.Page)
        cls.server.daemon_threads = True
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()
        for patch in cls.patches:
            patch.stop()
        cls.folder.cleanup()

    def ask(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            c.request(method, path, body=body, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
            r = c.getresponse()
            return r.status, r.read().decode("utf-8", "replace")
        except (http.client.RemoteDisconnected, ConnectionError) as error:
            self.fail(f"the page gave no answer: {type(error).__name__}")
        finally:
            c.close()

    def report(self, raw: bytes, name="verified_report.md"):
        page.OUTPUT.mkdir(exist_ok=True)
        folder = Path(tempfile.mkdtemp(dir=page.OUTPUT))
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / name).write_bytes(raw)
        return f"output/{folder.name}/{name}"

    # P1
    def test_links_and_images_in_a_report_are_not_live(self):
        path = self.report(b"[x](javascript:alert(1))\n\n![](http://example.com/x)\n\n[d](data:text/html,x)\n\n[r][1]\n\n[1]: javascript:alert(2)\n")
        status, text = self.ask("GET", "/report?path=" + path)
        self.assertEqual(status, 200)
        self.assertNotIn("javascript:", text)
        self.assertNotIn("<img", text)
        self.assertNotIn('href="data:', text)

    # P2
    def test_the_page_shows_the_digits_the_file_holds(self):
        path = self.report(b"Price 2*3*4 and 12*5 = 60*\n\n`R&D < 5`\n")
        status, text = self.ask("GET", "/report?path=" + path)
        shown = re.sub(r"<[^>]+>", "", text).replace("&lt;", "<").replace("&amp;", "&")
        self.assertIn("2*3*4", shown)
        self.assertIn("12*5 = 60*", shown)
        self.assertIn("R&D < 5", shown)

    def test_a_table_row_with_an_extra_cell_is_not_cut(self):
        path = self.report(b"| Line | Year 1 | Year 2 |\n|---|---|---|\n| Made-up debt | 5|6 | 100 | 200 |\n")
        status, text = self.ask("GET", "/report?path=" + path)
        self.assertIn("200", text)

    # P3
    def test_a_report_that_is_not_utf8_gets_an_answer(self):
        path = self.report(b"# owner cash flow \xf7 10%\n")
        status, text = self.ask("GET", "/report?path=" + path)
        self.assertIn(status, (415, 422, 500))
        self.assertIn("error", json.loads(text))

    # P4
    def test_a_network_path_never_reaches_the_filesystem(self):
        touched = []

        def guard(real):
            def wrapped(p, *a, **k):
                s = os.fspath(p) if isinstance(p, (str, os.PathLike)) else ""
                if s.startswith("\\\\") and not s.startswith("\\\\?\\"):
                    touched.append(s)
                    raise OSError(errno.ENOENT, "stand-in, nothing contacted", s, 53)
                return real(p, *a, **k)
            return wrapped

        with mock.patch.object(os, "stat", guard(os.stat)), mock.patch.object(ntpath, "_getfinalpathname", guard(ntpath._getfinalpathname), create=True), \
             mock.patch.object(ntpath, "_nt_readlink", guard(getattr(ntpath, "_nt_readlink", os.readlink)), create=True):
            self.assertIsNone(page.safe_report("\\\\made-up-host.invalid\\share\\output\\x.md"))
            self.assertIsNone(page.safe_report("//made-up-host.invalid/share/x.md"))
        self.assertEqual(touched, [])

    # P5
    def test_drafts_that_never_passed_the_audit_are_not_served(self):
        self.assertIsNone(page.safe_report(self.report(b"# draft\n", name="report.md")))
        folder = Path(tempfile.mkdtemp(dir=(page.ROOT / "runs/practice")))
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "report.md").write_text("# team-only draft, audit failed\n", encoding="utf-8")
        self.assertIsNone(page.safe_report(str(folder / "report.md")))

    # P6
    def test_a_crashed_setup_check_is_shown_as_a_fix(self):
        crashed = mock.Mock(returncode=1, stdout="ok    made-up line\n", stderr="Traceback (most recent call last):\nValueError: made-up crash\n")
        with mock.patch.object(page.subprocess, "run", return_value=crashed):
            status, text = self.ask("GET", "/setup")
        answer = json.loads(text)
        self.assertFalse(answer["ok"])
        self.assertTrue(any(line.startswith("FIX") for line in answer["lines"]), answer["lines"])

    # P7
    @unittest.skipUnless(os.name == "nt", "Windows lets a second socket bind a port in use when SO_REUSEADDR is set")
    def test_a_second_page_cannot_share_the_port(self):
        server_class = getattr(page, "Server", ThreadingHTTPServer)   # the fix adds page.Server
        with self.assertRaises(OSError):
            second = server_class(("127.0.0.1", self.port), page.Page)
            second.server_close()

    # P8
    def test_an_impossible_filing_time_is_refused_by_the_form(self):
        for value in ("2026-13-45T99:99:99", "2026-02-30T10:00:00", "0000-00-00T00:00:00", "2026-10-06T24:00:00",
                      "٢٠٢٦-١٠-٠٦T٢١:١٣:١٥"):
            args, problem = page.arguments({"ticker": "EXM", "filed": value})
            self.assertEqual(args, [], value)
            self.assertIn("YYYY-MM-DDTHH:MM:SS", problem)

    # P9
    def test_stop_does_not_claim_to_stop_a_finished_run(self):
        with mock.patch.object(page.subprocess, "Popen", return_value=FakeProcess()):
            page.RUN = page.Run(["EXM"])
        for _ in range(200):
            if page.RUN.done:
                break
            threading.Event().wait(0.01)
        self.addCleanup(setattr, page, "RUN", None)
        status, text = self.ask("POST", "/stop", "{}", {"Content-Type": "application/json"})
        self.assertEqual(json.loads(text), {"stopped": False})

    # P10
    def test_a_get_from_another_website_starts_nothing(self):
        with mock.patch.object(page.subprocess, "run") as run:
            status, _ = self.ask("GET", "/setup", headers={"Origin": "http://example.com", "Sec-Fetch-Site": "cross-site"})
            run.assert_not_called()
        self.assertEqual(status, 403)

    def test_a_link_to_the_page_from_another_website_still_opens_it(self):
        # The README on GitHub shows the page's address as a link. A click on it is a request that names another
        # website, and the first form of the check above answered it with an error instead of the page.
        clicked = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        status, text = self.ask("GET", "/", headers=clicked)
        self.assertEqual(status, 200)
        self.assertIn("<html", text.lower())
        # Typed in the address bar, and asked for by the page's own script.
        for headers in ({"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}, {"Sec-Fetch-Site": "same-origin"}, {}):
            self.assertEqual(self.ask("GET", "/", headers=headers)[0], 200, headers)
            self.assertEqual(self.ask("GET", "/status", headers=headers)[0], 200, headers)
        # Only the page itself, and only as a whole page: not inside another site's frame, and no other address.
        self.assertEqual(self.ask("GET", "/", headers={**clicked, "Sec-Fetch-Dest": "iframe"})[0], 403)
        for path in ("/status", "/runs", "/setup", "/report?path=runs/live/x/verified_report.md"):
            with mock.patch.object(page.subprocess, "run") as run:
                self.assertEqual(self.ask("GET", path, headers=clicked)[0], 403, path)
                run.assert_not_called()

    # P11
    def test_json_null_is_not_a_ticker_or_a_peer(self):
        self.assertEqual(page.arguments({"ticker": None})[0], [])
        self.assertEqual(page.arguments({"ticker": True})[0], [])
        self.assertEqual(page.arguments({"ticker": "EXM", "peers": None})[0], ["EXM"])

    # P12
    def test_deeply_nested_json_gets_an_answer(self):
        with mock.patch.object(page, "Run") as run:
            status, _ = self.ask("POST", "/run", b"[" * 100000 + b"]" * 100000, {"Content-Type": "application/json"})
            run.assert_not_called()
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
