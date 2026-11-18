#!/usr/bin/env python3
"""The hook: code that refuses "done" when a number in a saved output has no support.

It reads every number in the output itself, not in a file written for it. It makes no model call.

In a skill's output (the worksheet, the worksheet under a final report), a line that states a number ends with its
source in square brackets, and the hook checks the number against that source:
  [fact: TAG, START to END]   the run's facts.json holds that amount for that tag and period
  [computed: ARITHMETIC]      the arithmetic gives that number, and each of its inputs is printed above it
  [rate: KEY]                 the worksheet file, as the run saved it, holds that value
  [price: price.json]         the run's saved close is that amount
  [reader: liquidity.json, KEY]  the closes reader's saved output holds that value
  [line: FILE, "TEXT"]        the saved filing holds that text, and the text holds the number
  [worksheet: LABEL]          an earlier line with that label prints the same number
A date, a time, an accession number, a form or an exhibit names something and claims nothing; it is skipped.
In the persona's judgment a number passes only when a checked line above prints it. Any other number fails.

In the agent team's report, the Verifier has marked every number. The hook does not judge those numbers again. It
requires that the Verifier marked none wrong and none unsupported, and that the text is the text the Verifier
marked: a line that differs from the saved verified report is refused.

On a failure it prints "refused: line N, ..." for each line and ends with exit code 2. On a clean output it prints
nothing and ends with exit code 0.

Run it on a saved output:  python hook.py output/TICKER_DATE_TIME/worksheet.md
On a copy kept elsewhere:  python hook.py the_copy.md --run output/TICKER_DATE_TIME
"""

from __future__ import annotations

import argparse
import ast
import json
import operator
import re
import sys
import time
from pathlib import Path
from typing import Any

from worksheet import IDENTIFIERS, NUMBER, bare, numbers_in

VIEW_HEADING = "# The worksheet's view"  # desk.py writes this line above the worksheet in a final report
SOURCE = re.compile(r"\s*\[(fact|computed|rate|price|reader|line|worksheet): ?(.*)\]\s*$")
QUOTING = ("## Why it may be cheap",)  # under these headings a model wrote the text; it may quote and never compute
# The course's three closing lines claim no number. The second names the tools, and a model's name holds digits.
CLOSING = ("This is a learning exercise", "AI assistance:", "Any remaining errors")
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.USub: operator.neg}


def value_of(token: str) -> float:
    """The number a printed token states, without its sign: "$13,267.0M" is 13267.0 and "10.00%" is 10.0."""
    return float(bare(token) or 0)


def places(token: str) -> int:
    digits = bare(token)
    return len(digits.split(".")[1]) if "." in digits else 0


def same(token: str, actual: float) -> bool:
    """True when the printed number is the actual value at the precision it is printed with."""
    return abs(value_of(token) - abs(actual)) <= 0.5 * 10 ** -places(token) + 1e-9


def scaled(token: str, raw: float) -> float:
    """A raw amount in the unit of the printed token: a token that ends in M states millions."""
    return raw / {"M": 1e6, "B": 1e9, "K": 1e3}.get(token.rstrip(")")[-1:], 1)


def compute(expression: str) -> float:
    """The value of printed arithmetic: numbers, + - * / and parentheses, and nothing else."""
    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](walk(node.operand))
        raise ValueError("not plain arithmetic")
    return walk(ast.parse(expression.replace(",", "").replace("$", ""), mode="eval").body)


class Hook:
    """One check of one saved output against the run folder it belongs to."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.problems: list[tuple[int, str]] = []
        self.printed: dict[str, str] = {}  # label -> the number on a checked line
        self.known: set[str] = set()       # every number a checked line prints, and every number inside a quoted line
        self.facts = self.load("facts.json")
        self.method = self.load("worksheet_file.json")
        self.price = self.load("price.json").get("price")
        self.liquidity = self.load("liquidity.json")

    def load(self, name: str) -> dict[str, Any]:
        path = self.run_dir / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def refuse(self, number: int, why: str) -> None:
        self.problems.append((number, why))

    # --- the agent team's report ---

    def check_report(self, lines: list[str], first: int = 1) -> None:
        """The team's part of a report: the text the Verifier marked, with none of its marks wrong or unsupported."""
        saved_path = self.run_dir / "verified_report.md"
        if not saved_path.is_file():
            self.refuse(first, "the run folder holds no verified report, so no number of the report has a mark")
            return
        saved = saved_path.read_text(encoding="utf-8").splitlines()
        counts = self.load("verification.json").get("counts") or {}
        bad = int(counts.get("wrong", 0)) + int(counts.get("unsupported", 0))
        if not counts:
            self.refuse(first, "the run folder holds no marks of the Verifier (verification.json)")
        elif bad:
            self.refuse(first, f"the Verifier marked {bad} number(s) wrong or unsupported; its table under the report's first line names each")
        for offset, line in enumerate(lines):
            number = first + offset
            if offset >= len(saved):
                if line.strip():
                    self.refuse(number, "the verified report has no such line")
                continue
            if offset == 0:
                # The first line of a final report may name more filings than the verified report: what the worksheet read.
                if not line.startswith(saved[0].rstrip()):
                    self.refuse(number, "the first line does not begin with the verified report's list of filings")
                continue
            if line.rstrip() != saved[offset].rstrip():
                changed = [t for t in numbers_in(line) if t not in numbers_in(saved[offset])]
                held = [t for t in numbers_in(saved[offset]) if t not in numbers_in(line)]
                if changed:
                    was = f" (the saved line holds {', '.join(held)})" if held else ""
                    self.refuse(number, f"{', '.join(changed)} is not in the verified report{was}")
                else:
                    self.refuse(number, "the line is not the line of the verified report")
        if len(lines) < len(saved) and any(s.strip() for s in saved[len(lines):]):
            self.refuse(first + len(lines), "the report ends before the verified report does")

    # --- a skill's output ---

    def check_skill(self, lines: list[str], first: int = 1) -> None:
        quoting = False
        for offset, line in enumerate(lines):
            number = first + offset
            if line.startswith("#"):
                quoting = line.startswith(QUOTING)
                continue
            if line.startswith(CLOSING):
                continue
            source = SOURCE.search(line)
            text = line[:source.start()] if source else line
            tokens = numbers_in(text)
            if source and source.group(1) == "line":
                # The numbers inside a quoted filing line are printed inputs for the arithmetic below it.
                self.known.update(bare(t) for t in numbers_in(source.group(2)))
            if not tokens:
                continue
            if not source:
                # A model wrote this line, or code wrote words: a number here must be one that a checked line prints.
                for token in tokens:
                    if bare(token) not in self.known:
                        why = "is not printed on a line of the worksheet that has a source" if quoting or line.startswith("- Conviction") else "has no source"
                        self.refuse(number, f"{token} {why}")
                continue
            if len(tokens) > 1:
                self.refuse(number, f"the line states {len(tokens)} numbers ({', '.join(tokens)}) and gives one source; each number needs its own")
                continue
            token = tokens[0]
            why = self.supported(token, source.group(1), source.group(2).strip())
            if why:
                self.refuse(number, why)
            else:
                label = text.lstrip("- ").split(":", 1)[0].strip()
                self.printed[label] = token
                self.known.add(bare(token))

    def supported(self, token: str, kind: str, args: str) -> str:
        """Empty when the number has the support its source claims; else why not."""
        if kind == "fact":
            return self.fact(token, args)
        if kind == "computed":
            return self.computed(token, args)
        if kind == "rate":
            if args not in self.method:
                return f"{token} claims the value {args} of the worksheet file, and the file the run saved has none"
            actual = float(self.method[args]) * (100 if token.endswith("%") else 1)
            return "" if same(token, actual) else f"{token} is not the value of {args} in the worksheet file ({self.method[args]})"
        if kind == "price":
            if self.price is None:
                return f"{token} claims the run's close, and the run saved none"
            return "" if same(token, float(self.price)) else f"{token} is not the close in price.json ({float(self.price):,.2f})"
        if kind == "reader":
            name, _, key = (part.strip() for part in args.partition(","))
            held = self.liquidity.get(key or "median_dollar_volume_millions")
            if name != "liquidity.json" or held is None:
                return f"{token} claims the closes reader's output, and the run saved no such value"
            return "" if same(token, float(held)) else f"{token} is not in liquidity.json ({held})"
        if kind == "line":
            return self.quoted(token, args)
        label = args
        if label not in self.printed:
            return f"{token} claims the worksheet line \"{label}\", and no checked line above has that label"
        return "" if self.printed[label] == token else f"{token} is not the number on the worksheet line \"{label}\" ({self.printed[label]})"

    def fact(self, token: str, args: str) -> str:
        found = re.match(r"(?:us-gaap:)?(\w+), (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$", args) or re.match(r"(?:us-gaap:)?(\w+), as of ()(\d{4}-\d{2}-\d{2})$", args)
        if not found:
            return f"{token} names a fact the hook cannot read: {args}"
        tag, start, end = found.groups()
        rows = []
        for item in list((self.facts.get("facts") or {}).values()) + list((self.facts.get("worksheet") or {}).values()):
            if item and item.get("tag") == tag:
                rows += [item.get(which) for which in ("current", "prior")] + list(item.get("years") or [])
        values = [row["val"] for row in rows if row and row.get("end") == end and (row.get("start") or "") == start]
        if not values:
            return f"{token} is not in facts.json: no fact {tag} for {start + ' to ' if start else ''}{end}"
        if any(same(token, scaled(token, float(v)) * (100 if token.endswith("%") else 1)) for v in values):
            return ""
        return f"{token} is not in facts.json under {tag}, {start + ' to ' if start else ''}{end} (the facts file holds {scaled(token, float(values[0])):,.{places(token)}f})"

    def computed(self, token: str, expression: str) -> str:
        try:
            result = compute(expression)
        except (ValueError, SyntaxError, ZeroDivisionError):
            return f"{token} gives arithmetic the hook cannot redo: {expression}"
        rates = {bare(f"{float(v):g}") for v in self.method.values() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        for literal in numbers_in(expression):
            # An input is a number printed above, a rate of the worksheet file, or a small whole number of the arithmetic itself.
            if bare(literal) in self.known or bare(literal) in rates or (literal.isdigit() and int(literal) <= 12):
                continue
            return f"{token} is computed from {literal}, which no checked line above prints"
        if same(token, result * (100 if token.endswith("%") else 1)):
            return ""
        shown = result * (100 if token.endswith("%") else 1)
        return f"{token} is not what its arithmetic gives: {expression} = {shown:,.{places(token)}f}"

    def quoted(self, token: str, args: str) -> str:
        found = re.match(r"([^,]+), \"(.*)\"$", args)
        if not found:
            return f"{token} names a line the hook cannot read: {args}"
        name, quote = found.group(1).strip(), found.group(2)
        path = self.run_dir / name
        if not path.is_file():
            return f"{token} claims a line of {name}, and the run folder holds no such file"
        squeeze = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731
        if squeeze(quote) not in squeeze(path.read_text(encoding="utf-8")):
            return f"{token} claims a line that is not in {name}: \"{quote}\""
        if bare(token) not in {bare(t) for t in numbers_in(quote)}:
            return f"{token} is not in the line it quotes from {name}: \"{quote}\""
        return ""


def check(path: Path, run_dir: Path | None = None) -> list[tuple[int, str]]:
    """Every refusal for one saved output: (line number, why). An empty list means the output is clean."""
    run_dir = run_dir or path.parent
    hook = Hook(run_dir)
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].startswith("Filings read:"):
        cut = lines.index(VIEW_HEADING) if VIEW_HEADING in lines else len(lines)
        team = lines[:cut]
        while team and not team[-1].strip():
            team.pop()  # the blank lines desk.py puts between the report and the view
        hook.check_report(team)
        if cut < len(lines):
            hook.check_skill(lines[cut + 1:], first=cut + 2)
    else:
        hook.check_skill(lines)
    return sorted(hook.problems)


def latest(output: Path) -> Path | None:
    """The newest output of the newest run in the output folder: its final report, else its worksheet.
    This is what a coding agent's hook checks when the agent is about to say that it is done."""
    runs = sorted((p for p in output.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime) if output.is_dir() else []
    for run_dir in reversed(runs):
        for name in ("final_report.md", "worksheet.md"):
            if (run_dir / name).is_file():
                return run_dir / name
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="The hook: refuse \"done\" when a number in a saved output has no support")
    parser.add_argument("output", nargs="?", help="A saved output: a worksheet, a verified report or a final report")
    parser.add_argument("--run", metavar="RUN_FOLDER", help="The run folder the output belongs to; by default the output's own folder")
    parser.add_argument("--latest", action="store_true", help="Check the newest output in the output folder; silent when there is none")
    args = parser.parse_args()
    started = time.monotonic()
    if args.latest:
        newest = latest(Path(__file__).resolve().parent / "output")
        if newest is None:
            return 0
        args.output = str(newest)
    if not args.output:
        parser.error("give a saved output, or --latest")
    path = Path(args.output)
    if not path.is_file():
        print(f"refused: {path} does not exist", file=sys.stderr)
        return 2
    problems = check(path, Path(args.run) if args.run else None)
    for number, why in problems:
        print(f"refused: line {number}, {why}", file=sys.stderr)
    if problems:
        print(f"Hook: refused {len(problems)} line(s) of {path.name} in {time.monotonic() - started:.1f} seconds", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
