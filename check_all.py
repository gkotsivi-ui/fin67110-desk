#!/usr/bin/env python3
"""Every check of this repository, in one command:   python check_all.py

It runs the four test folders, the two seeded checks that test discovery does not collect, and the offline
live-record check, each in its own process, and prints one line for each. The exit code is 0 only when every
one passed. It needs no network and no key. Run it with the group environment's Python (.venv-desk).

Until 2026-11-22 the required check was `python -m unittest discover -s tests`, which ran 448 of the 663 tests:
it left out hooks/tests, both skills' tests and the two seeded checks.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_FOLDERS = ("tests", "hooks/tests", "skills/spinoff-worksheet/tests", "skills/us-spinoff-seeker/tests")
# Programs in tests/ whose names do not start with "test": discovery skips them, so they are named here.
SEEDED_CHECKS = ("tests/desk_tool_smoke.py", "tests/desk_all_roles_smoke.py")
CHECKS = ([(f"tests in {folder}", ["-m", "unittest", "discover", "-s", folder]) for folder in TEST_FOLDERS]
          + [(f"seeded check {script}", [script]) for script in SEEDED_CHECKS]
          + [("the live record, offline", ["live_record.py", "--offline", "--no-save"]),
             ("nothing private in what git tracks", ["check_public.py"])])


def main() -> int:
    # The children print UTF-8 so this program can read their lines. Their file reads and writes are left as
    # they are: a call that names no encoding must still fail here on Windows, as it would for a new user.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    failed, tests, skipped = [], 0, 0
    for name, arguments in CHECKS:
        began = time.perf_counter()
        done = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        output = done.stdout + done.stderr
        # The last count of the output: a failing test can print the count of a run it started itself.
        ran = (re.findall(r"^Ran (\d+) tests?", output, re.M) or [None])[-1]
        skip = (re.findall(r"skipped=(\d+)", output) or [None])[-1]
        tests += int(ran or 0)
        skipped += int(skip or 0)
        detail = (f"{ran} tests" + (f", {skip} skipped" if skip else "")) if ran else "ran"
        print(f"{'ok  ' if done.returncode == 0 else 'FAIL'}  {name}: {detail}, {time.perf_counter() - began:.0f} s", flush=True)
        if done.returncode:
            failed.append(name)
            print("      " + "\n      ".join(output.strip().splitlines()[-25:]), flush=True)
    print(f"\n{tests} tests in {len(TEST_FOLDERS)} folders, {skipped} skipped. "
          + (f"FAILED: {', '.join(failed)}" if failed else "Every check passed."))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
