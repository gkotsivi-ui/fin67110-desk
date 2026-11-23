"""check_public.py: what git tracks holds no key, no .env value, no data file and no list of closes.

Every key, name, email, path and price here is made up. The keys are built from pieces so that this file itself
holds no string shaped like a key.
"""
import json
from pathlib import Path
import tempfile
import unittest

import check_all
import check_public

ROOT = Path(__file__).resolve().parents[1]
ANTHROPIC = "sk-" + "ant-" + "a1B2" * 8
OPENAI = "sk-" + "proj-" + "c3D4" * 10
GOOGLE = "AI" + "za" + "e5F6" * 9
PRIVATE = "-----BEGIN RSA " + "PRIVATE KEY-----"


class WhatMustNotBePublic(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def found(self, files, env=""):
        for name, text in files.items():
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_text(text, encoding="utf-8")
        if env:
            (self.root / ".env").write_text(env, encoding="utf-8")
        return check_public.problems(self.root, list(files), check_public.env_secrets(self.root / ".env"))

    def test_clean_files_pass(self):
        self.assertEqual(self.found({"README.md": "API_KEY=your model key\nSEC_USER_AGENT=Your Name your.email@university.edu\n",
                                     "desk.py": "key = os.environ['API_KEY']\n"}), [])

    def test_each_kind_of_key_is_found_and_never_printed(self):
        found = self.found({"notes.md": f"one {ANTHROPIC}\ntwo {OPENAI}\nthree {GOOGLE}\n{PRIVATE}\n"})
        self.assertEqual([line.split(": ", 1)[1] for line in found], ["an Anthropic key", "an OpenAI key", "a Google key", "a private key"])
        self.assertEqual([line.split(":")[1] for line in found], ["1", "2", "3", "4"])
        self.assertFalse(any(key in line for line in found for key in (ANTHROPIC, OPENAI, GOOGLE)))

    def test_a_value_of_this_folders_env_is_found_by_its_name(self):
        env = 'SEC_USER_AGENT="Pat Example pat.example@school.example"\nLSEG_APP_KEY=0123456789abcdef0123\nMODEL=anthropic/a-model\n'
        found = self.found({"docs/notes.md": "ask pat.example@school.example\nkey 0123456789abcdef0123\nmodel anthropic/a-model\n"}, env)
        self.assertEqual(found, ["docs/notes.md:1: the email in SEC_USER_AGENT in .env", "docs/notes.md:2: the value of LSEG_APP_KEY in .env"])

    def test_a_tracked_env_file_and_a_data_file_are_found(self):
        found = self.found({".env": "API_KEY=x\n", "config/.env.local": "A=b\n", ".env.example": "API_KEY=\n", "data/closes.csv": "date,close\n"})
        self.assertEqual(found, [".env: a .env file is tracked", "config/.env.local: a .env file is tracked", "data/closes.csv: a data file is tracked"])

    def test_a_list_of_closes_is_found_and_one_close_is_not(self):
        series = {"method": "daily_closes_and_volumes", "output": [{"date": "2026-01-02", "close": 10.0, "volume": 5}, {"date": "2026-01-05", "close": 10.5, "volume": 6}]}
        one = {"method": "last_close_before", "output": {"close": 10.5, "close_time": "2026-01-05T16:00:00-05:00", "source": "a source"}}
        found = self.found({"runs/live/ZZZZ_1/sources/prices/a.json": json.dumps(series), "runs/live/ZZZZ_1/sources/prices/b.json": json.dumps(one),
                            "runs/live/ZZZZ_1/facts.json": json.dumps({"facts": {"revenue": {"value": 1}}})})
        self.assertEqual(found, ["runs/live/ZZZZ_1/sources/prices/a.json: a saved list of closes (more than one row with a close)"])

    def test_the_worksheets_liquidity_rows_are_found_once(self):
        text = "Input | Date | Close\n---|---|---\nLiquidity day | 2026-01-02 | 10.0 | 5\nLiquidity day | 2026-01-05 | 10.5 | 6\nLiquidity: historical\n"
        self.assertEqual(self.found({"runs/live/ZZZZ_1/final_report.md": text}),
                         ["runs/live/ZZZZ_1/final_report.md:3: a list of daily closes and volumes in a worksheet (its first row)"])

    def test_a_home_folder_path_and_the_readers_log_are_found(self):
        windows, mac = "C:" + "\\Users" + "\\someone\\desk\\runs", "/Users" + "/someone/desk"  # in pieces: this file holds no such path
        found = self.found({"docs/findings.json": json.dumps({"history_folder": windows}),
                            "docs/mac.md": f"saved in {mac}\n", "closes_diagnostics.jsonl": "{}\n"})
        self.assertEqual([line.split(": ", 1)[1] for line in found],
                         ["a path that names a user's home folder", "a path that names a user's home folder", "the closes reader's own log is tracked"])


    # The next four were found by an independent review, 2026-11-22.
    ROWS = [{"date": f"2026-01-{day:02d}", "close": 10 + day / 10} for day in (2, 5, 6, 7)]

    def test_a_list_of_closes_in_the_other_shapes_a_script_writes(self):
        rows = self.ROWS
        shapes = {
            "by_date.json": json.dumps({"output": {r["date"]: {"close": r["close"]} for r in rows}}),
            "dates_to_prices.json": json.dumps({r["date"]: r["close"] for r in rows}),
            "pandas_default.json": json.dumps({"date": {str(i): r["date"] for i, r in enumerate(rows)}, "close": {str(i): r["close"] for i, r in enumerate(rows)}}),
            "pandas_split.json": json.dumps({"columns": ["date", "close"], "data": [[r["date"], r["close"]] for r in rows]}),
            "another_column_name.json": json.dumps([{"Date": r["date"], "Close Price": r["close"]} for r in rows]),
            "five_deep.json": json.dumps({"a": {"b": {"c": {"d": {"e": {"rows": rows}}}}}}),
            "rows.jsonl": "\n".join(json.dumps(r) for r in rows) + "\n",
            "table.tsv": "date\tclose\n" + "\n".join(f"{r['date']}\t{r['close']}" for r in rows) + "\n",
            "in_a_report.md": "| Date | Close |\n|---|---|\n" + "\n".join(f"| {r['date']} | {r['close']} |" for r in rows) + "\n",
        }
        for name, text in shapes.items():
            with self.subTest(shape=name):
                self.assertEqual(len(self.found({"runs/live/ZZZZ_1/" + name: text})), 1)

    def test_one_close_and_the_two_closes_of_a_reaction_are_not_a_list(self):
        reaction = {"before_close": 10.5, "after_close": 11.0, "before_close_time": "2026-01-05T16:00:00-05:00", "after_close_time": "2026-01-06T16:00:00-05:00"}
        view = {"direction": "up", "view_time": "2026-01-05T17:00:00-05:00", "filing_time": "2026-01-05T16:05:00-05:00"}
        report = "| Claim | Value |\n|---|---|\n| Close before the release | $10.50 |\n| Date of the 10-K | 2026-01-02 |\n"
        # The one price a run saves, as the desk writes it: one row under a name that holds the word "close". The
        # first widened form of the scan called it a list, and would have failed the first live run with a price;
        # the test of a whole run caught it.
        price = {"selected_close": {"date": "2026-01-05", "close": 10.5, "volume": 100000.0, "close_time": "2026-01-05T16:00:00-05:00"},
                 "filing_cutoff": "2026-01-06T08:00:00-05:00"}
        self.assertEqual(self.found({"runs/live/ZZZZ_1/reaction.json": json.dumps(reaction), "runs/live/ZZZZ_1/view.json": json.dumps(view),
                                     "runs/live/ZZZZ_1/market_price.json": json.dumps(price), "runs/live/ZZZZ_1/facts.json": json.dumps({"market": price}),
                                     "runs/live/ZZZZ_1/final_report.md": report}), [])

    def test_a_file_that_is_not_utf8_is_read_too(self):
        # A file made with ">" in Windows PowerShell is UTF-16. The scan skipped every file it could not read as UTF-8.
        path = self.root / "setup_log.txt"
        path.write_text(f"API_KEY={ANTHROPIC}\n", encoding="utf-16")
        self.assertEqual(check_public.problems(self.root, ["setup_log.txt"], {}), ["setup_log.txt:1: an Anthropic key"])
        (self.root / "page.bin").write_bytes(b"\x93a saved page\x94 " + OPENAI.encode() + b"\n")
        self.assertEqual(check_public.problems(self.root, ["page.bin"], {}), ["page.bin:1: an OpenAI key"])

    def test_a_web_address_and_a_long_dashed_name_are_not_a_path_or_a_key(self):
        self.assertEqual(self.found({"runs/live/ZZZZ_1/report.md": "See https://investor.made-up.example/home/default.aspx and https://made-up.example/Users/guide.\n",
                                     "docs/a_note.md": "See docs/risk-factors-and-forward-looking-statements-of-2026.md for the list.\n"}), [])


    def test_a_linux_home_folder_is_found(self):
        linux = "/home" + "/someone/desk/runs"   # in pieces: this file holds no such path
        self.assertEqual(self.found({"docs/server.md": f"the run is in {linux}\n"}), ["docs/server.md:1: a path that names a user's home folder"])

    def test_what_git_would_add_is_scanned_and_what_it_ignores_is_not(self):
        import subprocess
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True, capture_output=True)
        for name, text in ((".gitignore", "ignored.txt\n"), ("tracked.txt", "a\n"), ("new.txt", "b\n"), ("ignored.txt", "c\n")):
            (self.root / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True, capture_output=True)
        self.assertEqual(sorted(check_public.tracked(self.root)), [".gitignore", "new.txt", "tracked.txt"])


class ThisRepository(unittest.TestCase):
    def test_what_git_tracks_here_is_clean(self):
        names = check_public.tracked(ROOT)
        if names is None:
            self.skipTest("not a git checkout")
        self.assertEqual(check_public.problems(ROOT, names, check_public.env_secrets(ROOT / ".env")), [])

    def test_the_one_command_runs_every_test_folder_and_every_seeded_check(self):
        folders = {path.parent.relative_to(ROOT).as_posix() for path in ROOT.rglob("test_*.py")
                   if not path.relative_to(ROOT).as_posix().startswith((".venv", "venv/", "runs/", "output/", "_"))}
        self.assertEqual(folders, set(check_all.TEST_FOLDERS))
        helpers = {"tests/portable.py", "tests/desk_stub_llm.py"}
        others = {path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").glob("*.py") if not path.name.startswith("test_")}
        self.assertEqual(others - helpers, set(check_all.SEEDED_CHECKS))


if __name__ == "__main__":
    unittest.main()
