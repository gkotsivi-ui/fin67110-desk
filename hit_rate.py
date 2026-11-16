#!/usr/bin/env python3
"""Read saved views and append available close-to-close reactions; never edit a view."""
import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import exchange_calendars

import closes
from live_record import eastern, release_named


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("view time must include a UTC offset")
    return result


def close_window(filed):
    """Scheduled US equity closes, including holidays and early closes."""
    calendar = exchange_calendars.get_calendar(
        "XNYS", start=(filed - timedelta(days=30)).date().isoformat(),
        end=(filed + timedelta(days=30)).date().isoformat())
    times = [t.to_pydatetime() for t in calendar.schedule["close"]]
    return max(t for t in times if t <= filed), min(t for t in times if t > filed)


def load(path):
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def row_for(run, now, offline=False):
    view = load(run / "view.json") if (run / "view.json").exists() else {}
    facts = load(run / "facts.json") if (run / "facts.json").exists() else {}
    ticker = view.get("ticker") or facts.get("ticker") or "unknown"
    filed_text = view.get("filing_time")
    if filed_text:
        filed = stamp(filed_text)
    else:
        report = next((run / n for n in ("verified_report.md", "report.md") if (run / n).exists()), None)
        named = release_named(report.read_text().splitlines()[0]) if report else None
        if not named or not named["accepted"]:
            raise ValueError("no saved filing acceptance time")
        filed = datetime.fromisoformat(named["accepted"]).replace(tzinfo=eastern())
    direction = view.get("direction", "not computed")
    if direction not in ("up", "down", "flat", "not computed"):
        raise ValueError("view direction must be up, down, flat, or not computed")
    viewed = stamp(view["time"]) if view.get("time") else None
    if direction != "not computed" and viewed is None:
        raise ValueError("computed view has no timestamp")
    before, after = close_window(filed)
    late = bool(viewed and viewed > after)
    reaction_path = run / "reaction.json"
    reaction = load(reaction_path) if reaction_path.exists() else None
    if reaction is None and not offline and now >= after:
        prices, source = closes.read(ticker, before.date(), after.date())
        prices = dict(prices)
        first, last = prices.get(before.date()), prices.get(after.date())
        if first is not None and last is not None:
            if not source:
                raise ValueError("reaction closes have no source")
            if not all(math.isfinite(p) and p > 0 for p in (first, last)):
                raise ValueError("reaction closes must be finite and positive")
            reaction = {"ticker": ticker, "filing_time": filed.isoformat(),
                        "before_close_time": before.isoformat(), "after_close_time": after.isoformat(),
                        "before_close": first, "after_close": last, "source": source,
                        "retrieved_at": now.isoformat()}
            # New evidence only: never overwrite an existing reaction or any original run file.
            with reaction_path.open("x") as handle:
                json.dump(reaction, handle, indent=2)
                handle.write("\n")
    change = None
    if reaction is not None:
        if (reaction["ticker"] != ticker or stamp(reaction["filing_time"]) != filed
                or stamp(reaction["before_close_time"]) != before
                or stamp(reaction["after_close_time"]) != after):
            raise ValueError("saved reaction does not match this filing and close window")
        first, last = reaction["before_close"], reaction["after_close"]
        if not all(isinstance(p, (int, float)) and not isinstance(p, bool)
                   and math.isfinite(p) and p > 0 for p in (first, last)):
            raise ValueError("saved reaction closes must be finite and positive")
        if not reaction.get("source"):
            raise ValueError("saved reaction has no source")
        if now >= after:
            change = (last / first - 1) * 100
    actual = None if change is None else "up" if change > 0 else "down" if change < 0 else "flat"
    eligible = actual is not None and direction != "not computed" and not late
    agreement = actual == direction if eligible else None
    fields = [ticker, filed.isoformat(), viewed.isoformat() if viewed else "not computed", direction,
              f"{change:+.4f}% ({actual})" if actual else "not available",
              ("agree" if agreement else "disagree") if agreement is not None else "—",
              "after" if late else ""]
    return fields, agreement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="runs/live or a separate practice folder")
    parser.add_argument("--offline", action="store_true", help="read saved reactions only; write nothing")
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error("folder does not exist")
    print("| Run | Ticker | Filing time | View time | Direction | Reaction | Agreement | Timing |")
    print("|---|---|---|---|---|---|---|---|")
    scored = []
    errors = 0
    for run in sorted(p for p in args.folder.iterdir() if p.is_dir() and not p.name.startswith(".")):
        try:
            fields, agreement = row_for(run, datetime.now(timezone.utc), args.offline)
            if agreement is not None:
                scored.append(agreement)
        except (ValueError, TypeError, KeyError, OSError, IndexError) as exc:
            errors += 1
            print(f"{run.name}: {exc}", file=sys.stderr)
            fields = ["unknown", "unknown", "not computed", "not computed", "not available", "—", "error"]
        print("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in [run.name, *fields]) + " |")
    print("\nThis is a learning exercise, not financial advice.\n\n"
          "AI assistance: OpenAI Codex. Calculations use saved views and sourced closes.\n\n"
          "Any remaining errors are my own.\n")
    print(f"Agreements: {sum(scored)}/{len(scored)}" +
          (f" ({sum(scored) / len(scored):.1%})" if scored else " (not computed)") +
          "; excludes after rows, views not computed, and unavailable reactions.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
