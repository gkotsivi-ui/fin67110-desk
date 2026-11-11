#!/usr/bin/env python3
"""FIN 67110 Lab 04: the desk as an agent team whose process is a graph in code, with LangGraph.

The nodes, in this order on every run: the steps; the Research Analyst; the Financial Analyst; the
Investment Advisor; the Strategy Manager; the Verifier. Code decides which node runs next; a model
never does. The Manager may send a failing part back to its role one time only, no role runs more
than two times in one run, and the Verifier runs after the Manager on every run. No option turns it off.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import requests
from langgraph.graph import END, START, StateGraph

import closes
from lab02_desk import Desk, api_key_problem, env_path, is_placeholder, load_dotenv, millions, user_agent_problem
from lab03_app import (
    DEFAULT_MODEL,
    FINANCIAL_ANALYST,
    INVESTMENT_ADVISOR,
    RESEARCH_ANALYST,
    Model,
    RoleError,
    StrategyManager,
    number_keys,
    resolve_price,
    write_audit,
)
from verifier import verify_run

ANALYSTS = ["research_analyst", "financial_analyst", "investment_advisor"]
ORDER = ["steps", *ANALYSTS, "strategy_manager", "verifier"]
NAMES = {
    "steps": "The steps",
    "research_analyst": "Research Analyst",
    "financial_analyst": "Financial Analyst",
    "investment_advisor": "Investment Advisor",
    "strategy_manager": "Strategy Manager",
    "verifier": "Verifier",
}
INSTRUCTIONS = {"research_analyst": RESEARCH_ANALYST, "financial_analyst": FINANCIAL_ANALYST, "investment_advisor": INVESTMENT_ADVISOR}
MAX_RUNS = 2  # No role runs more than two times in one run.


class TeamState(TypedDict, total=False):
    ticker: str
    peers: list[str]
    price: float | None
    filed: str | None  # --filed: the release's filing time, Eastern, when it overrides the 8-K's Accepted time
    run_dir: str
    desk: Desk  # the steps' results in memory; their files are in the run folder
    manager: StrategyManager  # the checklist that checks the parts and compiles the report
    more: list[dict[str, Any]]  # ratios computed in code for the Financial Analyst
    outputs: dict[str, dict[str, Any]]  # each analyst's latest output
    runs: dict[str, int]  # how many times each analyst has run
    feedback: dict[str, list[str]]  # what the Manager sends back, per analyst
    sent_back: list[str]  # the analysts the Manager has sent back; once each
    calculator: list[dict[str, Any]]  # the calculator's results for the Financial Analyst
    next: str  # the node the Manager hands to
    report_path: str
    verified_path: str


def more_ratios(desk: Desk) -> list[dict[str, Any]]:
    """Ratios the Financial Analyst often needs, computed in code so that it never computes them itself."""
    f = desk.fact_rows

    def v(name: str, which: str = "current") -> float | None:
        return Desk.value(f.get(name), which)

    out: list[dict[str, Any]] = []

    def add(name: str, value: float | None, shown: str, arithmetic: str) -> None:
        if value is not None:
            out.append({"name": name, "value": value, "shown": shown, "arithmetic": arithmetic})

    m = millions
    for name, label in (("operating_income", "Operating income"), ("net_income", "Net income"), ("cash_from_operations", "Cash from operations"), ("capex", "Additions to property and equipment")):
        a, b = v(name), v(name, "prior")
        if a is not None and b:
            add(f"{label} growth", a / b - 1, f"{a / b - 1:.2%}", f"{m(a)} / {m(b)} - 1")
    eps, eps_prior = v("diluted_eps"), v("diluted_eps", "prior")
    if eps is not None and eps_prior:
        add("Diluted EPS growth", eps / eps_prior - 1, f"{eps / eps_prior - 1:.2%}", f"{eps:.2f} / {eps_prior:.2f} - 1")
    for which, year in (("current", "latest year"), ("prior", "prior year")):
        rev, op, ni = v("revenue", which), v("operating_income", which), v("net_income", which)
        if rev:
            if op is not None and which == "prior":
                add(f"Operating margin, {year}", op / rev, f"{op / rev:.2%}", f"{m(op)} / {m(rev)}")
            if ni is not None:
                add(f"Net margin, {year}", ni / rev, f"{ni / rev:.2%}", f"{m(ni)} / {m(rev)}")
    cfo, capex, cfo_p, capex_p = v("cash_from_operations"), v("capex"), v("cash_from_operations", "prior"), v("capex", "prior")
    if cfo_p is not None and capex_p is not None:
        add("Free cash flow, prior year", cfo_p - capex_p, f"${m(cfo_p - capex_p)}M", f"{m(cfo_p)} - {m(capex_p)}")
        if cfo is not None and capex is not None and cfo_p - capex_p:
            g = (cfo - capex) / (cfo_p - capex_p) - 1
            add("Free cash flow growth", g, f"{g:.2%}", f"({m(cfo)} - {m(capex)}) / ({m(cfo_p)} - {m(capex_p)}) - 1")
    rev, ni = v("revenue"), v("net_income")
    if cfo is not None and capex is not None:
        if rev:
            add("Free cash flow margin", (cfo - capex) / rev, f"{(cfo - capex) / rev:.2%}", f"({m(cfo)} - {m(capex)}) / {m(rev)}")
        if ni:
            add("Free cash flow / net income", (cfo - capex) / ni, f"{(cfo - capex) / ni:.2f}", f"({m(cfo)} - {m(capex)}) / {m(ni)}")
    lt, cur, eq = v("long_term_debt", "prior"), v("current_debt", "prior") or 0.0, v("equity", "prior")
    if lt is not None and eq:
        if f.get("long_term_debt") and f["long_term_debt"]["tag"] == "LongTermDebt":
            cur = 0.0  # This tag already includes current maturities.
        add("Debt to equity, prior year", (lt + cur) / eq, f"{(lt + cur) / eq:.3f}", f"({m(lt)} + {m(cur)}) / {m(eq)}")
    q = desk.quarter
    if q.get("eps") is not None and q.get("eps_prior"):
        g = q["eps"] / q["eps_prior"] - 1
        add("Quarter diluted EPS growth on the same quarter last year", g, f"{g:.2%}", f"{q['eps']:.2f} / {q['eps_prior']:.2f} - 1 (the release's first two columns)")
    return out


class Team:
    """The graph's nodes and its edges. Every edge is code."""

    def __init__(self, settings: dict[str, Any], model: Model) -> None:
        self.settings = settings
        self.model = model
        self.count = 0

    @staticmethod
    def starting(node: str) -> None:
        print(f"\n=== {NAMES[node]} ===")

    def save(self, state: TeamState, node: str, given: Any, returned: Any) -> None:
        """Each node's input and output, numbered in the order the nodes ran."""
        self.count += 1
        folder = Path(state["run_dir"]) / "nodes"
        folder.mkdir(parents=True, exist_ok=True)
        record = {"node": NAMES[node], "input": given, "output": returned}
        (folder / f"{self.count:02d}_{node}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    # ----- the nodes -----

    def steps(self, state: TeamState) -> dict[str, Any]:
        self.starting("steps")
        desk = Desk(self.settings["user_agent"], Path(state["run_dir"]))
        desk.ticker = state["ticker"]
        desk.step1()
        desk.step2()
        filed = datetime.fromisoformat(state["filed"]) if state.get("filed") else None
        price, note = resolve_price(state.get("price"), desk, self.settings["prices_key"], filed)
        desk.step3()
        desk.step4()
        desk.step5(price)
        desk.step6()
        desk.step7(state.get("peers", []))
        manager = StrategyManager(desk, self.model, price, note, self.settings["run_time"], self.settings["tools"])
        more = more_ratios(desk)
        keys = ("accessionNumber", "filingDate", "reportDate", "accepted_index", "exhibit99_1", "saved_text")
        self.save(state, "steps", {"ticker": desk.ticker, "peers": state.get("peers", []), "price": state.get("price"), "filed": state.get("filed")}, {
            "company": desk.company,
            "cik": desk.cik,
            "filings": {form: {k: row.get(k) for k in keys} for form, row in desk.selected.items()},
            "facts": "facts.json and peer_facts.json in this folder",
            "ratios": desk.ratios,
            "more_ratios": more,
            "quarter": desk.quarter,
            "price": note,
        })
        return {"desk": desk, "manager": manager, "price": price, "more": more, "outputs": {}, "runs": {a: 0 for a in ANALYSTS}, "feedback": {}, "sent_back": [], "calculator": []}

    def analyst(self, role: str):
        def node(state: TeamState) -> dict[str, Any]:
            self.starting(role)
            runs = dict(state["runs"])
            if runs[role] >= MAX_RUNS:
                raise RoleError(f"{NAMES[role]} would run a third time; the graph allows two")
            packet = self.packet(role, state)
            output = self.model.ask(NAMES[role], INSTRUCTIONS[role], packet)
            runs[role] += 1
            self.save(state, role, packet, output)
            feedback = {k: v for k, v in state["feedback"].items() if k != role}
            return {"outputs": {**state["outputs"], role: output}, "runs": runs, "feedback": feedback}

        return node

    def packet(self, role: str, state: TeamState) -> dict[str, Any]:
        """The JSON the graph gives a role: the task, the context and the expected output, and nothing else."""
        m = state["manager"]
        if role == "research_analyst":
            packet = m.research_packet()
        elif role == "financial_analyst":
            packet = m.financial_packet()
            context = packet["context"]
            context["ratios_computed_in_code"] += [{"name": r["name"], "value": r["shown"], "arithmetic": f"{r['arithmetic']} ($ millions, except per share)"} for r in state["more"]]
            if state.get("calculator"):
                context["calculator_results"] = state["calculator"]
            m.known = number_keys(json.dumps(context, ensure_ascii=False))
        else:
            outputs = state["outputs"]
            packet = m.advice_packet(outputs["research_analyst"], outputs["financial_analyst"])
        feedback = state["feedback"].get(role)
        if feedback:
            packet = dict(packet, previous_output=state["outputs"].get(role), manager_feedback=feedback)
        return packet

    def strategy_manager(self, state: TeamState) -> dict[str, Any]:
        self.starting("strategy_manager")
        m, outputs, runs = state["manager"], state["outputs"], state["runs"]
        problems, calculator = self.review(state)
        sent = set(state.get("sent_back", []))
        for role in ANALYSTS:
            if problems[role] and runs[role] < MAX_RUNS and role not in sent:
                print(f"[Strategy Manager] Sending the {NAMES[role]}'s part back once: {len(problems[role])} problem(s)")
                for problem in problems[role][:5]:
                    print(f"    - {problem[:160]}")
                m.sent_back.append(f"{NAMES[role]} ({len(problems[role])} problem(s))")
                self.save(state, "strategy_manager", {"problems": problems}, {"next": NAMES[role], "manager_feedback": problems[role]})
                update: dict[str, Any] = {"feedback": {**state["feedback"], role: problems[role]}, "sent_back": sorted(sent | {role}), "next": role}
                if role == "financial_analyst" and calculator:
                    update["calculator"] = calculator
                return update
        for role in ANALYSTS:
            m.notes[NAMES[role]] = problems[role]
        research, financial, advice = (outputs[a] for a in ANALYSTS)
        parts = m.parts(research, financial, advice)
        empty = [name for name, body in parts.items() if "_Not provided._" in body or not body.strip()]
        print(f"[Strategy Manager] Five parts checked: {'all present' if not empty else 'incomplete: ' + ', '.join(empty)}")
        path = Path(state["run_dir"]) / "report.md"
        path.write_text(m.compile(parts, financial, research, empty), encoding="utf-8")
        write_audit(Path(state["run_dir"]) / "audit.md", state["desk"])
        print(f"[Strategy Manager] Report compiled: {path}")
        self.save(state, "strategy_manager", {"problems": problems, "runs": runs}, {"next": "Verifier", "report": str(path), "parts_missing": empty})
        return {"next": "verifier", "report_path": str(path)}

    def review(self, state: TeamState) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
        """The Manager's checklist on each analyst's latest output; a requested ratio is computed in code."""
        m, outputs = state["manager"], state["outputs"]
        research, financial, advice = (outputs[a] for a in ANALYSTS)
        calculator: list[dict[str, Any]] = []
        asks = financial.get("calculator_requests") or []
        financial_problems = m.check_financial(financial)
        if isinstance(asks, list) and asks and state["runs"]["financial_analyst"] < MAX_RUNS:
            calculator = m.run_calculator(asks)
            print(f"[Strategy Manager] Calculator: {len(calculator)} ratio(s) computed in code for the Financial Analyst")
            financial_problems = ["Use context.calculator_results for the ratios you asked for. Do not request more calculations."] + financial_problems
        advice_context = m.advice_packet(research, financial)["context"]
        problems = {
            "research_analyst": m.check_research(research),
            "financial_analyst": financial_problems,
            "investment_advisor": m.check_advice(advice, advice_context),
        }
        return problems, calculator

    def verifier(self, state: TeamState) -> dict[str, Any]:
        self.starting("verifier")
        run_dir = Path(state["run_dir"])
        result = verify_run(run_dir, self.model)
        given = {"report": "report.md", "filing_texts": sorted(p.name for p in run_dir.glob("*.txt")), "facts": ["facts.json", "peer_facts.json"]}
        self.save(state, "verifier", given, {"verified_report": result["path"], "counts": result["counts"]})
        return {"verified_path": result["path"]}

    # ----- the edges -----

    def graph(self):
        """The process: the same nodes in the same order on every run. Every path to the end runs the Verifier."""
        g = StateGraph(TeamState)
        g.add_node("steps", self.steps)
        for role in ANALYSTS:
            g.add_node(role, self.analyst(role))
        g.add_node("strategy_manager", self.strategy_manager)
        g.add_node("verifier", self.verifier)
        g.add_edge(START, "steps")
        g.add_edge("steps", "research_analyst")
        # A role the Manager sent back returns to the Manager; on the first pass the next analyst runs.
        g.add_conditional_edges("research_analyst", lambda s: "financial_analyst" if s["runs"]["financial_analyst"] == 0 else "strategy_manager", ["financial_analyst", "strategy_manager"])
        g.add_conditional_edges("financial_analyst", lambda s: "investment_advisor" if s["runs"]["investment_advisor"] == 0 else "strategy_manager", ["investment_advisor", "strategy_manager"])
        g.add_edge("investment_advisor", "strategy_manager")
        g.add_conditional_edges("strategy_manager", lambda s: s["next"], [*ANALYSTS, "verifier"])
        g.add_edge("verifier", END)
        return g.compile()


def new_run_dir(ticker: str, when: datetime) -> Path:
    """A folder named by company, date and time; never one that holds an earlier run."""
    base = Path("output") / f"{ticker}_{when:%Y%m%d_%H%M%S}"
    path, n = base, 1
    while path.exists():
        n += 1
        path = base.with_name(f"{base.name}_{n}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="FIN 67110 Lab 04: the agent team, a graph in code with a Verifier on every run")
    parser.add_argument("ticker", nargs="?", help="Ticker of any U.S. company that files with EDGAR")
    parser.add_argument("--peers", default="", help="Comma-separated peer tickers")
    parser.add_argument("--price", type=float, help="Close for P/E; without it, the closes reader gives the last close before the release's filing time")
    parser.add_argument("--filed", type=closes.parse_when, help="The release's filing time, YYYY-MM-DDTHH:MM:SS Eastern; it overrides the Accepted time on the 8-K's EDGAR index page")
    parser.add_argument("--verify-only", metavar="RUN_FOLDER", help="Run the Verifier on a saved run, and nothing else")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    env = load_dotenv()

    def setting(name: str, default: str = "") -> str:
        value = os.environ.get(name) or env.get(name) or ""
        return default if is_placeholder(value) else value

    api_key = setting("API_KEY") or setting("ANTHROPIC_API_KEY")
    problem = api_key_problem(api_key, env_path())
    if problem:
        print(problem, file=sys.stderr)
        return 2
    model = Model(api_key, setting("MODEL", DEFAULT_MODEL), setting("EFFORT", "medium"))
    print(f"Model: {model.vendor} {model.model}")

    if args.verify_only:
        run_dir = Path(args.verify_only)
        if not (run_dir / "report.md").exists() or not (run_dir / "facts.json").exists():
            print(f"{run_dir} is not a saved run: it needs report.md, facts.json and the filing texts.", file=sys.stderr)
            return 2
        print("\n=== Verifier ===")
        try:
            result = verify_run(run_dir, model)
        except RoleError as exc:
            print(f"Verifier stopped: {exc}", file=sys.stderr)
            return 1
        print(f"\nVerified report: {result['path']}")
        return 0

    if not args.ticker:
        parser.error("give a ticker, or --verify-only with a run folder")
    user_agent = setting("SEC_USER_AGENT")
    problem = user_agent_problem(user_agent, env_path())
    if problem:
        print(problem, file=sys.stderr)
        return 2
    run_time = datetime.now().astimezone()
    ticker = args.ticker.upper()
    run_dir = new_run_dir(ticker, run_time)
    settings = {"user_agent": user_agent, "prices_key": setting("FINANCIAL_DATASETS_API_KEY"), "run_time": run_time, "tools": setting("AI_TOOLS", "Claude Code")}
    team = Team(settings, model)
    print("Graph: " + " -> ".join(NAMES[n] for n in ORDER))
    state = {"ticker": ticker, "peers": [p.strip().upper() for p in args.peers.split(",") if p.strip()], "price": args.price,
             "filed": args.filed.isoformat() if args.filed else None, "run_dir": str(run_dir)}
    try:
        final = team.graph().invoke(state, {"recursion_limit": 40})
    except requests.RequestException as exc:
        print(f"SEC request failed: {exc}", file=sys.stderr)
        return 1
    except RoleError as exc:
        print(f"Agent team stopped: {exc}", file=sys.stderr)
        print(f"Everything this run saved is in {run_dir}. If the model cannot run, the fallback on the Week 2 page still produces a report.", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"Agent team stopped: {exc}", file=sys.stderr)
        return 1
    print(f"\nRun folder: {run_dir}\nReport: {final['report_path']}\nVerified report: {final['verified_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
