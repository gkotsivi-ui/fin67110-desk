#!/usr/bin/env python3
"""SEC data collection and calculations for an equity research desk."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from closes_reader import filing_time, last_close_before, NOT_AVAILABLE
from report_naming import create_run
from quarterly_cash_flow import quarterly_capital_spending
from desk_rules import annual_problem, exhibit_99_label, release_among

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


SEC_BASE = "https://www.sec.gov"
DATA_BASE = "https://data.sec.gov"
COMPANY_TICKERS_URL = f"{SEC_BASE}/files/company_tickers.json"
# Claim 7 divides long-term debt, with its current portion, by equity. A balance sheet holds that debt in two lines.
# Each pair is one definition, the noncurrent line then the current line, and both come from the same 10-K. The total
# tag is never the amount: filers use it for other measures (docs/decision-log.md, entry 9; on 2026-11-20 Lowe's
# LongTermDebt was its maturity schedule's total, not the balance sheet's). It only shows that there is no current
# portion, when it equals the noncurrent line and no current line is filed. This is the base desk's rule (lab02_desk.py).
DEBT_PAIRS = (
    ("LongTermDebtNoncurrent", "LongTermDebtCurrent"),
    ("LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent"),
)
DEBT_TOTAL = "LongTermDebt"
# A balance sheet whose current debt line is tagged DebtCurrent (Dell's 10-K for fiscal 2026). EDGAR describes that tag
# as "short-term debt and current maturity of long-term debt", so it can hold short-term borrowings, which claim 7
# leaves out. It is read as the current portion only when DEBT_TOTAL, in the same filing at the same date, equals
# LongTermDebtNoncurrent plus DebtCurrent: then nothing in the line lies outside the company's own long-term debt. The
# amount is still the two balance-sheet lines; the total is only the check (docs/decision-log.md, 2026-11-22).
DEBT_CURRENT_LINE = "DebtCurrent"
CONCEPTS: dict[str, dict[str, Any]] = {
    # Prefer total Revenues when a filer reports it. Fall back to other
    # standard revenue concepts when that tag is unavailable for a peer.
    "revenue": {"tags": ["Revenues", "RevenuesNetOfInterestExpense", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet", "RevenueFromContractWithCustomerIncludingAssessedTax"], "kind": "duration", "unit": "USD"},
    "operating_income": {"tags": ["OperatingIncomeLoss"], "kind": "duration", "unit": "USD"},
    "net_income": {"tags": ["ProfitLoss", "NetIncomeLoss"], "kind": "duration", "unit": "USD"},
    "noncontrolling_interest_income": {"tags": ["NetIncomeLossAttributableToNonredeemableNoncontrollingInterest", "NetIncomeLossAttributableToRedeemableNoncontrollingInterest"], "kind": "duration", "unit": "USD"},
    "net_income_attributable_to_parent": {"tags": ["NetIncomeLossAttributableToParent", "NetIncomeLoss"], "kind": "duration", "unit": "USD"},
    "diluted_eps": {"tags": ["EarningsPerShareDiluted"], "kind": "duration", "unit": "USD/shares"},
    "stockholders_equity": {"tags": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "kind": "instant", "unit": "USD"},
    # The balance sheet's two lines of long-term debt; compile_facts reads them as one pair (DEBT_PAIRS).
    "long_term_debt": {"tags": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"], "kind": "instant", "unit": "USD",
                       "label": "long-term debt, excluding current maturities (balance sheet)"},
    "current_portion_of_long_term_debt": {"tags": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"], "kind": "instant", "unit": "USD",
                                          "label": "current maturities of long-term debt (balance sheet)"},
    "short_term_borrowings": {"tags": ["ShortTermBorrowings"], "kind": "instant", "unit": "USD",
                              "label": "short-term borrowings; not part of debt to equity"},
    "cash_from_operations": {"tags": ["NetCashProvidedByUsedInOperatingActivities"], "kind": "duration", "unit": "USD"},
    "additions_to_property_and_equipment": {"tags": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsForProceedsFromProductiveAssets"], "kind": "duration", "unit": "USD"},
}


@dataclass
class Filing:
    form: str
    accession: str
    filed: str
    primary_document: str
    accepted: str = ""
    index_url: str = ""
    document_url: str = ""
    release_document: str = ""
    release_url: str = ""
    release_label: str = "99.1"  # the release's exhibit number on the 8-K's index page: 99.1, 99.2 or 99
    report_date: str = ""


DATE_CELL = re.compile(r"([A-Z][a-z]+)\.?\s+(\d{1,2}),?\s+(20\d{2})")
YEAR_CELL = re.compile(r"(20\d{2})")
MONTHS = {name: number for number, name in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
# One amount in a table cell: 22,756  $2.98  (0.12)  (0.12  -0.12. A dash alone is an empty amount.
# The amount may be printed without its zero: ".48", "(.23". Until 2026-11-25 such a cell was not an amount, the
# per-share rows held none, and the release's three claims were lost.
AMOUNT_CELL = re.compile(r"\$?\s*(\()?\s*\$?\s*([-−–])?\s*\$?\s*(\d[\d,]*(?:\.\d+)?|\.\d+)\s*\)?")
DASH_CELL = re.compile(r"[-–—−]+")
REVENUE_TIERS = (r"total\s+(?:net\s+)?revenues?|revenues?,?\s+total", r"(?:net\s+)?revenues?(?:,\s+net)?", r"total\s+net\s+sales|net\s+sales")
# A row or a per-share heading with one of these words is another measure, never GAAP diluted EPS.
NOT_GAAP = re.compile(r"adjusted|non-?\s?gaap|\bcore\b|excluding|continuing|discontinued", re.I)
# A table under one of these headings is not the income statement.
# "Adjusted EBITDA" and "adjusted results" name other measures; "per share amounts adjusted for the stock split"
# does not, and until 2026-11-22 that note in a statement's title made the desk skip the statement.
NOT_THE_STATEMENT = re.compile(r"non-?\s?gaap|reconciliation|\badjusted\s+(?!for\b)\w|outlook|guidance|forecast", re.I)
SPAN = re.compile(r"\b(?:(?:[A-Za-z-]+|\d+)\s+(?:Months|Weeks)|Quarter|(?:Fiscal\s+)?Year)s?\s+Ended\b", re.I)
SPAN_WORDS = {"three": 3, "six": 6, "nine": 9, "twelve": 12, "thirteen": 13, "fourteen": 14, "sixteen": 16, "seventeen": 17}
QUARTER_TOKEN = re.compile(r"(?:Q([1-4])\s*['’]?\s*(\d{2})|([1-4])\s*Q\s*['’]?\s*(\d{2}))", re.I)
# "Diluted earnings per share", and the same label with the word at its end: "Net income per share - diluted".
# A company with a loss prints one row for both, because they are equal: "Net loss per share, basic and diluted",
# also with "attributable to ... common stockholders" before the comma or the dash. That row is GAAP diluted EPS
# too. Until 2026-11-25 it was not read, and with it the quarter's revenue was lost (three of the 22 companies swept).
EPS_ROW = re.compile(r"(?:basic\s+and\s+)?diluted\s+(?:net\s+)?(?:earnings|income|loss)(?:\s+\((?:loss|income)\))?\s+per\s+(?:common\s+)?share"
                     r"|(?:net\s+)?(?:earnings|income|loss)(?:\s+\((?:loss|income)\))?\s+per\s+(?:common\s+)?share"
                     r"(?:\s+attributable\s+to\s+.{1,100}?)?\s*(?:[-–—:,]\s*|\()(?:basic\s+and\s+)?diluted\b\)?", re.I)
PER_SHARE_HEADING = re.compile(r"(?:earnings|income).*per\s+(?:common\s+)?share|per\s+share", re.I)
# A heading that counts shares. "Shares used in computing net income per share:" says "per share" and heads the
# rows "Basic" and "Diluted" of a share count: until 2026-11-22 the desk published that count as diluted EPS.
SHARE_COUNT_HEADING = re.compile(r"\bshares\b|weighted|outstanding", re.I)
# A heading row that opens a section of other measures inside a table, and one that returns to GAAP.
OTHER_MEASURES = re.compile(r"non-?\s?gaap|\badjusted\b", re.I)
BACK_TO_GAAP = re.compile(r"(?:U\.S\.\s+)?GAAP\b|as\s+reported\b", re.I)
# How many title lines above a table are read: a company's name, the statement's title, its unit, "(Unaudited)"
# and a date line are five already.
TITLE_LINES = 8
BLOCKS = ["p", "div", "li", "center", "h1", "h2", "h3", "h4", "h5", "h6"]


def other_measures_after(label: str, before: bool) -> bool:
    """Whether the rows under this heading row are other measures than GAAP: a section headed "Non-GAAP" or
    "Adjusted results" lasts until a heading says GAAP again. A per-share heading inside it does not end it."""
    if OTHER_MEASURES.search(label) and not PER_SHARE_HEADING.search(label):
        return True
    return before and not BACK_TO_GAAP.match(label)


def row_amounts(cells: list[str]) -> list[str | None]:
    """The amounts in a table row's cells, in order, as the table prints them, a loss with a minus sign.

    A filer prints a loss in parentheses or with a minus sign, and often splits it over two cells, "(0.12" then ")".
    A dash is an empty amount and keeps its column (None). A percentage is not an amount: the cell ends with "%",
    or the next cell starts with it. On 2026-11-22 the readers kept only the cells that were plain numbers, so a
    row with a loss held one amount fewer and the year-ago figure was read as the quarter's.
    """
    cells = [cell.strip() for cell in cells]
    amounts: list[str | None] = []
    for k, cell in enumerate(cells):
        # The percent sign may stand in the next cell, alone or behind the closing parenthesis of a negative
        # change: "(5" then ")%". Until 2026-11-22 only a next cell that starts with "%" was known, so "(5" was
        # an amount, the row held one too many and was dropped, and another row's figure was published.
        if re.match(r"[)\s]*%", next((c for c in cells[k + 1:] if c), "")):
            continue
        if DASH_CELL.fullmatch(cell):
            amounts.append(None)
            continue
        found = AMOUNT_CELL.fullmatch(cell)
        if found:
            amounts.append(("-" if found.group(1) or found.group(2) else "") + found.group(3))
    return amounts


def cell_period(cell: str) -> tuple[int, Any] | None:
    """A period column's label: (year, date) for "October 30, 2026" or "Oct. 30, 2026", (year, None) for "2026"."""
    text = cell.strip()
    found = DATE_CELL.fullmatch(text)
    if found:
        month = MONTHS.get(found.group(1)[:3].lower())
        try:
            return (int(found.group(3)), datetime(int(found.group(3)), month, int(found.group(2))).date()) if month else None
        except ValueError:
            return None
    found = YEAR_CELL.fullmatch(text)
    return (int(found.group(1)), None) if found else None


def latest_and_year_ago(periods: list[tuple[int, Any]]) -> tuple[int, int | None] | None:
    """Which of one group's period columns is the latest, and which is the same period a year before.

    Dates are compared as dates, and the year-ago column ends 350 to 380 days earlier (a 52- or 53-week year).
    Bare years: the year before. None when the latest period is printed twice or dates and years are mixed: the
    table does not say which column is which, and the desk does not guess.
    """
    if not periods:
        return None
    if all(day for _, day in periods):
        top = max(day for _, day in periods)
        if sum(day == top for _, day in periods) != 1:
            return None
        before = [k for k, (_, day) in enumerate(periods) if 350 <= (top - day).days <= 380]
        return [day for _, day in periods].index(top), before[0] if len(before) == 1 else None
    if any(day for _, day in periods):
        return None
    years = [year for year, _ in periods]
    if years.count(max(years)) != 1:
        return None
    return years.index(max(years)), years.index(max(years) - 1) if years.count(max(years) - 1) == 1 else None


def quarter_group(header: str) -> tuple[int, int, list[str]] | None:
    """Which group of period columns is the quarter, how many groups there are, and the header's words for it.

    A header names its groups in order: "Three Months Ended" then "Nine Months Ended", or "12 Weeks Ended" then
    "36 Weeks Ended". The quarter is the group of at most 17 weeks; with two, the shorter and then the first.

    In a fiscal year of 53 weeks the last quarter has a week more than a year before, and each of its columns has
    words of its own: "17 Weeks Ended" beside "16 Weeks Ended", then "53 Weeks Ended" beside "52 Weeks Ended".
    Spans one week apart are one group. Until 2026-11-25 they were two, the shorter was chosen, and last year's
    quarter was published as the latest. The words are returned for each column of the group, in order.
    """
    def weeks(span: str) -> float:
        first, unit = span.split()[0].lower(), span.lower()
        if first == "quarter":
            return 13
        number = int(first) if first.isdigit() else SPAN_WORDS.get(first)
        if number is None or "year" in unit:
            return 99
        return number * 13 / 3 if "month" in unit else number

    groups: list[list[str]] = []
    for span in (found.group(0) for found in SPAN.finditer(header)):
        last = groups[-1][-1] if groups else None
        if last is not None and span.lower() == last.lower():
            continue                         # one cell for each column repeats the words
        if last is not None and "week" in span.lower() and "week" in last.lower() and abs(weeks(span) - weeks(last)) <= 1:
            groups[-1].append(span)          # the same period in a 52-week and in a 53-week year
        else:
            groups.append([span])
    lengths = [min(weeks(span) for span in group) for group in groups]
    if not lengths or min(lengths) > 17:
        return None
    chosen = lengths.index(min(lengths))
    return chosen, len(groups), [" ".join(span.lower().split()) for span in groups[chosen]]


def read_quarter_table(rows: list[list[str]]) -> dict[str, Any] | None:
    """The latest quarter's revenue, the same quarter's revenue a year before, and GAAP diluted EPS, from one release
    table whose period columns carry dates or years under a "Three Months Ended", "Quarter Ended" or "N Weeks Ended" header.

    On 2026-11-20 step 6 read no quarter from Lowe's or Walmart: Lowe's dates its columns and pairs each amount with
    its percentage of sales, and Walmart's year cells do not line up with its merged header cells. Total revenues
    come before revenues, and revenues before net sales. A row is read only when it holds one amount for each period
    column (row_amounts), so a loss, a dash or a change column never moves a figure into another period's place.
    None when the table does not give the quarter's revenue and its diluted EPS.
    """
    texts = [" ".join(row) for row in rows]
    head = next((i for i, text in enumerate(texts) if quarter_group(text)), None)
    if head is None:
        return None
    group, groups, words = quarter_group(texts[head])
    period_row = next((i for i in range(head, min(head + 4, len(rows))) if sum(cell_period(c) is not None for c in rows[i]) >= 2), None)
    if period_row is None:
        return None
    # The rows down to the period columns are the table's own title. A statement that calls itself non-GAAP there
    # is not the income statement, wherever the lines above the table point (2026-11-22).
    if NOT_THE_STATEMENT.search(" ".join(texts[:period_row + 1])):
        return None
    labels = [c.strip() for c in rows[period_row] if cell_period(c) is not None]
    count = len(labels)
    if count % groups:
        return None
    size = count // groups
    columns = latest_and_year_ago([cell_period(c) for c in labels[group * size:(group + 1) * size]])
    if columns is None:
        return None
    # The latest quarter ends on the table's latest date. When the columns chosen do not hold it, the groups are
    # not of equal size (three quarters beside one column for the year) and the desk does not guess.
    periods = [cell_period(c) for c in labels]
    chosen = periods[group * size + columns[0]]
    if (all(day for _, day in periods) and chosen[1] != max(day for _, day in periods)) or (
            not any(day for _, day in periods) and chosen[0] != max(year for year, _ in periods)):
        return None
    # One span for each column ("17 weeks ended", "16 weeks ended"): the latest column's own words name the quarter.
    span = words[columns[0]] if len(words) == size else words[0]
    latest, prior = group * size + columns[0], None if columns[1] is None else group * size + columns[1]
    # Lowe's prints each period's amount and then its percentage of sales; only a header that says so pairs them.
    # A column of change is not a share of sales: "% Change" beside "% Change in Constant Currency" made two "%"
    # cells for two periods, the rows were read as pairs, and last year's revenue became 11.1 (2026-11-22).
    def share_of_sales(cell: str) -> bool:
        return "%" in cell and not re.search(r"change|growth|increase|decrease|\bvar|\bvs\b|currency|y/y|yoy", cell, re.I)
    paired = any(sum(share_of_sales(c) for c in row) >= count and not row_amounts(row[1:]) for row in rows[head:period_row + 3])

    def amounts(row: list[str]) -> list[str | None] | None:
        values = row_amounts(row[1:])
        if paired and len(values) == 2 * count:
            values = values[::2]
        return values if len(values) == count else None

    revenue: dict[int, tuple[str, list[str | None]]] = {}
    eps = None
    heading = ""
    other_measures = False
    for row in rows[period_row + 1:]:
        if not row:
            continue
        label = re.sub(r"\s*\(\w{1,2}\)$", "", row[0].strip().rstrip(":").strip())  # a footnote mark after the label
        values = amounts(row)
        if not values:
            heading = label or heading
            if label:
                other_measures = other_measures_after(label, other_measures)
            continue
        if other_measures:
            continue
        for tier, pattern in enumerate(REVENUE_TIERS):
            if tier not in revenue and re.fullmatch(pattern, label, re.I) and values[latest] and not values[latest].startswith("-"):
                revenue[tier] = (label, values)
        if eps is None and values[latest] is not None and not NOT_GAAP.search(label) and (
                EPS_ROW.match(label)
                or (re.fullmatch(r"diluted", label, re.I) and PER_SHARE_HEADING.search(heading)
                    and not NOT_GAAP.search(heading) and not SHARE_COUNT_HEADING.search(heading))
                or (re.fullmatch(r"GAAP", label, re.I) and EPS_ROW.search(heading))):
            eps = (label if EPS_ROW.match(label) else f"{heading}: {label}", values)
    if not revenue or eps is None:
        return None
    label, values = revenue[min(revenue)]
    return {"revenue": values[latest], "prior_revenue": values[prior] if prior is not None else None, "eps": eps[1][latest],
            "revenue_label": label, "eps_label": eps[0], "span": span, "latest": labels[latest], "prior": labels[prior] if prior is not None else None}


def read_quarter_token_table(rows: list[list[str]]) -> dict[str, Any] | None:
    """The same three figures from a table whose period columns are quarter tokens: Q3'26 and Q3'25, or 3Q26 and 3Q25.

    The latest token is the quarter and the same quarter of the year before is its comparison, wherever the columns
    stand. None when the latest token is printed twice (GAAP beside non-GAAP columns: the table does not say which is
    which), and a row is read only when it holds one amount for each token column.
    """
    def key(cell: str) -> tuple[int, int] | None:
        found = QUARTER_TOKEN.fullmatch(cell.strip())
        return (int(found.group(2) or found.group(4)), int(found.group(1) or found.group(3))) if found else None

    header = max(range(len(rows)), key=lambda i: sum(key(c) is not None for c in rows[i]), default=None)
    if header is None or sum(key(c) is not None for c in rows[header]) < 2:
        return None
    labels = [c.strip() for c in rows[header] if key(c) is not None]
    keys = [key(c) for c in labels]
    top = max(keys)
    if keys.count(top) != 1:
        return None
    if NOT_THE_STATEMENT.search(" ".join(" ".join(row) for row in rows[:header + 1])):
        return None  # the table's own title says it is another statement
    latest, year_ago = keys.index(top), (top[0] - 1, top[1])
    prior = keys.index(year_ago) if keys.count(year_ago) == 1 else None
    revenue = eps = None
    heading = ""
    other_measures = False
    for row in rows[header + 1:]:
        if not row:
            continue
        label = re.sub(r"\s*\(\w{1,2}\)$", "", row[0].strip().rstrip(":").strip())
        values = row_amounts(row[1:])
        if len(values) != len(keys):
            heading = label or heading
            if label:
                other_measures = other_measures_after(label, other_measures)
            continue
        if other_measures:
            continue
        if revenue is None and re.fullmatch(r"(?:(?:total|net)\s+)?revenues?(?:\s*[-–]\s*reported)?", label, re.I) and values[latest] and not values[latest].startswith("-"):
            revenue = (label, values)
        if eps is None and values[latest] is not None and not NOT_GAAP.search(label) and (
                re.fullmatch(r"(?:diluted\s+(?:EPS|earnings\s+per\s+share)|(?:EPS|earnings\s+per\s+share)\s*[-–]\s*diluted)", label, re.I)
                or (re.fullmatch(r"diluted", label, re.I) and re.search(r"earnings\s+per\s+share|EPS", heading, re.I) and not NOT_GAAP.search(heading))):
            eps = (label, values)
        heading = label or heading
    if revenue is None or eps is None:
        return None
    return {"revenue": revenue[1][latest], "prior_revenue": revenue[1][prior] if prior is not None else None, "eps": eps[1][latest],
            "revenue_label": revenue[0], "eps_label": eps[0], "span": "quarter", "latest": labels[latest], "prior": labels[prior] if prior is not None else None}


def table_heading(table: Any) -> str:
    """The title lines printed just above a release table, up to TITLE_LINES, in the order the page prints them:
    its title, and often its unit.

    A line is one block of the page, whatever bold or footnote tags split it into. A sentence is not a title, and
    neither is a footnote of the table before; what stands above either belongs to it. The paragraph before a
    release's statements usually speaks of outlook, guidance and non-GAAP measures: on 2026-11-22 the desk took
    those words for the table's title and skipped the income statement itself. It also read only four pieces of
    text, so a title five lines up, or one that tags had cut in pieces, was not seen at all.
    """
    lines: list[str] = []
    seen: set[int] = set()
    if table is not None:
        for text in table.find_all_previous(string=True, limit=120):
            if text.find_parent("table") is not None:
                break  # an earlier table: its heading is not this one's
            block = text.find_parent(BLOCKS)
            if block is not None and block.find(["table", "br"]) is None:
                if id(block) in seen:
                    continue
                seen.add(id(block))
                line = " ".join(block.get_text(" ").split())
            else:
                line = " ".join(text.split())
            if not line:
                continue
            sentence = line.rstrip("\"'”’").endswith(".") and line != line.upper()
            if sentence or re.match(r"\(\w{1,2}\)\s+\w|\*+\s*\w", line):
                break
            lines.append(line)
            if len(lines) == TITLE_LINES:
                break
    return " ".join(reversed(lines))


def table_unit(table: Any, rows: list[list[str]]) -> str:
    """A release table's unit: "in millions" in the table's own title rows, or else in the lines printed just above it.

    On 2026-11-21 Lowe's printed "In Millions, Except Per Share and Percentage Data" above its table, not in it, and
    the desk called its net sales "USD as shown"; an analyst who guessed the unit would write a wrong claim. The
    title rows end with the row of period columns (one filer prints its unit beside its years), or, in a table
    without one, before the first row of amounts. A row's own unit below them ("Weighted average shares (in
    thousands)") is that row's: until 2026-11-22 it was printed as the unit of the whole table.
    """
    pattern = r"\bin (millions|thousands|billions)\b"
    first_amounts = next((i for i, row in enumerate(rows) if any(amount is not None for amount in row_amounts(row[1:]))), len(rows))
    periods = next((i for i, row in enumerate(rows) if sum(cell_period(cell) is not None for cell in row) >= 2), None)
    end = periods + 1 if periods is not None and periods <= first_amounts else first_amounts
    title = " ".join(cell for row in rows[:end] for cell in row)
    found = re.search(pattern, title, re.I) or re.search(pattern, table_heading(table), re.I)
    return f"USD {found.group(1).lower()}" if found else "USD as shown"


def filings_line(filings: dict[str, Any], cik: str) -> str:
    """A report's first line: the filings the desk read, the earnings release by its exhibit, each EDGAR Accepted
    time and the CIK, in the base desk's form. live_record.py reads the 8-K, its exhibit, its Accepted time and the
    CIK from this line; on 2026-11-20 a line with no CIK made it read no 8-K at all."""
    def accepted(filing: Any) -> str:
        stamp = getattr(filing, "accepted", "") or ""
        return f"accepted {stamp} ET" if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", stamp) else ""
    entries = []
    for form, period in (("10-K", "fiscal year ended"), ("10-Q", "quarter ended"), ("8-K", "")):
        filing = filings.get(form)
        if not filing:
            continue
        if period:
            when = getattr(filing, "report_date", "") or ""
            details = [f"{period} {when}" if when else "", accepted(filing)]
        else:
            exhibit = getattr(filing, "release_document", "") or ""
            label = getattr(filing, "release_label", "") or "99.1"
            details = ["Item 2.02 earnings release" + (f", Exhibit {label} {exhibit}" if exhibit else ""), accepted(filing)]
        details = [d for d in details if d]
        entries.append(f"{form} {filing.accession}" + (f" ({', '.join(details)})" if details else ""))
    if cik:
        entries.append(f"XBRL company facts, CIK {str(cik).zfill(10)}")
    return "Filings read: " + "; ".join(entries)


class Desk:
    def __init__(self, ticker: str, peers: list[str], price: float | None = None, filed: str | None = None):
        load_dotenv(Path(__file__).with_name(".env"))
        user_agent = os.getenv("SEC_USER_AGENT", "").strip()
        if not user_agent:
            raise ValueError("SEC_USER_AGENT is missing or empty in .env")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.ticker = ticker.upper()
        self.peers = [p.upper() for p in peers]
        self.price = None
        self.filed_override = filed
        if filed:
            filing_time(filed)
        self.price_source = "not available"
        self.market_evidence = {}
        self.run_started_at = datetime.now().astimezone()
        self.run_timestamp = self.run_started_at.isoformat(timespec="seconds")
        self.company_tickers: dict[str, dict[str, Any]] = {}
        self.cik = ""
        self.company = ""
        self.submissions: dict[str, Any] = {}
        self.filings: dict[str, Filing] = {}
        self.facts: dict[str, Any] = {}
        self.peer_results: dict[str, Any] = {}
        self.computed_metrics: dict[str, Any] = {}
        self.quarter_results: dict[str, Any] = {}
        self.company_facts: dict[str, Any] = {}
        self.report_period = ""
        self.annual_problem = ""  # why no annual fact is stated; "" when they are
        self.output_dir: Path | None = None

    def get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=45)
        response.raise_for_status()
        return response

    def resolve_ticker(self, ticker: str) -> tuple[str, str]:
        if not self.company_tickers:
            data = self.get(COMPANY_TICKERS_URL).json()
            self.company_tickers = {str(row["ticker"]).upper(): {"cik": str(row["cik_str"]).zfill(10), "name": row["title"]} for row in data.values()}
        result = self.company_tickers.get(ticker.upper())
        if not result:
            raise ValueError(f"Ticker {ticker} was not found in SEC company_tickers.json")
        return result["cik"], result["name"]

    def get_submissions(self, cik: str) -> dict[str, Any]:
        data = self.get(f"{DATA_BASE}/submissions/CIK{cik}.json").json()
        recent = data.get("filings", {}).get("recent", {})
        records = [{k: recent[k][i] for k in recent} for i in range(len(recent.get("form", [])))]
        for old in data.get("filings", {}).get("files", []):
            older = self.get(f"{DATA_BASE}/submissions/{old['name']}").json()
            block = older.get("filings", older)
            rec = block.get("recent", block)
            records.extend({k: rec[k][i] for k in rec} for i in range(len(rec.get("form", []))))
        data["_records"] = records
        return data

    @staticmethod
    def archive_root(cik: str, accession: str) -> str:
        return f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"

    def index_info(self, cik: str, accession: str) -> tuple[str, list[dict[str, str]]]:
        url = f"{self.archive_root(cik, accession)}/{accession}-index.html"
        soup = BeautifulSoup(self.get(url).content, "html.parser")
        text = soup.get_text(" ", strip=True)
        match = re.search(r"Accepted\s*:?\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", text, re.I)
        accepted = match.group(1) if match else "Not shown on index page"
        files: list[dict[str, str]] = []
        for row in soup.select("table tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            link = cells[2].find("a", href=True)
            if not link:
                continue
            files.append({"name": link.get_text(" ", strip=True), "href": link["href"], "description": cells[3].get_text(" ", strip=True) if len(cells) > 3 else ""})
        return accepted, files

    def step1(self) -> None:
        print("Step 1/7: Resolve ticker to CIK.", flush=True)
        self.cik, self.company = self.resolve_ticker(self.ticker)
        self.create_output_dir()
        print(f"  {self.ticker} resolves to CIK {self.cik} ({self.company}).")

    def create_output_dir(self, company: str | None = None) -> Path:
        company = company or self.company
        root = Path(__file__).with_name("equity_research_output")
        self.output_dir = create_run(root, company, self.run_started_at, "report")
        return self.output_dir

    def step2(self) -> None:
        print("Step 2/7: Find latest 10-K, 10-Q, and qualifying earnings 8-K.", flush=True)
        if not self.cik:
            self.cik, self.company = self.resolve_ticker(self.ticker)
        self.submissions = self.get_submissions(self.cik)
        # Newest first, by the filing date. Until 2026-11-22 this sort named a key the rows do not have ("filed"),
        # so the order was only the order in which EDGAR returned them.
        records = sorted(self.submissions["_records"], key=lambda x: x.get("filingDate", ""), reverse=True)
        chosen: dict[str, Filing] = {}
        for row in records:
            form = row.get("form", "")
            if form not in {"10-K", "10-Q", "8-K"} or form in chosen:
                continue
            accession = row["accessionNumber"]
            root = self.archive_root(self.cik, accession)
            primary = row.get("primaryDocument", "")
            doc_url = f"{root}/{primary}" if primary else ""
            if form == "8-K":
                # The earnings 8-K is the newest 8-K with Item 2.02. EDGAR lists each 8-K's items; the document is
                # read only when that list is empty.
                items = [item.strip() for item in str(row.get("items") or "").split(",") if item.strip()]
                if items:
                    earnings = "2.02" in items
                else:
                    earnings = bool(doc_url) and bool(re.search(r"Item\s*2\.02\b", BeautifulSoup(self.get(doc_url).content, "html.parser").get_text(" ", strip=True), re.I))
                if not earnings:
                    continue
            accepted, files = self.index_info(self.cik, accession)
            filing = Filing(form, accession, row.get("filingDate", ""), primary, accepted, f"{root}/{accession}-index.html", doc_url,
                            report_date=row.get("reportDate", ""))
            if form == "8-K":
                # The release is an Exhibit 99 of this 8-K, found by what it holds (desk_rules.release_among): 99.1
                # for most filers, 99 or 99.2 for some. An 8-K with no Exhibit 99 stops the run with its accession.
                # The desk never goes back to an older 8-K: that is last quarter's release, with last quarter's
                # Accepted time, and until 2026-11-22 the desk took it without a word.
                candidates = [(label, f["name"]) for f in files for label in [exhibit_99_label(f["description"])]
                              if label and f["name"].lower().endswith((".htm", ".html", ".txt"))]
                if not candidates:
                    raise RuntimeError(f"The earnings 8-K {accession} has no Exhibit 99 that the desk can read, so there is no release to read. Choose another company.")

                def text_of(name: str, root: str = root) -> str | None:
                    try:
                        return self.html_to_text(self.get(f"{root}/{name}").content)
                    except (requests.RequestException, ValueError):
                        return None
                filing.release_label, filing.release_document = release_among(candidates, text_of)
                filing.release_url = f"{root}/{filing.release_document}"
            chosen[form] = filing
        missing = {f for f in ("10-K", "10-Q", "8-K") if f not in chosen}
        if missing:
            raise RuntimeError(f"Could not find required filings: {', '.join(sorted(missing))}")
        self.filings = chosen
        accepted = chosen["8-K"].accepted
        effective = self.filed_override or accepted.replace(" ", "T")
        try:
            effective = filing_time(effective).isoformat()
        except ValueError:
            effective = NOT_AVAILABLE
        self.market_evidence = {"edgar_accepted": accepted, "edgar_index_url": chosen["8-K"].index_url,
                                "earnings_accession": chosen["8-K"].accession,
                                "filed_override": self.filed_override, "effective_filed_eastern": effective}
        self.ensure_output()
        (self.output_dir / "filing_time.json").write_text(json.dumps(self.market_evidence, indent=2) + "\n", encoding="utf-8")
        print("  Latest qualifying filings (accession | EDGAR Accepted time):")
        for form in ("10-K", "10-Q", "8-K"):
            f = chosen[form]
            print(f"  {form} | {f.accession} | {f.accepted} | filed {f.filed}")

    @staticmethod
    def html_to_text(content: bytes) -> str:
        soup = BeautifulSoup(content, "html.parser")
        for node in soup(["script", "style", "ix:header"]):
            node.decompose()
        return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())

    def ensure_output(self) -> None:
        if self.output_dir is None:
            if not self.company:
                self.cik, self.company = self.resolve_ticker(self.ticker)
            self.create_output_dir()

    def step3(self) -> None:
        print("Step 3/7: Download filings, convert to plain text, and save them.", flush=True)
        if not self.filings:
            self.step2()
        self.ensure_output()
        names = {"10-K": "10-K.txt", "10-Q": "10-Q.txt", "8-K": "earnings_release_Ex99-1.txt"}
        for form, filing in self.filings.items():
            url = filing.release_url if form == "8-K" else filing.document_url
            txt = self.html_to_text(self.get(url).content)
            path = self.output_dir / names[form]
            path.write_text(txt, encoding="utf-8")
            print(f"  Saved {form}: {path}")
        print(f"  Downloaded and converted 3 filing documents to plain text in {self.output_dir}.")

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return self.get(f"{DATA_BASE}/api/xbrl/companyfacts/CIK{cik}.json").json()

    @staticmethod
    def fact_rows(facts: dict[str, Any], tag: str, unit: str, kind: str) -> list[dict[str, Any]]:
        concept = facts.get("facts", {}).get("us-gaap", {}).get(tag)
        if not concept:
            return []
        rows = concept.get("units", {}).get(unit, [])
        out = []
        for row in rows:
            if row.get("form") != "10-K" or not row.get("fy"):
                continue
            # Company Facts normally exposes standard, entity-wide facts only.
            # Keep this guard for payloads that include dimensional metadata.
            if row.get("segment") or row.get("dimensions"):
                continue
            start = row.get("start")
            # Keep full-year 10-K durations only. This excludes quarterly and
            # year-to-date contexts that can share the same fiscal-year end.
            if kind == "duration" and (not start or not (350 <= (datetime.fromisoformat(row["end"]) - datetime.fromisoformat(start)).days <= 380)):
                continue
            out.append(row)
        return out

    def select_fact(self, facts: dict[str, Any], metric: str) -> tuple[str | None, list[dict[str, Any]]]:
        spec = CONCEPTS[metric]
        candidates = []
        for tag in spec["tags"]:
            rows = self.fact_rows(facts, tag, spec["unit"], spec["kind"])
            if rows:
                candidates.append((max(r["end"] for r in rows), tag, rows))
        if not candidates:
            return None, []
        _, tag, rows = max(candidates, key=lambda x: (x[0], -spec["tags"].index(x[1])))
        return tag, rows

    def get_fy_fact(self, rows: list[dict[str, Any]], target_end: str, accession: str | None = None) -> dict[str, Any] | None:
        """The fact of the fiscal year that ends on target_end. With accession, the year before it instead, as that
        same filing states it.

        The audit checklist computes growth "from the two years in the same filing": a 10-K carries last year's
        figure as its comparative column, restated when the filer restated it, and last year's own 10-K holds the
        figure as first reported. Until 2026-11-22 the prior value came from last year's 10-K. It is now the row of
        the same accession whose period ended a year earlier, 350 to 380 days (a 52- or 53-week year); without such
        a row no prior value is stated.
        """
        if not rows:
            return None
        if accession is None:
            # Require the exact revenue period end so every current metric
            # belongs to the same fiscal year-end.
            matches = [r for r in rows if r.get("end") == target_end]
        else:
            target_date = datetime.fromisoformat(target_end).date()
            matches = [r for r in rows if r.get("accn") == accession and r.get("end", "") < target_end
                       and 350 <= (target_date - datetime.fromisoformat(r["end"]).date()).days <= 380]
        if not matches:
            return None
        return max(matches, key=lambda r: (r.get("end", ""), r.get("filed", "")))

    def fact_pair(self, rows: list[dict[str, Any]], target_end: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """This year's fact and, from the same filing, last year's."""
        current = self.get_fy_fact(rows, target_end)
        return current, self.get_fy_fact(rows, target_end, accession=current.get("accn")) if current else None

    def compile_facts(self, facts: dict[str, Any], ten_k_year_end: str = "") -> tuple[dict[str, Any], str, int]:
        """The annual facts of one company, its fiscal-year end and its fiscal year.

        ten_k_year_end is the year end of the 10-K the desk read (its reportDate), for the company the report is
        about. EDGAR's facts file can lag a new 10-K, and a filer can move its revenue to a tag the desk does not
        read; then the newest revenue is another year's. In both cases no annual fact is stated, each one says why
        (desk_rules.annual_problem), and the run goes on: a report with missing claims is better than one with
        another year's numbers. The base desk has had this rule since 2026-11-12; the group desk got it on 2026-11-22.
        """
        _, rev_rows = self.select_fact(facts, "revenue")
        rev_latest = max(rev_rows, key=lambda r: (r["end"], r.get("filed", ""))) if rev_rows else None
        problem = annual_problem(rev_latest["end"] if rev_latest else None, ten_k_year_end)
        if problem:
            empty = {"tag": None, "period_end": None, "fy": None, "filing": None, "value": None,
                     "prior_period_end": None, "prior_filing": None, "prior_value": None, "why": problem}
            return {metric: {**empty, **({"label": spec["label"]} if spec.get("label") else {})} for metric, spec in CONCEPTS.items()}, ten_k_year_end, 0
        target_end, target_fy = rev_latest["end"], int(rev_latest["fy"])
        output: dict[str, Any] = {}
        for metric, spec in CONCEPTS.items():
            tag, rows = self.select_fact(facts, metric)
            current, prior = self.fact_pair(rows, target_end)
            output[metric] = {"tag": tag, "period_end": current.get("end") if current else target_end, "fy": target_fy, "filing": current.get("accn") if current else None, "value": current.get("val") if current else None, "prior_period_end": prior.get("end") if prior else None, "prior_filing": prior.get("accn") if prior else None, "prior_value": prior.get("val") if prior else None}
            if spec.get("label"):
                output[metric]["label"] = spec["label"]
        output["long_term_debt"], output["current_portion_of_long_term_debt"] = self.debt_pair(
            facts, target_end, target_fy, output["long_term_debt"], output["current_portion_of_long_term_debt"])
        parent = output["net_income_attributable_to_parent"]
        if parent["value"] is None:
            consolidated = output["net_income"]
            nci = output["noncontrolling_interest_income"]
            if consolidated["value"] is not None and nci["value"] is not None:
                parent["value"] = consolidated["value"] - nci["value"]
                parent["tag"] = f"computed from {consolidated['tag']} less {nci['tag']}"
                parent["period_end"] = consolidated["period_end"]
                accessions = list(dict.fromkeys(x for x in (consolidated["filing"], nci["filing"]) if x))
                parent["filing"] = ", ".join(accessions) or None
                if consolidated["prior_value"] is not None and nci["prior_value"] is not None and consolidated["prior_period_end"] == nci["prior_period_end"]:
                    parent["prior_value"] = consolidated["prior_value"] - nci["prior_value"]
                    parent["prior_period_end"] = consolidated["prior_period_end"]
                    prior_accessions = list(dict.fromkeys(x for x in (consolidated["prior_filing"], nci["prior_filing"]) if x))
                    parent["prior_filing"] = ", ".join(prior_accessions) or None
                    parent["tag"] += f"; prior computed from {consolidated['tag']} less {nci['tag']}"
            elif consolidated["value"] is not None:
                # No noncontrolling-interest income fact was reported, so use
                # consolidated net income as parent-attributable net income.
                parent.update({"value": consolidated["value"], "tag": f"{consolidated['tag']} (no NCI income fact reported)", "period_end": consolidated["period_end"], "filing": consolidated["filing"], "prior_value": consolidated["prior_value"], "prior_period_end": consolidated["prior_period_end"], "prior_filing": consolidated["prior_filing"]})
        return output, target_end, target_fy

    def debt_pair(self, facts: dict[str, Any], target_end: str, target_fy: int,
                  noncurrent_default: dict[str, Any], current_default: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """The balance sheet's two lines of long-term debt, read as one pair from the same filing (DEBT_PAIRS).

        When no pair is filed, the first pair's noncurrent line stands alone only if the total tag holds the same
        amount: then there is no current portion. A current line tagged DEBT_CURRENT_LINE pairs with that noncurrent
        line only if the two add up to the total tag, all three from the same filing at the same date. Otherwise the
        defaults are kept, and debt to equity is not stated. A missing current line is never read as zero.
        """
        def entry(tag: str, metric: str) -> dict[str, Any]:
            rows = self.fact_rows(facts, tag, "USD", "instant")
            current, prior = self.fact_pair(rows, target_end)
            return {"tag": tag if rows else None, "period_end": current.get("end") if current else target_end, "fy": target_fy,
                    "filing": current.get("accn") if current else None, "value": current.get("val") if current else None,
                    "prior_period_end": prior.get("end") if prior else None, "prior_filing": prior.get("accn") if prior else None,
                    "prior_value": prior.get("val") if prior else None, "label": CONCEPTS[metric]["label"]}
        for noncurrent, current in DEBT_PAIRS:
            pair = entry(noncurrent, "long_term_debt"), entry(current, "current_portion_of_long_term_debt")
            if pair[0]["value"] is not None and pair[1]["value"] is not None and pair[0]["filing"] == pair[1]["filing"]:
                pair[0]["debt_basis"] = "pair"
                return pair
        alone, total = entry(DEBT_PAIRS[0][0], "long_term_debt"), entry(DEBT_TOTAL, "long_term_debt")
        if alone["value"] is not None and total["value"] == alone["value"] and total["filing"] == alone["filing"]:
            alone["debt_basis"] = "no current portion"
            alone["note"] = f"no current portion: {DEBT_TOTAL} holds the same amount as {DEBT_PAIRS[0][0]}, and no current line is filed"
            return alone, {**current_default, "tag": None, "value": None, "filing": None}
        line = entry(DEBT_CURRENT_LINE, "current_portion_of_long_term_debt")
        checked = (alone, line, total)
        if (all(item["value"] is not None for item in checked) and len({item["filing"] for item in checked}) == 1
                and len({item["period_end"] for item in checked}) == 1 and alone["value"] + line["value"] == total["value"]):
            alone["debt_basis"] = "pair"
            alone["note"] = (f"the current line is {DEBT_CURRENT_LINE}, which can include short-term borrowings; it is read as the current "
                             f"portion because {DEBT_TOTAL} in the same filing equals {DEBT_PAIRS[0][0]} plus {DEBT_CURRENT_LINE}")
            return alone, line
        # No pair and no proof of a zero current portion: the lines stay as facts, and debt to equity is not stated.
        return noncurrent_default, current_default

    @staticmethod
    def number(value: Any) -> str:
        return "n/a" if value is None else f"{value:,.4f}" if isinstance(value, float) else f"{value:,.2f}"

    @staticmethod
    def fact_source(item: dict[str, Any], prior: bool = False) -> str:
        tag = item.get("tag")
        period_end = item.get("prior_period_end" if prior else "period_end")
        accession = item.get("prior_filing" if prior else "filing")
        if not tag or not period_end or not accession:
            return "source unavailable"
        return f"XBRL tag {tag}, period end {period_end}, filing {accession}"

    @classmethod
    def has_fact_source(cls, item: dict[str, Any], prior: bool = False) -> bool:
        return cls.fact_source(item, prior) != "source unavailable"

    @classmethod
    def input_value(cls, item: dict[str, Any], prior: bool = False) -> str:
        value_key = "prior_value" if prior else "value"
        value = item.get(value_key)
        if value is None or not cls.has_fact_source(item, prior):
            return "n/a"
        return cls.number(value)

    def own_facts(self, facts: dict[str, Any]) -> dict[str, Any]:
        """The annual facts of the company the report is about, checked against the 10-K the desk read."""
        ten_k = self.filings.get("10-K") if self.filings else None
        self.facts, self.report_period, _ = self.compile_facts(facts, getattr(ten_k, "report_date", "") or "")
        self.annual_problem = next((item["why"] for item in self.facts.values() if item.get("why")), "")
        if self.annual_problem:
            print(f"  The annual facts are not stated: {self.annual_problem}")
        return self.facts

    def print_facts(self, facts: dict[str, Any], ticker: str, peer: bool = False) -> dict[str, Any]:
        if peer:
            result, end, fy = self.compile_facts(facts)
        else:
            result = self.own_facts(facts)
            end, fy = self.report_period, next((item["fy"] for item in result.values() if item.get("fy")), 0)
        print(f"  {ticker}: fiscal year {fy}, period end {end}")
        for metric, item in result.items():
            print(f"    {metric}: {self.number(item['value'])} (prior: {self.number(item['prior_value'])}) | tag={item['tag']} | period end={item['period_end']} | filing={item['filing']}")
        return result

    def step4(self) -> None:
        print("Step 4/7: Fetch and print annual XBRL facts and prior-year values.", flush=True)
        if not self.cik:
            self.cik, self.company = self.resolve_ticker(self.ticker)
        if not self.submissions:
            self.submissions = self.get(f"{DATA_BASE}/submissions/CIK{self.cik}.json").json()
        facts = self.get_company_facts(self.cik)
        self.company_facts = facts
        self.print_facts(facts, self.ticker)

    def quarterly_capex(self) -> dict[str, Any]:
        filing = self.filings.get("10-Q")
        if not filing:
            return {"value": None, "reason": "No selected 10-Q is available.", "inputs": [], "sources": []}
        if not getattr(self, "company_facts", None):
            self.company_facts = self.get_company_facts(self.cik)
        return quarterly_capital_spending(self.company_facts, filing.accession,
                                         CONCEPTS["additions_to_property_and_equipment"]["tags"])

    def is_financial_institution(self) -> bool:
        if not self.submissions:
            if not self.cik:
                self.cik, self.company = self.resolve_ticker(self.ticker)
            self.submissions = self.get(f"{DATA_BASE}/submissions/CIK{self.cik}.json").json()
        description = self.submissions.get("sicDescription", "")
        return bool(re.search(r"bank|broker|dealer|securities|investment management", description, re.I))

    def step5(self) -> None:
        print("Step 5/7: Calculate financial ratios and free cash flow.", flush=True)
        if not self.facts:
            self.own_facts(self.get_company_facts(self.cik or self.resolve_ticker(self.ticker)[0]))
        if not self.filings:
            self.step2()
        effective = self.market_evidence.get("effective_filed_eastern", NOT_AVAILABLE)
        selected_close = NOT_AVAILABLE
        if effective != NOT_AVAILABLE:
            local_time = datetime.fromisoformat(effective).strftime('%Y-%m-%dT%H:%M:%S')
            selected_close = last_close_before(self.ticker, local_time)
        self.price = selected_close["close"] if isinstance(selected_close, dict) else None
        self.price_source = (f"{selected_close['source']}; official close at {selected_close['close_time']}; strictly before filing {effective}"
                             if isinstance(selected_close, dict) else NOT_AVAILABLE)
        self.market_evidence["selected_close"] = selected_close
        self.market_evidence["price_source"] = self.price_source
        self.ensure_output()
        (self.output_dir / "market_price.json").write_text(json.dumps(self.market_evidence, indent=2) + "\n", encoding="utf-8")
        f = self.facts
        rev, prev_rev = f["revenue"]["value"], f["revenue"]["prior_value"]
        op = f["operating_income"]["value"]
        parent_net = f["net_income_attributable_to_parent"]["value"]
        eq = f["stockholders_equity"]["value"]
        prev_eq = f["stockholders_equity"]["prior_value"]
        cfo, capex = f["cash_from_operations"]["value"], f["additions_to_property_and_equipment"]["value"]
        def ratio(a: Any, b: Any) -> float | None:
            return a / b if a is not None and b not in (None, 0) else None
        revenue_sourced = self.has_fact_source(f["revenue"])
        prior_revenue_sourced = self.has_fact_source(f["revenue"], prior=True)
        op_sourced = self.has_fact_source(f["operating_income"])
        parent_net_sourced = self.has_fact_source(f["net_income_attributable_to_parent"])
        equity_sourced = self.has_fact_source(f["stockholders_equity"])
        prior_equity_sourced = self.has_fact_source(f["stockholders_equity"], prior=True)
        debt_item = f["long_term_debt"]
        current_debt_item = f["current_portion_of_long_term_debt"]
        # Claim 7: long-term debt with its current portion, the balance sheet's two lines as one pair (compile_facts).
        # Short-term borrowings are not part of that definition, so they are never added (on 2026-11-20 they would
        # have moved Walmart's ratio from 0.383 to 0.449).
        debt_components: list[dict[str, Any]] = []
        if debt_item.get("debt_basis") == "pair" and self.has_fact_source(debt_item) and self.has_fact_source(current_debt_item):
            debt_components = [debt_item, current_debt_item]
        elif debt_item.get("debt_basis") == "no current portion" and self.has_fact_source(debt_item):
            debt_components = [debt_item]
        long_term_base_complete = bool(debt_components)
        debt_inputs_sourced = bool(debt_components) and all(self.has_fact_source(item) for item in debt_components)
        debt_definition = ("long-term debt with its current portion, the balance sheet's noncurrent and current lines filed as one "
                           "pair in the same 10-K, divided by year-end stockholders' equity; short-term borrowings are not included")
        if debt_item.get("debt_basis") in ("no current portion", "pair") and debt_item.get("note"):
            debt_definition += "; " + debt_item["note"]
        cfo_sourced = self.has_fact_source(f["cash_from_operations"])
        capex_sourced = self.has_fact_source(f["additions_to_property_and_equipment"])
        eps_sourced = self.has_fact_source(f["diluted_eps"])
        growth = ratio(rev - prev_rev, prev_rev) if revenue_sourced and prior_revenue_sourced and rev is not None and prev_rev not in (None, 0) else None
        op_margin = ratio(op, rev) if op_sourced and revenue_sourced else None
        avg_equity = (eq + prev_eq) / 2 if eq is not None and prev_eq is not None else None
        roe = ratio(parent_net, avg_equity) if parent_net_sourced and equity_sourced and prior_equity_sourced else None
        total_debt = sum(item["value"] for item in debt_components) if debt_inputs_sourced and all(item.get("value") is not None for item in debt_components) else None
        debt_equity = ratio(total_debt, eq) if debt_inputs_sourced and equity_sourced else None
        fcf = cfo - capex if cfo_sourced and capex_sourced and cfo is not None and capex is not None else None
        diluted_eps = f["diluted_eps"]["value"]
        pe = ratio(self.price, diluted_eps) if self.price is not None and eps_sourced else None
        self.computed_metrics = {
            "revenue_growth": {"formula": f"({rev} - {prev_rev}) / {prev_rev}", "value": growth * 100 if growth is not None else None, "unit": "%", "sources": [self.fact_source(f["revenue"]), self.fact_source(f["revenue"], prior=True)]},
            "operating_margin": {"formula": f"{op} / {rev}", "value": op_margin * 100 if op_margin is not None else None, "unit": "%", "sources": [self.fact_source(f["operating_income"]), self.fact_source(f["revenue"])]},
            "return_on_average_equity": {"formula": f"{parent_net} / (({eq} + {prev_eq}) / 2)", "value": roe * 100 if roe is not None else None, "unit": "%", "method": "reported net income fact divided by the simple average of current and prior year-end stockholders' equity", "sources": [self.fact_source(f["net_income_attributable_to_parent"]), self.fact_source(f["stockholders_equity"]), self.fact_source(f["stockholders_equity"], prior=True)]},
            "debt_to_equity": {"formula": f"({' + '.join(str(item.get('value')) for item in debt_components) or 'n/a'}) / {eq}", "value": debt_equity, "unit": "ratio", "definition": debt_definition, "sources": [self.fact_source(item) for item in debt_components] + [self.fact_source(f["stockholders_equity"])]},
            # The amount the analysts call long-term debt: both balance-sheet lines, never one line or the total tag.
            "long_term_debt_with_current_portion": {"formula": " + ".join(str(item.get("value")) for item in debt_components) or "n/a", "value": total_debt, "unit": "USD", "definition": "long-term debt with its current portion: the balance sheet's noncurrent and current lines, one pair in the same 10-K", "sources": [self.fact_source(item) for item in debt_components]},
            "free_cash_flow": {"formula": f"{cfo} - {capex}", "value": fcf, "unit": "USD", "sources": [self.fact_source(f["cash_from_operations"]), self.fact_source(f["additions_to_property_and_equipment"])]},
            "pe": {"formula": f"{self.price} / {diluted_eps}", "value": pe, "unit": "ratio", "price_source": self.price_source, "sources": [self.price_source, self.fact_source(f["diluted_eps"])]},
        }
        print("  Calculator (amounts in USD; ratios shown as percentages where stated).")
        print(f"  Computed revenue growth = ({self.input_value(f['revenue'])} - {self.input_value(f['revenue'], prior=True)}) / {self.input_value(f['revenue'], prior=True)} = {self.number(growth * 100 if growth is not None else None)}% | inputs: revenue [{self.fact_source(f['revenue'])}]; prior revenue [{self.fact_source(f['revenue'], prior=True)}]")
        if op_margin is not None:
            print(f"  Computed operating margin = {self.input_value(f['operating_income'])} / {self.input_value(f['revenue'])} = {self.number(op_margin * 100)}% | inputs: operating income [{self.fact_source(f['operating_income'])}]; revenue [{self.fact_source(f['revenue'])}]")
        elif self.is_financial_institution():
            print("  Computed operating margin = n/a (not applicable to this financial institution; its income statement has no operating income line). No pre-tax income was substituted.")
        else:
            print(f"  Computed operating margin = n/a | inputs: operating income [{self.fact_source(f['operating_income'])}]; revenue [{self.fact_source(f['revenue'])}]")
        print(f"  Computed ROE (program method: reported net income fact / simple average of current and prior year-end stockholders' equity; equity may include preferred stock, so this may differ from reported average common ROE) = {self.input_value(f['net_income_attributable_to_parent'])} / (({self.input_value(f['stockholders_equity'])} + {self.input_value(f['stockholders_equity'], prior=True)}) / 2) = {self.number(roe * 100 if roe is not None else None)}% | inputs: reported net income fact [{self.fact_source(f['net_income_attributable_to_parent'])}]; stockholders' equity [{self.fact_source(f['stockholders_equity'])}]; prior stockholders' equity [{self.fact_source(f['stockholders_equity'], prior=True)}]")
        debt_formula = " + ".join(self.input_value(item) for item in debt_components) if debt_components else "n/a"
        debt_sources = "; ".join(self.fact_source(item) for item in debt_components) if debt_components else "source unavailable"
        if not long_term_base_complete:
            print(f"  Computed debt to equity = n/a (long-term debt with its current portion is not established: no balance-sheet pair of debt lines, and no proof of a zero current portion) | inputs: long-term debt [{self.fact_source(debt_item)}]; current portion [{self.fact_source(current_debt_item)}]")
        else:
            print(f"  Computed debt to equity = ({debt_formula}) / {self.input_value(f['stockholders_equity'])} = {self.number(debt_equity)} | inputs: borrowings [{debt_sources}]; equity [{self.fact_source(f['stockholders_equity'])}]; definition: {debt_definition}")
        print(f"  Computed free cash flow = {self.input_value(f['cash_from_operations'])} - {self.input_value(f['additions_to_property_and_equipment'])} = {self.number(fcf)} | inputs: cash from operations [{self.fact_source(f['cash_from_operations'])}]; additions to property and equipment [{self.fact_source(f['additions_to_property_and_equipment'])}]")
        price_input = self.number(self.price) if self.price is not None else "n/a"
        print(f"  Computed P/E = {price_input} / {self.input_value(f['diluted_eps'])} = {self.number(pe)} | inputs: price [{self.price_source}]; diluted EPS [{self.fact_source(f['diluted_eps'])}]")

    def step6(self) -> None:
        print("Step 6/7: Extract quarterly revenue and diluted EPS from the earnings release.", flush=True)
        if "8-K" not in self.filings:
            self.step2()
        response = self.get(self.filings["8-K"].release_url)
        soup = BeautifulSoup(response.content, "html.parser")
        release = self.html_to_text(response.content)
        lines = release.splitlines()
        # The quarter's three figures come from one table of the release: first a table whose columns are quarter
        # tokens, then one with dated or year columns. A table under a non-GAAP, reconciliation or outlook heading is
        # not the income statement. A table a reader cannot place in columns is not read, and it never stops the run:
        # a missing claim costs nothing, a figure from the wrong column fails the audit.
        tables = [(table, [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])] for row in table.find_all("tr")])
                  for table in soup.find_all("table")]
        found = None
        quarter_unit = "USD as shown"
        for reader in (read_quarter_token_table, read_quarter_table):
            for table, table_rows in tables:
                if NOT_THE_STATEMENT.search(table_heading(table)):
                    continue
                try:
                    found = reader(table_rows)
                except (ValueError, IndexError, TypeError):
                    found = None
                if found:
                    quarter_unit = table_unit(table, table_rows)
                    break
            if found:
                break

        def money(printed: str) -> str:
            return "-$" + printed[1:] if printed.startswith("-") else "$" + printed

        table_revenue_hit = table_prior_revenue_hit = table_eps_hit = None
        revenue_label = r"total\s+revenues?"
        if found:
            table_revenue_hit = f"Reported revenue, {found['revenue_label']} ({found['span']} {found['latest']}, {quarter_unit}): {found['revenue']}"
            if found["prior_revenue"]:
                table_prior_revenue_hit = f"Prior-year reported revenue, {found['revenue_label']} ({found['span']} {found['prior']}, {quarter_unit}): {found['prior_revenue']}"
            table_eps_hit = f"GAAP diluted EPS, {found['eps_label']} ({found['span']} {found['latest']}): {money(found['eps'])}"
            revenue_label = re.escape(found["revenue_label"])

        revenue_hits = [] if table_revenue_hit else [line for line in lines if not re.search(r"fiscal year|annual|forecast|guidance|expect|project", line, re.I) and (re.search(r"quarter(?:ly)?\s+(?:net\s+)?revenue", line, re.I) or re.search(r"(?:net\s+)?revenues?\s+of\s+\$\s*[\d,.]+\s*(?:billion|million)", line, re.I)) and re.search(r"\$\s*[\d,.]+", line)]
        eps_hits = [] if table_eps_hit else [line for line in lines if not re.search(r"forecast|guidance|expect|project", line, re.I) and (re.search(r"diluted", line, re.I) and re.search(r"earnings\s+per\s+share|per\s+diluted\s+share|per-share", line, re.I) or re.search(r"\bEPS\s+of\s+\$", line, re.I)) and re.search(r"\$\s*[\d,.]+|\b\d+\.\d+\b", line)]
        hits = ([table_revenue_hit] if table_revenue_hit else revenue_hits) + ([table_eps_hit] if table_eps_hit else eps_hits)
        if table_prior_revenue_hit:
            hits.append(table_prior_revenue_hit)
        hits = list(dict.fromkeys(hits))

        def number(printed: str | None) -> float | None:
            return float(printed.replace(",", "")) if printed else None

        def exact_quote(printed: str | None, label_pattern: str | None = None) -> str:
            """The release lines that hold a figure as the table prints it, from its label down to the amount."""
            if not printed:
                return "source unavailable"
            token = printed.lstrip("-")
            normalized = token.replace(",", "")
            holding = [i for i, line in enumerate(lines) if re.sub(r"[^\d.]", "", line) == normalized]
            if not holding:
                holding = [i for i, line in enumerate(lines) if re.search(rf"(?<![\d.])\$?{re.escape(token)}(?![\d.])", line)]
            if not holding:
                return "source unavailable"

            def label_above(index: int) -> int | None:
                return next((i for i in range(index - 1, max(-1, index - 6), -1) if re.search(label_pattern, lines[i], re.I)), None) if label_pattern else None
            # The first line with the value under its own label: Walmart's basic and diluted EPS were both 0.62 on
            # 2026-11-20, and the first 0.62 in the release was the basic one.
            value_index = next((i for i in holding if label_above(i) is not None), holding[0])
            start_index = label_above(value_index)
            start_index = value_index if start_index is None else start_index
            quoted = "\n".join(lines[start_index:value_index + 1])
            return f"{self.quarter_results.get('release_file', 'earnings_release_Ex99-1.txt')}:L{start_index + 1}-L{value_index + 1}; quote: {json.dumps(quoted, ensure_ascii=False)}"

        current_quarter_revenue = number(found["revenue"]) if found else None
        prior_quarter_revenue = number(found["prior_revenue"]) if found else None
        revenue_source = exact_quote(found["revenue"] if found else None, revenue_label)
        prior_revenue_source = exact_quote(found["prior_revenue"] if found else None, revenue_label)
        quarter_revenue_growth = None
        # Growth is stated on a positive base, from two lines the desk can show. Otherwise it is left out.
        if (current_quarter_revenue is not None and prior_quarter_revenue is not None and prior_quarter_revenue > 0
                and "source unavailable" not in (revenue_source, prior_revenue_source)):
            quarter_revenue_growth = (current_quarter_revenue - prior_quarter_revenue) / prior_quarter_revenue * 100
            self.computed_metrics["quarter_revenue_growth"] = {
                "formula": f"({current_quarter_revenue} - {prior_quarter_revenue}) / {prior_quarter_revenue} * 100",
                "value": quarter_revenue_growth,
                "unit": "%",
                "sources": [revenue_source, prior_revenue_source],
            }
            print(f"  Computed quarter total-revenue growth = ({self.number(current_quarter_revenue)} - {self.number(prior_quarter_revenue)}) / {self.number(prior_quarter_revenue)} * 100 = {self.number(quarter_revenue_growth)}% | inputs: current [{revenue_source}]; prior-year [{prior_revenue_source}]")

        # The quarter's figures come from a table a reader placed in columns, or not at all. Until 2026-11-22 a
        # fallback stated the first amount on the lines after "Total revenue" or "Diluted net income per common
        # share": last year's figure when the older column stands first, the nine months' when that group does.
        eps_printed = found["eps"] if found else None
        print("  Release lines that state quarterly total revenue and diluted EPS:")
        for line in hits:
            print(f"  {line}")
        adjusted_eps_lines = [line for line in lines if len(line) <= 150 and ((re.search(r"reported\s+EPS\s+from\s+\$?[\d.]+\s+to\s+\$?[\d.]+", line, re.I) and re.search(r"excluding|non-GAAP|adjusted", line, re.I)) or re.search(r"GAAP.*\$[\d.]+.*\$[\d.]+.*adjusted", line, re.I))]
        diluted_eps_value = number(eps_printed)
        self.quarter_results = {
            "results": hits,
            "adjusted_eps_flags": adjusted_eps_lines,
            "release_file": "earnings_release_Ex99-1.txt",
            "filing_accession": self.filings["8-K"].accession,
            "total_revenue": current_quarter_revenue,
            # The figure as the release table prints it, and that table's unit: the claims table prints these.
            "total_revenue_printed": found["revenue"] if found else None,
            "revenue_unit": quarter_unit if found else None,
            "prior_year_total_revenue": prior_quarter_revenue,
            "quarter_revenue_growth_percent": quarter_revenue_growth,
            "revenue_source": revenue_source,
            "prior_revenue_source": prior_revenue_source,
            "diluted_eps": diluted_eps_value,
            "diluted_eps_source": exact_quote(eps_printed, r"diluted|per\s+diluted\s+share|GAAP"),
            # Label this separately: the latest 10-Q can cover a different
            # quarter from the earnings release. Never label YTD cash flow QTD.
            "latest_10q_capital_spending": self.quarterly_capex(),
        }
        # Until 2026-11-22 a rule here read one company's sentence, "non-recurring benefit of $X per diluted share",
        # and saved a metric named for its fourth quarter. Nothing in the code names a company (AGENTS.md), and the
        # rule divided by the annual EPS of whatever 10-K the desk had read. It is gone; a role can still quote the line.
        for line in adjusted_eps_lines:
            print(f"  Flagged adjusted/non-GAAP figure (not used for diluted EPS): {line}")
        if not hits:
            print("  No lines matched revenue or diluted EPS terms. Review the saved release text.")

    def step7(self) -> None:
        print("Step 7/7: Fetch peer facts and calculate operating margins.", flush=True)
        if not self.facts:
            self.own_facts(self.get_company_facts(self.cik or self.resolve_ticker(self.ticker)[0]))
        print("  Operating margin uses operating income divided by revenue.")
        self.peer_results: dict[str, Any] = {}
        for peer in self.peers:
            cik, _ = self.resolve_ticker(peer)
            peer_facts = self.get_company_facts(cik)
            result, end, fy = self.compile_facts(peer_facts)
            revenue, op = result["revenue"]["value"], result["operating_income"]["value"]
            margin = op / revenue if self.has_fact_source(result["operating_income"]) and self.has_fact_source(result["revenue"]) and op is not None and revenue not in (None, 0) else None
            print(f"  {peer}: fiscal year {fy}, period end {end}")
            print(f"    Computed operating margin = {self.input_value(result['operating_income'])} / {self.input_value(result['revenue'])} = {self.number(margin * 100 if margin is not None else None)}% | inputs: operating income [{self.fact_source(result['operating_income'])}]; revenue [{self.fact_source(result['revenue'])}]")
            for metric, item in result.items():
                print(f"    {metric}: {self.number(item['value'])} (prior: {self.number(item['prior_value'])}) | tag={item['tag']} | period end={item['period_end']} | filing={item['filing']}")
            self.peer_results[peer] = {"cik": cik, "report_period": end, "facts": result, "operating_margin": margin * 100 if margin is not None else None, "operating_margin_unit": "%"}

    def save_facts(self) -> None:
        if not self.facts:
            return
        self.ensure_output()
        payload = {"ticker": self.ticker, "company": self.company, "cik": self.cik, "report_period": self.report_period, "annual_problem": getattr(self, "annual_problem", ""), "facts": self.facts, "peers": getattr(self, "peer_results", {}), "market_price": self.market_evidence}
        (self.output_dir / "facts.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the fixed-order equity research agent team.")
    parser.add_argument("ticker", nargs="?", help="Company ticker symbol")
    parser.add_argument("--peers", nargs="*", default=None, help="Peer ticker symbols")
    parser.add_argument("--price", type=float, help="Deprecated; accepted for compatibility but ignored. Uses the pre-filing official close.")
    parser.add_argument("--filed", type=lambda value: (filing_time(value), value)[1], help="Override earnings 8-K Accepted time: YYYY-MM-DDTHH:MM:SS, Eastern")
    parser.add_argument("--verify-only", metavar="RUN_PATH", help="Verify a saved run without running its data steps or analyst roles")
    return parser.parse_args()


def main() -> int:
    try:
        from equity_research_agent_team import run_cli
        return run_cli(parse_args())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
