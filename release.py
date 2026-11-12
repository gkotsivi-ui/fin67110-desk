#!/usr/bin/env python3
"""The release reader: the quarter's revenue, its growth and its diluted EPS, from an earnings release.

Claims 9, 10 and 11 of the report audit live in the earnings release, not in XBRL. This module reads them from
the release's text as step 3 saved it, with rules and no model:

  1. Find the income statement by its heading. A row outside it is not read: not an outlook table, not a
     summary, not a reconciliation.
  2. Read the statement's header: the units, the periods, and the date of each column of figures.
  3. The quarter is the column with the newest date. Last year's quarter is the column one year before it.
     A column is chosen by its date, never by its position.
  4. Read the total revenue row and the diluted EPS row at those two columns.

When a rule cannot be met, the claim is not stated and the reason is recorded. Nothing is guessed.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterator

# The heading of an income statement, in a release or in a filing.
STATEMENT = re.compile(r"statements? of (consolidated\s+|condensed\s+)*(income|operations|earnings)|income statements?", re.I)
# A line with those words that is not the GAAP statement's heading: an adjusted statement, or a note that points to one.
NOT_THE_STATEMENT = re.compile(r"non-?gaap|adjusted|reconcil|pro forma|supplement|segment|refer to", re.I)
# The heading of the table after the income statement.
NEXT_TABLE = re.compile(r"balance sheets?|financial position|cash flows?|reconcil|non-?gaap|segment (information|results)|supplement", re.I)
HEADING_LENGTH = 110  # a heading is a short line; a sentence that names a statement is longer
BLOCK_LENGTH = 150    # an income statement is shorter than this many lines

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
FULL_DATE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+((?:19|20)\d\d)\b", re.I)
BARE_YEAR = re.compile(r"(?<![\w,.$/-])((?:19|20)\d\d)(?![\w,./-])")
# A period in a header: "three months", "13 weeks", "three and nine months", "quarter", "year".
NUMBER_WORDS = {"three": 3, "six": 6, "nine": 9, "twelve": 12, "thirteen": 13, "fourteen": 14, "sixteen": 16, "seventeen": 17}
SPAN = re.compile(r"\b(three|six|nine|twelve|thirteen|fourteen|sixteen|seventeen|\d+)(?:\s+and\s+(?:three|six|nine|twelve|\d+))?\s+(months?|weeks?)\b"
                  r"|\b(quarters?)\b|\b(years?)\b", re.I)
LONGEST_QUARTER_IN_WEEKS = 17
UNITS = re.compile(r"\bin\s+(thousands|millions|billions)\b", re.I)

# The label of a total revenue row: "Revenue", "Total revenues", "Net sales", "Total net revenue". Not "Sales and
# marketing", and not one kind of revenue such as "Product revenue".
REVENUE_LABEL = re.compile(r"(total\s+)?(net\s+)?(revenues?|sales)(\s+and\s+(other\s+)?(operating\s+)?(revenues?|sales|income))?(,\s*net)?(\s*\(\w+\))?\s*:?", re.I)
AFTER_REVENUE = re.compile(r"\s*(total\s+)?(costs?|gross|operating (expenses|income|loss)|income from operations|expenses)\b", re.I)
PER_SHARE = re.compile(r"per[\s-]+(common\s+|ordinary\s+|diluted\s+)?share|\bEPS\b", re.I)
SHARE_COUNT = re.compile(r"shares used|weighted|average|number of shares|shares outstanding", re.I)
ONE_PART = re.compile(r"continuing|discontinued", re.I)
AMOUNT = re.compile(r"[-−–]?\s*\$?\s*\(?\s*\$?\s*(\d[\d,]*(?:\.\d+)?)\s*\)?")

NO_STATEMENT = "the release has no income statement with a total revenue row that the desk can read"
CLAIMS = ("revenue", "growth", "eps")


def amounts_in(line: str) -> list[tuple[str, float]]:
    """The figures of a table row after its label, each as the release prints it and as a number.
    A percentage is not a figure. "(1.2)" and "$ (1.2)" are negative."""
    found = []
    for cell in line.split(" | ")[1:]:
        text = cell.strip()
        match = AMOUNT.fullmatch(text)
        if match:
            value = float(match.group(1).replace(",", ""))
            found.append((text, -value if "(" in text or text[:1] in "-−–" else value))
    return found


def numbers_in(line: str) -> list[float]:
    """The figures of a table row after its label, as numbers."""
    return [value for _, value in amounts_in(line)]


def as_printed(text: str) -> str:
    """A figure as the release prints it, without the spaces some releases put inside it: "$ (0.04)" is "$(0.04)"."""
    return re.sub(r"\s+", "", text)


def per_share(text: str) -> str:
    """A per-share figure as the release prints it, with its dollar sign: "0.97" is "$0.97"."""
    printed = as_printed(text)
    return printed if "$" in printed else f"${printed}"


def has_income_statement(text: str) -> bool:
    """True when a short line of the text is the heading of an income statement."""
    return any(len(line) < HEADING_LENGTH and STATEMENT.search(line) for line in text.splitlines())


def is_data_row(line: str) -> bool:
    """True for a row of the statement: a label, then figures. A header line of years, such as
    "Three Months Ended June 30, | 2026 | 2025", is not a row of the statement."""
    figures = amounts_in(line)
    return (bool(figures) and bool(re.search(r"[A-Za-z]", line.split(" | ")[0]))
            and not all(BARE_YEAR.fullmatch(text.strip()) for text, _ in figures))


def statement_blocks(lines: list[str]) -> Iterator[tuple[int, int]]:
    """Each place where a short line is the heading of a GAAP income statement: the line's number, and the
    number of the line where the next table starts."""
    for start, line in enumerate(lines):
        if len(line) < HEADING_LENGTH and STATEMENT.search(line) and not NOT_THE_STATEMENT.search(line):
            limit = min(len(lines), start + BLOCK_LENGTH)
            end = next((i for i in range(start + 3, limit)
                        if len(lines[i]) < HEADING_LENGTH and (NEXT_TABLE.search(lines[i]) or STATEMENT.search(lines[i]))), limit)
            yield start, end


def revenue_row(lines: list[str], start: int, end: int) -> int | None:
    """The line of the statement's total revenue: the row "Total revenue" when the statement has one above its
    costs, else its first revenue row. None when no row has a total revenue label and two figures."""
    first = None
    for i in range(start + 1, end):
        label = lines[i].split(" | ")[0].strip()
        if REVENUE_LABEL.fullmatch(label) and len(amounts_in(lines[i])) >= 2:
            if label.lower().startswith("total"):
                return i
            first = i if first is None else first
        elif first is not None and AFTER_REVENUE.match(label):
            break
    return first


def eps_row(lines: list[str], start: int, end: int) -> tuple[int | None, str | None, str]:
    """The line of the statement's GAAP diluted EPS for the whole company, the heading above it, and, when
    there is no such line, the reason."""
    heading, parts = "", 0
    for i in range(start + 1, end):
        label = lines[i].split(" | ")[0].strip()
        figures = amounts_in(lines[i])
        if not figures:
            heading = lines[i].strip()  # the nearest line above that holds no figures
            continue
        if not re.search(r"\bdiluted\b", label, re.I):
            continue
        about = label if PER_SHARE.search(label) else f"{heading} {label}"
        if not PER_SHARE.search(about) or SHARE_COUNT.search(about):
            continue
        if not any(re.fullmatch(r"\d[\d,]*\.\d\d", re.sub(r"[^\d.,]", "", text)) for text, _ in figures):
            continue  # a per-share amount has two decimals; a count of shares does not
        if ONE_PART.search(about):
            parts += 1
            continue
        return i, (None if PER_SHARE.search(label) else heading), ""
    if parts:
        return None, None, "the income statement gives diluted EPS for continuing or discontinued operations only"
    return None, None, "the income statement has no diluted EPS row that the desk can read"


def dates_in(line: str) -> list[tuple[int, int, int]]:
    """Each date on a header line, in the line's order, as (year, month, day). A year alone is (year, 0, 0)."""
    found = [(m.start(), (int(m.group(3)), MONTHS.index(m.group(1)[:3].lower()) + 1, int(m.group(2)))) for m in FULL_DATE.finditer(line)]
    rest = FULL_DATE.sub(lambda m: " " * len(m.group(0)), line)
    found += [(m.start(), (int(m.group(1)), 0, 0)) for m in BARE_YEAR.finditer(rest)]
    return [when for _, when in sorted(found)]


def column_dates(header: list[str], count: int) -> list[tuple[int, int, int]] | None:
    """The date of each column of figures: the header line nearest the rows that holds one date for each column."""
    for line in reversed(header):
        dates = dates_in(line)
        if len(dates) == count:
            return dates
    return None


def first_period_is_a_quarter(header: list[str]) -> bool | None:
    """True when the first period the header names is a quarter: three months, 12 to 17 weeks, or "quarter".
    False when it is longer. None when the header names no period."""
    for line in header:
        named = SPAN.search(line)
        if named:
            number, unit, quarter, year = named.groups()
            if quarter:
                return True
            if year:
                return False
            count = NUMBER_WORDS.get(number.lower()) or int(number)
            return count == 3 if unit.lower().startswith("month") else count <= LONGEST_QUARTER_IN_WEEKS
    return None


def quarter_columns(dates: list[tuple[int, int, int]]) -> tuple[int, int | None]:
    """The column with the newest date, and the column of the same quarter one year before it (None when the
    statement has none). When two columns hold the same date, the first is the quarter and the other is the
    year to date."""
    current = max(range(len(dates)), key=lambda i: (dates[i], -i))
    year, month, day = dates[current]
    for i, (other_year, other_month, other_day) in enumerate(dates):
        if i == current:
            continue
        if month and other_month:
            try:
                days = (date(year, month, day) - date(other_year, other_month, other_day)).days
            except ValueError:
                continue
            if 350 <= days <= 380:  # 52 or 53 weeks, or a calendar year
                return current, i
        elif other_year == year - 1:
            return current, i
    return current, None


def date_label(when: tuple[int, int, int]) -> str:
    year, month, day = when
    return f"{MONTH_NAMES[month - 1]} {day}, {year}" if month else str(year)


def read_quarter(lines: list[str]) -> dict[str, Any]:
    """Claims 9, 10 and 11 from the lines of an earnings release. Each claim is a value, or a reason in "why"."""
    quarter: dict[str, Any] = {"statement": None, "units": "", "revenue_headers": [], "revenue_line": None, "eps_heading": None, "eps_line": None,
                               "period": None, "prior_period": None, "why": {}}
    found = next(((start, end, row) for start, end in statement_blocks(lines) for row in [revenue_row(lines, start, end)] if row is not None), None)
    if found is None:
        quarter["why"] = {claim: NO_STATEMENT for claim in CLAIMS}
        return quarter
    start, end, row = found
    # The header is everything from the heading down to the statement's first row of figures.
    first_row = next((i for i in range(start + 1, row + 1) if is_data_row(lines[i])), row)
    header = [line.strip() for line in lines[start:first_row] if line.strip()]
    figures = amounts_in(lines[row])
    units = UNITS.search(" ".join(header))
    quarter.update(statement=lines[start].strip(), units=units.group(1).lower() if units else "", revenue_headers=header, revenue_line=lines[row].strip())
    dates = column_dates(header, len(figures))
    is_quarter = first_period_is_a_quarter(header)
    problem = ("the income statement's header does not give one date for each column of figures" if dates is None
               else "the income statement's header does not name its periods" if is_quarter is None
               else "the first columns of the income statement are not a quarter" if not is_quarter else "")
    if problem:
        quarter["why"] = {claim: problem for claim in CLAIMS}
        return quarter
    current, prior = quarter_columns(dates)
    quarter.update(period=date_label(dates[current]), revenue=figures[current][1], revenue_shown=as_printed(figures[current][0]).lstrip("$"))
    if prior is None:
        quarter["why"]["growth"] = "the income statement has no column for the same quarter one year before"
    else:
        quarter.update(prior_period=date_label(dates[prior]), revenue_prior=figures[prior][1], revenue_prior_shown=as_printed(figures[prior][0]).lstrip("$"))
        if figures[prior][1]:
            quarter["revenue_growth"] = figures[current][1] / figures[prior][1] - 1
        else:
            quarter["why"]["growth"] = "last year's quarter has no revenue to divide by"
    index, heading, problem = eps_row(lines, start, end)
    amounts = amounts_in(lines[index]) if index is not None else []
    if index is not None and len(amounts) != len(dates):
        problem = "the diluted EPS row does not have one figure for each column"
    if problem:
        quarter["why"]["eps"] = problem
        return quarter
    quarter.update(eps_line=lines[index].strip(), eps_heading=heading, eps=amounts[current][1], eps_shown=per_share(amounts[current][0]))
    if prior is not None:
        quarter.update(eps_prior=amounts[prior][1], eps_prior_shown=per_share(amounts[prior][0]))
    return quarter
