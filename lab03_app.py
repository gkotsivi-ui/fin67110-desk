#!/usr/bin/env python3
"""FIN 67110 Lab 03: the four roles of Francis & Zhang (2026), Figure 1, on the Lab 02 steps.

The Research Analyst, the Financial Analyst and the Investment Advisor are each one model call.
Each receives only what the Strategy Manager sends it: JSON with the task, the context and the
expected output. The Strategy Manager is a checklist in code. It checks the five parts, sends a
failing part back to its role once, and compiles the report.
"""

from __future__ import annotations

import argparse
import ast
import json
import operator
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import requests

import closes
from lab02_desk import Desk, api_key_problem, env_path, is_placeholder, load_dotenv, millions, provider_of, user_agent_problem
from prices import last_close_before

DEFAULT_MODEL = "claude-opus-5-5"
# Models that accept the server-side fallback, which re-runs a declined request on another model.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
# With a Google AI Studio key (it starts with AIza), the roles run on Gemini instead; MODEL can name another Gemini model.
GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_STOPS = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}


def model_for(provider: str, model: str) -> str:
    """The model ID for the key's provider. MODEL may be written as CrewAI writes it (gemini/gemini-3.5-flash-lite);
    a model of the other provider does not apply, so that provider's default is used."""
    if provider == "google":
        name = model.removeprefix("gemini/").removeprefix("models/")
        return name if name.startswith("gemini") else GEMINI_MODEL
    return model if model.startswith("claude") else DEFAULT_MODEL
PARTS = [
    "Overview",
    "Market Positioning and Growth Outlook",
    "Valuation Insights",
    "Future Developments and Strategic Recommendations",
    "Investment Recommendation",
]
RESEARCH_SECTIONS = ["overview", "business_model", "competitive_position", "catalysts", "recent_developments"]
FINANCIAL_SECTIONS = ["statement_analysis", "latest_quarter", "peer_comparison", "valuation"]
LABELS = {
    "revenue": "Total revenue",
    "operating_income": "Operating income",
    "net_income": "Net income attributable to the company",
    "diluted_eps": "Diluted EPS (GAAP)",
    "equity": "Stockholders' equity",
    "long_term_debt": "Long-term debt",
    "current_debt": "Current portion of long-term debt",
    "cash_from_operations": "Cash from operations",
    "capex": "Additions to property and equipment",
}

# The 10-K's own headings; the table of contents repeats them, so the longest span wins.
BUSINESS = (r"^\s*item\s*1\s*[.:\u2013\u2014-]?\s*(?:\|\s*)?business\b", r"^\s*item\s*1a\b")
MDNA = (r"^\s*item\s*7\s*[.:\u2013\u2014-]?\s*(?:\|\s*)?management", r"^\s*item\s*7a\b|^\s*item\s*8\b")

ROLES = Path(__file__).resolve().parent / "roles"


def role_instructions(name: str) -> str:
    """A role's instructions, from its own file in the roles folder."""
    return (ROLES / f"{name}.md").read_text(encoding="utf-8").strip()


RESEARCH_ANALYST = role_instructions("research_analyst")
FINANCIAL_ANALYST = role_instructions("financial_analyst")
INVESTMENT_ADVISOR = role_instructions("investment_advisor")

CLAIM = {"claim": "One plain sentence.", "quote": "The exact line from the context that supports it.", "source": "10-K Item 1, 10-K Item 7 or Earnings release"}
RESEARCH_OUTPUT = {
    "overview": "a list of 2 to 3 claims: what the company does and how it earns money",
    "business_model": "a list of 2 to 4 claims: its segments, its customers and its sources of revenue and profit",
    "competitive_position": "a list of 2 to 4 claims: its scale, its advantages, the competitors the filing names, and the threats",
    "catalysts": "a list of 2 to 4 claims: what management says will drive future results",
    "recent_developments": "a list of 2 to 4 claims from the earnings release and the MD&A",
    "each claim has this shape": CLAIM,
}
FINANCIAL_OUTPUT = {
    "calculator_requests": 'a list, possibly empty, of {"name": "what it is", "expression": "arithmetic over context.calculator_variables, for example net_income / revenue"}',
    "statement_analysis": "Markdown: growth, margins, returns on equity, leverage and free cash flow, each number with its source",
    "latest_quarter": "Markdown: the quarter's revenue, its growth on the same quarter last year and its GAAP diluted EPS, quoting the release lines",
    "peer_comparison": "Markdown table: company, fiscal year end, total revenue, operating income, operating margin, and the source of each",
    "valuation": "Markdown: P/E with its price, date and arithmetic, and what the ratios say about value; say so when there is no price",
    "definitions": "a list of sentences, one for each definition you chose",
}
ADVISOR_OUTPUT = {
    "recommendation": "Buy, Hold or Sell",
    "deciding_number": {"label": "what the number is", "value": "the number, copied exactly", "source": "its source, as the Financial Analyst gave it"},
    "thesis": "Markdown, 3 to 6 sentences",
    "what_would_change_it": "one or two sentences",
    "strategic_recommendations": "a list of 2 to 3 sentences for the client: what to watch or do next, each tied to a number or a quote in the context",
}
# Lab 05: each analyst's output ends with one Insight, a claim the filings support that the release's first paragraph does not state.
INSIGHT = {
    "claim": "one sentence with at least one number: a claim the filings support that context.release_first_paragraph does not state",
    "source": "the filing it comes from (10-K, 10-Q or Earnings release) and where in it",
    "line": "the line of that filing that states the claim's number, word for word",
}
RESEARCH_OUTPUT["insight"] = INSIGHT
FINANCIAL_OUTPUT["insight"] = dict(INSIGHT, line="the release line from the context that states the claim's number, word for word, or the XBRL tag and period of the fact in context.facts that states it")
ADVISOR_OUTPUT["insight"] = dict(INSIGHT, line="a filing line that the analysts quote, word for word, that states the claim's number")
FIRST_PARAGRAPH = "release_first_paragraph"
# The exhibit's own header lines, before the release's text starts.
RELEASE_HEADER = re.compile(r"EX-99.*|Exhibit 99\.1|Press Release|Document|\d+|\S+\.html?", re.I)
FIGURE = re.compile(r"(\$\s*)?(\d[\d,]*(?:\.\d+)?)\s*(%|percent\b|per cent\b|trillion\b|billion\b|million\b|thousand\b)?", re.I)
SCALE = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3}


def first_paragraph(release: str, size: int = 1000) -> str:
    """The release's first paragraph, read broadly: its opening lines after the exhibit's header, to about 1,000
    characters, so that the headline figures are in it whether the release prints them in a paragraph or in bullets."""
    kept: list[str] = []
    for line in (raw.strip() for raw in release.splitlines()):
        if not line or (not kept and RELEASE_HEADER.fullmatch(line)):
            continue
        kept.append(line)
        if sum(len(k) for k in kept) >= size:
            break
    return "\n".join(kept)


def figures(text: str) -> list[tuple[float, float, bool]]:
    """Each figure in the text as (value, half a unit of its last digit, whether it is a percent), with its scale word
    applied: $93.9 billion and $93,873 million can be compared. Years and bare counts under 100 are left out."""
    found = []
    for m in FIGURE.finditer(text):
        dollar, digits, unit = m.group(1), m.group(2).replace(",", ""), (m.group(3) or "").lower()
        value = float(digits)
        if not dollar and not unit and "." not in digits and (value < 100 or 1900 <= value <= 2100):
            continue
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        scale = SCALE.get(unit, 1.0)
        found.append((value * scale, 0.5 * 10 ** -decimals * scale, unit in ("%", "percent", "per cent")))
    return found


def only_restates(claim: str, paragraph: str) -> bool:
    """True when every figure in the claim is a figure the paragraph states: as exact as the paragraph's figure or more,
    and equal to it at the paragraph's rounding. $93,873 million restates $93.9 billion; 11% does not restate 11.2%,
    which may be another measure."""
    mine, theirs = figures(claim), figures(paragraph)
    slack = 1 + 1e-9
    return bool(mine) and all(any(p == q and t <= u * slack and abs(v - w) <= u * slack for w, u, q in theirs) for v, t, p in mine)


def context_numbers(context: dict[str, Any]) -> set[str]:
    """The numbers the Investment Advisor may state: those of the analysts' outputs, without the release's first
    paragraph, which its context holds only so that its Insight can say something else."""
    return number_keys(json.dumps({k: v for k, v in context.items() if k != FIRST_PARAGRAPH}, ensure_ascii=False))


class RoleError(RuntimeError):
    pass


def section(text: str, start: str, end: str) -> str:
    """The longest span from a heading that matches start to the next heading that matches end."""
    ends = [m.start() for m in re.finditer(end, text, re.I | re.M)]
    best = ""
    for m in re.finditer(start, text, re.I | re.M):
        stop = next((e for e in ends if e > m.start()), len(text))
        if stop - m.start() > len(best):
            best = text[m.start():stop]
    return best.strip()


def normalize(text: str) -> str:
    """Lowercase, straight quotes, plain dashes and single spaces, so a quote compares with its filing."""
    table = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "})
    return re.sub(r"\s+", " ", text.lower().translate(table)).strip()


def quote_found(quote: str, normalized_source: str) -> bool:
    pieces = [p.strip(" .,;:") for p in re.split(r"\.\.\.|\u2026", normalize(quote))]
    pieces = [p for p in pieces if len(p) >= 12] or [normalize(quote)]
    return all(p in normalized_source for p in pieces)


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def number_key(token: str) -> str:
    """One plain form per number: 303,154.0 and 303154 are both 303154."""
    plain = token.replace(",", "")
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return plain.lstrip("0") or "0"


def number_keys(text: str) -> set[str]:
    return {number_key(token) for token in NUMBER.findall(text)}


def untraced(text: str, known: set[str]) -> list[str]:
    """The numbers in text that known does not hold, leaving out years and counts under 100."""
    missing: list[str] = []
    for token in NUMBER.findall(text):
        key = number_key(token)
        if re.fullmatch(r"(19|20)\d\d", key) or (key.isdigit() and int(key) < 100):
            continue
        if key not in known and token not in missing:
            missing.append(token)
    return missing


OPERATIONS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def calculate(expression: str, variables: dict[str, float]) -> float:
    """Evaluate + - * / over numbers and the named variables. Nothing else runs."""

    def value(node: ast.AST) -> float:
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATIONS:
            return OPERATIONS[type(node.op)](value(node.left), value(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -value(node.operand)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in variables:
            return variables[node.id]
        raise ValueError(f"the calculator takes + - * / over numbers and these names: {', '.join(sorted(variables))}")

    return value(ast.parse(expression, mode="eval").body)


def parse_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    for candidate in (text, text[text.find("{"):text.rfind("}") + 1]):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def cell(text: Any) -> str:
    """Text safe inside a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


class Model:
    """One model behind the analyst roles and the Verifier: Anthropic's API for an Anthropic key, Google's Gemini API
    for a Google AI Studio key. Every exchange is kept for roles.json."""

    def __init__(self, api_key: str, model: str, effort: str) -> None:
        self.provider = "google" if provider_of(api_key) == "google" else "anthropic"
        self.vendor = "Google" if self.provider == "google" else "Anthropic"
        self.model = model_for(self.provider, model)
        self.effort = effort
        self.exchanges: list[dict[str, Any]] = []
        self.api_key = api_key if self.provider == "google" else ""
        self.client = anthropic.Anthropic(api_key=api_key) if self.provider == "anthropic" else None

    def ask(self, role: str, instructions: str, packet: dict[str, Any]) -> dict[str, Any]:
        print(f"[{role}] working ({self.model})")
        text, message = self.send(instructions, packet)
        data = parse_json(text)
        if data is None:
            # A reply that is not JSON gets one more try, with the reason.
            retry = dict(packet, manager_feedback=["Your last reply was not one valid JSON object. Reply with the JSON object only."])
            text, message = self.send(instructions, retry)
            data = parse_json(text)
        usage = message.usage
        self.exchanges.append({
            "role": role,
            "sent": packet,
            "received": data if data is not None else text,
            "served_by": message.model,
            "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
        })
        if data is None:
            raise RoleError(f"{role} did not return JSON (stop reason {message.stop_reason}).")
        print(f"[{role}] done: {usage.input_tokens:,} input and {usage.output_tokens:,} output tokens")
        return data

    def send(self, instructions: str, packet: dict[str, Any]) -> tuple[str, Any]:
        if self.provider == "google":
            return self.send_gemini(instructions, packet)
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 32000,
            "system": instructions,
            "output_config": {"effort": self.effort},
            "messages": [{"role": "user", "content": json.dumps(packet, indent=1, ensure_ascii=False)}],
        }
        try:
            if self.model in FALLBACK_MODELS:
                stream = self.client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)
            else:
                stream = self.client.messages.stream(**request)
            with stream as events:
                message = events.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise RoleError("The Anthropic API rejected API_KEY. Paste a valid key from platform.claude.com into .env.") from exc
        except anthropic.NotFoundError as exc:
            raise RoleError(f"Model {self.model} was not found. Set MODEL in .env to a current model ID.") from exc
        except anthropic.RateLimitError as exc:
            raise RoleError("The Anthropic API is rate limiting this key. Wait a minute and run again.") from exc
        except anthropic.APIStatusError as exc:
            raise RoleError(f"The Anthropic API refused the request ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise RoleError("Could not reach the Anthropic API. Check the network and run again.") from exc
        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            raise RoleError(f"The model declined the request (category: {getattr(details, 'category', None)}).")
        if message.stop_reason == "max_tokens":
            print("    the reply reached max_tokens and may be cut off")
        return "".join(block.text for block in message.content if block.type == "text"), message

    def send_gemini(self, instructions: str, packet: dict[str, Any]) -> tuple[str, Any]:
        """One generateContent call to Gemini. The reply gets the fields that ask() reads from an Anthropic message."""
        body = {
            "systemInstruction": {"parts": [{"text": instructions}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps(packet, indent=1, ensure_ascii=False)}]}],
            "generationConfig": {"maxOutputTokens": 32000, "responseMimeType": "application/json"},
        }
        try:
            # The key goes in a header, never in the URL.
            response = requests.post(f"{GEMINI_API}/models/{self.model}:generateContent", json=body,
                                     headers={"x-goog-api-key": self.api_key}, timeout=600)
        except requests.RequestException as exc:
            raise RoleError("Could not reach the Gemini API. Check the network and run again.") from exc
        if response.status_code != 200:
            raise RoleError(gemini_error(response, self.model))
        try:
            data = response.json()
        except ValueError as exc:
            raise RoleError("The Gemini API sent a reply that is not JSON. Run again.") from exc
        blocked = (data.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise RoleError(f"The model declined the request (Gemini block reason {blocked}).")
        candidate = (data.get("candidates") or [{}])[0]
        finish = str(candidate.get("finishReason") or "")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought"))
        if not text and finish not in GEMINI_STOPS:
            raise RoleError(f"The model declined the request (Gemini finish reason {finish or 'none'}).")
        usage = data.get("usageMetadata") or {}
        message = SimpleNamespace(
            model=data.get("modelVersion") or self.model,
            stop_reason=GEMINI_STOPS.get(finish, finish.lower()),
            usage=SimpleNamespace(
                input_tokens=int(usage.get("promptTokenCount") or 0),
                output_tokens=int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
            ),
        )
        if message.stop_reason == "max_tokens":
            print("    the reply reached max_tokens and may be cut off")
        return text, message


def gemini_error(response: requests.Response, model: str) -> str:
    """The Gemini API's error, with what to do about it."""
    try:
        error = response.json().get("error") or {}
    except (ValueError, AttributeError):
        error = {}
    said = str(error.get("message") or response.text[:300]).strip()
    code = response.status_code
    if code in (401, 403) or "API key" in said or "API_KEY" in json.dumps(error):
        return f"The Gemini API rejected API_KEY ({code}: {said}). Paste a valid key from aistudio.google.com into .env."
    if code == 404:
        return f"Model {model} was not found ({said}). Set MODEL in .env to a current Gemini model ID, for example {GEMINI_MODEL}."
    if code == 429:
        return (f"The Gemini API is limiting this key ({said}). Wait a minute and run again, "
                "or set MODEL in .env to a model with more free quota, for example gemini-3.5-flash-lite.")
    return f"The Gemini API refused the request ({code}): {said}"


class StrategyManager:
    """The checklist that coordinates the three analysts and compiles the five-part report."""

    def __init__(self, desk: Desk, model: Model, price: float | None, price_note: str, run_time: datetime, tools: str) -> None:
        self.desk = desk
        self.model = model
        self.price = price
        self.price_note = price_note
        self.run_time = run_time
        self.tools = tools
        self.notes: dict[str, list[str]] = {}
        self.sent_back: list[str] = []
        self.calculator_count = 0
        ten_k = Path(desk.selected["10-K"]["saved_text"]).read_text(encoding="utf-8")
        self.release = Path(desk.selected["8-K"]["saved_text"]).read_text(encoding="utf-8")
        self.business = section(ten_k, *BUSINESS)
        self.mdna = section(ten_k, *MDNA)
        if not self.business or not self.mdna:
            print("[Strategy Manager] Could not find Item 1 or Item 7 headings; sending the 10-K's opening text instead")
            self.business = self.business or ten_k[:80000]
            self.mdna = self.mdna or ten_k[80000:200000]
        self.sources = normalize(ten_k + "\n" + self.release)
        self.first_paragraph = first_paragraph(self.release)
        self.tags = {f"us-gaap:{item['tag']}" for item in desk.fact_rows.values() if item}
        self.variables, self.money = self.calculator_variables()

    # ----- the three analysts -----

    def research_packet(self) -> dict[str, Any]:
        d = self.desk
        return {
            "task": f"Describe {d.company} ({d.ticker}) for an equity research report: its business model, its competitive position, its catalysts and its recent developments.",
            "context": {
                "company": d.company,
                "ticker": d.ticker,
                "10-K": f"accession {d.selected['10-K']['accessionNumber']}, fiscal year ended {d.selected['10-K']['reportDate']}",
                "10-K Item 1 Business": self.business,
                "10-K Item 7 MD&A": self.mdna,
                "Earnings release": f"8-K accession {d.selected['8-K']['accessionNumber']}, Exhibit 99.1",
                "Earnings release text": self.release,
                FIRST_PARAGRAPH: self.first_paragraph,
            },
            "expected_output": RESEARCH_OUTPUT,
        }

    def research(self) -> dict[str, Any]:
        packet = self.research_packet()
        print(f"[Strategy Manager] Research Analyst context: {len(self.business):,} + {len(self.mdna):,} + {len(self.release):,} characters of filings")
        output = self.model.ask("Research Analyst", RESEARCH_ANALYST, packet)
        problems = self.check_research(output)
        if problems:
            output = self.send_back("Research Analyst", RESEARCH_ANALYST, packet, output, problems)
            problems = self.check_research(output)
        self.notes["Research Analyst"] = problems
        return output

    def check_research(self, output: dict[str, Any]) -> list[str]:
        problems = []
        for key in RESEARCH_SECTIONS:
            claims = output.get(key)
            if not isinstance(claims, list) or not claims:
                problems.append(f"{key}: missing; give at least one claim with its quote")
                continue
            for claim in claims:
                if not isinstance(claim, dict) or not claim.get("claim") or not claim.get("quote"):
                    problems.append(f"{key}: a claim has no quote")
                elif not quote_found(str(claim["quote"]), self.sources):
                    problems.append(f"{key}: this quote is not in the filings word for word: {str(claim['quote'])[:240]}")
                else:
                    extra = untraced(str(claim["claim"]), number_keys(str(claim["quote"])))
                    if extra:
                        problems.append(f"{key}: the claim states {', '.join(extra)}, which its quote does not contain: {str(claim['claim'])[:240]}")
        return problems + self.insight_problems(output, None)

    def insight_problems(self, output: dict[str, Any], known: set[str] | None, tags: bool = False) -> list[str]:
        """Lab 05's two checks on a role's Insight. It must be there: a claim with a number, its source, and the filing's
        line, which the filings contain. And it must say more than the figures of the release's first paragraph.
        known holds the numbers the claim may state; None means the numbers of its own line."""
        insight = output.get("insight") if isinstance(output.get("insight"), dict) else {}
        claim, source, line = (str(insight.get(k) or "").strip() for k in ("claim", "source", "line"))
        if not (claim and source and line):
            return ["insight: missing. End your output with insight: one claim with a number, the filing it comes from, and that filing's line, word for word."]
        if not [k for k in number_keys(claim) if not re.fullmatch(r"(19|20)\d\d", k)]:
            return ["insight: the claim states no number. State one claim with a number that the filings support."]
        problems = []
        tag = re.search(r"us-gaap:\w+", line)
        if not quote_found(line, self.sources) and not (tags and tag and tag.group(0) in self.tags):
            problems.append(f"insight: this line is not in the filings word for word: {line[:240]}")
        missing = untraced(claim, number_keys(line) if known is None else known)
        if missing:
            problems.append(f"insight: the claim states {', '.join(missing)}, which its source does not hold: {claim[:240]}")
        if only_restates(claim, self.first_paragraph):
            problems.append("insight: the claim only restates a figure that the earnings release's first paragraph states. State a claim the first paragraph does not.")
        return problems

    def financial_packet(self) -> dict[str, Any]:
        """The Financial Analyst's packet; the numbers in its context are the ones the analyst may state."""
        d = self.desk
        context = self.financial_context()
        self.known = number_keys(json.dumps(context, ensure_ascii=False))
        return {
            "task": f"Write the statement analysis of {d.company} ({d.ticker}) for its fiscal year ended {d.selected['10-K']['reportDate']}: growth, margins, returns, leverage and cash flow; then the latest quarter from the release; then the peers; then valuation.",
            "context": context,
            "expected_output": FINANCIAL_OUTPUT,
        }

    def financial(self) -> dict[str, Any]:
        packet = self.financial_packet()
        context = packet["context"]
        output = self.model.ask("Financial Analyst", FINANCIAL_ANALYST, packet)
        asks = output.get("calculator_requests") or []
        if isinstance(asks, list) and asks:
            results = self.run_calculator(asks)
            print(f"[Strategy Manager] Calculator: {len(results)} ratio(s) computed in code and sent to the Financial Analyst")
            context["calculator_results"] = results
            self.known |= number_keys(json.dumps(results, ensure_ascii=False))
            output = self.model.ask("Financial Analyst", FINANCIAL_ANALYST, dict(packet, previous_output=output, manager_feedback=["Use context.calculator_results. Do not request more calculations."]))
        problems = self.check_financial(output)
        if problems:
            output = self.send_back("Financial Analyst", FINANCIAL_ANALYST, packet, output, problems)
            problems = self.check_financial(output)
        self.notes["Financial Analyst"] = problems
        return output

    def check_financial(self, output: dict[str, Any]) -> list[str]:
        problems = []
        for key in FINANCIAL_SECTIONS:
            text = output.get(key)
            if not isinstance(text, str) or len(text.strip()) < 40:
                problems.append(f"{key}: missing or too short")
                continue
            missing = untraced(text, self.known)
            if missing:
                problems.append(f"{key}: these numbers are not in the context as given: {', '.join(missing[:12])}. Copy each number exactly as the context shows it, or ask the calculator.")
        if self.price is not None and not re.search(r"P/E|price[- ]to[- ]earnings", str(output.get("valuation", "")), re.I):
            problems.append("valuation: state the P/E from the context with its price, date and arithmetic")
        for peer in self.desk.peers:
            if peer["ticker"] not in str(output.get("peer_comparison", "")):
                problems.append(f"peer_comparison: the peer {peer['ticker']} is missing")
        return problems + self.insight_problems(output, self.known, tags=True)

    def advice_packet(self, research: dict[str, Any], financial: dict[str, Any]) -> dict[str, Any]:
        d = self.desk
        analyst = {k: v for k, v in financial.items() if k != "calculator_requests"}
        return {
            "task": f"Write the investment thesis and the recommendation on {d.company} ({d.ticker}) from the two analysts' outputs.",
            "context": {"research_analyst": research, "financial_analyst": analyst, FIRST_PARAGRAPH: self.first_paragraph},
            "expected_output": ADVISOR_OUTPUT,
        }

    def advice(self, research: dict[str, Any], financial: dict[str, Any]) -> dict[str, Any]:
        packet = self.advice_packet(research, financial)
        output = self.model.ask("Investment Advisor", INVESTMENT_ADVISOR, packet)
        problems = self.check_advice(output, packet["context"])
        if problems:
            output = self.send_back("Investment Advisor", INVESTMENT_ADVISOR, packet, output, problems)
            problems = self.check_advice(output, packet["context"])
        self.notes["Investment Advisor"] = problems
        return output

    def check_advice(self, output: dict[str, Any], context: dict[str, Any]) -> list[str]:
        problems = []
        known = context_numbers(context)
        if output.get("recommendation") not in {"Buy", "Hold", "Sell"}:
            problems.append("recommendation: write exactly Buy, Hold or Sell")
        number = output.get("deciding_number") if isinstance(output.get("deciding_number"), dict) else {}
        keys = number_keys(str(number.get("value", "")))
        if not keys or not keys <= known:
            problems.append("deciding_number: copy one number exactly from the Financial Analyst's output, with its source")
        if len(str(output.get("thesis", ""))) < 80:
            problems.append("thesis: missing or too short")
        written = " ".join([str(output.get("thesis", "")), str(output.get("what_would_change_it", "")), " ".join(map(str, output.get("strategic_recommendations") or []))])
        missing = untraced(written, known)
        if missing:
            problems.append(f"these numbers are not in the analysts' outputs: {', '.join(missing[:12])}")
        return problems + self.insight_problems(output, known)

    def send_back(self, role: str, instructions: str, packet: dict[str, Any], output: dict[str, Any], problems: list[str]) -> dict[str, Any]:
        print(f"[Strategy Manager] Sending the {role}'s part back once: {len(problems)} problem(s)")
        for problem in problems[:5]:
            print(f"    - {problem[:160]}")
        self.sent_back.append(f"{role} ({len(problems)} problem(s))")
        return self.model.ask(role, instructions, dict(packet, previous_output=output, manager_feedback=problems))

    # ----- what the Financial Analyst sees -----

    def financial_context(self) -> dict[str, Any]:
        d = self.desk
        facts = [self.fact_entry(name, item) for name, item in d.fact_rows.items() if item and item.get("current")]
        q = d.quarter
        quarter: dict[str, Any] = {
            "release": f"8-K accession {d.selected['8-K']['accessionNumber']}, Item 2.02, Exhibit 99.1, accepted {self.accepted('8-K')}",
            "units": "the release states its own units (usually $ millions, except per share); copy its numbers as written",
            "header_lines": q.get("revenue_headers", []),
            "revenue_line": q.get("revenue_line"),
            "eps_heading": q.get("eps_heading"),
            "eps_line": q.get("eps_line"),
            "release_sentence": q.get("sentence"),
        }
        if q.get("revenue_growth") is not None:
            quarter["computed_in_code"] = [{
                "name": "Quarter revenue growth on the same quarter last year",
                "value": f"{q['revenue_growth']:.2%}",
                "arithmetic": f"{q['revenue']:,.0f} / {q['revenue_prior']:,.0f} - 1 (the first two columns of the revenue line)",
            }]
        peers = []
        for peer in d.peers:
            facts_ = peer["facts"]
            rev, op = facts_.get("revenue"), facts_.get("operating_income")
            peers.append({
                "company": peer["company"],
                "ticker": peer["ticker"],
                "fiscal_year_end": peer["fiscal_year_end"],
                "ten_k": peer["ten_k"],
                "total_revenue": f"${millions(rev['current']['val'])} million (us-gaap:{rev['tag']})" if rev and rev.get("current") else "not found",
                "operating_income": f"${millions(op['current']['val'])} million (us-gaap:{op['tag']})" if op and op.get("current") else "not found",
                "operating_margin": f"{peer['operating_margin']:.2%} = {millions(op['current']['val'])} / {millions(rev['current']['val'])} ($ millions)" if peer.get("operating_margin") is not None else "not computed",
            })
        return {
            "company": d.company,
            "ticker": d.ticker,
            "fiscal_year_end": d.selected["10-K"]["reportDate"],
            "facts": facts,
            "ratios_computed_in_code": [{"name": r["name"], "value": r["shown"], "arithmetic": f"{r['arithmetic']} ($ millions, except per share)"} for r in d.ratios],
            "latest_quarter": quarter,
            FIRST_PARAGRAPH: self.first_paragraph,
            "peers": peers,
            "price": self.price_note,
            "calculator_variables": {name: f"{value / 1e6:,.1f} ($ millions)" if name in self.money else f"{value:,.2f}" for name, value in self.variables.items()},
        }

    def fact_entry(self, name: str, item: dict[str, Any]) -> dict[str, Any]:
        def shown(fact: dict[str, Any]) -> str:
            return f"${millions(fact['val'])} million" if item["unit"] == "USD" else f"${fact['val']:.2f}"

        def period(fact: dict[str, Any]) -> str:
            return f"{fact['start']} to {fact['end']}" if fact.get("start") else f"at {fact['end']}"

        current, prior = item["current"], item.get("prior")
        entry = {
            "concept": LABELS.get(name, name),
            "calculator_name": name,
            "value": shown(current),
            "period": period(current),
            "tag": f"us-gaap:{item['tag']} ({item['label']})",
            "filing": f"{current.get('form')} {current.get('accn')}, filed {current.get('filed')}",
        }
        if prior:
            entry.update(prior_year_value=shown(prior), prior_period=period(prior), prior_filing=f"{prior.get('form')} {prior.get('accn')}")
        return entry

    def calculator_variables(self) -> tuple[dict[str, float], set[str]]:
        variables: dict[str, float] = {}
        money: set[str] = set()
        for name, item in self.desk.fact_rows.items():
            if not item:
                continue
            for period, suffix in (("current", ""), ("prior", "_prior")):
                fact = item.get(period)
                if fact:
                    variables[name + suffix] = float(fact["val"])
                    if item["unit"] == "USD":
                        money.add(name + suffix)
        for key in ("revenue", "revenue_prior", "eps", "eps_prior"):
            if self.desk.quarter.get(key) is not None:
                variables[f"quarter_{key}"] = float(self.desk.quarter[key])
        if self.price is not None:
            variables["price"] = self.price
        return variables, money

    def run_calculator(self, asks: list[Any]) -> list[dict[str, Any]]:
        results = []
        for ask in asks[:10]:
            ask = ask if isinstance(ask, dict) else {"expression": str(ask)}
            name, expression = str(ask.get("name", "")), str(ask.get("expression", ""))
            self.calculator_count += 1
            try:
                result = calculate(expression, self.variables)
            except (ValueError, SyntaxError, ZeroDivisionError, TypeError) as exc:
                results.append({"name": name, "expression": expression, "error": str(exc)})
                continue
            used = [v for v in dict.fromkeys(re.findall(r"[A-Za-z_]\w*", expression)) if v in self.variables]
            inputs = {v: f"{self.variables[v] / 1e6:,.1f} ($ millions)" if v in self.money else f"{self.variables[v]:,.2f}" for v in used}
            results.append({
                "name": name,
                "expression": expression,
                "inputs": inputs,
                "result": f"{result:,.4f}",
                "result_in_millions": f"{result / 1e6:,.1f}",
                "as_percent": f"{result:.2%}",
            })
        return results

    # ----- the report -----

    def run(self) -> Path:
        print("\n[Strategy Manager] Sending each analyst its task as JSON")
        research = self.research()
        financial = self.financial()
        advice = self.advice(research, financial)
        parts = self.parts(research, financial, advice)
        empty = [name for name, body in parts.items() if "_Not provided._" in body or not body.strip()]
        print(f"[Strategy Manager] Five parts checked: {'all present' if not empty else 'incomplete: ' + ', '.join(empty)}")
        report = self.compile(parts, financial, research, empty)
        path = self.desk.outdir / "report.md"
        path.write_text(report, encoding="utf-8")
        (self.desk.outdir / "roles.json").write_text(json.dumps(self.model.exchanges, indent=1, ensure_ascii=False), encoding="utf-8")
        write_audit(self.desk.outdir / "audit.md", self.desk)
        return path

    def parts(self, research: dict[str, Any], financial: dict[str, Any], advice: dict[str, Any]) -> dict[str, str]:
        def claims(key: str) -> str:
            items = [c for c in research.get(key) or [] if isinstance(c, dict) and c.get("claim")]
            if not items:
                return "_Not provided._"
            lines = []
            for c in items:
                flag = "" if quote_found(str(c.get("quote", "")), self.sources) else " **[quote not found word for word in the filings]**"
                lines.append(f"- {str(c['claim']).strip()} ({c.get('source', 'filing')}: \"{str(c.get('quote', '')).strip()}\"){flag}")
            return "\n".join(lines)

        def text(key: str) -> str:
            value = financial.get(key)
            return value.strip() if isinstance(value, str) and value.strip() else "_Not provided._"

        def bullets(items: Any) -> str:
            items = [str(i).strip() for i in items or [] if str(i).strip()]
            return "\n".join(f"- {i}" for i in items) if items else "_Not provided._"

        def insight(output: dict[str, Any], role: str) -> str:
            """The role's Insight line, with the filing and the line it comes from."""
            item = output.get("insight") if isinstance(output.get("insight"), dict) else {}
            claim, source, line = (str(item.get(k) or "").strip() for k in ("claim", "source", "line"))
            if not claim:
                return f"Insight: _the {role} gave none._"
            if "us-gaap:" in line:
                return f"Insight: {claim} ({role}; {source}: {line})"
            flag = "" if quote_found(line, self.sources) else " **[line not found word for word in the filings]**"
            return f"Insight: {claim} ({role}; {source}: \"{line}\"){flag}"

        number = advice.get("deciding_number") if isinstance(advice.get("deciding_number"), dict) else {}
        recommendation = advice.get("recommendation") if advice.get("recommendation") in {"Buy", "Hold", "Sell"} else None
        decision = (
            f"**Recommendation: {recommendation}.**\n\n"
            f"The deciding number: {number.get('label', '')}: **{number.get('value', '')}** ({number.get('source', '')}).\n\n"
            f"{str(advice.get('thesis', '')).strip()}\n\n"
            f"What would change it: {str(advice.get('what_would_change_it', '')).strip()}"
        ) if recommendation else "_Not provided._"
        return {
            "Overview": "\n\n".join([claims("overview"), claims("business_model"), insight(research, "Research Analyst"),
                                     "### Core figures from the desk's steps (read and computed in code)", self.core_table()]),
            "Market Positioning and Growth Outlook": "\n\n".join([
                "### Competitive position (Research Analyst)", claims("competitive_position"),
                "### Growth, margins, returns and cash flow (Financial Analyst)", text("statement_analysis"),
                "### The latest quarter (Financial Analyst)", text("latest_quarter"),
                "### Peers on the same definitions (Financial Analyst)", text("peer_comparison"),
            ]),
            "Valuation Insights": "\n\n".join([text("valuation"), insight(financial, "Financial Analyst")]),
            "Future Developments and Strategic Recommendations": "\n\n".join([
                "### Catalysts (Research Analyst)", claims("catalysts"),
                "### Recent developments (Research Analyst)", claims("recent_developments"),
                "### Strategic recommendations (Investment Advisor)", bullets(advice.get("strategic_recommendations")),
            ]),
            "Investment Recommendation": "\n\n".join([decision, insight(advice, "Investment Advisor")]),
        }

    def core_table(self) -> str:
        d = self.desk
        ratios = {r["name"]: r for r in d.ratios}

        def fact(name: str) -> tuple[str, str]:
            item = d.fact_rows.get(name)
            current = item.get("current") if item else None
            if not current:
                return "not found", "the desk found no fact for the fiscal year"
            value = f"${millions(current['val'])}M" if item["unit"] == "USD" else f"${current['val']:.2f}"
            return value, f"us-gaap:{item['tag']}, {current.get('start', 'instant')} to {current['end']}, {current.get('form')} {current.get('accn')}"

        def ratio(name: str) -> tuple[str, str]:
            r = ratios.get(name)
            if not r or r["value"] is None:
                return "not computed", "an input is missing"
            # P/E divides a price by a per-share figure; the other ratios use $ millions.
            return r["shown"], r["arithmetic"] if name == "P/E" else f"{r['arithmetic']} ($ millions)"

        q = d.quarter
        rows = [
            ("1", f"Total revenue, fiscal year ended {d.selected['10-K']['reportDate']}", *fact("revenue")),
            ("2", "Revenue growth versus the prior year", *ratio("Revenue growth")),
            ("3", "Operating income", *fact("operating_income")),
            ("3", "Operating margin (operating income / total revenue)", *ratio("Operating margin")),
            ("4", "Net income attributable to the company", *fact("net_income")),
            ("5", "Diluted EPS, GAAP", *fact("diluted_eps")),
            ("6", "Return on average equity", *ratio("Return on average equity")),
            ("7", "Debt to equity, current portion included", *ratio("Debt to equity")),
            ("8", "Free cash flow (cash from operations - additions to property and equipment)", *ratio("Free cash flow")),
            ("9", "Latest quarter's revenue (release units)", f"{q['revenue']:,.0f}" if q.get("revenue") is not None else "not found", f"release line: {q.get('revenue_line')}"),
            ("10", "Quarter growth versus the same quarter last year", f"{q['revenue_growth']:.2%}" if q.get("revenue_growth") is not None else "not computed", f"{q['revenue']:,.0f} / {q['revenue_prior']:,.0f} - 1, the release's first two columns" if q.get("revenue_growth") is not None else "no revenue line"),
            ("11", "Quarter diluted EPS, GAAP", f"${q['eps']:.2f}" if q.get("eps") is not None else "not found", f"release line: {q.get('eps_line')}"),
            ("-", "P/E (price / diluted EPS)", *ratio("P/E")),
        ]
        lines = ["| # | Claim | Value | Source |", "|---|---|---|---|"]
        lines += [f"| {n} | {cell(claim)} | {cell(value)} | {cell(source)} |" for n, claim, value, source in rows]
        return "\n".join(lines)

    def accepted(self, form: str) -> str:
        row = self.desk.selected[form]
        return f"{row['accepted_index']} ET" if row.get("accepted_index") else f"{row['acceptanceDateTime']} UTC"

    def compile(self, parts: dict[str, str], financial: dict[str, Any], research: dict[str, Any], empty: list[str]) -> str:
        d, s = self.desk, self.desk.selected
        line1 = (
            f"Filings read: 10-K {s['10-K']['accessionNumber']} (fiscal year ended {s['10-K']['reportDate']}, accepted {self.accepted('10-K')}); "
            f"10-Q {s['10-Q']['accessionNumber']} (quarter ended {s['10-Q']['reportDate']}, accepted {self.accepted('10-Q')}); "
            f"8-K {s['8-K']['accessionNumber']} (Item 2.02 earnings release, Exhibit 99.1 {s['8-K'].get('exhibit99_1', '')}, accepted {self.accepted('8-K')}); "
            f"XBRL company facts, CIK {d.cik}"
        )
        t = self.run_time
        line2 = f"Run time: {t:%Y-%m-%d %H:%M:%S} {t.tzname()} (UTC{t:%z}); model {self.model.model}; price: {self.price_note}"
        quotes = [c for key in RESEARCH_SECTIONS for c in research.get(key) or [] if isinstance(c, dict) and c.get("quote")]
        found = sum(quote_found(str(c["quote"]), self.sources) for c in quotes)
        insights = [line for body in parts.values() for line in body.splitlines() if line.startswith("Insight:")]
        given = [line for line in insights if "gave none" not in line]
        checklist = [
            f"- The five parts: {'all present' if not empty else 'missing ' + ', '.join(empty)}",
            f"- Research Analyst quotes found word for word in the filings: {found} of {len(quotes)}",
            f"- Insight lines, one from each analyst: {len(given)} of {len(insights)}",
            f"- Calculator requests computed in code: {self.calculator_count}",
            f"- Parts sent back once: {', '.join(self.sent_back) if self.sent_back else 'none'}",
        ]
        for role, problems in self.notes.items():
            if problems:
                checklist.append(f"- Still open after the send-back, {role}: " + "; ".join(p[:200] for p in problems[:6]))
        definitions = [str(x).strip() for x in financial.get("definitions") or [] if str(x).strip()]
        body = [
            line1,
            line2,
            "Partner's check (two core claims, marked by hand against the filings): ",
            "",
            f"# {d.company} ({d.ticker}): equity research report",
            "",
            "Every number carries its filing and its line, or its XBRL tag and period. Code read the facts and computed the ratios; the model roles wrote the text.",
            "",
        ]
        for number, name in enumerate(PARTS, 1):
            body += [f"## {number}. {name}", "", parts[name], ""]
        body += ["---", "", "### Definitions used (Financial Analyst)", "", "\n".join(f"- {x}" for x in definitions) or "_None stated._", ""]
        body += ["### Strategy Manager's checklist", "", "\n".join(checklist), ""]
        body += [
            "This is a learning exercise, not financial advice.",
            f"AI assistance: {self.tools} (desk code); {getattr(self.model, 'vendor', 'Anthropic')} {self.model.model} (the analyst roles). I verified the sources myself; the judgments are mine.",
            "Any remaining errors are my own.",
            "",
        ]
        return "\n".join(body)


def write_audit(path: Path, desk: Desk) -> None:
    """A blank audit table for the human sign-off; the marks are filled by hand from the filings."""
    claims = [
        ("1", "Total revenue, latest fiscal year", "10-K income statement"),
        ("2", "Revenue growth versus the prior year", "computed from the two years in the 10-K"),
        ("3", "Operating income and operating margin", "10-K income statement; operating income / total revenue"),
        ("4", "Net income attributable to the company", "10-K income statement"),
        ("5", "Diluted EPS, GAAP", "10-K per-share section"),
        ("6", "Return on average equity", "10-K balance sheet; net income / average of two years' equity"),
        ("7", "Debt to equity", "10-K balance sheet; long-term debt including current portion / equity"),
        ("8", "Free cash flow", "10-K cash flow statement; cash from operations - additions to PP&E"),
        ("9", "The latest quarter's revenue", "earnings release, income statement"),
        ("10", "The quarter's growth versus the same quarter last year", "computed from the release's two columns"),
        ("11", "The quarter's diluted EPS, GAAP", "earnings release, per-share section"),
    ]
    rows = [f"| {n} | {claim} |  |  |  | {where} |" for n, claim, where in claims]
    rows += [
        "| - | (each other number in the Financial Analyst's part: peers, extra ratios, P/E) |  |  |  |  |",
        "| Template | the five parts present |  | - |  | - |",
        "| Recommendation | Buy, Hold or Sell names a number the report states; the thesis uses numbers marked correct |  | - |  | - |",
    ]
    lines = [
        f"# Audit: {desk.company} ({desk.ticker}) report in this folder",
        "",
        "Errors (wrong + unsupported): __   Missing: __",
        "",
        "Marked by hand against the filings named on the report's first line. Marks: Correct, Wrong, Unsupported, Missing, Not in filings.",
        "",
        "| # | Claim | Report said | Filing says | Mark | Where |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def resolve_price(price: float | None, desk: Desk, key: str, filed: datetime | None = None) -> tuple[float | None, str]:
    """The one market number: --price when given; else the last close before the release's filing time, from the
    closes reader (LSEG Workspace or the CSV file in .env), then from financialdatasets.ai. --filed overrides the
    "Accepted" time that step 2 read from the 8-K's EDGAR index page."""
    if price is not None:
        return price, f"${price:,.2f}, given with --price"
    accepted = desk.selected["8-K"].get("accepted_index")
    if filed is None and not accepted:
        return None, "none; the 8-K has no Accepted time, so give --filed or --price"
    when = filed or datetime.strptime(accepted, "%Y-%m-%d %H:%M:%S")
    moment = f"{when:%Y-%m-%d %H:%M:%S} ET, " + ("given with --filed" if filed else "when the release was accepted")
    found = closes.last_close_with_source(desk.ticker, when)
    if isinstance(found, tuple):
        day, close, source = found
        note = f"${close:,.2f}, the close of {day}, the last close before {moment}, from {source}"
        print(f"\nPrice: {note}")
        return close, note
    if not key:
        return None, "none; the closes reader has no close for it; set LSEG_APP_KEY or CLOSES_FILE in .env, or give --price"
    try:
        found = last_close_before(desk.ticker, when, key)
    except requests.RequestException as exc:
        return None, f"none; the price request failed ({exc.__class__.__name__})"
    if not found:
        return None, "none; no close found before the release"
    day, close = found
    note = f"${close:,.2f}, the close of {day}, the last close before {moment}, from financialdatasets.ai"
    print(f"\nPrice: {note}")
    return close, note


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN 67110 Lab 03: the seven steps, then the four roles and a five-part report")
    parser.add_argument("ticker", help="Ticker of any U.S. company that files with EDGAR")
    parser.add_argument("--peers", default="", help="Comma-separated peer tickers")
    parser.add_argument("--price", type=float, help="Close for P/E; without it, the last close before the release (needs FINANCIAL_DATASETS_API_KEY)")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    env = load_dotenv()

    def setting(name: str, default: str = "") -> str:
        value = os.environ.get(name) or env.get(name) or ""
        return default if is_placeholder(value) else value

    user_agent, api_key = setting("SEC_USER_AGENT"), setting("API_KEY") or setting("ANTHROPIC_API_KEY")
    problem = user_agent_problem(user_agent, env_path()) or api_key_problem(api_key, env_path())
    if problem:
        print(problem, file=sys.stderr)
        return 2
    run_time = datetime.now().astimezone()
    ticker = args.ticker.upper()
    desk = Desk(user_agent, Path("output") / f"{ticker}_{run_time:%Y%m%d_%H%M%S}")
    desk.ticker = ticker
    peers = [p.strip().upper() for p in args.peers.split(",") if p.strip()]
    try:
        desk.step1()
        desk.step2()
        price, price_note = resolve_price(args.price, desk, setting("FINANCIAL_DATASETS_API_KEY"))
        desk.step3()
        desk.step4()
        desk.step5(price)
        desk.step6()
        desk.step7(peers)
    except requests.RequestException as exc:
        print(f"SEC request failed: {exc}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"Desk stopped: {exc}", file=sys.stderr)
        return 1
    model = Model(api_key, setting("MODEL", DEFAULT_MODEL), setting("EFFORT", "medium"))
    try:
        path = StrategyManager(desk, model, price, price_note, run_time, setting("AI_TOOLS", "Claude Code")).run()
    except RoleError as exc:
        (desk.outdir / "roles.json").write_text(json.dumps(model.exchanges, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"Roles stopped: {exc}", file=sys.stderr)
        print(f"The seven steps are saved in {desk.outdir}. If the model cannot run, the fallback on the Week 2 page still counts.", file=sys.stderr)
        return 1
    print(f"\nReport: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
