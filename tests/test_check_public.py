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
