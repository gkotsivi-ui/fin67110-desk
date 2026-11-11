#!/usr/bin/env python3
"""The Verifier: the agent team's last node, on every run.

It receives only the compiled report, the saved filing texts and the saved facts. It never sees the
roles' instructions and never reruns them, and it skips the Investment Advisor's thesis. For every
other sourced number it checks in code first: a number sourced to an XBRL tag and period against
the facts file, exactly; a number sourced to a line, that the line appears in that filing's text,
allowing for spacing and formatting; a ratio, by recomputing it from its quoted inputs. Then the
model checks that each quoted line states that number, for that period, in that definition.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from lab03_app import calculate, cell, normalize

READER = """You are the Verifier's reader on an equity research desk.
You receive one JSON message with three keys: task, context and expected_output.
The context holds numbered lines of a research report and the names of the facts the desk saved.
List every number in those lines that states a figure: an amount, a growth rate, a margin, a ratio, a per-share figure, a count or a price.
Leave out dates, years, fiscal-year names, accession numbers, item numbers, section numbers, footnote marks, and the numbers in tag names or in period lengths such as "16 weeks".
For each number, record the source the report gives it, exactly as the report gives it, in its own line or in the line or heading it belongs to.
Do not supply a source the report does not give, and do not judge whether the number is right. Code checks that.
Keep "what" to six words or fewer, and leave out every key that does not apply to a number.
Reply with one JSON object in the shape of expected_output and nothing else."""

CHECKER = """You are the Verifier's line check on an equity research desk.
You receive one JSON message with three keys: task, context and expected_output.
Each item is a number from a research report, what the report says it is, its period, and the filing line the report cites for it.
Decide whether that line states that number, for that period, in that definition.
A line that states the number for another period or column, or in another definition (net sales where the report says total revenue, adjusted where the report says GAAP, year-end where the report says average), does not state it.
Reply with one JSON object in the shape of expected_output and nothing else."""

READ_OUTPUT = {
    "numbers": [{
        "line": "the report line's number",
        "number": "the number exactly as written, with its $ or % sign",
        "what": "what the number is, in a few words",
        "period": "the period or date it is for, as the report states it, or empty",
        "scale": "one of: units, thousands, millions, billions, percent, ratio, per_share",
        "fact": "the key of the saved fact it states, from context.facts, or empty",
        "source": {
            "type": "one of: xbrl, line, ratio, price, none",
            "tag": "for xbrl: the tag the report names",
            "period_end": "for xbrl: the period end the report names, as YYYY-MM-DD",
            "document": "for line: 10-K, 10-Q or release",
            "line": "for line: the line the report quotes, exactly",
            "label": "for line: the row label the report names when it does not quote the line",
            "arithmetic": "for ratio: the arithmetic the report shows, with its numbers as written",
        },
        "definition_missing": "true when the number is a ratio the filing could define two ways and the report does not say which",
    }],
}
CHECK_OUTPUT = {"checks": [{"id": "the item's id", "states_it": "true or false", "reason": "one short sentence"}]}

SCALES = {"units": 1.0, "thousands": 1e3, "millions": 1e6, "billions": 1e9, "percent": 0.01, "ratio": 1.0, "per_share": 1.0}
# The words a filing prints beside each fact, to find the line that states it.
KEYWORDS = {
    "revenue": ["total revenue", "total net sales", "total revenues", "net sales", "revenue"],
    "operating_income": ["operating income"],
    "net_income": ["net income"],
    "diluted_eps": ["diluted"],
    "equity": ["stockholders", "shareholders", "total equity"],
    "long_term_debt": ["long-term debt"],
    "current_debt": ["current portion", "current maturities"],
    "cash_from_operations": ["operating activities"],
    "capex": ["property and equipment", "property, plant"],
}
DOCUMENTS = {"10-K": "10K_*.txt", "10-Q": "10Q_*.txt", "release": "8K_*.txt"}


def plain(text: str) -> str:
    """Text without table bars, dollar signs, commas, quotes or emphasis, so a quote compares with its filing."""
    text = normalize(text.replace("\\|", "|"))
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 303,154 -> 303154
    text = re.sub(r"[|$*`\",]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .;:")


def parse_number(text: str) -> tuple[float, int] | None:
    """A written number and its count of decimals: "$(1.25)" is -1.25 with 2 decimals."""
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not match:
        return None
    digits = match.group(0).replace(",", "")
    value = float(digits)
    if re.match(r"\s*(\(|-|\$\(|-\$|\(\$)", text):
        value = -value
    return value, len(digits.split(".")[1]) if "." in digits else 0


def same(number: str, scale: str, true: float) -> bool:
    """The written number equals the true value after rounding to what the report shows."""
    parsed = parse_number(number)
    if not parsed:
        return False
    value, decimals = parsed
    factor = SCALES.get(scale, 1.0)
    return abs(value * factor - true) <= 0.5 * 10 ** -decimals * factor * (1 + 1e-9) + abs(true) * 1e-12


def number_in(number: str, text: str) -> bool:
    parsed = re.search(r"\d[\d,]*(?:\.\d+)?", number)
    if not parsed:
        return False
    digits = parsed.group(0).replace(",", "")
    return bool(re.search(rf"(?<![\d.]){re.escape(digits)}(?![\d])", plain(text)))


def fact_table(facts: dict[str, Any], peers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every saved fact by key (revenue, revenue_prior, PEER.revenue), with its tag, period and value."""
    table: dict[str, dict[str, Any]] = {}
    groups = [(facts.get("ticker", ""), "", facts.get("facts", {}))] + [(p["ticker"], f"{p['ticker']}.", p.get("facts", {})) for p in peers]
    for ticker, prefix, items in groups:
        for name, item in items.items():
            if not item:
                continue
            for period, suffix in (("current", ""), ("prior", "_prior")):
                fact = item.get(period)
                if fact:
                    table[f"{prefix}{name}{suffix}"] = {
                        "name": name, "company": ticker, "peer": bool(prefix), "tag": item["tag"], "label": item.get("label", name),
                        "unit": item.get("unit") or fact.get("unit", "USD"), "start": fact.get("start"), "end": fact.get("end", ""), "val": float(fact["val"]),
                    }
    return table


def lines_to_check(lines: list[str]) -> list[tuple[int, str]]:
    """The report's lines, numbered from 1, without the run's header, the Investment Advisor's thesis and the Manager's checklist."""
    keep, section, sub = [], "", ""
    for number, line in enumerate(lines, 1):
        if line.startswith("## "):
            section, sub = line, ""
        elif line.startswith("### "):
            sub = line
        elif line.strip() == "---":
            section, sub = "appendix", ""
        if number <= 3 or not line.strip() or re.fullmatch(r"\|?[\s\-:|]+\|?", line.strip()):
            continue
        if line.startswith("Insight:"):
            keep.append((number, line))  # every role's Insight is checked, the Investment Advisor's too
            continue
        if line.startswith(("This is a learning exercise", "AI assistance:", "Any remaining errors")):
            continue
        if "checklist" in sub.lower() or "(Investment Advisor)" in sub:
            continue
        if section.startswith("## 5.") and not re.match(r"\*\*Recommendation:|The deciding number:", line):
            continue
        keep.append((number, line))
    return keep


def recompute(arithmetic: str) -> float | None:
    """The value of the arithmetic a report shows, from its numbers as written."""
    text = arithmetic.replace("−", "-").replace("–", "-").replace("×", "*").replace("÷", "/")
    text = re.sub(r"(?<=\d)\s*[xX]\s*(?=[\d(])", " * ", text)
    # Words in brackets, such as "($ millions)" or "(price / diluted EPS)", are labels, not arithmetic.
    pieces = [re.sub(r"\([^()\d]*\)", " ", p) for p in re.split(r"=", text)]
    # Recompute the side written in numbers; "net_income / revenue = 9,226.0 / 303,154.0" names its inputs first.
    pieces = [p for p in pieces if re.search(r"\d\s*[-+*/]\s*[\d(]|\)\s*[-+*/]", p) and not re.search(r"[A-Za-z_]", p)]
    if not pieces:
        return None
    expression = re.sub(r"[^\d.+\-*/() ]", " ", max(pieces, key=len).replace(",", ""))
    try:
        return calculate(expression.strip(), {})
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError):
        return None


def shown(value: float, scale: str, decimals: int) -> str:
    if scale == "per_share":
        return f"${value:,.2f}"
    if scale == "percent":
        return f"{value * 100:,.{decimals}f}%"
    return f"{value / SCALES.get(scale, 1.0):,.{decimals}f}"


class Verifier:
    def __init__(self, run_dir: Path, model: Any) -> None:
        self.run_dir = run_dir
        self.model = model
        self.report = (run_dir / "report.md").read_text(encoding="utf-8")
        self.lines = self.report.splitlines()
        self.texts: dict[str, list[str]] = {}
        for name, pattern in DOCUMENTS.items():
            found = sorted(run_dir.glob(pattern))
            self.texts[name] = found[0].read_text(encoding="utf-8").splitlines() if found else []
        self.plain = {name: plain(" ".join(lines)) for name, lines in self.texts.items()}
        facts = json.loads((run_dir / "facts.json").read_text(encoding="utf-8"))
        peers_file = run_dir / "peer_facts.json"
        peers = json.loads(peers_file.read_text(encoding="utf-8")) if peers_file.exists() else []
        self.facts = fact_table(facts, peers)

    def run(self) -> dict[str, Any]:
        checked = lines_to_check(self.lines)
        print(f"[Verifier] Reading {len(checked)} report lines against {len(self.facts)} saved facts and {sum(1 for t in self.texts.values() if t)} filing texts")
        packet = {
            "task": "List every number in these report lines, with the source the report gives it.",
            "context": {
                "report_lines": [{"line": n, "text": text} for n, text in checked],
                "facts": [{"fact": key, "what": f["label"], "company": f["company"], "tag": f"us-gaap:{f['tag']}", "period_end": f["end"]} for key, f in self.facts.items()],
            },
            "expected_output": READ_OUTPUT,
        }
        allowed = {n for n, _ in checked}
        found = self.model.ask("Verifier (reader)", READER, packet).get("numbers") or []
        # A count spelled out in words ("three segments") holds no digits for the code to check.
        records = [self.check(r) for r in found if isinstance(r, dict) and str(r.get("line", "")).isdigit() and int(r["line"]) in allowed and re.search(r"\d", str(r.get("number", "")))]
        self.line_check(records)
        self.carry(records)
        for r in records:
            self.correct(r)
        counts = {mark: sum(1 for r in records if r["mark"] == mark) for mark in ("correct", "wrong", "unsupported", "not checked")}
        path = self.save(records, counts)
        print(f"[Verifier] {len(records)} numbers: {counts['correct']} correct, {counts['wrong']} wrong, {counts['unsupported']} unsupported, {counts['not checked']} not checked (prices)")
        print(f"[Verifier] Verified report: {path}")
        return {"path": str(path), "counts": counts, "records": records}

    # ----- the code checks -----

    def lookup(self, r: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        """The saved fact a number states: by the reader's key, else by the tag and period the report names."""
        key = str(r.get("fact") or "").strip()
        if key in self.facts:
            return key, self.facts[key]
        source = r.get("source") if isinstance(r.get("source"), dict) else {}
        tag = str(source.get("tag", "")).split(":")[-1].strip()
        end = str(source.get("period_end", "")).strip()
        hits = [(k, f) for k, f in self.facts.items() if tag and f["tag"] == tag and (not end or f["end"] == end)]
        # Two peers can share a tag and a year end; the one whose value the report states is the one it means.
        matching = [h for h in hits if self.matches(str(r.get("number", "")), str(r.get("scale", "units")), h[1])]
        return (matching or hits or [None])[0]

    def find_line(self, source: dict[str, Any], number: str) -> tuple[str, str] | None:
        """The filing line a source names, quoted or by its row label, that holds the number."""
        documents = [d for d in [str(source.get("document", ""))] if d in self.texts] + [d for d in self.texts if d != source.get("document")]
        quote = str(source.get("line", "")).strip()
        if quote:
            pieces = [p for p in (plain(x) for x in re.split(r"\.\.\.|…", quote)) if len(p) >= 8]
            for document in documents:
                if pieces and all(p in self.plain[document] for p in pieces):
                    return document, quote
            return None
        label = plain(str(source.get("label", "")))
        if len(label) >= 3:
            for document in documents:
                for line in self.texts[document]:
                    if plain(line).startswith(label) and number_in(number, line):
                        return document, line.strip()
        return None

    def check(self, r: dict[str, Any]) -> dict[str, Any]:
        source = r.get("source") if isinstance(r.get("source"), dict) else {}
        kind = str(source.get("type", "none")).lower()
        number, scale = str(r.get("number", "")), str(r.get("scale", "units")).lower()
        fact = self.lookup(r)
        out = {**r, "kind": kind, "fact_key": fact[0] if fact else None, "mark": "", "code": "", "model": "", "correction": "", "real": ""}
        if str(r.get("definition_missing")).lower() == "true":
            return {**out, "mark": "unsupported", "code": "no definition stated where the filing offers two"}
        if kind == "price":
            return {**out, "mark": "not checked", "code": "a share price; the filings hold no prices"}
        if kind == "ratio":
            value = recompute(str(source.get("arithmetic", "")))
            parsed = parse_number(number)
            if value is None or not parsed:
                return {**out, "mark": "unsupported", "code": "no arithmetic the Verifier can recompute"}
            stated, decimals = parsed
            tolerance = 0.5 * 10 ** -decimals * (1 + 1e-9)
            as_percent = scale == "percent" or "%" in number
            if abs(value - stated) <= tolerance or (as_percent and abs(value * 100 - stated) <= tolerance):
                return {**out, "mark": "correct", "code": f"recomputed: {source.get('arithmetic')}"}
            right = value * 100 if as_percent and abs(value * 100 - stated) < abs(value - stated) else value
            return {**out, "mark": "wrong", "code": f"recomputed {right:,.{decimals}f}, not {stated:,.{decimals}f}",
                    "correction": f"{right:,.{decimals}f}{'%' if as_percent else ''}", "real": f"arithmetic: {source.get('arithmetic')}"}
        if kind == "xbrl":
            if not fact:
                return {**out, "mark": "unsupported", "code": f"{source.get('tag')} at {source.get('period_end') or 'that period'} is not in the saved facts"}
            key, f = fact
            if self.matches(number, scale, f):
                return {**out, "mark": "correct", "code": f"equals the facts file: us-gaap:{f['tag']} at {f['end']}"}
            return {**out, "mark": "wrong", "code": f"the facts file holds {f['val']:,} for us-gaap:{f['tag']} at {f['end']}"}
        if kind == "line":
            if source.get("line") and not re.search(r"\d", str(source["line"])) and len(str(source["line"]).split()) <= 5:
                # "the release sentence" names a line; it does not quote one.
                source = {**source, "label": source["line"], "line": ""}
                out["source"] = source
            hit = self.find_line(source, number)
            if hit and number_in(number, hit[1]):
                return {**out, "line_found": hit[1], "document": hit[0], "code": f"the line is in the {hit[0]} text", "mark": "pending"}
            if fact and not self.matches(number, scale, fact[1]):
                return {**out, "mark": "wrong", "code": "the quoted line is not in the filing, and the facts file holds another value"}
            return {**out, "mark": "unsupported", "code": "the quoted line is not in the filing" if hit is None else "the line does not hold this number"}
        if fact and self.matches(number, scale, fact[1]):
            return {**out, "mark": "unsupported", "code": f"no source given (the number equals the saved fact {fact[0]})"}
        return {**out, "mark": "unsupported", "code": "no source given"}

    def matches(self, number: str, scale: str, fact: dict[str, Any]) -> bool:
        if fact["unit"] == "USD/shares" or scale == "per_share":
            return same(number, "per_share", fact["val"])
        if scale in ("percent", "ratio"):
            return False
        # An amount may be written in units, thousands, millions or billions; the digits decide.
        return any(same(number, s, fact["val"]) for s in dict.fromkeys([scale, "millions", "billions", "thousands", "units"]))

    # ----- the model check -----

    def line_check(self, records: list[dict[str, Any]]) -> None:
        pending = [r for r in records if r["mark"] == "pending"]
        if not pending:
            return
        items = [{"id": i, "number": r.get("number"), "what": r.get("what"), "period": r.get("period"), "document": r["document"], "line": r["line_found"]} for i, r in enumerate(pending)]
        packet = {"task": "For each item, decide whether the cited line states the number, for that period, in that definition.", "context": {"items": items}, "expected_output": CHECK_OUTPUT}
        answers = {str(a.get("id")): a for a in self.model.ask("Verifier (line check)", CHECKER, packet).get("checks") or [] if isinstance(a, dict)}
        for i, r in enumerate(pending):
            answer = answers.get(str(i), {})
            states = str(answer.get("states_it")).lower() == "true"
            r["model"] = ("states it" if states else "does not state it") + (f": {answer.get('reason')}" if answer.get("reason") else "")
            if states:
                r["mark"] = "correct"
            elif r["fact_key"] and not self.matches(str(r.get("number")), str(r.get("scale")), self.facts[r["fact_key"]]):
                r["mark"] = "wrong"
            else:
                r["mark"] = "unsupported"

    @staticmethod
    def same_number(r: dict[str, Any]) -> str:
        """A number's digits and its percent sign: "$95,723 million" and "95,723" are the same number."""
        found = re.search(r"\d[\d,]*(?:\.\d+)?", str(r.get("number", "")))
        return (found.group(0).replace(",", "") if found else "") + ("%" if "%" in str(r.get("number", "")) else "")

    def carry(self, records: list[dict[str, Any]]) -> None:
        """A line that restates a number the report sources elsewhere carries that source.

        A quote the filing does not contain gets no such pass: it stays unsupported, however plausible.
        """
        sourced: dict[str, dict[str, Any]] = {}
        for r in records:
            if r["mark"] == "correct" and r["kind"] in ("xbrl", "line", "ratio"):
                sourced.setdefault(self.same_number(r), r)
        for r in records:
            quoted = r["kind"] == "line" and str((r.get("source") or {}).get("line", "")).strip()
            if r["mark"] == "unsupported" and r["kind"] in ("none", "line") and not quoted and str(r.get("definition_missing")).lower() != "true":
                hit = sourced.get(self.same_number(r))
                if hit:
                    r["mark"] = "correct"
                    r["code"] = f"restates line {hit['line']}, where the report sources it ({hit['kind']})"

    # ----- the corrections -----

    def correct(self, r: dict[str, Any]) -> None:
        """For a wrong or unsupported number: the filing's figure, with the real line or tag beside it."""
        if r["mark"] not in ("wrong", "unsupported") or r["correction"]:
            return
        if r["fact_key"]:
            f = self.facts[r["fact_key"]]
            parsed = parse_number(str(r.get("number", "")))
            decimals = parsed[1] if parsed else 1
            scale = "per_share" if f["unit"] == "USD/shares" else (r.get("scale") if r.get("scale") in ("units", "thousands", "millions", "billions") else "millions")
            r["correction"] = shown(f["val"], scale, decimals)
            line = None if f["peer"] else self.real_line(f)
            tag = f"us-gaap:{f['tag']}, {f['start'] + ' to ' if f.get('start') else 'at '}{f['end']}"
            r["real"] = f"10-K line: {line} ({tag})" if line else tag
            return
        for document, lines in self.texts.items():
            hit = next((line.strip() for line in lines if number_in(str(r.get("number", "")), line)), None)
            if hit:
                r["correction"] = "not stated as the report says"
                r["real"] = f"nearest {document} line with this number: {hit[:200]}"
                return
        r["correction"] = "not stated in the filings"

    def real_line(self, f: dict[str, Any]) -> str | None:
        """The 10-K line that prints the fact: its value beside the words the statements use for it."""
        words = KEYWORDS.get(f["name"], [f["label"].lower()])
        value = f["val"]
        forms = [f"{value:.2f}"] if f["unit"] == "USD/shares" else [f"{value / 1e6:,.0f}", f"{value / 1e3:,.0f}", f"{value / 1e6:,.1f}"]
        hits = [line.strip() for line in self.texts.get("10-K", []) if any(w in line.lower() for w in words) and any(re.search(rf"(?<![\d,.]){re.escape(x)}(?![\d])", line) for x in forms)]
        # The statement's own row ("Diluted | $20.76 | ...") before a sentence in the MD&A that repeats the figure.
        rows = [h for h in hits if " | " in h and h.lower().startswith(tuple(words))]
        return (rows or [h for h in hits if " | " in h] or hits or [None])[0]

    # ----- the verified report -----

    def save(self, records: list[dict[str, Any]], counts: dict[str, int]) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.run_dir / "verified_report.md"
        if path.exists():
            path = self.run_dir / f"verified_report_{stamp}.md"
        rows = [
            "| # | Line | Number | What | Source in the report | Check in code | Check by the model | Mark | Correction from the filings | Real line or tag |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for i, r in enumerate(records, 1):
            source = r.get("source") or {}
            given = source.get("tag") or source.get("line") or source.get("label") or source.get("arithmetic") or r["kind"]
            # A quote copied from a Markdown table already escapes its bars; escape each bar once.
            rows.append("| " + " | ".join(cell(str(x).replace("\\|", "|")) for x in (
                i, r.get("line"), r.get("number"), r.get("what"), f"{r['kind']}: {given}"[:160], r["code"], r["model"] or "-",
                f"**{r['mark']}**", r["correction"] or "-", r["real"] or "-",
            )) + " |")
        flags: dict[int, list[str]] = {}
        for r in records:
            if r["mark"] in ("wrong", "unsupported"):
                flags.setdefault(int(r["line"]), []).append(f"{r.get('number')} is {r['mark']}" + (f"; the filings: {r['correction']}" if r["correction"] else ""))
        body = [line + (f" **[Verifier: {'; '.join(flags[n])}]**" if n in flags else "") for n, line in enumerate(self.lines, 1)]
        header = [
            body[0],
            "",
            "## Verifier's marks",
            "",
            f"Run {stamp}. Checked in code against the saved facts and filing texts, then by the model for what each quoted line states. "
            f"The Investment Advisor's thesis is not checked. Correct: {counts['correct']} | Wrong: {counts['wrong']} | Unsupported: {counts['unsupported']} | Not checked (prices): {counts['not checked']}",
            "",
            *rows,
            "",
        ]
        path.write_text("\n".join(header + body[1:]) + "\n", encoding="utf-8")
        (self.run_dir / path.name.replace("verified_report", "verification").replace(".md", ".json")).write_text(
            json.dumps({"counts": counts, "records": records}, indent=1, ensure_ascii=False), encoding="utf-8")
        return path


def verify_run(run_dir: Path, model: Any) -> dict[str, Any]:
    """Verify one saved run: its report.md against its own filing texts and facts."""
    return Verifier(run_dir, model).run()
