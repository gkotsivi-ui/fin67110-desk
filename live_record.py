#!/usr/bin/env python3
"""The live record: one row for each report in runs/live, from SEC EDGAR and git.

Each folder in runs/live holds one run. The first line of its report names the earnings 8-K the desk read.
For each report this program reads that line, asks SEC EDGAR for the 8-K's "Accepted" time, and asks git
for the time of the commit that first added the report. A report is inside its window when that commit is
at or after the Accepted time and no more than 24 hours after it. The commit's time is the record.

Print the table and save it in docs/live-record.md:   python live_record.py
Without the network:                                  python live_record.py --offline
Before a push (exit code 1 when a report is late):    python live_record.py --check
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lab02_desk import Desk, env_path, load_dotenv, user_agent_problem

ROOT = Path(__file__).resolve().parent
LIVE = ROOT / "runs" / "live"
SAVED = ROOT / "docs" / "live-record.md"
WINDOW = timedelta(hours=24)
# The live-record weeks, Monday to Sunday, as the course schedule gives them.
WEEKS = {
    4: (date(2026, 11, 9), date(2026, 11, 15)),
    5: (date(2026, 11, 16), date(2026, 11, 22)),
    6: (date(2026, 11, 23), date(2026, 11, 29)),
    7: (date(2026, 11, 30), date(2026, 12, 6)),
}
NEEDED = 3  # The top tier needs a report inside its window in three of the four weeks.
REPORTS = ("verified_report.md", "report.md")  # the verified report, when the run has one
ACCESSION = r"\d{10}-\d{2}-\d{6}"
PAUSE = 0.3  # seconds between requests to SEC EDGAR, well under its limit of 10 a second
STAMP = "%Y-%m-%d %H:%M:%S"


def eastern() -> ZoneInfo:
    """U.S. Eastern time. On Windows the zone data comes from the tzdata package in requirements.txt."""
    try:
        return ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        raise SystemExit("No time-zone data. Install the packages: python -m pip install -r requirements.txt") from None


def release_named(first_line: str) -> dict[str, str] | None:
    """What a report's first line says about the earnings 8-K it read. None when the line names no 8-K."""
    filing = re.search(rf"8-K ({ACCESSION})([^;]*)", first_line)
    cik = re.search(r"CIK (\d{1,10})\b", first_line)
    if not filing or not cik:
        return None
    exhibit = re.search(r"Exhibit (99(?:\.\d+)?) ([^,)\s]+)", filing.group(2))
    accepted = re.search(r"accepted (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ET", filing.group(2))
    return {
        "accession": filing.group(1),
        "cik": cik.group(1).zfill(10),
        "exhibit_label": exhibit.group(1) if exhibit else "",
        "exhibit": exhibit.group(2) if exhibit else "",
        "accepted": accepted.group(1) if accepted else "",
    }


def week_of(day: date) -> str:
    """The live-record week a filing date falls in."""
    for number, (first, last) in WEEKS.items():
        if first <= day <= last:
            return f"Week {number}"
    return "outside Weeks 4 to 7"


def hours(span: timedelta) -> str:
    return f"{span.total_seconds() / 3600:.1f} hours"


def judge(accepted: datetime, committed: datetime | None, now: datetime) -> str:
    """Whether the report is inside its window; for a report not committed yet, the time that is left."""
    deadline = accepted + WINDOW
    if committed is None:
        if now > deadline:
            return "NO: not committed, and the window has closed"
        return f"not committed yet; {hours(deadline - now)} left"
    if committed < accepted:
        return "NO: the commit is before the Accepted time"
    return "yes" if committed <= deadline else "NO: late"


def git(root: Path, *args: str) -> str:
    """What a git command prints; "" when git fails or is not installed."""
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def first_commit(path: Path, root: Path = ROOT) -> tuple[str, datetime] | None:
    """The commit that first added the file, and that commit's time. None when the file is not committed."""
    lines = git(root, "log", "--diff-filter=A", "--format=%H %cI", "--", path.relative_to(root).as_posix()).splitlines()
    if not lines:
        return None
    commit, stamp = lines[-1].split(" ", 1)  # git lists the newest commit first
    return commit, datetime.fromisoformat(stamp)


def accepted_on_edgar(desk: Desk, cik: str, accession: str) -> str:
    """The "Accepted" time on the filing's EDGAR index page, in Eastern time. "" when EDGAR does not give it."""
    desk.cik = cik
    row = {"accessionNumber": accession}
    desk.fetch_index_acceptance(row)
    return row.get("accepted_index", "")


def read_run(folder: Path, desk: Desk | None, now: datetime, root: Path = ROOT) -> dict[str, Any]:
    """One row of the live record. desk is None when the program must not ask SEC EDGAR."""
    row: dict[str, Any] = {"ticker": folder.name.split("_")[0], "folder": folder.name, "problem": "", "inside": ""}
    report = next((folder / name for name in REPORTS if (folder / name).is_file()), None)
    if report is None:
        return {**row, "problem": "the folder holds no report"}
    with report.open(encoding="utf-8", errors="replace") as handle:
        named = release_named(handle.readline())
    if named is None:
        return {**row, "problem": f"the first line of {report.name} names no 8-K"}
    row.update(named, report=report.relative_to(root).as_posix())
    printed = named["accepted"]
    checked = accepted_on_edgar(desk, named["cik"], named["accession"]) if desk else ""
    if checked and printed and checked != printed:
        row["problem"] = f"the report prints Accepted {printed}, and EDGAR says {checked}"
    stamp = checked or printed
    if not stamp:
        return {**row, "problem": "no Accepted time: EDGAR gave none and the report's first line prints none in Eastern time"}
    row["accepted_from"] = "EDGAR index page" if checked else "the report's first line, not checked on EDGAR"
    accepted = datetime.strptime(stamp, STAMP).replace(tzinfo=eastern())
    found = first_commit(report, root)
    committed = found[1].astimezone(eastern()) if found else None
    row.update(week=week_of(accepted.date()), accepted_at=accepted, deadline=accepted + WINDOW,
               commit=found[0] if found else "", committed_at=committed, inside=judge(accepted, committed, now))
    return row


def late(row: dict[str, Any]) -> bool:
    """True for a report that is outside its window or that the program could not read."""
    return bool(row["problem"]) or row["inside"].startswith("NO")


def release_link(row: dict[str, Any]) -> str:
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(row['cik'])}/{row['accession'].replace('-', '')}"
    if row["exhibit"]:
        return f"8-K {row['accession']}, Exhibit {row['exhibit_label']} [{row['exhibit']}]({folder}/{row['exhibit']})"
    return f"8-K [{row['accession']}]({folder}/{row['accession']}-index.html)"


def render(rows: list[dict[str, Any]], now: datetime, offline: bool, tools: str) -> str:
    """The live record as Markdown: the table, the count of weeks, and what the program could not read."""
    lines = [
        "# The live record",
        "",
        f"Made by `python live_record.py{' --offline' if offline else ''}` on {now:%Y-%m-%d %H:%M} Eastern. "
        "One row for each report in `runs/live`. The release and its Accepted time are the 8-K that the report's first line names"
        + (", as that line prints them." if offline else ", checked on its SEC EDGAR index page.")
        + " The commit is the one that first added the report, and its time is the record. "
        "A report is inside its window when the commit is no more than 24 hours after the Accepted time.",
        "",
    ]
    good = [r for r in rows if r.get("accepted_at")]
    if not rows:
        lines += ["No live report yet.", ""]
    if good:
        lines += [
            "| Week | Ticker | Release the report read | Accepted (ET) | Window closes (ET) | Commit | Commit time (ET) | After the release | Inside the window |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in sorted(good, key=lambda r: r["accepted_at"]):
            committed = r["committed_at"]
            lines.append("| " + " | ".join([
                r["week"], r["ticker"], release_link(r), f"{r['accepted_at']:{STAMP}}", f"{r['deadline']:{STAMP}}",
                f"`{r['commit'][:7]}`" if r["commit"] else "-", f"{committed:{STAMP}}" if committed else "-",
                hours(committed - r["accepted_at"]) if committed else "-", r["inside"],
            ]) + " |")
        weeks = sorted({r["week"] for r in good if r["inside"] == "yes" and r["week"].startswith("Week")})
        lines += ["", f"Weeks with a report inside its window: {len(weeks)} of {len(WEEKS)}"
                  + (f" ({', '.join(weeks)})" if weeks else "") + f". The top tier needs {NEEDED}.", ""]
    problems = [f"- `{r['folder']}`: {r['problem']}" for r in rows if r["problem"]]
    if problems:
        lines += ["Could not read, or does not agree:", "", *problems, ""]
    unchecked = sorted({r["accepted_from"] for r in good if "not checked" in r["accepted_from"]})
    if unchecked:
        lines += ["The Accepted times above come from the reports' first lines and were not checked on EDGAR in this run.", ""]
    lines += [
        "This is a learning exercise, not financial advice.",
        "",
        f"AI assistance: {tools}. I verified the sources myself; the judgments are mine.",
        "",
        "Any remaining errors are my own.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="The live record: each report in runs/live, the release it read, the Accepted time, the commit time, and whether it is inside the 24-hour window")
    parser.add_argument("--offline", action="store_true", help="Do not ask SEC EDGAR; use the Accepted time printed on each report's first line")
    parser.add_argument("--check", action="store_true", help="Exit with code 1 when a report is late or cannot be read")
    parser.add_argument("--no-save", action="store_true", help="Print the table only; do not write docs/live-record.md")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    env = load_dotenv()
    desk = None
    if not args.offline:
        agent = os.environ.get("SEC_USER_AGENT") or env.get("SEC_USER_AGENT", "")
        problem = user_agent_problem(agent, env_path())
        if problem:
            print(f"{problem}\nOr run it without SEC EDGAR: python live_record.py --offline", file=sys.stderr)
            return 2
        desk = Desk(agent, ROOT)
    now = datetime.now(eastern())
    folders = sorted(p for p in LIVE.iterdir() if p.is_dir()) if LIVE.is_dir() else []
    rows = []
    for number, folder in enumerate(folders):
        if desk and number:
            time.sleep(PAUSE)
        rows.append(read_run(folder, desk, now))
    text = render(rows, now, args.offline, os.environ.get("AI_TOOLS") or env.get("AI_TOOLS") or "Claude Code")
    print(text)
    if not args.no_save:
        SAVED.parent.mkdir(parents=True, exist_ok=True)
        SAVED.write_text(text, encoding="utf-8")
        print(f"Saved: {SAVED.relative_to(ROOT).as_posix()}")
    # A commit that no remote branch holds is not on GitHub yet, and the window runs to the push.
    for r in rows:
        if r.get("commit") and not git(ROOT, "branch", "-r", "--contains", r["commit"]):
            print(f"Not pushed yet: {r['folder']} (commit {r['commit'][:7]})")
    return 1 if args.check and any(late(r) for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
