#!/usr/bin/env python3
"""Closing prices from financialdatasets.ai, with the class key read as FINANCIAL_DATASETS_API_KEY from .env."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta
from typing import Any

import requests

from lab02_desk import is_placeholder, load_dotenv

API = "https://api.financialdatasets.ai/prices/"
CLOSE = time(16, 0)  # A trading day's close is 4:00 PM Eastern.


def api_key() -> str:
    key = os.environ.get("FINANCIAL_DATASETS_API_KEY") or load_dotenv().get("FINANCIAL_DATASETS_API_KEY", "")
    return "" if is_placeholder(key) else key


def daily_closes(ticker: str, start: date, end: date, key: str) -> list[dict[str, Any]]:
    response = requests.get(
        API,
        params={"ticker": ticker, "interval": "day", "start_date": start.isoformat(), "end_date": end.isoformat()},
        headers={"X-API-KEY": key},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("prices") or []


def last_close_before(ticker: str, when: datetime, key: str) -> tuple[str, float] | None:
    """The last daily close at or before `when` (Eastern time); that day's own close counts from 4:00 PM."""
    last_day = when.date() if when.time() >= CLOSE else when.date() - timedelta(days=1)
    rows = [r for r in daily_closes(ticker, last_day - timedelta(days=10), last_day, key) if str(r.get("time", ""))[:10] <= last_day.isoformat()]
    if not rows:
        return None
    row = max(rows, key=lambda r: str(r["time"])[:10])
    return str(row["time"])[:10], float(row["close"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the last close at or before a date and time (Eastern)")
    parser.add_argument("ticker", help="Ticker of a U.S.-listed stock")
    parser.add_argument("date", help="YYYY-MM-DD")
    parser.add_argument("time", nargs="?", default="16:00", help="HH:MM Eastern; the default 16:00 includes that day's close")
    args = parser.parse_args()
    key = api_key()
    if not key:
        print("Missing FINANCIAL_DATASETS_API_KEY. Add it to .env, then retry.", file=sys.stderr)
        return 2
    ticker = args.ticker.upper()
    when = datetime.combine(date.fromisoformat(args.date), time.fromisoformat(args.time))
    try:
        found = last_close_before(ticker, when, key)
    except requests.RequestException as exc:
        print(f"Price request failed: {exc.__class__.__name__} {getattr(exc.response, 'status_code', '')}", file=sys.stderr)
        return 1
    if not found:
        print(f"No close found for {ticker} in the 10 days before {when:%Y-%m-%d %H:%M}.", file=sys.stderr)
        return 1
    day, close = found
    print(f"{ticker} close on {day}: {close:.2f} (financialdatasets.ai; the last close at or before {when:%Y-%m-%d %H:%M} Eastern)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
