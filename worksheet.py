#!/usr/bin/env python3
"""The worksheet skill: one name's facts, owner cash flow, a value range against the price, and a view.

It runs on a saved run of the agent team and reads only what that run saved. Code fills the facts and does the
arithmetic, and prints the arithmetic. One model call, with the persona a team member wrote, writes the judgment
and chooses the view. No model computes a number.

Three files are written by hand, by a team member, and no AI writes them:
  the worksheet file (the method, its rates, the client's purchase size, the conviction rule),
  the persona file, and, for the seeker, the factors file.
Their places are in .env (WORKSHEET_FILE, PERSONA_FILE), or client/worksheet.json and client/persona.md.

Every line that states a number ends with its source in square brackets, so that the hook (hook.py) can check it:
  [fact: TAG, START to END]   a fact in the run's facts.json
  [computed: ARITHMETIC]      recomputed from the numbers printed above it
  [rate: KEY]                 a value in the worksheet file
  [price: price.json]         the close that the run saved
  [reader: liquidity.json]    what the closes reader returned, as the worksheet saved it
  [line: FILE, "TEXT"]        a line of a filing that the run saved
  [worksheet: LABEL]          a number printed on an earlier line of this worksheet

Run it on a saved run:  python worksheet.py output/TICKER_DATE_TIME
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
METHOD = "owner cash flow divided by a rate"
# What the worksheet file must hold. A team member writes each value by hand.
REQUIRED = {
    "method": "the name of the method; this code knows one: " + METHOD,
    "owner_cash_flow_years": "how many fiscal years of owner cash flow are averaged, 1 to 3",
    "low_rate": "the rate of the low case, as a fraction: 0.10 is 10%",
    "mid_rate": "the rate of the mid case, as a fraction",
    "purchase_size": "the client's purchase size, in dollars",
    "liquidity_days": "how many trading days of dollar volume the liquidity line reads",
    "liquidity_share_of_daily_volume": "the largest share of one day's dollar volume the client may buy, as a fraction",
    "conviction_rule": "in words: what makes a conviction high, and what makes it low",
}
NUMBER = re.compile(r"\(?-?\$?\d(?:[\d,]*\d)?(?:\.\d+)?\)?[MBK%]?")  # a comma after a number is not part of it
# Digits that name something and claim nothing: a date, a time, an accession number, a form, an exhibit, an item.
IDENTIFIERS = re.compile(
    r"\d{10}-\d{2}-\d{6}|\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(?::\d{2})?|\b[A-Z.]{1,6}_\d{8}_\d{6}(?:_\d+)?\b"
    r"|\b10-K\b|\b10-Q\b|\b8-K\b|\b10-12[BG]\b|\bForm (?:10|4|3)\b|\bExhibit \d+(?:\.\d+)?\b|\bItem \d+(?:\.\d+)?\b|\bCIK \d+\b|\bline \d+\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}\b"
    # A year alone names a column or a period: 2026, and not 2,026 or 2026.5 or $2026.
    r"|(?<![\d,.$])(?:19|20)\d{2}(?!\d|,\d|\.\d|%)",
    re.I,
)


class WorksheetError(RuntimeError):
    """The worksheet cannot be written. The message says what is missing and who writes it."""


def setting(name: str) -> str:
    from lab02_desk import is_placeholder, load_dotenv

    value = os.environ.get(name) or load_dotenv().get(name, "")
    return "" if is_placeholder(value) else value


def client_file(env_name: str, default: str) -> Path:
    """A hand-written file: its place from .env, else its place in client/."""
    given = setting(env_name)
    return Path(given).expanduser() if given else HERE / "client" / default


def load_method(path: Path) -> dict[str, Any]:
    """The worksheet file. It stops when the file is missing, when a value is missing, or when it names a method
    this code does not know. Code never fills a value the team did not write."""
    if not path.is_file():
        raise WorksheetError(f"The worksheet file is missing: {path}. A team member writes it by hand; no AI writes it. "
                             f"client/README.md gives its shape.")
    try:
        method = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise WorksheetError(f"The worksheet file {path} is not valid JSON ({exc}).") from exc
    missing = [f"{key} ({what})" for key, what in REQUIRED.items() if method.get(key) in (None, "")]
    if missing:
        raise WorksheetError(f"The worksheet file {path} does not state: " + "; ".join(missing) + ".")
    if str(method["method"]).strip().lower() != METHOD:
        raise WorksheetError(f"The worksheet file names the method \"{method['method']}\". This code knows one method: \"{METHOD}\".")
    for key in ("low_rate", "mid_rate", "liquidity_share_of_daily_volume"):
        if not 0 < float(method[key]) < 1:
            raise WorksheetError(f"{key} in {path} must be a fraction between 0 and 1, as 0.10 for 10%.")
    if not 1 <= int(method["owner_cash_flow_years"]) <= 3:
        raise WorksheetError(f"owner_cash_flow_years in {path} must be 1, 2 or 3: a run saves three fiscal years at most.")
    return method


def load_persona(path: Path) -> str:
    if not path.is_file() or not path.read_text(encoding="utf-8-sig").strip():
        raise WorksheetError(f"The persona file is missing or empty: {path}. A team member writes it by hand; no AI writes it.")
    return path.read_text(encoding="utf-8-sig").strip()


def eastern_iso(accepted: str | None) -> str:
    """EDGAR's "Accepted" time, which is Eastern and has no offset, as ISO 8601 with its offset."""
    if not accepted:
        return ""
    from live_record import eastern

    return datetime.strptime(accepted, "%Y-%m-%d %H:%M:%S").replace(tzinfo=eastern()).isoformat()


# ----- how a number is written, and read back -----

def millions(value: float) -> str:
    return f"{value / 1e6:,.1f}"


def as_number(text: str) -> float | None:
    """The value a printed number has: "$13,267.0M" is 13267.0 (in millions), "10.00%" is 10.0, "(5.2)" is -5.2."""
    found = NUMBER.search(text)
    if not found:
        return None
    token = found.group(0)
    negative = token.startswith("(") and token.endswith(")") or "-" in token[:3]
    digits = re.sub(r"[^\d.]", "", token)
    return (-1 if negative else 1) * float(digits) if digits else None


def numbers_in(text: str) -> list[str]:
    """Every number written in the text, as written, without the digits that only name something."""
    return [m.group(0) for m in NUMBER.finditer(IDENTIFIERS.sub(" ", text))]


def bare(token: str) -> str:
    """A number without its sign, its dollar sign and its scale letter: how two printed numbers are compared."""
    return re.sub(r"[^\d.]", "", token).rstrip(".")


# ----- the worksheet -----

class Worksheet:
    """One worksheet for one saved run. build() returns its lines; save() writes worksheet.md, view.json and, when
    the reader gave volumes, liquidity.json."""

    def __init__(self, run_dir: Path, model: Any, method: dict[str, Any], persona: str, method_path: Path, persona_path: Path,
                 registry: dict[str, Any] | None = None, bars: Any = None, now: datetime | None = None, tools: str = "Claude Code") -> None:
        self.run_dir = run_dir
        self.model = model
        self.tools = tools  # the coding tools named on the closing lines
        self.method = method
        self.persona = persona
        self.method_path, self.persona_path = method_path, persona_path
        self.registry = registry or {}
        self.bars = bars  # a function (ticker, last_day, days) -> the reader's closes and volumes, or None
        self.now = now or datetime.now().astimezone()
        for name in ("facts.json", "verified_report.md"):
            if not (run_dir / name).is_file():
                raise WorksheetError(f"{run_dir} is not a finished run of the agent team: it has no {name}.")
        self.facts = json.loads((run_dir / "facts.json").read_text(encoding="utf-8"))
        self.ticker = str(self.facts.get("ticker") or "")
        self.company = str(self.facts.get("company") or self.ticker)
        steps = run_dir / "nodes" / "01_steps.json"
        self.steps = json.loads(steps.read_text(encoding="utf-8")).get("output", {}) if steps.is_file() else {}
        price_file = run_dir / "price.json"
        self.price_record = json.loads(price_file.read_text(encoding="utf-8")) if price_file.is_file() else {}
        self.price = self.price_record.get("price")
        self.lines: list[str] = []
        self.not_known: list[str] = []
        self.printed: dict[str, str] = {}  # label -> the number printed on that line
        self.liquidity: dict[str, Any] | None = None
        self.view: dict[str, Any] = {}

    # --- lines ---

    def add(self, label: str, shown: str, source: str, tail: str = "") -> None:
        """One line that states one number, with its source for the hook."""
        self.printed[label] = shown
        self.lines.append(f"- {label}: {shown}{tail} [{source}]")

    def say(self, text: str) -> None:
        self.lines.append(text)

    def unknown(self, label: str, why: str) -> None:
        self.lines.append(f"- {label}: not known. {why}")
        self.not_known.append(f"{label}: {why}")

    # --- the parts ---

    def build(self) -> list[str]:
        self.say(f"# {self.company} ({self.ticker}): worksheet, {self.now:%Y-%m-%d %H:%M:%S} {self.now.tzname()}")
        self.say("Screens to look at, not a recommendation.")
        self.say(f"Saved run: {self.run_dir.name}. Worksheet file: {self.method_path.name}. Persona file: {self.persona_path.name}.")
        self.say("")
        self.spinoff_facts()
        self.statement_facts()
        self.release_facts()
        self.value_range()
        self.judgment()
        self.can_you_buy_it()
        self.the_view()
        self.say("")
        self.say("## Not known")
        self.lines += [f"- {item}" for item in self.not_known] or ["- Nothing the worksheet looked for is missing."]
        # The course's three closing lines, with the tools that made this worksheet.
        vendor, name = getattr(self.model, "vendor", "Anthropic"), getattr(self.model, "model", "")
        self.lines += ["", "This is a learning exercise, not financial advice.", "",
                       f"AI assistance: {self.tools} (desk code); {vendor} {name} (the persona's judgment). I verified the sources myself; the judgments are mine.",
                       "", "Any remaining errors are my own."]
        return self.lines

    def spinoff_facts(self) -> None:
        self.say("## Facts of the spinoff")
        row = self.registry.get(self.ticker.upper())
        if not row:
            self.say("- Not applicable. The ticker is not in the seeker's registry, so the worksheet has no parent, ratio or distribution date to state.")
            self.say("")
            return
        for label, key in (("Parent", "parent"), ("Distribution ratio", "ratio"), ("Record date", "record_date"), ("Distribution date", "distribution_date")):
            fact = row.get(key) or {}
            if fact.get("value"):
                self.say(f"- {label}: {fact['value']} (registry: {fact.get('filing', 'no filing')}, {fact.get('section', 'no section')})")
            else:
                self.unknown(label, "The seeker's registry holds no value for it.")
        for label in ("Debt raised, and where the cash went", "Liabilities and restrictions the parent left", "Insiders' open-market purchases (Form 4, code P)"):
            self.unknown(label, "This worksheet does not read it from the filing yet.")
        self.say("")

    def years(self, name: str) -> list[dict[str, Any]]:
        item = (self.facts.get("worksheet") or {}).get(name)
        return item["years"] if item else []

    def tag(self, name: str) -> str:
        return "us-gaap:" + (self.facts.get("worksheet") or {})[name]["tag"]

    def statement_facts(self) -> None:
        self.say("## Facts from the 10-K's statements, historical")
        if self.facts.get("not_stated"):
            self.unknown("The annual facts", f"The run states none: {self.facts['not_stated']}.")
            self.say("")
            return
        names = {"net_income": "Net income", "depreciation": "Depreciation and amortization", "capex": "Capital spending"}
        want = int(self.method["owner_cash_flow_years"])
        for name, label in names.items():
            years = self.years(name)[:want]
            if not years:
                self.unknown(label, "The 10-K's facts hold no full-year amount under the tags the desk reads.")
            for fact in years:
                self.add(f"{label}, fiscal year ended {fact['end']}", f"${millions(fact['val'])}M", f"fact: {self.tag(name)}, {fact['start']} to {fact['end']}")
        shares = self.years("diluted_shares")[:1]
        if shares:
            fact = shares[0]
            self.add(f"Diluted shares, fiscal year ended {fact['end']}", f"{millions(fact['val'])}M", f"fact: {self.tag('diluted_shares')}, {fact['start']} to {fact['end']}")
        else:
            self.unknown("Diluted shares", "The 10-K's facts hold no weighted-average diluted share count.")
        if self.price is not None:
            self.add("Price", f"${float(self.price):,.2f}", "price: price.json", tail=f" ({self.price_note()})")
        else:
            self.say(f"- Price: not computed. The run has no close ({self.price_record.get('note') or 'no price was saved'}).")
            self.not_known.append("Price: the run has no close, so the price lines and the view are not computed.")
        self.say("")

    def price_note(self) -> str:
        """Where the close came from, without the amount: the amount is stated once, with its source."""
        note = str(self.price_record.get("note") or "")
        return re.sub(r"^\$[\d,.]+,\s*", "", note) or "the close the run saved"

    def release_facts(self) -> None:
        self.say("## Facts from the earnings release")
        q = self.steps.get("quarter") or {}
        release = next(iter(sorted(self.run_dir.glob("8K_*.txt"))), None)
        name = release.name if release else "the saved release"
        if q.get("revenue") is not None and q.get("revenue_line"):
            self.add(f"Revenue of the quarter ({q.get('period') or 'the latest column'}), in {q.get('units') or 'the release units'}",
                     str(q.get("revenue_shown") or f"{q['revenue']:,.0f}"), f"line: {name}, \"{q['revenue_line']}\"")
            if q.get("revenue_growth") is not None and q.get("revenue_prior_shown"):
                self.add("Growth of the quarter's revenue on the same quarter last year", f"{q['revenue_growth']:.2%}",
                         f"computed: {q['revenue_shown']} / {q['revenue_prior_shown']} - 1")
        else:
            self.unknown("Revenue of the quarter", "The run did not read it from the release.")
        if q.get("eps") is not None and q.get("eps_line"):
            self.add("Diluted EPS of the quarter, GAAP", str(q.get("eps_shown") or f"${q['eps']:.2f}"), f"line: {name}, \"{q['eps_line']}\"")
        else:
            self.unknown("Diluted EPS of the quarter", "The run did not read it from the release.")
        self.say("")

    def value_range(self) -> None:
        m = self.method
        self.say("## Value range")
        self.say(f"- Method, from the worksheet file: {METHOD}. Owner cash flow is net income plus depreciation and amortization minus capital spending.")
        self.add("Rate of the low case", f"{float(m['low_rate']):.2%}", "rate: low_rate")
        self.add("Rate of the mid case", f"{float(m['mid_rate']):.2%}", "rate: mid_rate")
        want = int(m["owner_cash_flow_years"])
        parts = {name: {f["end"]: f["val"] for f in self.years(name)} for name in ("net_income", "depreciation", "capex")}
        ends = [f["end"] for f in self.years("net_income")[:want]]
        full = [end for end in ends if all(end in parts[name] for name in parts)]
        if len(full) < want:
            # The reason holds no number: every number in the worksheet has a source.
            why = "The method asks for more fiscal years with net income, depreciation and capital spending than the run saved."
            self.say(f"- Owner cash flow: not computed. {why}")
            self.not_known.append(f"Owner cash flow and the value range: {why}")
            self.say("")
            return
        flows = []
        for end in full:
            terms = [round(parts[name][end] / 1e6, 1) for name in ("net_income", "depreciation", "capex")]
            flow = round(terms[0] + terms[1] - terms[2], 1)
            flows.append(flow)
            self.add(f"Owner cash flow, fiscal year ended {end}", f"${flow:,.1f}M", f"computed: {terms[0]:,.1f} + {terms[1]:,.1f} - {terms[2]:,.1f}")
        if want > 1:
            average = round(sum(flows) / want, 1)
            self.add("Owner cash flow, the average of the fiscal years above", f"${average:,.1f}M",
                     "computed: (" + " + ".join(f"{flow:,.1f}" for flow in flows) + f") / {want}")
        else:
            average = flows[0]
        if average <= 0:
            why = "Owner cash flow is not above zero, and the method divides it by a rate."
            self.say(f"- Low case and mid case: not computed. {why}")
            self.not_known.append(f"The value range: {why}")
            self.say("")
            return
        cases = {}
        for case in ("low", "mid"):
            rate = float(m[f"{case}_rate"])
            cases[case] = round(average / rate, 1)
            self.add(f"{case.capitalize()} case, value", f"${cases[case]:,.1f}M", f"computed: {average:,.1f} / {rate:g}")
        shares = self.years("diluted_shares")[:1]
        if not shares:
            self.say("- Low case and mid case, per share: not computed. The run saved no diluted share count.")
            self.say("")
            return
        count = round(shares[0]["val"] / 1e6, 1)
        per_share = {}
        for case in ("low", "mid"):
            per_share[case] = round(cases[case] / count, 2)
            self.add(f"{case.capitalize()} case, per share", f"${per_share[case]:,.2f}", f"computed: {cases[case]:,.1f} / {count:,.1f}")
        if self.price is None:
            self.say("- Price against the low case: not computed. The run has no close.")
        else:
            gap = float(self.price) / per_share["low"] - 1
            words = "above" if gap >= 0 else "below"
            self.add("Price against the low case", f"{abs(gap):.2%}", f"computed: {float(self.price):,.2f} / {per_share['low']:,.2f} - 1", tail=f" {words} the low case")
        self.say("")

    def judgment(self) -> None:
        """The one model call. The persona receives the lines above and nothing else. A number it writes must be
        a number those lines print; when it is not, the judgment is left out and the view is not computed."""
        self.say("## Why it may be cheap, or why it is not that story")
        given = [line for line in self.lines if line.startswith("- ") or line.startswith("## ")]
        packet = {
            "task": "Write the judgment for this worksheet, as your persona. Then choose the view on the earnings release: is the company "
                    "worth more or less than the price? Name the one number that decides it, and state a conviction by the conviction rule.",
            "context": {"worksheet_lines": given, "conviction_rule": self.method["conviction_rule"]},
            "expected_output": {
                "why": "Two to five sentences: why the name may be cheap, or why it is not that story.",
                "what_would_change_the_view": "One sentence: what in the next filing would change the view.",
                "view": "more or less",
                "deciding_label": "The label of the worksheet line whose number decides the view, copied exactly, without the leading dash.",
                "conviction": "high or low",
                "conviction_reason": "One sentence that applies the conviction rule.",
            },
        }
        rules = ("\n\nRules of the worksheet, fixed in code:\n- Reply with one JSON object and nothing else.\n"
                 "- You may quote a number only as a worksheet line prints it. Never compute a number, and never write one from memory.\n"
                 "- Write no other digit. A score, a count or the number of a criterion is written as a word.\n"
                 "- You see the worksheet's lines and nothing else.")
        reply = self.model.ask("Worksheet (persona)", self.persona + rules, packet)
        allowed = {bare(token) for line in given for token in numbers_in(line)}
        text = {key: str(reply.get(key) or "").strip() for key in ("why", "what_would_change_the_view", "conviction_reason")}
        foreign = sorted({token for value in text.values() for token in numbers_in(value) if bare(token) not in allowed})
        self.problem = ""
        if foreign:
            # The number itself is not repeated here: it has no source. It is kept in view.json.
            self.problem = "the persona wrote a number that the worksheet does not print"
        elif not text["why"] or not text["what_would_change_the_view"]:
            self.problem = "the persona gave no judgment"
        if self.problem:
            self.say(f"- Not written: {self.problem}.")
            self.not_known.append(f"The judgment: {self.problem}.")
            self.reply = {}
            self.foreign = foreign
        else:
            self.say(text["why"])
            self.say(f"What would change the view: {text['what_would_change_the_view']}")
            self.reply = dict(reply, **text)
        self.say("")

    def can_you_buy_it(self) -> None:
        """The liquidity line, in code, after the model call: the persona never sees it."""
        m = self.method
        self.say("## Can you buy it")
        self.add("The client's purchase size", f"${float(m['purchase_size']):,.0f}", "rate: purchase_size")
        self.add("Trading days the worksheet file asks for", f"{int(m['liquidity_days'])}", "rate: liquidity_days")
        self.add("Largest share of a day's dollar volume", f"{float(m['liquidity_share_of_daily_volume']):.2%}", "rate: liquidity_share_of_daily_volume")
        day = self.price_day()
        rows = self.bars(self.ticker, day, int(m["liquidity_days"])) if self.bars and day else None
        if not rows or isinstance(rows, str):
            self.unknown("Median daily dollar volume", "The closes reader gave no closes with volumes." if day else "The run has no close, so no last trading day.")
            self.say("")
            return
        series, source = rows
        median = round(statistics.median(close * volume for _, close, volume in series) / 1e6, 1)
        self.liquidity = {"median_dollar_volume_millions": median, "days": len(series), "from": str(series[0][0]), "to": str(series[-1][0]), "source": source}
        # One number on a line, each with its own source.
        self.add("Trading days the reader gave", f"{len(series)}", "reader: liquidity.json, days")
        self.add(f"Median daily dollar volume of those days, to {series[-1][0]}, from {source}", f"${median:,.1f}M",
                 "reader: liquidity.json, median_dollar_volume_millions")
        limit = round(median * float(m["liquidity_share_of_daily_volume"]), 1)
        self.add("The most the client may buy in one day", f"${limit:,.1f}M", f"computed: {median:,.1f} * {float(m['liquidity_share_of_daily_volume']):g}")
        size = float(m["purchase_size"]) / 1e6
        self.say(f"- At the purchase size: {'buyable in one day' if size <= limit else 'not buyable in one day'}, by the worksheet file's limit.")
        self.say("")

    def price_day(self) -> date | None:
        found = re.search(r"the close of (\d{4}-\d{2}-\d{2})", str(self.price_record.get("note") or ""))
        return date.fromisoformat(found.group(1)) if found else None

    def the_view(self) -> None:
        self.say("## The view on the release")
        reply = getattr(self, "reply", {})
        release = (self.steps.get("filings") or {}).get("8-K") or {}
        # The first four keys are what hit_rate.py reads: the ticker, the release's filing time and the view's own
        # time, each with its UTC offset, and the direction. "up" is worth more than the price; "down" is worth less.
        view = {"ticker": self.ticker, "filing_time": eastern_iso(release.get("accepted_index")), "time": self.now.isoformat(timespec="seconds"),
                "direction": "not computed", "view": "not computed", "number": None, "number_label": None, "conviction": None,
                "price": self.price, "run": self.run_dir.name, "release": release.get("accessionNumber"), "why_not": ""}
        if not view["filing_time"]:
            del view["filing_time"]  # hit_rate.py then reads the time from the report's first line
        label = str(reply.get("deciding_label") or "").strip().lstrip("- ").strip()
        direction = str(reply.get("view") or "").strip().lower()
        if self.price is None:
            view["why_not"] = "the run has no close"
        elif not reply:
            view["why_not"] = getattr(self, "problem", "") or "the persona gave no judgment"
        elif direction not in ("more", "less"):
            view["why_not"] = "the persona did not say more or less"
        elif label not in self.printed:
            view["why_not"] = "the persona named a deciding line that the worksheet does not print"
        if view["why_not"]:
            self.say(f"- View: not computed, because {view['why_not']}.")
            self.not_known.append(f"The view: {view['why_not']}.")
        else:
            view.update(view=direction, direction="up" if direction == "more" else "down", number=self.printed[label], number_label=label)
            self.say(f"- View: the company is worth {direction} than the price.")
            self.add("The number that decides it", self.printed[label], f"worksheet: {label}")
            conviction = str(reply.get("conviction") or "").strip().lower()
            if conviction in ("high", "low"):
                view["conviction"] = conviction
                self.say(f"- Conviction: {conviction}, by the rule in the worksheet file. {reply.get('conviction_reason', '')}".rstrip())
            else:
                self.say("- Conviction: not stated. The persona did not say high or low.")
        self.view = view

    def save(self) -> Path:
        path = self.run_dir / "worksheet.md"
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        (self.run_dir / "view.json").write_text(json.dumps(dict(self.view, numbers_left_out=getattr(self, "foreign", [])), indent=1), encoding="utf-8")
        # The method as the worksheet read it is saved with the run: the hook matches every rate against it, and a
        # reader of an old run sees the rates that made it.
        (self.run_dir / "worksheet_file.json").write_text(json.dumps(self.method, indent=1), encoding="utf-8")
        if self.liquidity:
            (self.run_dir / "liquidity.json").write_text(json.dumps(self.liquidity, indent=1), encoding="utf-8")
        return path


# ----- what the worksheet takes from outside the run -----

def reader_bars(ticker: str, last_day: date, days: int) -> tuple[list[tuple[date, float, float]], str] | str:
    """The last `days` trading days of closes and volumes up to last_day, oldest first, with the source's name.
    Today the source is financialdatasets.ai: the closes reader does not read volumes from LSEG yet.
    The series is used for one median and is not saved: a raw pull stays out of the run folder."""
    import prices

    key = prices.api_key()
    if not key:
        return "not available"
    rows = prices.daily_closes(ticker, last_day - timedelta(days=int(days * 1.6) + 10), last_day, key)
    series = sorted((date.fromisoformat(str(r["time"])[:10]), float(r["close"]), float(r["volume"])) for r in rows if r.get("close") and r.get("volume"))
    return (series[-days:], "financialdatasets.ai") if series else "not available"


def load_registry(path: Path) -> dict[str, Any]:
    """The seeker's registry, by ticker. No registry means that no name is a spinoff the seeker saw."""
    if not path.is_file():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows = rows.get("names", rows) if isinstance(rows, dict) else rows
    return {str(row.get("ticker", "")).upper(): row for row in rows if isinstance(row, dict) and row.get("ticker")}


def run(run_dir: Path, model: Any, bars: Any = reader_bars) -> Path:
    """Write the worksheet for one saved run. Returns its path."""
    method_path, persona_path = client_file("WORKSHEET_FILE", "worksheet.json"), client_file("PERSONA_FILE", "persona.md")
    sheet = Worksheet(run_dir, model, load_method(method_path), load_persona(persona_path), method_path, persona_path,
                      registry=load_registry(HERE / "seeker" / "registry.json"), bars=bars, tools=setting("AI_TOOLS") or "Claude Code")
    sheet.build()
    return sheet.save()


def main() -> int:
    parser = argparse.ArgumentParser(description="The worksheet skill: a value range against the price and a view, on a saved run of the agent team")
    parser.add_argument("run_folder", help="A saved run of the agent team, for example output/TICKER_DATE_TIME")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    started = time.monotonic()
    from lab02_desk import api_key_problem, env_path
    from lab03_app import DEFAULT_MODEL, Model, RoleError

    key = setting("API_KEY") or setting("ANTHROPIC_API_KEY")
    problem = api_key_problem(key, env_path())
    if problem:
        print(problem, file=sys.stderr)
        return 2
    try:
        path = run(Path(args.run_folder), Model(key, setting("MODEL") or DEFAULT_MODEL, setting("EFFORT") or "medium"))
    except (WorksheetError, RoleError) as exc:
        print(f"Worksheet stopped: {exc}", file=sys.stderr)
        return 1
    print(f"Worksheet: {path}")
    print(f"Worksheet: {time.monotonic() - started:.1f} seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
