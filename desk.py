#!/usr/bin/env python3
"""The one command: the agent team and the skills as one desk.

The parts run in an order that this file fixes. No model chooses it:

  the seeker (only when asked) -> the pick -> the agent team -> the hook on the team's report
  -> the worksheet -> the hook on the worksheet -> the final report -> the hook on the final report

The join is the pipeline. Each part reads the files that the part before it saved in one run folder, named by the
ticker and the date and time the command started. No part fetches a filing that another part saved. The final
report is the team's verified report with the worksheet's view under it. Each part prints the seconds it took on
its last line. A part that fails stops the command: it prints which part failed and the error, and keeps the run
folder. A refusal of the hook does not stop the parts after it; the command then ends "not done".

  python desk.py TICKER                     run the desk on a ticker
  python desk.py screen                     run it on the top name of the seeker's latest report
  python desk.py screen --from YYYY-MM-DD   run the seeker first, from that start date
  python desk.py --replay RUN_FOLDER        rebuild a saved run's final report from its saved outputs:
                                            no fetch, no model
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import hook
import worksheet

HERE = Path(__file__).resolve().parent
OUTPUT = Path("output")
SEEKER_REPORTS = HERE / "seeker" / "reports"
SEEKER, PICK, TEAM, SHEET, FINAL = "Seeker", "Pick", "Agent team", "Worksheet", "Final report"
HOOKS = {"verified_report.md": "Hook on the team's report", "worksheet.md": "Hook on the worksheet", "final_report.md": "Hook on the final report"}
# The order of the parts. It is the same on every run. The seeker runs only when the command asks for it.
ORDER = [SEEKER, PICK, TEAM, HOOKS["verified_report.md"], SHEET, HOOKS["worksheet.md"], FINAL, HOOKS["final_report.md"]]


class PartFailed(RuntimeError):
    """A part of the desk could not finish. The command stops at that part."""


def final_report(run_dir: Path) -> str:
    """The team's verified report with the worksheet's view under it. Its first line names every filing any part
    read: the verified report's own list, then the filings the worksheet fetched for a spinoff, when it fetched any."""
    report = (run_dir / "verified_report.md").read_text(encoding="utf-8").splitlines()
    sheet = (run_dir / "worksheet.md").read_text(encoding="utf-8").splitlines()
    more_file = run_dir / "worksheet_filings.json"
    more = json.loads(more_file.read_text(encoding="utf-8")) if more_file.is_file() else []
    first = report[0] + "".join(f"; {item}" for item in more)
    while report and not report[-1].strip():
        report.pop()
    return "\n".join([first, *report[1:], "", hook.VIEW_HEADING, "", *sheet]) + "\n"


class DeskRun:
    """One run of the command. It keeps what each part did, for the last lines and for desk.json."""

    def __init__(self, started: datetime) -> None:
        self.started = started
        self.run_dir: Path | None = None
        self.parts: list[dict[str, Any]] = []
        self.refused: dict[str, list[tuple[int, str]]] = {}

    def part(self, name: str, work: Callable[[], str | None]) -> None:
        """Run one part: its name, its work, and the seconds it took on its last line."""
        print(f"\n=== {name} ===", flush=True)
        begun = time.monotonic()
        record: dict[str, Any] = {"part": name}
        self.parts.append(record)
        try:
            record["outcome"] = work() or "ran"
        except Exception as exc:  # noqa: BLE001 - whatever the error, the command says which part failed
            record.update(outcome="failed", error=f"{type(exc).__name__}: {exc}")
            raise PartFailed(f"{name}: {exc}") from exc
        finally:
            record["seconds"] = round(time.monotonic() - begun, 1)
            print(f"{name}: {record['seconds']:.1f} seconds", flush=True)

    def check(self, output: str) -> None:
        """The hook on one saved output. A refusal is printed and kept; the parts after it still run."""
        def work() -> str:
            assert self.run_dir is not None
            problems = hook.check(self.run_dir / output, self.run_dir)
            for number, why in problems:
                print(f"refused: line {number}, {why}")
            if problems:
                self.refused[output] = problems
            return f"refused {len(problems)} line(s)" if problems else "clean"
        self.part(HOOKS[output], work)

    def save(self, command: list[str]) -> None:
        if self.run_dir and self.run_dir.is_dir():
            record = {"command": command, "started": f"{self.started:%Y-%m-%d %H:%M:%S} {self.started.tzname()}", "order": ORDER, "parts": self.parts,
                      "refused": {name: [f"line {n}, {why}" for n, why in problems] for name, problems in self.refused.items()}}
            (self.run_dir / "desk.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")


def top_of_the_screen(reports: Path | None = None) -> dict[str, Any]:
    """The top name of the seeker's latest report, with the report it came from."""
    reports = reports or SEEKER_REPORTS
    saved = sorted(reports.glob("screen_*.json")) if reports.is_dir() else []
    if not saved:
        raise PartFailed("the seeker has written no report. Run the seeker first: python desk.py screen --from YYYY-MM-DD")
    latest = saved[-1]
    names = [row for row in json.loads(latest.read_text(encoding="utf-8")).get("in_window") or [] if row.get("ticker")]
    if not names:
        raise PartFailed(f"the seeker's latest report, {latest.name}, has no name in its window with a ticker. Give the command a ticker.")
    return {"ticker": str(names[0]["ticker"]).upper(), "from": f"the top of the seeker's report {latest.name}", "report": latest.name}


def run(target: str, make_team: Callable[[], Any], model: Any, state: dict[str, Any], started: datetime, command: list[str],
        seek: Callable[[], str | None] | None = None, bars: Any = worksheet.reader_bars, output: Path = OUTPUT) -> int:
    """Run the desk once. Returns the exit code: 0 done, 1 a part failed, 2 the hook refused."""
    import team

    desk = DeskRun(started)
    print("Order: " + " -> ".join(part for part in ORDER if part != SEEKER or seek))
    try:
        if seek:
            desk.part(SEEKER, seek)

        def pick() -> str:
            chosen = top_of_the_screen() if target.lower() == "screen" else {"ticker": target.upper(), "from": "the command"}
            folder = output / f"{chosen['ticker']}_{started:%Y%m%d_%H%M%S}"
            count = 1
            while folder.exists():  # never a folder that holds an earlier run
                count += 1
                folder = output / f"{chosen['ticker']}_{started:%Y%m%d_%H%M%S}_{count}"
            folder.mkdir(parents=True)
            desk.run_dir = folder
            (folder / "pick.json").write_text(json.dumps(chosen, indent=1), encoding="utf-8")
            print(f"{chosen['ticker']}, from {chosen['from']}. Run folder: {folder}")
            return chosen["ticker"]
        desk.part(PICK, pick)
        assert desk.run_dir is not None
        run_dir = desk.run_dir
        ticker = desk.parts[-1]["outcome"]

        def the_team() -> str:
            final = team.run_graph(make_team(), dict(state, ticker=ticker, run_dir=str(run_dir)), run_dir)
            if final is None:
                raise PartFailed("a part of the agent team stopped; the lines above name it, and its record is in the run folder's nodes/")
            print(f"Verified report: {final['verified_path']}")
            return "ran"
        desk.part(TEAM, the_team)
        desk.check("verified_report.md")

        def the_sheet() -> str:
            print(f"Worksheet: {worksheet.run(run_dir, model, bars)}")
            return "ran"
        desk.part(SHEET, the_sheet)
        desk.check("worksheet.md")

        def the_final() -> str:
            (run_dir / "final_report.md").write_text(final_report(run_dir), encoding="utf-8")
            return "ran"
        desk.part(FINAL, the_final)
        desk.check("final_report.md")
    except PartFailed as exc:
        desk.save(command)
        print(f"\nThe desk stopped at this part: {exc}", file=sys.stderr)
        if desk.run_dir:
            print(f"The run folder is kept: {desk.run_dir}", file=sys.stderr)
        return 1
    desk.save(command)
    print(f"\nRun folder: {run_dir}")
    print(f"Final report: {run_dir / 'final_report.md'}")
    if desk.refused:
        lines = sum(len(problems) for problems in desk.refused.values())
        print(f"Not done: the hook refused {lines} line(s) in {', '.join(desk.refused)}. Each refusal is printed above and saved in desk.json.", file=sys.stderr)
        return 2
    print("Done: the hook refused nothing.")
    return 0


@contextlib.contextmanager
def no_network() -> Iterator[None]:
    """Inside this block any attempt to open a connection is an error. The replay runs inside it."""
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the replay fetches nothing, and something tried to open a connection")
    kept = socket.socket.connect, socket.create_connection
    socket.socket.connect, socket.create_connection = refuse, refuse  # type: ignore[method-assign, assignment]
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection = kept  # type: ignore[method-assign, assignment]


def replay(run_dir: Path) -> int:
    """Rebuild a saved run's final report from its saved outputs, and run the hook on each output again.
    It fetches nothing and calls no model. It writes nothing: the saved run stays as it is.
    Returns 0 when the rebuilt report is the saved one and the hook refuses nothing; else 2."""
    needed = ["verified_report.md", "worksheet.md", "final_report.md"]
    missing = [name for name in needed if not (run_dir / name).is_file()]
    if missing:
        print(f"{run_dir} is not a finished run of the desk: it has no {', '.join(missing)}.", file=sys.stderr)
        return 1
    saved = json.loads((run_dir / "desk.json").read_text(encoding="utf-8")) if (run_dir / "desk.json").is_file() else {}
    ran = [part["part"] for part in saved.get("parts", [])] or ORDER[1:]
    print("Order: " + " -> ".join(ran))
    refused = 0
    with no_network():
        for name in ran:
            print(f"\n=== {name} ===")
            begun = time.monotonic()
            output = next((file for file, part in HOOKS.items() if part == name), "")
            if output:
                problems = hook.check(run_dir / output, run_dir)
                for number, why in problems:
                    print(f"refused: line {number}, {why}")
                refused += len(problems)
                print("The hook read the saved output again: " + (f"refused {len(problems)} line(s)" if problems else "clean"))
            elif name == FINAL:
                print("Rebuilt from the saved verified report and the saved worksheet.")
            else:
                print("Replayed from its saved output. Nothing was fetched, and no model was called.")
            print(f"{name}: {time.monotonic() - begun:.1f} seconds")
        same = final_report(run_dir) == (run_dir / "final_report.md").read_text(encoding="utf-8")
    print(f"\nRun folder: {run_dir}")
    print(f"Final report: {run_dir / 'final_report.md'}")
    print(f"The replay gives the same final report: {'yes' if same else 'NO'}. Nothing was fetched.")
    if refused:
        print(f"Not done: the hook refused {refused} line(s).", file=sys.stderr)
    return 0 if same and not refused else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="The one command: the agent team, the worksheet and the hook, in an order fixed in code")
    parser.add_argument("target", nargs="?", help="A ticker of a U.S. company that files with EDGAR, or the word screen")
    parser.add_argument("--from", dest="start", metavar="YYYY-MM-DD", help="With screen: run the seeker first, from this start date")
    parser.add_argument("--peers", default="", help="Comma-separated peer tickers, for the agent team")
    parser.add_argument("--price", type=float, help="The close, by hand; without it the closes reader gives it")
    parser.add_argument("--filed", help="The release's filing time, YYYY-MM-DDTHH:MM:SS Eastern, when you do not want the 8-K's own")
    parser.add_argument("--replay", metavar="RUN_FOLDER", help="Rebuild a saved run's final report from its saved outputs; no fetch, no model")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    if args.replay:
        return replay(Path(args.replay))
    if not args.target:
        parser.error("give a ticker, the word screen, or --replay with a run folder")
    if args.start and args.target.lower() != "screen":
        parser.error("--from goes with screen: it runs the seeker first")

    import closes
    import team
    from lab02_desk import api_key_problem, env_path, user_agent_problem
    from lab03_app import DEFAULT_MODEL, Model

    setting = worksheet.setting
    key = setting("API_KEY") or setting("ANTHROPIC_API_KEY")
    user_agent = setting("SEC_USER_AGENT")
    problem = api_key_problem(key, env_path()) or user_agent_problem(user_agent, env_path())
    if problem:
        print(problem, file=sys.stderr)
        return 2
    started = datetime.now().astimezone()
    model = Model(key, setting("MODEL") or DEFAULT_MODEL, setting("EFFORT") or "medium")
    print(f"Model: {model.vendor} {model.model}")
    settings = {"user_agent": user_agent, "prices_key": setting("FINANCIAL_DATASETS_API_KEY"), "run_time": started, "tools": setting("AI_TOOLS") or "Claude Code"}
    state = {"peers": [p.strip().upper() for p in args.peers.split(",") if p.strip()], "price": args.price,
             "filed": closes.parse_when(args.filed).isoformat() if args.filed else None}
    seek = None
    if args.start:
        def seek() -> str | None:
            try:
                import seeker
            except ImportError as exc:
                raise PartFailed("the seeker is not in this repository yet, so the command cannot run it") from exc
            return seeker.run(args.start)
    return run(args.target, lambda: team.Team(settings, model), model, state, started, sys.argv[1:], seek=seek)


if __name__ == "__main__":
    raise SystemExit(main())
