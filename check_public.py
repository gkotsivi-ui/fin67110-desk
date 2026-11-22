#!/usr/bin/env python3
"""Before a push: nothing private and nothing licensed is in what git tracks.   python check_public.py

It reads every file that git tracks in this folder and every new file that git does not ignore, and fails on:
- a model key, a private key, or a value of this folder's .env (a key, or the name and email sent to SEC EDGAR);
- a file named .env;
- a data file (csv, xlsx, parquet and the like), which .gitignore refuses unless a file is forced in;
- a saved list of closes: a closes-reader answer with more than one row, the worksheet's "Liquidity day" rows,
  or the closes reader's diagnostics. One close, printed in a report with its source, is not a list;
- a path that names a user's home folder.
It prints the file, the line and the kind of thing, never the value. The exit code is 1 when it finds something.

This is a second guard. The rule is in AGENTS.md: keys, names and emails live only in .env, and raw pulls and
exports of every price source stay out of the repository.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEYS = {
    "an Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "an OpenAI key": re.compile(r"sk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "a Google key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "a private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# A home folder on Windows, macOS or Linux. The pattern is written in pieces so that this file does not hold one.
HOME = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+\w|/" + r"Users/\w|/" + r"home/\w")
DATA_FILE = re.compile(r"\.(csv|xlsx?|parquet|feather|sas7bdat|dta|pkl|pickle)$", re.I)
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|SEC_USER_AGENT", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LIQUIDITY_ROW = re.compile(r"^Liquidity day\s*\|")


def tracked(root: Path) -> list[str] | None:
    """The files git tracks under root and the new files it does not ignore (the next `git add` takes them);
    None when root is not a git checkout."""
    try:
        done = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root, capture_output=True)
    except OSError:
        return None
    return [name for name in done.stdout.decode("utf-8", "replace").split("\0") if name] if done.returncode == 0 else None


def env_secrets(env_file: Path) -> dict[str, str]:
    """The values in .env that must never be public, each with the name to print for it."""
    secrets: dict[str, str] = {}
    if not env_file.is_file():
        return secrets
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        name, mark, value = line.strip().removeprefix("export ").partition("=")
        value = value.strip().strip("\"'")
        if not mark or line.lstrip().startswith("#") or not SECRET_NAME.search(name) or len(value) < 8:
            continue
        secrets[value] = f"the value of {name.strip()} in .env"
        for email in EMAIL.findall(value):
            secrets[email] = f"the email in {name.strip()} in .env"
    return secrets


def closes_list(data: object, depth: int = 0) -> bool:
    """True for a list of two or more rows that each hold a close: a series, not one price."""
    if isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict) and any(key.lower() == "close" for key in row)]
        return len(rows) >= 2 or (depth < 4 and any(closes_list(item, depth + 1) for item in data))
    if isinstance(data, dict) and depth < 4:
        return any(closes_list(item, depth + 1) for item in data.values())
    return False


def problems(root: Path, names: list[str], secrets: dict[str, str]) -> list[str]:
    found: list[str] = []
    for name in names:
        path = root / name
        base = Path(name).name
        if base == ".env" or (base.startswith(".env.") and base != ".env.example"):
            found.append(f"{name}: a .env file is tracked")
        if DATA_FILE.search(name):
            found.append(f"{name}: a data file is tracked")
        if base.startswith("closes_diagnostics") or base.startswith("closes_errors_"):
            found.append(f"{name}: the closes reader's own log is tracked")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # a missing or binary file holds no text to read
        if name.endswith(".json"):
            try:
                if closes_list(json.loads(text)):
                    found.append(f"{name}: a saved list of closes (more than one row with a close)")
            except ValueError:
                pass
        for number, line in enumerate(text.splitlines(), 1):
            for kind, pattern in KEYS.items():
                if pattern.search(line):
                    found.append(f"{name}:{number}: {kind}")
            for value, kind in secrets.items():
                if value in line:
                    found.append(f"{name}:{number}: {kind}")
            if HOME.search(line):
                found.append(f"{name}:{number}: a path that names a user's home folder")
            if LIQUIDITY_ROW.match(line):
                found.append(f"{name}:{number}: a list of daily closes and volumes in a worksheet (its first row)")
                break  # one line for the list, not one for each day
    return found


def main() -> int:
    names = tracked(ROOT)
    if names is None:
        print("This folder is not a git checkout, so nothing here is tracked. Nothing was checked.")
        return 0
    secrets = env_secrets(ROOT / ".env")
    found = problems(ROOT, names, secrets)
    for line in found:
        print(line)
    note = "" if secrets else " There is no .env here with values to look for, so only key patterns were checked."
    if found:
        print(f"\n{len(found)} thing(s) that must not be public, in {len(names)} files that git tracks or would add. Take each out before any push.{note}")
        return 1
    print(f"ok: {len(names)} files that git tracks or would add hold no key, no .env value, no data file, no list of closes and no home path.{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
