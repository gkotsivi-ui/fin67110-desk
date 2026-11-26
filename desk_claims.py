"""Claims ledger: the model selects evidence, code checks it and writes every number.

The research role returns
    {"claims": [...], "draft": "prose with {c1} placeholders"}

Each claim is one of:
    {"id": "c1", "file": "earnings_release_Ex99-1.txt", "line": 10,
     "quote": "Net sales for the quarter increased 11.2 percent, to $93.9 billion",
     "value": "$93.9 billion", "metric": "Q4 net sales", "period": "Q4 FY2026"}
    {"id": "c2", "fact": "net_income", "which": "value"}           # from facts.json

Checking is literal, not interpretive:
  * the quote must appear on the cited line,
  * the value must appear inside the quote, copied character for character,
  * the prose may not contain a financial number outside a {cN} placeholder.

Because the value is a substring of the quote, a wrong amount, scale, or line fails
without any unit parsing. Scale ("amounts in millions") is decided here, from the
filing's own section header, never by the model.
"""
from __future__ import annotations

import bisect
from datetime import date
import json
import unicodedata
from pathlib import Path
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from desk_quantities import SMALL,TENS,SCALES,enumeration_spans,heading_spans

PLACEHOLDER = re.compile(r"\{(c\d+)\}")
SCALE_WORD = re.compile(r"\b(thousand|million|billion|trillion)s?\b", re.I)
# A header that puts the amounts below it in a scale: "(amounts in millions, except per share data)", and also
# "(in millions, ...)" and "(dollars in millions)", the wording of both filers of the first two live reports, which
# this pattern did not read until 2026-11-22.
HEADER = re.compile(r"\((?:(?:dollar\s+)?amounts\s+|dollars\s+)?in (thousands|millions|billions)([^)]*)\)", re.I)
STATEMENT_TITLE = re.compile(r"statements?|balance\s+sheets?|consolidated|condensed|selected|summary|highlights|schedule", re.I)


def header_scale(line: str):
    """The match of a header that scales the amounts below it, or None.

    A row of a table states its own unit the same way: "Membership cardholders (in thousands)", "Customer
    transactions (in millions)". The first wider form of HEADER took such a row for the scale of every amount
    under it, and "$4,828" under a header in millions was published as "$4,828 thousand" (found by an independent
    review, 2026-11-22). A header stands on a line of its own, or says "amounts" or "dollars", or names what it
    leaves out ("except per share data"), or follows a statement's title.
    """
    found = HEADER.search(line)
    if not found:
        return None
    before, words = line[:found.start()].strip(), found.group(0).lower()
    if not before or re.match(r"\((?:dollar\s+)?(?:amounts|dollars)\s", words) or "except" in words or STATEMENT_TITLE.search(before):
        return found
    return None
# Text typed next to a placeholder that would change the number's size or sign: a currency sign or a minus before
# it, a multiplier before it, a scale after it. A rate after it ("{c1} percent of sales" for a bare table cell)
# and parentheses around it (an aside) are a real model's ordinary sentences (the replies of 2026-11-20) and are
# not refused: whether the label fits the cell is the Verifier's question, as every label is.
SCALE_OR_RATE = r"thousand|million|billion|trillion|bn|mn|percent|per\s+cent|pct|percentage\s+points?|basis\s+points?|bps|points?|times|fold|x"
# "half" multiplies a claim only as "half of {c1}": "the second half {c1}" is a period.
TYPED_BEFORE = re.compile(r"(?:[$€£+]|(?<![\w)\]}])[-−–—]|\b(?:(?:minus|negative|twice|thrice|double|triple)\s+(?:of\s+)?|half\s+of\s+))\{c\d+\}", re.I)
TYPED_AFTER = re.compile(r"\{c\d+\}\s*-?(?:thousand|million|billion|trillion|bn|mn|fold)s?\b", re.I)
# A Roman numeral with a scale or a percentage after it is an amount: "XII percent". A numeral that names a thing
# is not: "Basel III points to". The first form of this rule (2026-11-22) also refused every multiplier in words,
# "doubled", "twice", "twofold", and with them "double taxation", "a third party" and "twice in the filing", which
# stand in a real Verifier's reasons. A multiplier typed before a claim is still refused (TYPED_BEFORE). One that
# stands alone ("revenue doubled") is a statement about two figures, and whether it is true is the Verifier's.
ROMAN_AMOUNT = re.compile(r"\b[IVXLCDM]{2,}\s*(?:%|(?:thousand|million|billion|trillion|bn|mn|percent|per\s+cent|pct|percentage\s+points?|basis\s+points?|bps)\b)")
SECTION = re.compile(r"^Item\s+\d+[A-C]?\s*[—\-–.]", re.I)
# "Q3", "H1", "FY2026", and a quarter or a half with its year: "Q3 2026".
QUARTER = re.compile(r"\b(?:(?:Q[1-4]|H[12])(?:\s+(?:19|20)\d{2}\b)?|FY\d{2,4})\b")
# Allowed bare digits: list labels "(1)" or "1." at line start, Item numbers, ordinals in dates.
LIST_LABEL = re.compile(r"(?:^|\n)\s*(?:\(\d{1,2}\)|\d{1,2}[.)])\s|\(\d{1,2}\)")
ITEM_REF = re.compile(r"\bItem\s+\d+[A-C]?\b", re.I)
# A number that names a part of a text or of the accounting rules: "Note 17", "ASC 606", "Level 2", "Tier 1".
LABEL_REF=re.compile(r'\b(?:section|criterion|table|figure|chapter|note|asc|asu|topic|level|tier)\s+\d+\b|\bclaim\s+c\d+\b',re.I)
ISO_DATE=re.compile(r'(?<![\w$])\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?\b')
MONTHS=(r'(?:January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?')
# "August 30", "Aug. 30, 2026", "August 30th", "October 31 of 2026" -- the year is optional; a day is 1-31 only.
# A month with its year and no day is a date too: "November 2026".
TEXT_DATE=re.compile(r'\b'+MONTHS+r'\s+(?:(?:[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\b(?:,?\s+(?:of\s+)?(?:19|20)\d{2}\b)?|(?:19|20)\d{2}\b)')
# Source line identifiers in prose: L1030, L83-L85, L83–85, 10-K.txt:L1030, "line 83", "lines 83-85".
LINE_REF=re.compile(r'(?:\b[\w./-]+\.(?:txt|json|md):)?(?<![\w$])L\d+(?:\s*[-–—]\s*L?\d+)?\b'
                    r'|\blines?\s+\d+(?:\s*(?:[-–—]|to|and)\s*\d+)?\b',re.I)
ACCESSION_REF=re.compile(r'\b\d{10}-\d{2}-\d{6}\b')
FORM_REF = re.compile(r'\b(?:10-K|10-Q|8-K|20-F|40-F|6-K)(?:/A)?\b|\bForm\s+(?:3|4|5|10|144)\b',re.I)
NUMBER_WORDS = '|'.join(SMALL|TENS|SCALES|{'hundred':100})
UNIT_WORDS = (r"percent|percentage points?|basis points?|bps|trillion|billion|million|thousand|"
              r"warehouses?|stores?|members?|shares?|units?|cents?|dollars?|USD|EUR|GBP|times|x")
IDENTIFIER_END=r'(?![\w%$€£]|\.\d|\s*(?:'+UNIT_WORDS+r')\b)'
LINE_REF=re.compile('(?:'+LINE_REF.pattern+')'+IDENTIFIER_END,re.I)
TEXT_DATE=re.compile('(?:'+TEXT_DATE.pattern+')'+IDENTIFIER_END)
# "fy 2025": the Verifier quotes facts.json's fy field (2026-11-19), a fiscal-year label like "fiscal 2025".
# A unit after the year makes it a count ("in 2026 shares"), except "share of": a part of something.
YEAR = re.compile(r'\b(?:fiscal(?:\s+year)?|fy|year|in|for|during|the|from|since|through|versus|vs\.?|with)\s+(?:19|20)\d{2}\b(?!\s*(?!share\s+of\b)(?:'+UNIT_WORDS+r')\b)|(?<![\w$.,])(?:19|20)\d{2}(?=\s+(?:net\s+(?:sales|income)|gross\s+margin|fiscal\s+year|revenue|results)\b)',re.I)
PERIOD_SEQUENCE=re.compile(r'\b(?:the|years?|fiscal\s+years?|periods?)\s+(?:19|20)\d{2}(?:\s*(?:,|and)\s*(?:19|20)\d{2})+\s+(?:sequence|years?|periods?)\b',re.I)
# "the third quarter of 2025", "the nine months of 2025", "the first half of 2026".
PERIOD_OF=re.compile(r'\b(?:quarters?|half|months|weeks)\s+of\s+(?:fiscal\s+(?:year\s+)?)?(?:19|20)\d{2}\b'+IDENTIFIER_END,re.I)
# A second year after a first: "2026 and 2025", "2026, 2025 and 2024", "2025 to 2026". Only the later years are
# taken here; the first is a year when the other rules say so.
YEAR_LIST=re.compile(r'(?<![\w$.,])((?:19|20)\d{2})((?:\s*,\s*(?:19|20)\d{2})*\s*,?\s*(?:and|or|to|through|versus|vs\.?)\s+(?:19|20)\d{2}'+IDENTIFIER_END+')',re.I)
# A term with a hyphen ("364-day", "12-month") and a list after "the" ("the Fortune 500"): names, when a filing prints them.
TERM=re.compile(r'(?<![\w$.,-])\d{1,4}-(?:day|week|month|year)\b')
# A span of time as the filing words it: "the next 12 months", "the trailing 12 months".
SPAN=re.compile(r'\b(?:next|trailing|last|past|prior|preceding|following)\s+\d{1,3}\s+(?:days|weeks|months|years)\b',re.I)
LISTED=re.compile(r'(?<=\b[Tt]he\s)[A-Z][A-Za-z&]+\s+\d{2,4}\b'+IDENTIFIER_END)
YEAR_END=re.compile(r'\b(?:end|beginning)\s+of\s+(?:(?:fiscal\s+)?year\s+)?(?:19|20)\d{2}\b'+IDENTIFIER_END,re.I)
YEAR_METRIC=re.compile(r'(?<![\w$.,])(?:19|20)\d{2}(?=\s+(?:(?:long|short)[- ]term\s+debt|operating\s+income|cash\s+flow|capital\s+spending|membership\s+fees?)\b)',re.I)
CLOCK_VALUE=r'(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?'
CLOCK_REF=re.compile(r'\b(?:at|before|after|by|close|closing|cutoff|time)\s+(?:'+CLOCK_VALUE+r')\b|(?<![\w$])'+CLOCK_VALUE+r'\s*(?:ET|EST|EDT|UTC|GMT|AM|PM)\b',re.I)
WORD_AMOUNT = re.compile(
    rf"\b(?:{NUMBER_WORDS})(?:[\s-]+(?:{NUMBER_WORDS}))*[\s-]+(?:{UNIT_WORDS}|per\s+cent|pct|bn|mn)\b"
    rf"|\b(?:{NUMBER_WORDS})(?:[\s-]+(?:{NUMBER_WORDS}))*\s*%"
    rf"|\b(?:{NUMBER_WORDS})(?:[\s-]+(?:{NUMBER_WORDS}))+\b", re.I)


def _norm(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip()


def source_identifier_pattern(texts,facts,origins):
    """Only exempt actual saved key/tag/claim names, never arbitrary digit words."""
    names=set()
    def add(name):
        if isinstance(name,str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name) and re.search(r'\d',name):names.add(name)
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                add(key)
                if key=='tag':add(item)
                walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(facts or {})
    for name,text in texts.items():
        if name.endswith('.json'):
            try:walk(json.loads(text))
            except (ValueError,TypeError):pass # Broken saved data is checked at its source boundary.
    for claims in (origins or {}).values():
        if isinstance(claims,dict):
            for name in claims:add(name)
    if not names:return None
    return re.compile(r'(?<![\w$])(?:'+'|'.join(re.escape(name) for name in sorted(names,key=len,reverse=True))+r')(?![\w%])')


# A scale or a rate. After a number it makes an amount, whatever words stand before the number.
AMOUNT_AFTER = re.compile(r"\s*(?:%|(?:thousand|million|billion|trillion|bn|mn|percent|per\s+cent|pct|percentage\s+points?|basis\s+points?|bps)\b)", re.I)  # "in 2026 thousands of members" is not an amount


def a_reference(found, kind):
    """Whether typed text that reads as a reference (an Item, a form, a table, a year, a date) is one.

    Until 2026-11-22 the words before a number decided it alone: "Sales of Item 12 million" and "Insiders filed
    Form 4 billion" passed with no claim, and so did "9999-99-99". A reference followed by a scale or a rate is an
    amount, and a date must be a date of the calendar.
    """
    if AMOUNT_AFTER.match(found.string, found.end()):
        return False
    if kind is ISO_DATE:
        try:
            date.fromisoformat(found.group(0)[:10])
        except ValueError:
            return False
    return True


def a_difference(line: str, typed) -> bool:
    """Whether a typed "minus {c2}" stands straight after another claim: "{c1} minus {c2}".

    One claim minus another is a subtraction said in words. Neither number changes, and the sentence states no
    result. Until 2026-11-25 the rule read the word as a sign typed on the second claim (the Financial Analyst of
    the Lowe's practice run, 2026-11-22). A minus after anything else ("the change was minus {c2}") is a sign."""
    return typed.group(0).lower().startswith("minus") and bool(re.search(r"\{c\d+\}\s+$", line[:typed.start()]))


# A year with the capitalised words after it: "2025 Term Loan", "2029 Notes", "2019 Equity Plan".
YEAR_NAME = re.compile(r"(?<![\w$.,])(?:19|20)\d{2}(?:\s+[A-Z][A-Za-z]+)+")


def without_a_filings_name(phrase: str, texts: dict[str, str]) -> str:
    """The phrase with its year taken out, when a saved filing prints that year with the word after it.

    Filings name loans, notes and plans by year. "the 2025 Term Loan" always passed, because a year after "the"
    does; "(2025 Term Loan)" and "its 2029 Notes" were refused as typed numbers (the Verifier of the Lowe's
    practice run, 2026-11-22). The name must be the filing's own: the year and at least the next word, word for
    word, in a saved filing text. A unit is never a name: "2025 Stores" is a count, whatever the filing prints."""
    words = phrase.split()
    if re.fullmatch(UNIT_WORDS + r"|pct|bn|mn", words[1], re.I):
        return phrase
    for count in range(len(words), 1, -1):
        if printed_in_a_filing(" ".join(words[:count]), texts):
            return " ".join(["", *words[1:]])
    return phrase


def printed_in_a_filing(phrase: str, texts: dict[str, str]) -> bool:
    """Whether a saved filing text prints the phrase word for word, as whole words."""
    printed = re.compile(r"(?<![\w$.,-])" + r"\s+".join(re.escape(word) for word in phrase.split()) + r"(?![\w-])")
    return any(printed.search(text) for name, text in texts.items() if name.endswith(".txt"))


def a_filings_name(found, texts: dict[str, str]) -> str:
    """A blank for a term, a list or a span of time that a saved filing prints ("364-day", "the Fortune 500",
    "next 12 months"), or the text as it was.

    Both were refused as typed numbers in real runs (Lowe's 2026-11-19 and 2026-11-20, Workday 2026-11-25). The
    filing must print the same words: "a 180-day facility" stays a number when the filing has a 364-day one. A
    list needs "the" before it, so that a table row ("Locations 612") is not read as a name, and its word is
    never a unit or a month."""
    phrase = found.group(0)
    if re.fullmatch(UNIT_WORDS + r"|pct|bn|mn|" + MONTHS, phrase.split()[0], re.I):
        return phrase
    return " " if printed_in_a_filing(phrase, texts) else phrase


def printed_scale(typed: str, claims: list, texts: dict[str, str]) -> bool:
    """Whether "{c1} billion" types the scale the filing itself prints right after the cited number.

    The desk saves each tagged piece of a filing on a line of its own: "approximately $", "99.6", "billion, $".
    The claim's value is one line, so it cannot hold that scale, and a real reply of 2026-11-19 typed it, rightly.
    The typed word passes only when it is the first word after the number in the saved text: on the rest of the
    cited line, or at the start of the next line that holds text. Any other typed scale is still refused.
    """
    found = re.fullmatch(r"\{(c\d+)\}\s*(thousand|million|billion|trillion)", typed, re.I)
    claim = next((c for c in claims if isinstance(c, dict) and found and c.get("id") == found.group(1)), None)
    if not claim or not all(isinstance(claim.get(k), str) for k in ("file", "value")) or not isinstance(claim.get("line"), int):
        return False
    lines = texts.get(claim["file"], "").splitlines()
    index = claim["line"] - 1
    if not 0 <= index < len(lines) or claim["value"] not in lines[index]:
        return False
    after = lines[index].split(claim["value"], 1)[1]
    if not after.strip():
        after = next((line for line in lines[index + 1:index + 3] if line.strip()), "")
    return bool(re.match(r"\s*" + re.escape(found.group(2)) + r"\b", after, re.I))


def complete_value(value,quote,source):
    """Require a complete literal value, not part of a larger amount or unit."""
    if len(re.findall(r'\d[\d,]*(?:\.\d+)?',value))>1:return False
    for q in re.finditer(re.escape(quote),source):
        for v in re.finditer(re.escape(value),quote):
            start,end=q.start()+v.start(),q.start()+v.end()
            left,right=source[:start],source[end:]
            # A loss is printed with a minus sign, a dash, or in parentheses: "(1,234)". Until 2026-11-22 the value
            # could be cut out of its parentheses or from behind an en dash, and a loss was published as a gain.
            if left and (left[-1].isalnum() or left[-1] in '$€£.,−-'):continue
            # An en or em dash before the value is a minus sign when it opens the amount ("changed –0.4 points"),
            # and punctuation when it closes what stands before it: a range ("24.5%–25.5%") or an aside
            # ("margin—12.3 percent—was"). The first form of this rule refused both of the latter (2026-11-22).
            if left and left[-1] in '–—' and value[:1].isdigit() and not re.search(r'[\w%)]$',left[:-1]):continue
            # Parentheses around an amount are a loss, "(1,234)". Around a percentage inside a sentence they are
            # an aside: "increased $412 million (9%)".
            aside=value.rstrip().endswith('%') and re.search(r'\w\s+\($',left)
            if left.endswith('(') and right.startswith(')') and not aside:continue
            if right and (right[0].isalnum() or right[0] in '%'):continue
            if re.match(r'[.,]\d',right):continue
            # "per cent", "bp" and "points" were not in this list until 2026-11-22: "5.2" could be cut from
            # "5.2 per cent", and the unit was then the model's to type.
            if re.match(r'\s*(?:thousand|million|billion|trillion)s?\b|\s*(?:percent(?:age)?|per\s+cent|pct|basis\s+points?|bps?|pp|points?|pts|bn|mn|USD|EUR|GBP|dollars?)\b',right,re.I):continue
            if not re.search(r'\d|\b(?:'+NUMBER_WORDS+r')\b',value,re.I):continue
            return True
    return False


class ResponseFormatError(ValueError):
    """A model reply that is not exactly one JSON object. Keeps the raw text for the record."""
    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def parse_response(text: str, role: str) -> dict[str, Any]:
    """Exactly one JSON object, optionally in a ```json fence. Anything else is a repairable error.

    Words before the object are dropped: "Here is the corrected JSON:" cannot be a second answer. Until
    2026-11-25 they were refused, and so were four of the thirteen role calls of one practice run. Words that
    hold a brace are not a plain preamble and are still refused, as is anything after the object. The whole
    reply stays in raw_responses.json."""
    cleaned=(text or '').strip()
    starts=[at for at in (cleaned.find('{'),cleaned.find('```')) if at>=0]
    if starts:cleaned=cleaned[min(starts):]      # the object or its fence, whichever comes first
    if cleaned.startswith('```') or cleaned.endswith('```'):
        fence=re.fullmatch(r'```(?:json)?\s*\n?(.*?)\s*```',cleaned,re.I|re.S)
        if not fence:
            closed=cleaned.count('```')>=2
            where='text after its JSON fence' if cleaned.startswith('```') else 'text with a brace before its JSON fence'
            raise ResponseFormatError(f'{role} reply has '+(where if closed else 'a JSON fence that is not closed')
                                      +'. Return exactly one JSON object with nothing before or after it.',text)
        cleaned=fence[1].strip()
    start = cleaned.find("{")
    if start < 0:
        raise ResponseFormatError(f"{role} reply contained no JSON object. Return exactly one JSON object.", text)
    try:
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('duplicate JSON key: '+key)
                result[key]=value
            return result
        def finite(value):raise ValueError('nonfinite JSON number: '+value)
        value, end = json.JSONDecoder(object_pairs_hook=unique,parse_constant=finite).raw_decode(cleaned, start)
    except ValueError as error:
        raise ResponseFormatError(f"{role} reply is not valid JSON ({error}). Return exactly one JSON object.", text) from None
    if not isinstance(value, dict):
        raise ResponseFormatError(f"{role} reply was JSON but not an object. Return exactly one JSON object.", text)
    before, after = cleaned[:start].strip(), cleaned[end:].strip()
    if before or after:
        # Never guess which part was meant: a trailing object may be a revised answer.
        extra = (before or after)[:160]
        raise ResponseFormatError(f"{role} reply had text outside its JSON object ({extra!r}). Return exactly one "
                                  "JSON object with nothing before or after it.", text)
    return unix_lines(value)


def unix_lines(value: Any) -> Any:
    """Every string of a reply with its line ends as "\\n". A model may end a draft's lines with "\\r\\n". Windows
    then saved the draft as text with "\\r\\r\\n", read it back as two line ends, and the check that the saved draft
    equals the checked one stopped the run (found on 2026-11-22, on a made-up reply)."""
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(value, list):
        return [unix_lines(item) for item in value]
    if isinstance(value, dict):
        return {key: unix_lines(item) for key, item in value.items()}
    return value


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    rendered: str = ""
    values: dict[str,str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def repair_message(self) -> str:
        """Text to send back to the model for a targeted retry."""
        # "with nothing before or after it": two of three repaired replies of one run opened with an explanation
        # and were refused for it (Dell, 2026-11-23).
        return ("Your output failed these checks. Fix only the listed items and return the "
                "full JSON again, with nothing before or after it:\n- " + "\n- ".join(self.errors))


def section_scale(lines: list[str], index: int) -> tuple[str | None, str]:
    """Scale declared by the nearest '(amounts in ...)' header above, within the same Item."""
    for i in range(index, -1, -1):
        match = header_scale(lines[i])
        if match:
            return match.group(1).lower().rstrip("s"), match.group(2).lower()
        if i < index and SECTION.match(lines[i].strip()):
            return None, ""
    return None, ""


class ScaleInDoubt(ValueError):
    """A "$" amount under a header that scales the amounts, where the line does not say which scale it is in."""


def display_value(claim: dict, lines: list[str]) -> str:
    """Literal source value, with the section's scale added only where the filing implies it.

    A header such as "(amounts in millions, except per share data)" scales the dollar amounts of the tables and
    the text under it, but not every dollar amount: a dividend of $1.16 or a wage of $20 an hour, a few lines
    below, is in dollars. Until 2026-11-22 the header's scale went on every "$" value in the Item, and the desk
    itself wrote "$1.16 million" for a dividend. The scale is now added only to an amount that cannot be anything
    else: whole dollars with a thousands separator ("$9,226"). A per-share amount keeps its own unit. Any other
    amount under such a header is in doubt, and the claim is refused with the reason (ScaleInDoubt).
    """
    value = claim["value"].strip()
    if not value.startswith("$") or SCALE_WORD.search(value):
        return value
    scale, exceptions = section_scale(lines, claim["line"] - 1)
    if not scale:
        return value
    # The short quote may end at the value; its per-share qualifier is still
    # present on the saved filing line and must not be lost.
    quote = _norm(lines[claim['line']-1])
    quote_start=quote.find(_norm(claim['quote']))
    start=quote_start+_norm(claim['quote']).find(value)
    after = quote[start + len(value):][:30].lower()
    before = quote[max(0, start - 40):start].lower()
    # "$20 an hour", "$65 a year", "$4.82 per diluted share", "earnings per share of $4.82". Not "$43,440 a year
    # ago", and not "$4.82 per diluted share, compared with $1,980": the first form of these two patterns read both
    # as amounts for each unit and published them without the header's scale (2026-11-22).
    if re.match(r"\s*(?:,\s*)?(?:or\s+)?(?:per|a|an|each)\s+(?:\w+\s+)?(?:share|hour|unit|member|day|month|year)\b(?!\s+(?:ago|earlier|before|prior|later))", after) \
            or re.search(r"per\s+(?:\w+\s+)?share[\s:,]*(?:(?:of|was|were|is|to|at)\s+)?$", before):
        return value
    if re.fullmatch(r"\$\(?\d{1,3}(?:,\d{3})+\)?", value):
        return f"{value} {scale}"
    raise ScaleInDoubt(f"the filing's header puts the amounts of this section in {scale}s, and the cited line does not say whether "
                       f"{value} is in that scale. Cite a line that states the scale in words, or use a saved fact")


def format_fact(key: str, fact: dict, which: str) -> str:
    value = fact.get(which)
    if value is None:
        raise ValueError(f"facts.json {key}.{which} is empty")
    value=Decimal(str(value))
    # The sign goes before the dollar sign: "-$9.917 billion", not "$-9.917 billion" (a deficit, 2026-11-20).
    sign='-' if value<0 else ''
    value=abs(value)
    def exact(value):
        text=format(value,',f')
        return text.rstrip('0').rstrip('.') if '.' in text else text
    if "eps" in key or "per_share" in key:
        return sign+'$'+exact(value)
    for size, word in ((Decimal('1e12'), "trillion"), (Decimal('1e9'), "billion"), (Decimal('1e6'), "million")):
        if value >= size:
            return sign+'$'+exact(value/size)+f' {word}'
    return sign+'$'+exact(value)


def guidance_range_errors(draft, rendered, texts):
    """Check explicit guidance endpoint relationships, beyond literal value matching.

    Scope: placeholder pairs joined by to/dashes or between/and in a guidance sentence.
    Both values must occur as one range on one saved filing line. This is conservative:
    split-line or unsupported ranges must be omitted or quoted without assembling endpoints.
    """
    errors = []
    guidance = re.compile(r'\b(?:guidance|guides?|project(?:ed|s|ion)?|forecast(?:s|ed)?|outlook)\b', re.I)
    pairs = (re.compile(r'\{(c\d+)\}\s*(?:to|[-–—])\s*\{(c\d+)\}', re.I),
             re.compile(r'between\s+\{(c\d+)\}\s+and\s+\{(c\d+)\}', re.I))
    citation = re.compile(r'(.+?) \[([^]\n]+):L(\d+)\]')
    for number, line in enumerate(draft.splitlines(), 1):
        for sentence in re.split(r'(?<=[.!?])\s+', line):
            if not guidance.search(sentence):
                continue
            for pattern in pairs:
                for match in pattern.finditer(sentence):
                    left, right = (citation.fullmatch(rendered.get(cid, '')) for cid in match.groups())
                    valid = False
                    if left and right and left.groups()[1:] == right.groups()[1:] and left[2] in texts:
                        lines = texts[left[2]].splitlines()
                        index = int(left[3]) - 1
                        if 0 <= index < len(lines):
                            source = _norm(lines[index])
                            relation = re.escape(_norm(left[1])) + r'\s*(?:to|[-–—])\s*' + re.escape(_norm(right[1]))
                            between = r'between\s+' + re.escape(_norm(left[1])) + r'\s+and\s+' + re.escape(_norm(right[1]))
                            valid = bool(re.search(relation, source, re.I) or re.search(between, source, re.I))
                    if not valid:
                        errors.append(f'draft line {number}: guidance range endpoints {{{match[1]}}} and {{{match[2]}}} '
                                      'must form one range on the same cited filing line. Use that source range or omit the range.')
    return errors


def check(output: dict[str, Any], texts: dict[str, str], facts: dict[str, Any] | None = None,origins=None,reference_only=False) -> Result:
    result = Result()
    identifiers=source_identifier_pattern(texts,facts,origins)
    if not isinstance(output,dict):
        result.errors.append('Return JSON with "claims" (array) and "draft" (string).')
        return result
    claims = output.get("claims")
    draft = output.get("draft")
    if not isinstance(claims, list) or not isinstance(draft, str):
        result.errors.append('Return JSON with "claims" (array) and "draft" (string).')
        return result

    rendered: dict[str, str] = {}
    fact_table = (facts or {}).get("facts", {})
    ids=set()
    for claim in claims:
        if not isinstance(claim,dict):
            result.errors.append('Each claim must be a JSON object.')
            continue
        cid = claim.get("id", "?")
        if not isinstance(cid,str) or not PLACEHOLDER.fullmatch('{'+cid+'}'):
            result.errors.append('Each claim id must have the form c1, c2, and so on.')
            continue
        if cid in ids:
            result.errors.append(f"{cid}: duplicate claim id.")
            continue
        ids.add(cid)
        if 'from' in claim:
            origin=claim.get('from');reference=claim.get('claim')
            key=claim.get('from_file',origin)
            if not isinstance(origin,str) or not isinstance(reference,str) or not isinstance(key,str) or reference not in (origins or {}).get(key,{}):
                result.errors.append(f'{cid}: referenced analyst claim is not available.')
                continue
            if key!=origin and not re.fullmatch('nodes/'+re.escape(origin.replace(' ','_'))+r'_[12]/output\.json',key):
                result.errors.append(f'{cid}: referenced file does not belong to the named analyst.')
                continue
            rendered[cid]=origins[key][reference]
            continue
        if reference_only:
            result.errors.append(f'{cid}: use an existing analyst claim with from and claim; do not add a value.')
            continue
        if 'computed' in claim or 'quarter' in claim:
            group='metrics' if 'computed' in claim else 'quarter_results'
            key=claim.get('computed',claim.get('quarter'))
            try:
                saved=json.loads(texts['calculated_facts.json'])
                if not isinstance(key,str):raise ValueError('key must be a string')
                entry=saved[group][key]
                if not isinstance(entry,dict) or entry.get('value') is None:raise ValueError('saved value is unavailable; state that limitation without a numeric claim')
                import ast,operator,math
                ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}
                def evaluate(node):
                    if isinstance(node,ast.Constant) and type(node.value) in (int,float):return Decimal(str(node.value))
                    if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):return (-1 if isinstance(node.op,ast.USub) else 1)*evaluate(node.operand)
                    if isinstance(node,ast.BinOp) and type(node.op) in ops:return ops[type(node.op)](evaluate(node.left),evaluate(node.right))
                    raise ValueError('unsupported saved formula')
                formula=entry.get('formula','')
                expected=evaluate(ast.parse(formula,mode='eval').body)
                if entry.get('unit')=='%' and not re.search(r'\*\s*100\b',formula):expected*=100
                if not math.isclose(float(expected),float(entry['value']),rel_tol=1e-12,abs_tol=1e-12):raise ValueError('saved calculation does not match its formula')
                unit=entry.get('unit')
                if unit=='USD':shown=format_fact(key,entry,'value')
                # A client reads these: two decimals for a percentage, three for a ratio, not the float's sixteen
                # digits ("11.766682891778505%" on 2026-11-20). The saved value keeps full precision for the hook.
                elif unit=='%':shown=f"{float(entry['value']):.2f}%"
                elif unit=='ratio':shown=f"{float(entry['value']):.3f} times"
                else:raise ValueError('saved calculation has no supported unit')
                sources=entry.get('sources',[])
                if not sources or any(s=='not available' for s in sources):raise ValueError('saved calculation has no source evidence')
                rendered[cid]=shown+f' [saved calculated_facts.json#/{group}/{key}; computed, rechecked given calculations; formula {formula}; inputs: '+'; '.join(sources)+']'
            except (KeyError,TypeError,ValueError,SyntaxError,ArithmeticError) as error:result.errors.append(f'{cid}: {error}')
            continue
        if "fact" in claim:
            key, which = claim["fact"], claim.get("which", "value")
            if not isinstance(key,str) or which not in ('value','prior_value'):
                result.errors.append(f'{cid}: fact must name a saved key and which must be value or prior_value.')
                continue
            peer=claim.get('peer')
            table=fact_table if peer is None else (facts or {}).get('peers',{}).get(peer,{}).get('facts',{}) if isinstance(peer,str) else {}
            fact = table.get(key)
            if not fact or fact.get(which) is None or not fact.get("tag"):
                result.errors.append(f"{cid}: facts.json has no value for {key}.{which}.")
                continue
            period = fact.get("period_end" if which == "value" else "prior_period_end")
            filing = fact.get("filing" if which == "value" else "prior_filing")
            if not period or not filing:
                result.errors.append(f'{cid}: saved fact has no period or filing.')
                continue
            rendered[cid] = (f"{format_fact(key, fact, which)} "
                             f"[XBRL tag {fact['tag']}, period end {period}, filing {filing}]")
            continue

        name, line_no = claim.get("file"), claim.get("line")
        quote, value = claim.get("quote", ""), claim.get("value", "")
        if not isinstance(name,str) or name not in texts:
            result.errors.append(f"{cid}: file {name!r} is not one of your supplied sources.")
            continue
        lines = texts[name].splitlines()
        if type(line_no) is not int or not 1 <= line_no <= len(lines):
            result.errors.append(f"{cid}: {name} has no line {line_no}.")
            continue
        source_line = _norm(lines[line_no - 1])
        if not isinstance(quote,str) or not isinstance(value,str):
            result.errors.append(f'{cid}: quote and value must be strings.')
            continue
        if not quote or _norm(quote) not in source_line:
            hits = [i + 1 for i, l in enumerate(lines) if quote and _norm(quote) in _norm(l)]
            hint = f" It appears on line {hits[0]}." if hits else " It does not appear in that file."
            result.errors.append(f"{cid}: quote is not on {name}:L{line_no}.{hint}")
            continue
        if not value or _norm(value) not in _norm(quote):
            result.errors.append(
                f"{cid}: value {value!r} must be copied exactly from the quote; it is not in it.")
            continue
        if not re.search(r'\d|\b(?:'+NUMBER_WORDS+r')\b',value,re.I):
            # 2026-11-19: "sixth consecutive quarter" was sent back three times as "a substring of a larger
            # value", a message the model could not act on, and its whole paragraph was then left out.
            result.errors.append(f'{cid}: value {value!r} holds no number. A claim is a number copied from the cited line; '
                                 'state this fact in words without a claim, or cite the number.')
            continue
        if not complete_value(_norm(value),_norm(quote),source_line):
            result.errors.append(f'{cid}: value must be a complete amount and unit copied from the cited line, not a substring of a larger value.')
            continue
        claim = {**claim, "value": _norm(value), "line": line_no}
        try:
            rendered[cid] = f'{display_value(claim, lines)} [{name}:L{line_no}]'
        except ScaleInDoubt as doubt:
            result.errors.append(f"{cid}: {doubt}.")

    used = set(PLACEHOLDER.findall(draft))
    for cid in sorted(used - rendered.keys() - ids):
        result.errors.append(f"{{{cid}}} is used in the draft but no claim has that id.")
    for cid in sorted(ids - used):
        result.errors.append(f"{cid} is never used in the draft; remove it or place it.")

    saved_names = re.compile('|'.join(re.escape(name) for name in sorted(texts, key=len, reverse=True))) if texts else None
    for n, line in enumerate(draft.splitlines(), 1):
        # A scale, a sign or a multiplier typed next to a placeholder changes the number the claim checked:
        # "{c1} billion" for a cell that holds 9,200, "-{c1}" for a gain, "twice {c1}". Until 2026-11-22 these
        # passed. The claim's own value holds its scale and sign, copied from the cited line, or code renders them.
        for match in (*TYPED_BEFORE.finditer(line), *TYPED_AFTER.finditer(line)):
            if printed_scale(match.group(0), claims, texts) or a_difference(line, match):
                continue
            result.errors.append(f"draft line {n}: {match.group(0)!r} types a scale, a sign or a multiplier next to a claim. "
                                 "The claim's value must hold it, copied from the cited line (\"$4.1 billion\", \"-0.4 points\"); do not type it.")
        # A citation is written by code when a claim is rendered. A typed one looks checked and is not.
        for match in re.finditer(r"\[(?:[\w./-]+\.(?:txt|json|md):L\d+|XBRL tag|saved calculated_facts)", line):
            result.errors.append(f"draft line {n}: a source citation is typed ({match.group(0)!r}...). Code writes the citation of each claim; do not type one.")
        # A role writes sentences under its headings. A table row in a draft, or a heading with one of the desk's
        # own titles, can pass for the tables that code prints (the core claims, the Verifier's marks). A sentence
        # that only names them ("the core claims above show") is a sentence.
        if line.lstrip().startswith("|") or re.search(r"\|\s*Mark\s*\|", line) or (
                re.match(r"\s*(?:#{1,6}|\*\*|==)", line) and re.search(r"core claims|read and computed in code|Worksheet view and evidence", line, re.I)):
            result.errors.append(f"draft line {n}: a draft holds no table row and none of the desk's own table titles; write a sentence.")
        prose = PLACEHOLDER.sub("", line)
        prose = re.sub(r"\[[\w./-]+\.txt:L\d+\]", "", prose) # source identifiers only
        prose = LINE_REF.sub(" ", prose)
        for start,end in reversed(enumeration_spans(prose)):
            prose=prose[:start]+' '*(end-start)+prose[end:]
        if identifiers:prose=identifiers.sub(' ',prose)
        if saved_names:prose=saved_names.sub(' ',prose)   # "earnings_release_Ex99-1.txt" is a file's name, not two numbers
        prose = YEAR_NAME.sub(lambda found: without_a_filings_name(found.group(0), texts), prose)
        for name in (TERM, LISTED, SPAN):
            prose = name.sub(lambda found: a_filings_name(found, texts), prose)
        prose = YEAR_LIST.sub(lambda found: found.group(1) + re.sub(r'\d{4}', ' ', found.group(2)), prose)
        for allowed in (ISO_DATE,TEXT_DATE,ACCESSION_REF,PERIOD_SEQUENCE,PERIOD_OF,YEAR_END,YEAR_METRIC,YEAR,CLOCK_REF, QUARTER, ITEM_REF, FORM_REF,LABEL_REF):
            prose = allowed.sub(lambda found, kind=allowed: " " if a_reference(found, kind) else found.group(0), prose)
        for start,end in reversed(heading_spans(prose)):
            prose=prose[:start]+' '*(end-start)+prose[end:]
        for match in re.finditer(r"[$%]?\d[\d,.]*%?", prose):
            result.errors.append(
                f"draft line {n}: number {match.group(0)!r} is typed directly; use a {{cN}} claim.")
        for match in (*WORD_AMOUNT.finditer(prose), *ROMAN_AMOUNT.finditer(prose)):
            result.errors.append(
                f"draft line {n}: written amount {match.group(0)!r} must be a {{cN}} claim.")
        # Superscripts, fractions, circled and other numerals are numbers too, and the digit scan above reads
        # only the digits 0 to 9 and their look-alikes. A subscript after a letter is part of a name ("CO₂").
        odd = sorted({ch for k, ch in enumerate(prose) if not ch.isascii() and unicodedata.numeric(ch, None) is not None
                      and not ("₀" <= ch <= "₉" and k and prose[k - 1].isalpha())})
        if odd:
            result.errors.append(f"draft line {n}: number character(s) {''.join(odd)!r} are typed directly; use a {{cN}} claim.")

    result.errors.extend(guidance_range_errors(draft, rendered, texts))
    if result.ok:
        result.values=rendered
        result.rendered = PLACEHOLDER.sub(lambda m: rendered[m.group(1)], draft)
    return result


SOURCE_FILES = ("10-K.txt", "10-Q.txt", "earnings_release_Ex99-1.txt",'calculated_facts.json')


def load_sources(run) -> tuple[dict[str, str], dict[str, Any]]:
    """Filing texts and saved XBRL facts from a run folder, as the hook reads them."""
    run = Path(run)
    texts = {name: (run / name).read_text(encoding="utf-8", errors="replace")
             for name in SOURCE_FILES if (run / name).is_file()}
    facts = json.loads((run / "facts.json").read_text(encoding="utf-8")) if (run / "facts.json").is_file() else {}
    return texts, facts


def verify_saved(run, data: dict[str, Any],role=None) -> list[str]:
    """Hook check for a saved claims output: recheck every claim and the rendering."""
    texts, facts = load_sources(run)
    role=role or data.get('role','Research Analyst')
    from desk_role_contracts import origins_for
    try:origins=origins_for(run,role)
    except ValueError as error:return [str(error)]
    result = check({"claims": data.get("claims"), "draft": data.get("template")}, texts, facts,origins,role=='Investment Advisor')
    if result.ok and result.rendered != data.get("draft"):
        return ["Saved draft differs from the rendering of its checked claims and template."]
    return result.errors


CLAIM_ERROR = re.compile(r"^\{?(c\d+)\}?(?::| is never used| is used in the draft)")
LINE_ERROR = re.compile(r"^draft line (\d+):")


def _failing(errors):
    """The claim ids and draft line numbers the errors name, or None when an error is of another kind."""
    ids, lines = set(), set()
    for error in errors:
        if match := LINE_ERROR.match(error):
            lines.add(int(match[1]))
        elif match := CLAIM_ERROR.match(error):
            ids.add(match[1])
        else:
            return None
    return ids, lines


def _by_number(ids):
    return sorted(ids, key=lambda cid: int(cid[1:]) if re.fullmatch(r"c\d+", str(cid)) else 0)


# What stands in a Verifier mark's reason when the reason itself failed the code's check after its repairs.
LEFT_OUT_REASON = "The Verifier's reason for this mark failed the code's check after its repairs and is left out."


def _text_of_each_line(texts):
    """For "\\n".join(texts), split into lines as check() splits a draft: the index of the text each line is in."""
    starts, position = [], 0
    for text in texts:
        starts.append(position)
        position += len(text) + 1
    owners, offset = [], 0
    for line in "\n".join(texts).splitlines(keepends=True):
        owners.append(bisect.bisect_right(starts, offset) - 1)
        offset += len(line)
    return owners


def verifier_without_failing(raw, errors):
    """A Verifier reply whose failing reasons and corrections are left out, and the claims only they used.

    The Verifier's prose is checked as one draft: each check's reason, then its correction. A text that holds
    a failing line or a failing claim is replaced (a reason by LEFT_OUT_REASON, a correction by nothing); every
    mark stays. Returns (reply, claim ids left out, prose line numbers left out), or None.
    """
    checks, claims = raw.get("checks"), raw.get("claims", [])
    if not isinstance(checks, list) or not isinstance(claims, list) or not all(isinstance(c, dict) for c in checks):
        return None
    failing = _failing(errors)
    if failing is None:
        return None
    ids, lines = failing
    where = [(i, key) for i in range(len(checks)) for key in ("reason", "correction")]
    texts = [checks[i].get(key, "") for i, key in where]
    if not all(isinstance(text, str) for text in texts):
        return None
    owners = _text_of_each_line(texts)
    bad = {owners[n - 1] for n in lines if 0 < n <= len(owners)}
    bad |= {k for k, text in enumerate(texts) if ids & set(PLACEHOLDER.findall(text))}
    mended = [dict(check) for check in checks]
    for k in bad:
        i, key = where[k]
        mended[i][key] = LEFT_OUT_REASON if key == "reason" else ""
    used = set(PLACEHOLDER.findall("\n".join(mended[i].get(key, "") for i, key in where)))
    kept = [c for c in claims if isinstance(c, dict) and c.get("id") in used and c.get("id") not in ids]
    left_out = ids | {c.get("id") for c in claims if isinstance(c, dict)} - {c["id"] for c in kept}
    return {**raw, "checks": mended, "claims": kept}, _by_number(left_out), sorted(lines)


def without_failing(raw, errors):
    """The reply with each failing claim left out, and every draft line that failed or uses a failing claim.

    Returns (reply, claim ids left out, draft line numbers left out). Returns None when an error is of
    another kind, such as the reply's shape, which only a new reply can mend, or when no line would be left.
    A Verifier's reply has checks in place of a draft; verifier_without_failing mends it.
    """
    if isinstance(raw, dict) and "draft" not in raw and isinstance(raw.get("checks"), list):
        return verifier_without_failing(raw, errors)
    if not isinstance(raw, dict) or not isinstance(raw.get("claims"), list) or not isinstance(raw.get("draft"), str):
        return None
    failing = _failing(errors)
    if failing is None:
        return None
    ids, lines = failing
    kept, dropped = [], []
    for n, line in enumerate(raw["draft"].splitlines(), 1):
        if n in lines or ids & set(PLACEHOLDER.findall(line)):
            dropped.append(n)
        else:
            kept.append(line)
    if not any(line.strip() for line in kept):
        return None
    used = set(PLACEHOLDER.findall("\n".join(kept)))
    claims = [c for c in raw["claims"] if isinstance(c, dict) and c.get("id") in used and c.get("id") not in ids]
    left_out = ids | {c.get("id") for c in raw["claims"] if isinstance(c, dict)} - {c["id"] for c in claims}
    return {**raw, "claims": claims, "draft": "\n".join(kept)}, _by_number(left_out), dropped


def with_repairs(ask, texts: dict[str, str], facts: dict[str, Any], repairs: int = 2,on_attempt=None,validator=None):
    """Call ask(feedback) until the claims pass, sending each failure back once.

    ask(None) is the first call; ask(message) is a repair call. Returns
    (final_output_dict, attempts) where attempts lists every raw output and its errors.
    When repairs run out, the latest reply is published without its failing claims and lines, and the
    record of what was left out is the last attempt. Raises ValueError with the remaining errors when the
    reply has the wrong shape or nothing would be left.
    """
    attempts, feedback = [], None
    for _ in range(repairs + 1):
        try:
            raw = ask(feedback)
        except ResponseFormatError as error:
            # A malformed reply uses one bounded repair attempt instead of stopping the run.
            raw, result = {"unparsed_response": error.raw}, Result(errors=[str(error)])
        else:
            result = validator(raw) if validator else check(raw, texts, facts)
        attempts.append({"output": raw, "errors": result.errors})
        if on_attempt:on_attempt(attempts)
        if result.ok:
            if hasattr(result,'output'):return {**result.output,'claim_attempts':len(attempts)},attempts
            return {"claims": raw["claims"], "template": raw["draft"], "draft": result.rendered,
                    "claim_attempts": len(attempts)}, attempts
        feedback = result.repair_message()
    # One claim of forty that still fails stopped a whole run on 2026-11-19. A missing claim costs nothing in
    # the audit, and a run that stops publishes nothing, so the latest reply that can be mended this way is
    # checked again without its failing claims and lines.
    for number in range(len(attempts), 0, -1):
        trimmed = without_failing(attempts[number - 1]["output"], attempts[number - 1]["errors"])
        if trimmed is None:
            continue
        reply, left_out, lines = trimmed
        checked = validator(reply) if validator else check(reply, texts, facts)
        if not checked.ok:
            continue
        attempts.append({"output": reply, "errors": [], "left_out": left_out, "left_out_lines": lines,
                         "from_attempt": number})
        if on_attempt:on_attempt(attempts)
        if hasattr(checked,'output'):return {**checked.output,'claim_attempts':len(attempts)},attempts
        return {"claims": reply["claims"], "template": reply["draft"], "draft": checked.rendered,
                "claim_attempts": len(attempts)}, attempts
    raise ValueError("Role claims still fail after repairs:\n- " + "\n- ".join(result.errors))
