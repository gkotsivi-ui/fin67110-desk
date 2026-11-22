"""Rules that both desks share, each in one place.

The base desk (lab02_desk.py) and the group desk (equity_research_desk.py) read the same SEC data. On 2026-11-22
the audit found rules that one desk had and the other did not. A rule that both need lives here, and both import it.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable

from release import has_income_statement

# A cover page can give a 52-week year's end as the month end, a few days from the statements' date.
# A difference of a year means that the facts are another year's.
SAME_YEAR_END_DAYS = 7


def annual_problem(facts_year_end: str | None, ten_k_year_end: str) -> str:
    """Why the annual facts cannot be stated; "" when the latest fiscal year of the company facts is the year
    of the 10-K the desk read. The reason holds dates and no amounts."""
    if facts_year_end is None:
        return "the XBRL company facts hold no full-year revenue under the tags the desk reads"
    if not ten_k_year_end:
        return ""
    if abs((date.fromisoformat(facts_year_end) - date.fromisoformat(ten_k_year_end)).days) <= SAME_YEAR_END_DAYS:
        return ""
    return f"the XBRL company facts end their latest fiscal year on {facts_year_end}, and the 10-K the desk read ends its year on {ten_k_year_end}"


FOOTER_FIRST = "This is a learning exercise, not financial advice."
FOOTER_LAST = "Any remaining errors are my own."


def course_footer(assistance: str) -> str:
    """The course's three lines, which end everything the team makes public. assistance names the tools that were
    actually used, for the middle line: "AI assistance: [the tools you used]. I verified the sources myself; the
    judgments are mine." The member who files the report is the one who says so."""
    return f"{FOOTER_FIRST}\n\nAI assistance: {assistance}. I verified the sources myself; the judgments are mine.\n\n{FOOTER_LAST}\n"


# An earnings release is an Exhibit 99 of its 8-K: EX-99.1 for most filers, EX-99 or another number for some.
EXHIBIT_99 = re.compile(r"\bEX-99(?:\.(\d+))?(?![\d.])", re.I)


def exhibit_99_label(kind: str) -> str | None:
    """The number of an Exhibit 99 from the type EDGAR's index page gives it: "99.1" for "EX-99.1", "99" for
    "EX-99". None for any other type."""
    found = EXHIBIT_99.search(kind or "")
    return None if not found else "99" + (f".{found.group(1)}" if found.group(1) else "")


def release_among(candidates: list[tuple[str, str]], text_of: Callable[[str], str | None]) -> tuple[str, str]:
    """Which Exhibit 99 is the earnings release: the first of the first four that holds an income statement.
    The first exhibit when there is only one, or when none holds an income statement.

    candidates are (number, file name) in the index page's order; text_of(file name) gives a document's text,
    or None when it cannot be read. Some filers put a slide deck or a letter in Exhibit 99.1 and the release
    in 99.2 (docs/decision-log.md, 2026-11-11).
    """
    if len(candidates) > 1:
        for label, name in candidates[:4]:
            text = text_of(name)
            if text and has_income_statement(text):
                return label, name
    return candidates[0]
