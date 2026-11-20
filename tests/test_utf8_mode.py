"""The desk's programs run in Python's UTF-8 mode on Windows; see utf8_mode.py."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import utf8_mode

ROOT = Path(__file__).resolve().parents[1]


class Utf8ModeTests(unittest.TestCase):
    def test_already_in_utf8_mode_or_not_windows_runs_on(self):
        with patch.object(utf8_mode.os, "name", "posix"), patch.object(utf8_mode.subprocess, "call") as call:
            utf8_mode.ensure()
        call.assert_not_called()

    def test_on_windows_without_it_the_program_starts_again_with_it(self):
        flags = type("Flags", (), {"utf8_mode": 0})()
        with patch.object(utf8_mode.os, "name", "nt"), patch.object(utf8_mode.sys, "flags", flags), \
                patch.object(utf8_mode.sys, "orig_argv", ["python", "-u", "desk.py", "LOW"]), \
                patch.dict(utf8_mode.os.environ, {}, clear=False), \
                patch.object(utf8_mode.subprocess, "call", return_value=3) as call:
            with self.assertRaises(SystemExit) as stop:
                utf8_mode.ensure()
            self.assertEqual(os.environ["PYTHONUTF8"], "1")
        call.assert_called_once_with([sys.executable, "-u", "desk.py", "LOW"])
        self.assertEqual(stop.exception.code, 3)

    def test_the_programs_of_the_readme_call_it_first(self):
        for name in ("desk.py", "page.py", "hit_rate.py", "live_record.py", "desk_error_review.py"):
            with self.subTest(name=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                main = text[text.rindex("__main__"):]
                self.assertLess(main.index("utf8_mode.ensure()"), main.index("main()"))

    def test_a_rule_with_a_division_sign_reads_the_same_in_any_mode(self):
        rules = (ROOT / "spinoff-rules.md").read_text(encoding="utf-8")
        self.assertIn("owner cash flow ÷", rules)
        script = ("import sys;sys.path.insert(0,r'%s');import worksheet;"
                  "c=worksheet.load_worksheet(r'%s');print(sorted(c)[:1])") % (
            ROOT / "skills/spinoff-worksheet/scripts", ROOT / "spinoff-rules.md")
        with tempfile.TemporaryDirectory() as cwd:
            env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
            done = subprocess.run([sys.executable, "-X", "utf8=0", "-c", script], cwd=cwd, env=env,
                                  capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
