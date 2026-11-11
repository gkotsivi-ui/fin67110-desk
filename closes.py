#!/usr/bin/env python3
"""The closes reader (Week 4): a ticker's official daily closes, and the last close before a date and time.

The source is LSEG Workspace, through LSEG's Data Library for Python (lseg-data): the Workspace desktop app runs
and is signed in, and .env holds the App Key as LSEG_APP_KEY. Until LSEG approves your account, the source can be
a CSV file exported from Workspace, kept outside this folder, with its path in .env as CLOSES_FILE. When the
source has nothing for a ticker, the functions return "not available", and the agent team still finishes.

The closes stay in code: the agent team takes one close, for P/E, and saves no list of closes anywhere.

Install the library:  python -m pip install lseg-data
Print a last close:    python closes.py TICKER 2026-09-24T16:17:37
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from lab02_desk import is_placeholder, load_dotenv

NOT_AVAILABLE = "not available"
CLOSE = time(16, 0)  # A trading day's close is 4:00 PM Eastern.
# The LSEG field the reader asks for. Set LSEG_CLOSE_FIELD in .env to ask for another one, for example OFF_CLOSE.
CLOSE_FIELD = "TR.PriceClose"
# Exchange suffixes of U.S. RICs, tried in this order unless LSEG_RICS in .env gives a ticker's RIC.
SUFFIXES = (".O", ".N", ".A", ".K", ".P")
DATE_COLUMNS = ("date", "trade date", "exchange date", "timestamp", "as of date")
# Close columns in the order they are preferred; an adjusted close is never used.
CLOSE_COLUMNS = ("official close", "off_close", "close official", "price close", "close price", "close", "trdprc_1")
TICKER_COLUMNS = ("ticker", "symbol", "ric", "instrument", "identifier")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y", "%Y/%m/%d", "%d/%m/%Y")


def setting(name: str) -> str:
    value = os.environ.get(name) or load_dotenv().get(name, "")
    return "" if is_placeholder(value) else value


def daily_closes(ticker: str, start: date, end: date) -> list[tuple[date, float]] | str:
    """The official daily closes for a ticker from start to end, both days included, oldest first.
    "not available" when the source has none."""
    rows, _ = read(ticker, start, end)
    return rows or NOT_AVAILABLE


def last_close_before(ticker: str, when: datetime) -> tuple[date, float] | str:
    """The last close at or before `when`, a date and time in Eastern time; a day's own close counts from 4:00 PM.
    "not available" when the source has none."""
    found = last_close_with_source(ticker, when)
    return found[:2] if isinstance(found, tuple) else NOT_AVAILABLE


def last_close_with_source(ticker: str, when: datetime) -> tuple[date, float, str] | str:
    """last_close_before, with the source that gave the close, for the report's price note."""
    last_day = when.date() if when.time() >= CLOSE else when.date() - timedelta(days=1)
    rows, source = read(ticker, last_day - timedelta(days=10), last_day)
    return (*rows[-1], source) if rows else NOT_AVAILABLE


def read(ticker: str, start: date, end: date) -> tuple[list[tuple[date, float]], str]:
    """The closes from start to end and the source's name: LSEG first when LSEG_APP_KEY is set, then CLOSES_FILE."""
    ticker = ticker.strip().upper()
    attempts = []
    if setting("LSEG_APP_KEY"):
        attempts.append(lambda: lseg_closes(ticker, start, end))
    if setting("CLOSES_FILE"):
        attempts.append(lambda: (file_closes(Path(setting("CLOSES_FILE")).expanduser(), ticker), "the CSV file in CLOSES_FILE"))
    for attempt in attempts:
        rows, source = attempt()
        rows = sorted({day: close for day, close in rows if start <= day <= end}.items())
        if rows:
            return rows, source
    return [], ""


# ----- LSEG Workspace -----

def rics_for(ticker: str) -> list[str]:
    """The RICs to try: the one LSEG_RICS gives (TICKER=RIC pairs, comma-separated), else the ticker with each U.S. suffix."""
    for pair in setting("LSEG_RICS").split(","):
        name, _, ric = pair.partition("=")
        if name.strip().upper() == ticker and ric.strip():
            return [ric.strip()]
    return [ticker + suffix for suffix in SUFFIXES]


def lseg_closes(ticker: str, start: date, end: date) -> tuple[list[tuple[date, float]], str]:
    """Daily closes from LSEG Workspace, through a desktop session opened with the App Key."""
    try:
        import lseg.data as ld
    except ImportError:
        print("Closes reader: lseg-data is not installed. Install it with: python -m pip install lseg-data", file=sys.stderr)
        return [], ""
    field = setting("LSEG_CLOSE_FIELD") or CLOSE_FIELD
    try:
        ld.open_session(name="desktop.workspace", app_key=setting("LSEG_APP_KEY"))
    except Exception as exc:  # The library's documentation names no exception classes.
        print(f"Closes reader: no LSEG Workspace session ({exc.__class__.__name__}: {exc}). "
              "Start the Workspace desktop app, sign in, and check LSEG_APP_KEY.", file=sys.stderr)
        return [], ""
    try:
        for ric in rics_for(ticker):
            try:
                frame = ld.get_history(universe=ric, fields=[field], interval="daily", start=start.isoformat(), end=end.isoformat())
            except Exception:
                continue  # Not this RIC; try the next suffix.
            rows = frame_rows(frame)
            if rows:
                return rows, f"LSEG Workspace, {ric} {field}"
        return [], ""
    finally:
        try:
            ld.close_session()
        except Exception:
            pass


def frame_rows(frame: Any) -> list[tuple[date, float]]:
    """(day, close) pairs from the table get_history returns: the dates in its index, the closes in its first column."""
    columns = list(getattr(frame, "columns", []))
    if not columns:
        return []
    rows = []
    for when, value in zip(frame.index, frame[columns[0]]):
        day, close = to_date(when), to_float(value)
        if day is not None and close is not None:
            rows.append((day, close))
    return rows


# ----- an exported CSV file -----

def named_for(path: Path, ticker: str) -> bool:
    """True when the file's name starts with the ticker: ABC.csv, ABC.O.csv or ABC_closes.csv for ABC."""
    stem = path.stem.upper()
    return stem == ticker or (stem.startswith(ticker) and stem[len(ticker)] in "._- ")


def file_closes(path: Path, ticker: str) -> list[tuple[date, float]]:
    """(day, close) pairs for the ticker: from the CSV file, or from the CSV files in the folder whose names start with it."""
    if path.is_dir():
        files = [p for p in sorted(path.glob("*.csv")) if named_for(p, ticker)]
    elif path.is_file():
        files = [path]
    else:
        print(f"Closes reader: CLOSES_FILE names {path}, which does not exist.", file=sys.stderr)
        return []
    rows = []
    for file in files:
        if file.suffix.lower() != ".csv":
            print(f"Closes reader: {file.name} is not a .csv file. Save the export as CSV.", file=sys.stderr)
            continue
        rows += csv_closes(file, ticker)
    return rows


def close_column(names: list[str]) -> int | None:
    for wanted in CLOSE_COLUMNS:
        if wanted in names:
            return names.index(wanted)
    return next((i for i, n in enumerate(names) if "close" in n and "adj" not in n), None)


def csv_closes(file: Path, ticker: str) -> list[tuple[date, float]]:
    """The file's closes for the ticker. The header may come after a few title lines. A file without a ticker
    column holds one company's closes, and its name must start with the ticker."""
    with file.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        table = list(csv.reader(handle))
    for start, row in enumerate(table[:30]):
        names = [c.strip().lower() for c in row]
        when = next((i for i, n in enumerate(names) if n in DATE_COLUMNS), None)
        close = close_column(names)
        if when is not None and close is not None:
            who = next((i for i, n in enumerate(names) if n in TICKER_COLUMNS), None)
            break
    else:
        return []
    if who is None and not named_for(file, ticker):
        return []
    rows = []
    for row in table[start + 1:]:
        if who is not None and not (len(row) > who and same_ticker(row[who], ticker)):
            continue
        day = to_date(row[when]) if len(row) > when else None
        value = to_float(row[close]) if len(row) > close else None
        if day is not None and value is not None:
            rows.append((day, value))
    return rows


def same_ticker(cell: str, ticker: str) -> bool:
    """ABC, ABC.O and "ABC US" all name ABC."""
    value = cell.strip().upper()
    return value == ticker or value.split(".")[0] == ticker or value.split(" ")[0] == ticker


# ----- values -----

def to_float(value: Any) -> float | None:
    try:
        number = float(str(value).replace("$", "").replace(",", "").strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date") and callable(value.date):  # a pandas Timestamp
        try:
            return value.date()
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    for candidate in dict.fromkeys([text, text.split("T")[0], text.split(" ")[0]]):
        for form in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, form).date()
            except ValueError:
                continue
    return None


def parse_when(text: str) -> datetime:
    """YYYY-MM-DDTHH:MM:SS in Eastern time; a date alone means after that day's close."""
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(text), CLOSE)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text} is not YYYY-MM-DDTHH:MM:SS (Eastern) or YYYY-MM-DD") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a ticker's last close before a date and time (Eastern), from LSEG Workspace or the CSV file in CLOSES_FILE")
    parser.add_argument("ticker", help="The ticker, as EDGAR gives it")
    parser.add_argument("when", type=parse_when, help="YYYY-MM-DDTHH:MM:SS, Eastern; a date alone means after that day's close")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    ticker = args.ticker.strip().upper()
    if not setting("LSEG_APP_KEY") and not setting("CLOSES_FILE"):
        print("Set LSEG_APP_KEY (with the Workspace desktop app running) or CLOSES_FILE in .env.", file=sys.stderr)
        return 2
    found = last_close_with_source(ticker, args.when)
    if not isinstance(found, tuple):
        print(f"{ticker}: {NOT_AVAILABLE} (no close in the 10 days before {args.when:%Y-%m-%d %H:%M:%S} Eastern)")
        return 1
    day, close, source = found
    print(f"{ticker}: {close:,.2f}, the close of {day}, the last close before {args.when:%Y-%m-%d %H:%M:%S} Eastern ({source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
