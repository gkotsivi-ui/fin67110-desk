#!/usr/bin/env python3
"""FIN 67110 Lab 02: SEC filings and XBRL data pipeline (no model calls)."""

from __future__ import annotations

import argparse
import contextlib
import html
import io
import json
import os
import re
import sys
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests

SEC = "https://www.sec.gov"
DATA = "https://data.sec.gov"


HERE = Path(__file__).resolve().parent
# Values that are still as .env.example gives them.
PLACEHOLDERS = ("paste-", "your name", "your.email")


def env_path() -> Path | None:
    """The .env file in the current folder, else the one next to the code; None when there is neither."""
    for folder in (Path.cwd(), HERE):
        if (folder / ".env").is_file():
            return folder / ".env"
    return None


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """The NAME=value lines of .env. It reads UTF-8, UTF-8 with a BOM, and the UTF-16 that Windows PowerShell 5.1 writes."""
    path = path or env_path()
    values: dict[str, str] = {}
    if path is None or not path.is_file():
        return values
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def is_placeholder(value: str) -> bool:
    """True for an empty value, or one that is still as .env.example gives it."""
    text = value.strip().lower()
    return not text or any(p in text for p in PLACEHOLDERS)


def no_env_message() -> str:
    for folder in (Path.cwd(), HERE):
        if (folder / ".env.txt").is_file():
            return f"There is no .env file, but there is {folder / '.env.txt'}. Rename it to .env (Notepad adds .txt), then retry."
    return (f"There is no .env file in {Path.cwd()}. Copy .env.example to .env in the repository folder, "
            "fill it in, and run the commands from that folder.")


def user_agent_problem(agent: str, where: Path | None) -> str | None:
    """Why SEC EDGAR would refuse SEC_USER_AGENT; None when it holds a name and an email."""
    if agent and not is_placeholder(agent) and "@" in agent:
        return None
    if where is None and not agent:
        return no_env_message()
    return (f"SEC_USER_AGENT in {where or 'the environment'} needs your own name and email, "
            "as in SEC_USER_AGENT=Your Name your.email@purdue.edu. SEC EDGAR refuses requests without them.")


def provider_of(key: str) -> str:
    """The model provider an API key belongs to, from the key's prefix."""
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("AIza"):
        return "google"
    if key.startswith("sk-"):
        return "openai"
    return ""


def api_key_problem(key: str, where: Path | None) -> str | None:
    """Why API_KEY cannot run the roles; None for an Anthropic key or a Google AI Studio key."""
    provider = provider_of(key)
    if provider in ("anthropic", "google"):
        return None
    if where is None and not key:
        return no_env_message()
    place = where or "the environment"
    if is_placeholder(key):
        return (f"API_KEY in {place} is empty or still the example. Paste your Anthropic key (it starts with sk-ant-) "
                "or your Google AI Studio key (it starts with AIza), or run python set_keys.py.")
    kind = "an OpenAI key" if provider == "openai" else "not a key this desk can use"
    return (f"API_KEY in {place} is {kind}. The roles and the Verifier run on Anthropic's API (a key that starts with sk-ant-, "
            "from platform.claude.com) or on Google's Gemini API (a key that starts with AIza, from aistudio.google.com). "
            "The seven steps alone (lab02_desk.py) need no model key.")


CELL_BREAK = "\x01"  # a block tag inside a table cell; see html_to_text


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.cells = 0
        self.pre = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "ix:header"}:
            self.skip += 1
        elif tag == "pre":
            self.pre += 1
        elif tag in {"td", "th"}:
            # Mark each table cell so a row prints as "Total revenue | 95,723 | 86,156".
            self.cells += 1
            self.parts.append("\t")
        elif tag == "tr":
            self.parts.append("\n")
        elif tag in {"p", "div", "li", "br", "h1", "h2", "h3"}:
            self.parts.append(CELL_BREAK if self.cells else "\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "ix:header"} and self.skip:
            self.skip -= 1
        elif tag == "pre" and self.pre:
            self.pre -= 1
        elif tag in {"td", "th"}:
            self.cells = max(0, self.cells - 1)
        elif tag == "tr":
            self.parts.append("\n")
        elif tag in {"p", "div", "li", "br", "h1", "h2", "h3"}:
            self.parts.append(CELL_BREAK if self.cells else "\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            # A line break in HTML source is a space; only <pre> keeps its lines.
            self.parts.append(data if self.pre else data.replace("\r", " ").replace("\n", " "))


def html_to_text(content: str) -> str:
    parser = TextExtractor()
    parser.feed(content)
    lines = []
    for row in "".join(parser.parts).splitlines():
        # A row of several cells stays on one line, so a label wrapped in a <div> keeps its numbers.
        # A single cell used for page layout keeps its paragraphs as lines.
        pieces = [row.replace(CELL_BREAK, " ")] if row.count("\t") > 1 else row.split(CELL_BREAK)
        lines += [join_cells(piece.split("\t")) for piece in pieces]
    return "\n".join(line for line in lines if line)


def join_cells(cells: list[str]) -> str:
    """Join one line's table cells with " | ", keeping "$" with its number and ")" or "%" with theirs."""
    out: list[str] = []
    for cell in (re.sub(r"\s+", " ", html.unescape(c)).strip() for c in cells):
        if not cell:
            continue
        if out and (out[-1] in {"$", "($", "$("} or cell in {")", "%", ")%", "%)"}):
            out[-1] += cell
        else:
            out.append(cell)
    return " | ".join(out)


def is_annual(fact: dict[str, Any]) -> bool:
    """True for a balance-sheet instant or a duration of one fiscal year (52 or 53 weeks)."""
    if not fact.get("start"):
        return True
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    return 340 <= days <= 390


def millions(value: float | None) -> str:
    return f"{value / 1e6:,.1f}" if value is not None else "n/a"


def numbers_in(line: str) -> list[float]:
    """The numeric cells of a table row after its label, without percentages; "(1.2)" is negative."""
    values = []
    for cell in line.split(" | ")[1:]:
        match = re.fullmatch(r"\$?\(?\$?\s?(\d[\d,]*(?:\.\d+)?)\)?", cell.strip())
        if match:
            value = float(match.group(1).replace(",", ""))
            values.append(-value if "(" in cell else value)
    return values


class Desk:
    def __init__(self, user_agent: str, outdir: Path) -> None:
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.outdir = outdir
        self.company: str = ""
        self.ticker: str = ""
        self.cik: str = ""
        self.submissions: dict[str, Any] = {}
        self.filings: dict[str, dict[str, str]] = {}
        self.facts: dict[str, Any] = {}
        self.selected: dict[str, dict[str, str]] = {}
        self.skipped_8k: list[dict[str, str]] = []
        self.fact_rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.ratios: list[dict[str, Any]] = []
        self.quarter: dict[str, Any] = {}
        self.peers: list[dict[str, Any]] = []

    def get_json(self, url: str) -> Any:
        response = self.http.get(url, timeout=45)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str) -> str:
        response = self.http.get(url, timeout=45)
        response.raise_for_status()
        return response.text

    @staticmethod
    def accession_path(accession: str) -> str:
        return accession.replace("-", "")

    def step1(self) -> None:
        print("\n[1/7] Resolve ticker to CIK")
        companies = self.get_json(f"{SEC}/files/company_tickers.json")
        match = next((v for v in companies.values() if v["ticker"].upper() == self.ticker), None)
        if not match:
            raise ValueError(f"Ticker {self.ticker} was not found in SEC company_tickers.json")
        self.cik = f"{int(match['cik_str']):010d}"
        self.company = match["title"]
        print(f"{self.ticker} -> CIK {self.cik} -> {self.company}")

    def step2(self) -> None:
        print("\n[2/7] Find latest 10-K, 10-Q, and earnings 8-K (Item 2.02)")
        self.submissions = self.get_json(f"{DATA}/submissions/CIK{self.cik}.json")
        rows = self.filing_rows(self.submissions["filings"]["recent"])
        rows.sort(key=lambda row: row["filingDate"], reverse=True)
        self.select_filings(rows)
        if len(self.selected) != 3:
            # The recent list covers about a year of filings; older ones sit in archived files.
            for file in self.submissions["filings"].get("files", []):
                # Archived submissions files contain the arrays directly, unlike the
                # current CIK submissions response, which wraps them in filings.recent.
                rows += self.filing_rows(self.get_json(f"{DATA}/submissions/{file['name']}"))
            rows.sort(key=lambda row: row["filingDate"], reverse=True)
            self.select_filings(rows)
        self.filings = {row["accessionNumber"]: row for row in rows}
        if len(self.selected) != 3:
            raise RuntimeError("Could not find all three required filings (latest 10-K, 10-Q, earnings 8-K Item 2.02).")
        for form, row in self.selected.items():
            self.fetch_index_acceptance(row)
            accepted = f"{row['accepted_index']} (index page, Eastern)" if row.get("accepted_index") else f"{row['acceptanceDateTime']} (submissions API, UTC)"
            period = "Item 2.02" if form == "8-K" else f"period {row['reportDate']}"
            print(f"{form}: accession {row['accessionNumber']} | filed {row['filingDate']} | {period} | accepted {accepted}")
        for row in self.skipped_8k:
            print(f"  skipped newer 8-K {row['accessionNumber']} filed {row['filingDate']} (items {row['items'] or 'not listed'}): no Item 2.02")

    @staticmethod
    def filing_rows(rec: dict[str, Any]) -> list[dict[str, str]]:
        keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument", "acceptanceDateTime", "items")
        count = len(rec["form"])
        return [{key: str(rec.get(key, [""] * count)[i]) for key in keys} for i in range(count)]

    def select_filings(self, rows: list[dict[str, str]]) -> None:
        self.selected, self.skipped_8k = {}, []
        for form in ("10-K", "10-Q"):
            found = next((r for r in rows if r["form"] == form), None)
            if found:
                self.selected[form] = found
        for row in rows:
            if row["form"] != "8-K":
                continue
            # EDGAR lists each 8-K's items; read the document only when the list is empty.
            if row["items"]:
                earnings = "2.02" in row["items"].split(",")
            else:
                body = self.get_text(self.filing_url(row, row["primaryDocument"]))
                earnings = bool(re.search(r"Item\s+2\.02\b", html_to_text(body), re.I))
            if earnings:
                self.selected["8-K"] = row
                break
            self.skipped_8k.append(row)

    def filing_url(self, row: dict[str, str], filename: str) -> str:
        return f"{SEC}/Archives/edgar/data/{int(self.cik)}/{self.accession_path(row['accessionNumber'])}/{filename}"

    def fetch_index_acceptance(self, row: dict[str, str]) -> None:
        url = f"{SEC}/Archives/edgar/data/{int(self.cik)}/{self.accession_path(row['accessionNumber'])}/{row['accessionNumber']}-index.html"
        try:
            page = html_to_text(self.get_text(url))
            m = re.search(r"Accepted\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", page, re.I)
            if m:
                row["accepted_index"] = m.group(1)
        except requests.RequestException:
            pass

    def step3(self) -> None:
        print("\n[3/7] Download filings and extract Exhibit 99.1")
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.selected["8-K"]["exhibit99_1"] = self.find_exhibit(self.selected["8-K"])
        for form in ("10-K", "10-Q", "8-K"):
            row = self.selected[form]
            name = row["primaryDocument"]
            if form == "8-K":
                name = row["exhibit99_1"]
            raw = self.get_text(self.filing_url(row, name))
            text = html_to_text(raw) if "<html" in raw[:1000].lower() or "<document" in raw[:1000].lower() else raw
            path = self.outdir / f"{form.replace('-', '')}_{row['filingDate']}_{Path(name).stem}.txt"
            path.write_text(text, encoding="utf-8")
            row["saved_text"] = str(path)
            print(f"{form}: {name} -> {path}")

    def find_exhibit(self, row: dict[str, str]) -> str:
        base = f"{SEC}/Archives/edgar/data/{int(self.cik)}/{self.accession_path(row['accessionNumber'])}"
        # The filing index labels each document's exhibit type, so read it first.
        # Many issuers use descriptive names (for example, earningsrelease.htm).
        try:
            index_url = f"{base}/{row['accessionNumber']}-index.html"
            index_html = self.get_text(index_url)
            for table_row in re.findall(r"<tr\b[^>]*>.*?</tr>", index_html, re.I | re.S):
                if not re.search(r"EX[- ]?99\.1\b", html_to_text(table_row), re.I):
                    continue
                links = re.findall(r"href=[\"']([^\"']+)[\"']", table_row, re.I)
                for href in links:
                    filename = Path(href.split("?", 1)[0]).name
                    if filename and filename != row["primaryDocument"]:
                        return filename
        except requests.RequestException:
            pass
        # Without an index page, guess from the file names in the filing directory.
        try:
            listing = self.get_json(f"{base}/index.json")
            items = listing["directory"]["item"]
            names = [x["name"] for x in items if x.get("type") != "dir"]
            candidates = [n for n in names if re.search(r"(?:ex|exhibit)[-_]?99[._-]?1|99[._-]1", n, re.I) and n != row["primaryDocument"]]
            if candidates:
                return candidates[0]
        except (requests.RequestException, ValueError, KeyError):
            pass
        # Fall back to the filing's document links and identify the exhibit by its label.
        body = self.get_text(self.filing_url(row, row["primaryDocument"]))
        links = re.findall(r"href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a", body, re.I | re.S)
        for href, label in links:
            if re.search(r"Exhibit\s+99\.1|EX-99\.1", html_to_text(label), re.I):
                return Path(href).name
        raise RuntimeError("Could not locate the 8-K's Exhibit 99.1 in the SEC filing directory.")

    def step4(self) -> None:
        print("\n[4/7] Read latest fiscal-year XBRL facts")
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.facts = self.get_json(f"{DATA}/api/xbrl/companyfacts/CIK{self.cik}.json")
        facts = self.facts["facts"].get("us-gaap", {})
        # Candidate tags in order of preference: the newest latest year wins, and a tie goes to
        # the earlier tag (total revenues under Revenues before net sales under the contract tag).
        choices = {
            "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "RevenuesNetOfInterestExpense"],
            "operating_income": ["OperatingIncomeLoss"],
            "net_income": ["NetIncomeLoss", "ProfitLoss"],
            "diluted_eps": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
            "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
            "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"],
            "current_debt": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
            "cash_from_operations": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
            "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
        }
        chosen = {label: self.choose_fact(facts, tags, label) for label, tags in choices.items()}
        # Revenue is the fiscal-year anchor; all duration facts must share its exact periods.
        rev = chosen["revenue"]
        if not rev:
            raise RuntimeError("No supported revenue tag found in SEC company facts.")
        current_end = rev["current"]["end"]
        prior_end = rev["prior"]["end"] if rev.get("prior") else None
        for label, item in chosen.items():
            if item and label not in {"equity", "long_term_debt", "current_debt"}:
                item["current"] = self.match_period(item["all"], current_end, duration=True)
                item["prior"] = self.match_period(item["all"], prior_end, duration=True) if prior_end else None
        # Balance sheet concepts are instant facts at each fiscal year end.
        for label in ("equity", "long_term_debt", "current_debt"):
            item = chosen[label]
            if item:
                item["current"] = self.match_period(item["all"], current_end, duration=False)
                item["prior"] = self.match_period(item["all"], prior_end, duration=False) if prior_end else None
        self.fact_rows = chosen
        self.print_facts(chosen)
        self.check_year_end(chosen)
        out = {
            "company": self.company,
            "ticker": self.ticker,
            "cik": self.cik,
            "fiscal_year_end": current_end,
            "ten_k": self.selected.get("10-K", {}).get("accessionNumber"),
            "facts": {name: self.public(item) for name, item in chosen.items()},
        }
        (self.outdir / "facts.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Saved XBRL facts: {self.outdir / 'facts.json'}")

    def choose_fact(self, facts: dict[str, Any], tags: list[str], label: str) -> dict[str, Any] | None:
        candidates = []
        for tag in tags:
            concept = facts.get(tag)
            if not concept:
                continue
            units = concept.get("units", {})
            # Full fiscal years only: a 10-K can also tag a quarter with fp=FY.
            vals = [dict(v, unit=unit) for unit, unitvals in units.items() for v in unitvals if v.get("form") == "10-K" and v.get("fp") == "FY" and is_annual(v)]
            if vals:
                candidates.append((max(v["end"] for v in vals), tag, concept, vals))
        if not candidates:
            print(f"  {label}: no candidate fact found")
            return None
        _, tag, concept, vals = max(candidates, key=lambda x: x[0])
        latest_end = max(v["end"] for v in vals)
        this = [v for v in vals if v["end"] == latest_end]
        # For repeated filings of the same period, use the most recently filed 10-K.
        this.sort(key=lambda x: x.get("filed", ""), reverse=True)
        current = this[0]
        # The prior year ends about a year earlier. Match it by date: a fact's fy is its filing's year, not its own.
        prior_candidates = [v for v in vals if 350 <= (date.fromisoformat(latest_end) - date.fromisoformat(v["end"])).days <= 380]
        prior = max(prior_candidates, key=lambda v: (v.get("filed", ""), v["end"])) if prior_candidates else None
        return {
            "tag": tag,
            "label": concept.get("label", label),
            "unit": current["unit"],
            "current": current,
            "prior": prior,
            "candidates": {c[1]: c[0] for c in candidates},
            "all": vals,
        }

    @staticmethod
    def public(item: dict[str, Any] | None) -> dict[str, Any] | None:
        """A fact without its full history, as saved to facts.json."""
        return {k: v for k, v in item.items() if k != "all"} if item else None

    def check_year_end(self, chosen: dict[str, dict[str, Any] | None]) -> None:
        year_end = self.selected.get("10-K", {}).get("reportDate")
        if not year_end:
            return
        off = [f"{name} ({item['current']['end']})" for name, item in chosen.items() if item and item.get("current") and item["current"]["end"] != year_end]
        missing = [name for name, item in chosen.items() if not item or not item.get("current")]
        print(f"  Check: every period end equals the 10-K's fiscal year end {year_end}: {'OK' if not off else 'MISMATCH ' + ', '.join(off)}")
        if missing:
            print(f"  Not found for that fiscal year: {', '.join(missing)}")

    @staticmethod
    def match_period(vals: list[dict[str, Any]], end: str | None, duration: bool) -> dict[str, Any] | None:
        if not end:
            return None
        matching = [v for v in vals if v.get("end") == end and (bool(v.get("start")) == duration)]
        if not matching:
            return None
        matching.sort(key=lambda v: (v.get("filed", ""), v.get("accn", "")), reverse=True)
        return matching[0]

    @staticmethod
    def value(item: dict[str, Any] | None, which: str = "current") -> float | None:
        if not item or not item.get(which):
            return None
        return float(item[which]["val"])

    def print_facts(self, chosen: dict[str, dict[str, Any] | None]) -> None:
        for name, item in chosen.items():
            if not item:
                continue
            for period in ("current", "prior"):
                fact = item.get(period)
                if fact:
                    shown = f" (${millions(fact['val'])}M)" if item["unit"] == "USD" else ""
                    print(f"  {name}: {fact['val']} {item['unit']}{shown} | tag={item['tag']} | period={fact.get('start', 'instant')}..{fact['end']} | filing={fact.get('accn')} ({fact.get('filed')})")
            others = [f"{tag} (latest {end})" for tag, end in item.get("candidates", {}).items() if tag != item["tag"]]
            if others:
                print(f"    other candidate tags, not chosen: {', '.join(others)}")

    def step5(self, price: float | None) -> None:
        print("\n[5/7] Calculate ratios from the printed XBRL inputs ($ millions, except per share)")
        f = self.fact_rows
        rev, op, ni, eps, equity = (self.value(f.get(k)) for k in ("revenue", "operating_income", "net_income", "diluted_eps", "equity"))
        prior_rev = self.value(f.get("revenue"), "prior")
        prior_equity = self.value(f.get("equity"), "prior")
        debt_lt = self.value(f.get("long_term_debt")) or 0.0
        debt_cur = self.value(f.get("current_debt")) or 0.0
        debt_terms = f"({millions(debt_lt)} + {millions(debt_cur)})"
        if f.get("long_term_debt") and f["long_term_debt"]["tag"] == "LongTermDebt":
            # This tag already includes current maturities; adding the current portion would count it twice.
            debt_cur, debt_terms = 0.0, f"{millions(debt_lt)} [LongTermDebt includes its current portion]"
        cfo, capex = self.value(f.get("cash_from_operations")), self.value(f.get("capex"))
        avg_equity = ((equity + prior_equity) / 2) if equity is not None and prior_equity is not None else None
        self.ratios = []

        def ratio(label: str, value: float | None, shown: str, arithmetic: str) -> None:
            self.ratios.append({"name": label, "value": value, "shown": shown if value is not None else "unavailable", "arithmetic": arithmetic})
            print(f"  {label}: {shown} = {arithmetic}" if value is not None else f"  {label}: unavailable (missing input)")

        m = millions
        growth = rev / prior_rev - 1 if rev is not None and prior_rev else None
        ratio("Revenue growth", growth, f"{growth:.2%}" if growth is not None else "", f"{m(rev)} / {m(prior_rev)} - 1")
        margin = op / rev if op is not None and rev else None
        ratio("Operating margin", margin, f"{margin:.2%}" if margin is not None else "", f"{m(op)} / {m(rev)}")
        roae = ni / avg_equity if ni is not None and avg_equity else None
        ratio("Return on average equity", roae, f"{roae:.2%}" if roae is not None else "", f"{m(ni)} / (({m(equity)} + {m(prior_equity)}) / 2)")
        dte = (debt_lt + debt_cur) / equity if equity else None
        ratio("Debt to equity", dte, f"{dte:.3f}" if dte is not None else "", f"{debt_terms} / {m(equity)}")
        fcf = cfo - capex if cfo is not None and capex is not None else None
        ratio("Free cash flow", fcf, f"${m(fcf)}M" if fcf is not None else "", f"{m(cfo)} - {m(capex)}")
        pe = price / eps if price is not None and eps else None
        ratio("P/E", pe, f"{pe:.1f}" if pe is not None else "", f"{price:,.2f} / {eps:.2f} (price / diluted EPS)" if pe is not None else "needs --price")
        if self.outdir.exists():
            (self.outdir / "ratios.json").write_text(json.dumps(self.ratios, indent=2), encoding="utf-8")

    def step6(self) -> None:
        print("\n[6/7] Quote quarter revenue and diluted EPS lines from the release")
        path = Path(self.selected["8-K"]["saved_text"])
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Search the income statement first: a reconciliation table above it can repeat the same labels
        # with adjusted figures in its second column.
        start = next((i for i, line in enumerate(lines) if len(line) < 90 and re.search(r"statements? of (income|operations|earnings)|income statements?", line, re.I)), 0)
        order = list(range(start, len(lines))) + list(range(start))
        # A total row first; a release without one states revenue or sales on a row of its own.
        patterns = [r"\s*total\s*(net\s*)?(revenues?|sales)\b", r"\s*(net\s*)?(revenues?|sales)\b"]
        revenue_index = next((i for p in patterns for i in order if re.match(p, lines[i], re.I) and len(numbers_in(lines[i])) >= 2), None)
        print("  Total revenue row:")
        if revenue_index is None:
            print("    No matching table row found; inspect the saved release text manually.")
        else:
            for line in lines[max(0, revenue_index - 6):revenue_index + 1]:
                if line.strip():
                    print(f"    {line.strip()[:500]}")

        eps_index = next((i for i in order if re.match(r"\s*diluted\b.*\d\.\d{2}\b", lines[i], re.I) and numbers_in(lines[i])), None)
        eps_heading = None
        if eps_index is not None:
            eps_heading = next((i for i in range(eps_index - 1, max(-1, eps_index - 6), -1) if re.search(r"net income per common share|earnings per share", lines[i], re.I)), None)
        print("  Diluted EPS row:")
        if eps_index is None:
            print("    No matching table row found; inspect the saved release text manually.")
        else:
            if eps_heading is not None:
                print(f"    {lines[eps_heading].strip()}")
            print(f"    {lines[eps_index].strip()[:500]}")

        # The release's own sentence, which reads word for word in the filing.
        sentence = next((line for line in lines if re.search(r"per diluted share|diluted (?:earnings|EPS|net income) per", line, re.I) and re.search(r"\$\s?\d", line)), None)
        if sentence:
            flag = " (mentions adjusted or non-GAAP figures; claim 11 is GAAP)" if re.search(r"adjusted|non-GAAP", sentence, re.I) else ""
            print(f"  Release sentence{flag}:\n    {sentence.strip()[:700]}")

        self.quarter = {
            "revenue_line": lines[revenue_index].strip() if revenue_index is not None else None,
            "revenue_headers": [x.strip() for x in lines[max(0, revenue_index - 6):revenue_index] if x.strip()] if revenue_index is not None else [],
            "eps_line": lines[eps_index].strip() if eps_index is not None else None,
            "eps_heading": lines[eps_heading].strip() if eps_heading is not None else None,
            "sentence": sentence.strip() if sentence else None,
        }
        revenue = numbers_in(lines[revenue_index]) if revenue_index is not None else []
        eps = numbers_in(lines[eps_index]) if eps_index is not None else []
        if len(revenue) >= 2 and revenue[1]:
            growth = revenue[0] / revenue[1] - 1
            self.quarter.update(revenue=revenue[0], revenue_prior=revenue[1], revenue_growth=growth)
            print(f"  Quarter revenue growth = {revenue[0]:,.0f} / {revenue[1]:,.0f} - 1 = {growth:.2%} (first two columns: this quarter and the same quarter last year; check the headers above)")
        if len(eps) >= 2:
            self.quarter.update(eps=eps[0], eps_prior=eps[1])
            print(f"  Quarter diluted EPS = {eps[0]:.2f}; same quarter last year {eps[1]:.2f} (first two columns)")

    def step7(self, peers: list[str]) -> None:
        print("\n[7/7] Peer facts and operating margins")
        outputs = []
        for ticker in peers:
            peer = Desk(self.http.headers["User-Agent"], self.outdir / f"peer_{ticker.upper()}")
            peer.ticker = ticker.upper()
            peer.step1()
            peer.step2()
            peer.step4()
            rev = peer.fact_rows.get("revenue")
            op = peer.fact_rows.get("operating_income")
            revenue, operating = peer.value(rev), peer.value(op)
            margin = operating / revenue if revenue and operating is not None else None
            end = rev["current"]["end"] if rev and rev.get("current") else "unknown"
            shown = f"{margin:.2%} = {millions(operating)} / {millions(revenue)}" if margin is not None else "unavailable"
            print(f"  {peer.company} ({peer.ticker}), FY end {end}, 10-K {peer.selected['10-K']['accessionNumber']}: revenue ${millions(revenue)}M [{rev['tag'] if rev else 'n/a'}], operating income ${millions(operating)}M [{op['tag'] if op else 'n/a'}], operating margin {shown}")
            outputs.append({
                "company": peer.company,
                "ticker": peer.ticker,
                "fiscal_year_end": end,
                "ten_k": peer.selected["10-K"]["accessionNumber"],
                "facts": {name: Desk.public(item) for name, item in peer.fact_rows.items()},
                "operating_margin": margin,
            })
        self.peers = outputs
        self.outdir.mkdir(parents=True, exist_ok=True)
        (self.outdir / "peer_facts.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
        print(f"Saved peer facts: {self.outdir / 'peer_facts.json'}")

    def run(self, step: int | None, price: float | None, peers: list[str]) -> None:
        actions = [self.step1, self.step2, self.step3, self.step4, lambda: self.step5(price), self.step6, lambda: self.step7(peers)]
        if step is None:
            for action in actions:
                action()
            return
        # Prepare data required by the requested step, but only show that step's output.
        prerequisites = {
            1: [],
            2: [1],
            3: [1, 2],
            4: [1, 2],
            5: [1, 2, 4],
            6: [1, 2, 3],
            7: [],
        }
        for number in prerequisites[step]:
            with contextlib.redirect_stdout(io.StringIO()):
                actions[number - 1]()
        actions[step - 1]()


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN 67110 Lab 02 SEC data-side desk")
    parser.add_argument("ticker", help="Ticker of any U.S. company that files with EDGAR")
    parser.add_argument("--peers", default="", help="Comma-separated peer tickers")
    parser.add_argument("--price", type=float, help="Last close before the relevant earnings release")
    parser.add_argument("--step", type=int, choices=range(1, 8), help="Run one numbered step only")
    args = parser.parse_args()
    # A filing's curly quotes or dashes must not stop a run whose output is piped to a file.
    sys.stdout.reconfigure(errors="replace")
    env = load_dotenv()
    user_agent = os.environ.get("SEC_USER_AGENT") or env.get("SEC_USER_AGENT", "")
    problem = user_agent_problem(user_agent, env_path())
    if problem:
        print(problem, file=sys.stderr)
        return 2
    ticker = args.ticker.upper()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path("output") / f"{ticker}_{run_id}"
    desk = Desk(user_agent, outdir)
    desk.ticker = ticker
    try:
        desk.run(args.step, args.price, [p.strip().upper() for p in args.peers.split(",") if p.strip()])
    except requests.RequestException as exc:
        print(f"SEC request failed: {exc}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"Desk stopped: {exc}", file=sys.stderr)
        return 1
    print(f"\nRun folder: {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
