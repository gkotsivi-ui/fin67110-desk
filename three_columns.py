#!/usr/bin/env python3
"""The three-column table of Lab 09: what did joining the parts change?

Column one is the parts alone: a run where the agent team ran by itself and the worksheet ran after it.
Column two is the joined desk: a run of the one command. Column three is where the filing holds the number.
The rows are the eleven core claims, the view, and the one number that decides the view. A row where the
first two columns differ is marked, for a person to check against the filing. Code compares what the two runs
saved; it judges nothing and calls no model.

Make the two runs on the same ticker, then print the table:
  python team.py TICKER                        (the agent team alone)
  python worksheet.py output/TICKER_DATE_TIME  (the worksheet alone, on that run)
  python desk.py TICKER                        (the joined desk)
  python three_columns.py output/<the run of the parts alone> output/<the run of the joined desk>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CORE_HEADING = "### Core figures from the desk's steps"


def core_rows(report: Path) -> list[tuple[str, str, str, str]]:
    """The rows of a report's core table: the claim's number, the claim, its value and its source."""
    rows = []
    inside = False
    for line in report.read_text(encoding="utf-8").splitlines():
        if line.startswith(CORE_HEADING):
            inside = True
            continue
        if inside and line.startswith("#"):
            break
        cells = [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)[1:-1]] if inside and line.startswith("|") else []
        if len(cells) == 4 and re.fullmatch(r"\d+|-", cells[0]):
            rows.append((cells[0], cells[1], cells[2], cells[3]))
    return rows


def view_rows(run_dir: Path) -> list[tuple[str, str, str]]:
    """The view and the one number that decides it, from the view the worksheet saved: the row's name, its
    value, and where the worksheet took it from."""
    path = run_dir / "view.json"
    if not path.is_file():
        return [("The view", "no worksheet ran", ""), ("The one number", "no worksheet ran", "")]
    view = json.loads(path.read_text(encoding="utf-8"))
    words = {"more": "worth more than the price", "less": "worth less than the price"}.get(view.get("view"), "not computed")
    why = f" ({view['why_not']})" if view.get("why_not") else ""
    number = str(view.get("number") or "not computed")
    return [("The view", words + why, "the worksheet's view, by its persona"), ("The one number", number, f"worksheet line: {view.get('number_label') or 'none'}")]


def table(alone: Path, joined: Path) -> list[str]:
    report = joined / "final_report.md" if (joined / "final_report.md").is_file() else joined / "verified_report.md"
    first = {(n, claim): value for n, claim, value, _ in core_rows(alone / "verified_report.md")}
    lines = ["| # | Row | The parts alone | The joined desk | Where the filing holds it | Same? |", "|---|---|---|---|---|---|"]
    differ = 0

    def add(number: str, name: str, left: str, right: str, source: str) -> None:
        nonlocal differ
        same = left == right
        differ += not same
        cell = lambda text: text.replace("|", "\\|")  # noqa: E731
        lines.append(f"| {number} | {cell(name)} | {cell(left)} | {cell(right)} | {cell(source)} | {'same' if same else 'DIFFERS: check it against the filing'} |")

    for number, claim, value, source in core_rows(report):
        add(number, claim, first.get((number, claim), "not in that run"), value, source)
    for (name, left, _), (_, right, source) in zip(view_rows(alone), view_rows(joined)):
        add("-", name, left, right, source)
    lines += ["", f"Rows that differ: {differ}." + (" The join changed nothing in these rows: it is a pipeline." if not differ else
                                                " Check each marked row against the filing.")]
    lines += ["", f"The parts alone: {alone.name}. The joined desk: {joined.name}. The view and its number are a model's choice in each run, "
                  "so they can differ between two runs that read the same files."]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="The three-column table: the parts alone, the joined desk, and where the filing holds each number")
    parser.add_argument("alone", help="A run folder where the agent team ran alone and the worksheet ran after it")
    parser.add_argument("joined", help="A run folder of the one command, desk.py, on the same ticker")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    alone, joined = Path(args.alone), Path(args.joined)
    for folder in (alone, joined):
        if not (folder / "verified_report.md").is_file():
            print(f"{folder} holds no verified report.", file=sys.stderr)
            return 1
    print("\n".join(table(alone, joined)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
