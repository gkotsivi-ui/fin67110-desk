#!/usr/bin/env python3
"""The group desk page. Enter a ticker or screen. The page calls this repository's desk.py
and shows its progress and verified report.

Start it:  python page.py
Or double-click start_page.bat (Windows) or start_page.command (Mac). The page opens in your browser.
It listens on this computer only (127.0.0.1), and runs one job at a time.
"""

from __future__ import annotations

import argparse
from datetime import date
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import markdown

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
DESK_COMMAND = ROOT / "desk.py"
NODES = ["inputs", "seeker", "pick", "team", "worksheet", "final report"]


TICKER = re.compile(r"[A-Za-z][A-Za-z0-9.\-]{0,15}")
FILED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
PORT = 8765


class Run:
    """One run of the group pipeline. Its output is kept line by line for the page."""

    def __init__(self, args: list[str]) -> None:
        self.args = args
        self.lines: list[str] = []
        self.code: int | None = None
        self.verified = ""
        self.lock = threading.Lock()
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PYTHONUTF8="1")
        self.process = subprocess.Popen([sys.executable, "-u", str(DESK_COMMAND), *args], cwd=ROOT, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self.read, daemon=True).start()

    def read(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            line = raw.rstrip("\r\n")
            found = re.match(r"Final report: (.+)$", line)
            if found:
                self.verified = found.group(1).strip()
            with self.lock:
                self.lines.append(line)
        self.code = self.process.wait()  # set after the last line, so a finished run has all its lines

    @property
    def done(self) -> bool:
        return self.code is not None


RUN: Run | None = None
RUN_LOCK = threading.Lock()
REVIEW_JOB = None


def review_folder(value: str) -> Path:
    """Review only saved runs under this repository, never arbitrary filesystem folders."""
    path = (ROOT / value).resolve()
    allowed = [(ROOT / "runs/live").resolve(), (ROOT / "runs/practice").resolve(), OUTPUT.resolve()]
    if not path.is_dir() or not any(base in path.parents for base in allowed):
        raise ValueError("Choose a run folder inside runs/live, runs/practice, or output.")
    return path


class ReviewJob:
    """A separate read-only review job. It cannot stop or repair a desk run."""
    def __init__(self, folder, number, use_model):
        self.done = False
        self.result = None
        self.error = ""
        self.folder = folder
        self.number = number
        self.use_model = use_model
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            from desk_error_review import configured_model, review_run
            model = configured_model() if self.use_model else None
            self.result = review_run(self.folder, ROOT / "runs/live", self.number,
                                     (ROOT / "runs/live").resolve() not in self.folder.parents,
                                     ROOT, model=model)
        except Exception as exc:
            # Do not send provider errors or credentials to the browser.
            self.error = f"Review stopped ({type(exc).__name__}). Check saved evidence and review configuration."
        finally:
            self.done = True


def arguments(body: dict[str, Any]) -> tuple[list[str], str]:
    """Arguments for this repository's complete pipeline, never another project."""
    ticker = str(body.get("ticker", "")).strip().upper()
    if not TICKER.fullmatch(ticker):
        return [], "Type a ticker or screen."
    args = ["screen" if ticker == "SCREEN" else ticker]
    peers = [p.strip().upper() for p in str(body.get("peers", "")).split(",") if p.strip()]
    if len(peers) > 10 or any(not TICKER.fullmatch(p) for p in peers):
        return [], "Peers are tickers with commas between them, ten at most."
    if peers:
        args += ["--peers", *peers]
    refresh = str(body.get("refresh_screen", "")).strip()
    if refresh:
        try:
            if date.fromisoformat(refresh).isoformat() != refresh:
                raise ValueError
        except ValueError:
            return [], "The seeker start date is YYYY-MM-DD."
        args += ["--refresh-screen", refresh]
    registry = str(body.get("registry", "")).strip()
    if registry:
        path = (ROOT / registry).resolve()
        if ROOT.resolve() not in path.parents or not path.is_file() or path.suffix != ".json":
            return [], "Select a saved registry JSON inside this repository."
        args += ["--registry", str(path)]
    filed = str(body.get("filed", "")).strip()
    if filed:
        if not FILED.fullmatch(filed):
            return [], "The filing time is YYYY-MM-DDTHH:MM:SS, in Eastern time."
        args += ["--filed", filed]
    if body.get("live") is True:
        args += ["--live"]
    return args, ""


def safe_report(relative: str) -> Path | None:
    """The report file, when it is a Markdown file inside the output folder; None for any other path."""
    try:
        path = (ROOT / relative).resolve()
    except (OSError, ValueError):
        return None
    if path.suffix.lower() != ".md" or not path.is_file():
        return None
    if OUTPUT.resolve() in path.parents:
        return path
    roots = [(ROOT / "runs" / kind).resolve() for kind in ("live", "practice")]
    if (path.parent.parent in roots and path.name in {"report.md", "verified_report.md"}
            and not (path.parent / "desk_run.json").exists()):
        return path
    if path.parent.parent in roots and path.name == "final_report.md":
        try:
            state = json.loads((path.parent / "desk_run.json").read_text())
            if state.get("status") == "complete" and state.get("final_report") == path.name:
                return path
        except (OSError, ValueError, AttributeError):
            pass
    return None


def report_link(printed: str) -> str:
    """The verified report's path as team.py printed it, made relative to this folder for the page."""
    if not printed:
        return ""
    path = safe_report(printed)
    return path.relative_to(ROOT.resolve()).as_posix() if path else ""


def render(path: Path) -> str:
    """The report as HTML. Its text is escaped first, so nothing in a filing or a model's reply becomes markup."""
    text = html.escape(path.read_text(encoding="utf-8"), quote=False)
    # Reports verified before the Verifier's fix escape a quoted table bar twice (\\|), which would split the row.
    text = text.replace("\\\\|", "\\|")
    return markdown.markdown(text, extensions=["tables", "sane_lists", "nl2br"])


class Page(BaseHTTPRequestHandler):
    server_version = "DeskPage/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Keep the terminal quiet; the page shows what matters.

    # ----- requests -----

    def from_here(self) -> bool:
        """Only this computer's own browser: the Host must be this page, and a POST must come from this page as JSON,
        so that another website cannot start a run that spends the API key."""
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed:
            self.send_json({"error": "This page answers only at its own address."}, HTTPStatus.FORBIDDEN)
            return False
        if self.command == "POST":
            origin = self.headers.get("Origin")
            if origin and origin.removeprefix("http://") not in allowed:
                self.send_json({"error": "A run starts only from this page."}, HTTPStatus.FORBIDDEN)
                return False
            if not str(self.headers.get("Content-Type", "")).startswith("application/json"):
                self.send_json({"error": "Send JSON."}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return False
        return True

    def do_GET(self) -> None:
        if not self.from_here():
            return
        url = urlparse(self.path)
        routes = {"/": self.route_page, "/status": self.route_status, "/events": self.route_events, "/report": self.route_report, "/runs": self.route_runs, "/setup": self.route_setup,
                  "/review/status": self.route_review_status, "/review/download": self.route_review_download}
        handler = routes.get(url.path)
        if handler is None:
            self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        handler(parse_qs(url.query))

    def do_POST(self) -> None:
        if not self.from_here():
            return
        path = urlparse(self.path).path
        if path == "/run":
            self.route_start()
        elif path == "/stop":
            self.route_stop()
        elif path == "/review":
            self.route_review_start()
        else:
            self.send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    # ----- answers -----

    def send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def route_page(self, query: dict[str, list[str]]) -> None:
        self.send_html(PAGE.replace("__NODES__", json.dumps(NODES)))

    def route_status(self, query: dict[str, list[str]]) -> None:
        run = RUN
        self.send_json({"running": bool(run and not run.done), "command": " ".join(["desk.py", *run.args]) if run else ""})

    def route_start(self) -> None:
        global RUN
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": "Send JSON."}, HTTPStatus.BAD_REQUEST)
            return
        args, problem = arguments(body if isinstance(body, dict) else {})
        if problem:
            self.send_json({"error": problem}, HTTPStatus.BAD_REQUEST)
            return
        with RUN_LOCK:
            if REVIEW_JOB and not REVIEW_JOB.done:
                self.send_json({"error": "A saved-run review is active. Wait for it to finish."}, HTTPStatus.CONFLICT)
                return
            if RUN and not RUN.done:
                self.send_json({"error": "A run is still going. Wait for it to end, or stop it."}, HTTPStatus.CONFLICT)
                return
            try:
                RUN = Run(args)
            except OSError as exc:
                self.send_json({"error": f"Could not start the desk ({exc.strerror})."}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        self.send_json({"command": " ".join(["desk.py", *args])})

    def route_stop(self) -> None:
        run = RUN
        if run and not run.done:
            run.process.terminate()
        self.send_json({"stopped": bool(run)})

    def route_review_start(self):
        global REVIEW_JOB
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= 16384:
                raise ValueError("invalid request length")
            body = json.loads(self.rfile.read(length))
            folder = review_folder(str(body.get("folder", "")))
            number = body.get("record_number")
            if number not in (None, ""):
                if isinstance(number, bool) or not str(number).isdigit() or int(number) < 1:
                    raise ValueError("Record number must be a positive integer.")
                number = int(number)
            else:
                number = None
            use_model = body.get("model", False)
            if not isinstance(use_model, bool):
                raise ValueError("Model selection must be true or false.")
        except (ValueError, TypeError, AttributeError, OSError):
            self.send_json({"error": "Choose a valid saved run folder and positive record number."}, HTTPStatus.BAD_REQUEST)
            return
        with RUN_LOCK:
            if (RUN and not RUN.done) or (REVIEW_JOB and not REVIEW_JOB.done):
                self.send_json({"error": "A desk run or review is active. Wait for it to finish."}, HTTPStatus.CONFLICT)
                return
            REVIEW_JOB = ReviewJob(folder, number, use_model)
        self.send_json({"started": True}, HTTPStatus.ACCEPTED)

    def route_review_status(self, query):
        job = REVIEW_JOB
        self.send_json({"done": job.done if job else True, "error": job.error if job else "",
                        "result": job.result if job and job.done else None})

    def route_review_download(self, query):
        job = REVIEW_JOB
        key = query.get("kind", [""])[0]
        if not job or not job.done or not job.result or key not in {"human", "ai"}:
            self.send_json({"error": "No review document is available."}, HTTPStatus.NOT_FOUND)
            return
        path = Path(job.result["outputs"][key])
        # Serve only the exact output of the current review, not a user-supplied path.
        prefix = "Error Documentation " if key == "human" else "AI Error Prompt "
        if (path.is_symlink() or path.resolve().parent != job.folder.resolve()
                or path.suffix != ".md" or not path.name.startswith(prefix)):
            self.send_json({"error": "Invalid review output."}, HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{key}-error-report.md"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def route_events(self, query: dict[str, list[str]]) -> None:
        """The run's output as server-sent events, one per line, then one event when the run ends."""
        run = RUN
        if run is None:
            self.send_json({"error": "No run yet."}, HTTPStatus.NOT_FOUND)
            return
        try:
            sent = int(self.headers.get("Last-Event-ID", "-1")) + 1
        except ValueError:
            sent = 0
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                with run.lock:
                    new = run.lines[sent:]
                for line in new:
                    self.wfile.write(f"id: {sent}\nevent: line\ndata: {json.dumps(line)}\n\n".encode("utf-8"))
                    sent += 1
                if new:
                    self.wfile.flush()
                if run.done:
                    with run.lock:
                        finished = sent >= len(run.lines)
                    if finished:
                        end = {"code": run.code, "verified": report_link(run.verified) if run.code == 0 else ""}
                        self.wfile.write(f"id: {sent}\nevent: done\ndata: {json.dumps(end)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        return
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def route_report(self, query: dict[str, list[str]]) -> None:
        path = safe_report(query.get("path", [""])[0])
        if path is None:
            self.send_json({"error": "That report is unavailable."}, HTTPStatus.NOT_FOUND)
            return
        self.send_html(render(path))

    def route_runs(self, query: dict[str, list[str]]) -> None:
        """The saved runs that have a verified report, newest first, each with its newest verified report."""
        found = []
        for folder in sorted(OUTPUT.iterdir()) if OUTPUT.is_dir() else []:
            reports = sorted(folder.glob("verified_report*.md"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
            if reports:
                newest = reports[-1]
                found.append({"name": folder.name, "path": newest.relative_to(ROOT).as_posix(), "time": newest.stat().st_mtime})
        for kind in ("live", "practice"):
            for folder in (ROOT / "runs" / kind).glob("*"):
                if not folder.is_dir():
                    continue
                # Joined runs publish only the final report. Historical team-only records remain readable.
                name = "final_report.md" if (folder / "desk_run.json").exists() else "verified_report.md"
                report = safe_report(str(folder / name))
                if report:
                    found.append({"name": folder.name, "path": report.relative_to(ROOT.resolve()).as_posix(), "time": report.stat().st_mtime})
        found.sort(key=lambda r: r["time"], reverse=True)
        self.send_json(found[:60])

    def route_setup(self, query: dict[str, list[str]]) -> None:
        """check_env.py without its network checks, so the page can say what to fix before a run."""
        try:
            done = subprocess.run([sys.executable, str(ROOT / "check_pipeline.py")], cwd=ROOT, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=60, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            self.send_json({"ok": done.returncode == 0, "lines": [line for line in done.stdout.splitlines() if line.strip()]})
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.send_json({"ok": False, "lines": [f"FIX   check_env.py did not run: {exc}"]})


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Equity research desk</title>
<style>
:root { --bg: #f6f7f9; --card: #ffffff; --text: #1d2330; --muted: #5d6677; --line: #dde1e8; --accent: #1f5fbf;
        --ok: #1b7a3d; --ok-bg: #e7f5ec; --bad: #b3261e; --bad-bg: #fbeaea; --warn: #8a5a00; --warn-bg: #fdf3dc; --now: #fff4cc; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #14171c; --card: #1c2027; --text: #e6e9ef; --muted: #9aa3b2; --line: #2e3440; --accent: #7aa8ff;
          --ok: #6fd18f; --ok-bg: #16301f; --bad: #ff8a80; --bad-bg: #3a1c1c; --warn: #f2c66d; --warn-bg: #3a2f14; --now: #3a3416; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 20px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.card h2 { font-size: 16px; margin: 0 0 12px; }
form .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
label { display: block; font-weight: 600; font-size: 13px; margin-bottom: 4px; }
label span { font-weight: 400; color: var(--muted); }
input { width: 100%; padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--text); font: inherit; }
.buttons { display: flex; gap: 8px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
button { padding: 8px 18px; border-radius: 6px; border: 1px solid var(--accent); background: var(--accent); color: #fff; font: inherit; font-weight: 600; cursor: pointer; }
button.quiet { background: transparent; color: var(--accent); }
button:disabled { opacity: .5; cursor: default; }
.hint { color: var(--muted); font-size: 13px; }
.message { margin-top: 10px; padding: 8px 10px; border-radius: 6px; }
.message.bad { background: var(--bad-bg); color: var(--bad); }
.message.ok { background: var(--ok-bg); color: var(--ok); }
.setup { padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
.setup.good { background: var(--ok-bg); color: var(--ok); }
.setup.bad { background: var(--warn-bg); color: var(--warn); }
.setup ul { margin: 6px 0 0 18px; padding: 0; }
ol.graph { list-style: none; display: flex; flex-wrap: wrap; gap: 8px; padding: 0; margin: 0 0 12px; }
ol.graph li { border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; color: var(--muted); font-size: 14px; }
ol.graph li .n { font-weight: 700; margin-right: 6px; }
ol.graph li.ran { border-color: var(--ok); color: var(--ok); }
ol.graph li.now { border-color: var(--warn); color: var(--text); background: var(--now); }
ol.timeline { margin: 0; padding-left: 22px; }
ol.timeline li { margin: 2px 0; }
ol.timeline li time { color: var(--muted); font-size: 12px; margin-left: 8px; }
.command { font-family: ui-monospace, Consolas, monospace; font-size: 13px; color: var(--muted); margin: 0 0 8px; word-break: break-all; }
details summary { cursor: pointer; color: var(--accent); }
pre.log { max-height: 320px; overflow: auto; background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 10px; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
.report-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.report-head select { padding: 6px 8px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg); color: var(--text); font: inherit; max-width: 100%; }
#report { overflow-x: auto; }
#report table { border-collapse: collapse; font-size: 13px; margin: 8px 0 16px; }
#report th, #report td { border: 1px solid var(--line); padding: 4px 8px; vertical-align: top; text-align: left; }
#report th { background: var(--bg); }
#report h1 { font-size: 22px; } #report h2 { font-size: 18px; margin-top: 28px; } #report h3 { font-size: 15px; }
#report p.insight { border-left: 4px solid var(--accent); padding: 6px 10px; background: var(--bg); border-radius: 4px; }
.mark-correct { color: var(--ok); } .mark-wrong { color: var(--bad); } .mark-unsupported { color: var(--warn); } .mark-not-checked { color: var(--muted); }
.empty { color: var(--muted); }
</style>
</head>
<body>
<main>
<h1>Equity research desk</h1>
<p class="sub">Run this repository's seeker, team, worksheet, and blocking hook from one command.</p>
<div id="setup" class="setup" hidden></div>

<section class="card">
<h2>Run the group desk</h2>
<form id="form" autocomplete="off">
<div class="row">
<div><label for="ticker">Ticker or screen</label><input id="ticker" required maxlength="16" placeholder="Ticker"></div>
<div><label for="peers">Peers <span>optional, with commas</span></label><input id="peers" maxlength="120" placeholder="Separate tickers with commas"></div>
<div><label for="refresh-screen">Refresh seeker <span>distribution start date</span></label><input id="refresh-screen" type="date"></div><div><label for="registry">Saved registry <span>optional local JSON path</span></label><input id="registry" placeholder="runs/practice/SAVED_RUN/registry.json"></div>
<div><label for="filed">Filing time <span>optional, Eastern</span></label><input id="filed" maxlength="19" placeholder="YYYY-MM-DDTHH:MM:SS"></div>
</div>
<p><label><input id="live-run" type="checkbox" style="width:auto"> Save as a live record</label></p><p class="hint">For a fresh clone, provide a seeker start date. Otherwise select a saved local registry.</p>
<div class="buttons">
<button id="run" type="submit">Run</button>
<button id="stop" type="button" class="quiet" disabled>Stop</button>
<span class="hint">A run calls the model with the key in .env, which costs a little, and takes several minutes.</span>
</div>
<div id="message" class="message" hidden></div>
</form>
</section>

<section class="card">
<h2>Desk execution order</h2>
<p id="command" class="command"></p>
<ol id="graph" class="graph"></ol>
<ol id="timeline" class="timeline"></ol>
<p id="idle" class="empty">Each desk part appears here when it starts.</p>
<details><summary>Everything the run prints</summary><pre id="log" class="log"></pre></details>
</section>

<section class="card">
<div class="report-head"><h2>Final report</h2><select id="saved"><option value="">Open a saved report</option></select></div>
<div id="report"><p class="empty">The verified team report and worksheet view appear here after the final output check passes.</p></div>
</section>
<section class="card">
<h2>Review a saved run</h2>
<p class="hint">Save review reports in the run folder while preserving its original research files. Findings do not authorize repairs.</p>
<form id="review-form">
<div class="row">
<div><label for="review-folder">Saved run folder</label><input id="review-folder" required placeholder="runs/live/TICKER_timestamp"></div>
<div><label for="review-number">Record number <span>blank: use the established number</span></label><input id="review-number" type="number" min="1"></div>
</div>
<p><label><input id="review-model" type="checkbox" style="width:auto"> Use the configured model to review patterns and conclusions</label></p>
<p class="hint">Model review sends saved SEC evidence to your configured provider and uses your API key. Code checks work offline.</p>
<button id="review-start" type="submit">Review saved run</button>
</form>
<p id="review-message" role="status"></p>
<div id="review-downloads" hidden>
<a href="/review/download?kind=human" download>Download human report</a> ·
<a href="/review/download?kind=ai" download>Download AI prompt</a>
</div>
<div id="review-results"></div>
</section>
</main>
<script>
const NODES = __NODES__;
const $ = (s) => document.querySelector(s);
let source = null;

function say(text, kind) { const m = $('#message'); m.textContent = text; m.className = 'message ' + kind; m.hidden = !text; }

function graph() {
  $('#graph').innerHTML = '';
  NODES.forEach((name, i) => {
    const li = document.createElement('li'); li.dataset.node = name;
    const n = document.createElement('span'); n.className = 'n'; n.textContent = i + 1;
    li.append(n, document.createTextNode(name)); $('#graph').append(li);
  });
}

function reached(name) {
  $('#idle').hidden = true;
  document.querySelectorAll('#graph li.now').forEach((li) => { li.classList.remove('now'); li.classList.add('ran'); });
  const chip = document.querySelector(`#graph li[data-node="${CSS.escape(name)}"]`);
  if (chip) { chip.classList.remove('ran'); chip.classList.add('now'); }
  const li = document.createElement('li'); li.textContent = name;
  const t = document.createElement('time'); t.textContent = new Date().toLocaleTimeString(); li.append(t);
  $('#timeline').append(li);
}

function busy(on) { $('#run').disabled = on; $('#stop').disabled = !on; }

function listen() {
  if (source) source.close();
  busy(true);
  source = new EventSource('/events');
  source.addEventListener('line', (e) => {
    const line = JSON.parse(e.data);
    const log = $('#log'); log.textContent += line + '\\n'; log.scrollTop = log.scrollHeight;
    const part = line.match(/^Part starting: (.+)$/); if (part && NODES.includes(part[1])) reached(part[1]);
  });
  source.addEventListener('done', async (e) => {
    source.close(); source = null; busy(false);
    document.querySelectorAll('#graph li.now').forEach((li) => { li.classList.remove('now'); li.classList.add('ran'); });
    const end = JSON.parse(e.data);
    if (end.code === 0 && end.verified) { say('The run completed. The final report is below.', 'ok'); await saved(); showReport(end.verified); }
    else {
      const last = $('#log').textContent.trim().split('\\n').slice(-6).join('\\n');
      say(`The run stopped (exit code ${end.code}). Its last lines:\\n${last}`, 'bad');
      $('#message').style.whiteSpace = 'pre-wrap';
    }
  });
}

async function showReport(path) {
  const r = await fetch('/report?path=' + encodeURIComponent(path));
  if (!r.ok) { $('#report').innerHTML = '<p class="empty">That report could not be opened.</p>'; return; }
  $('#report').innerHTML = await r.text();  // The server escapes the report's text before it renders the Markdown.
  const marks = { 'correct': 'mark-correct', 'wrong': 'mark-wrong', 'unsupported': 'mark-unsupported', 'not checked': 'mark-not-checked' };
  document.querySelectorAll('#report strong').forEach((s) => { const c = marks[s.textContent.trim()]; if (c) s.classList.add(c); });
  document.querySelectorAll('#report p').forEach((p) => { if (p.textContent.startsWith('Insight:')) p.classList.add('insight'); });
  $('#saved').value = path;
}

async function saved() {
  const runs = await (await fetch('/runs')).json();
  const select = $('#saved'); const keep = select.value;
  select.length = 1;
  runs.forEach((r) => { const o = document.createElement('option'); o.value = r.path; o.textContent = r.name; select.append(o); });
  select.value = keep;
}

async function setup() {
  const s = await (await fetch('/setup')).json();
  const box = $('#setup'); box.hidden = false; box.innerHTML = '';
  const fixes = s.lines.filter((l) => l.startsWith('FIX'));
  if (!fixes.length) { box.className = 'setup good'; box.textContent = 'Desk setup passed the local checks.'; return; }
  box.className = 'setup bad';
  const head = document.createElement('strong'); head.textContent = 'Fix the setup before a run:'; box.append(head);
  const ul = document.createElement('ul');
  fixes.forEach((l) => { const li = document.createElement('li'); li.textContent = l.replace(/^FIX\\s+/, ''); ul.append(li); });
  box.append(ul);
}

$('#form').addEventListener('submit', async (e) => {
  e.preventDefault(); say('', ''); $('#message').style.whiteSpace = '';
  const body = { ticker: $('#ticker').value, peers: $('#peers').value, refresh_screen: $('#refresh-screen').value, registry: $('#registry').value, live: $('#live-run').checked, filed: $('#filed').value };
  const r = await fetch('/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const answer = await r.json();
  if (!r.ok) { say(answer.error, 'bad'); return; }
  graph(); $('#timeline').innerHTML = ''; $('#log').textContent = '';
  $('#command').textContent = 'python ' + answer.command;
  $('#report').innerHTML = '<p class="empty">The verified report appears here when the run ends.</p>';
  listen();
});

$('#stop').addEventListener('click', async () => {
  await fetch('/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
});

$('#saved').addEventListener('change', (e) => { if (e.target.value) showReport(e.target.value); });

function showReview(result) {
  const box = $('#review-results'); box.replaceChildren();
  for (const [status, title] of [['confirmed', 'Confirmed errors'], ['unconfirmed', 'Unconfirmed errors']]) {
    const heading = document.createElement('h3'); heading.textContent = title; box.append(heading);
    const findings = result.findings.filter((f) => f.status === status);
    if (!findings.length) { const p = document.createElement('p'); p.textContent = 'None observed in completed checks.'; box.append(p); }
    for (const f of findings) {
      const article = document.createElement('article');
      const h = document.createElement('h4'); h.textContent = f.id + ': ' + f.type; article.append(h);
      for (const [label, value] of [['Where in the process', f.stage], ['Description', f.description],
          ['Observed', f.observed], ['Expected', f.expected], ['Why it happened', f.cause],
          ['Effect', f.effect], ['Uncertainty', f.uncertainty], ['Previous pattern', f.prior_pattern]]) {
        const p = document.createElement('p'); p.textContent = label + ': ' + value; article.append(p);
      }
      for (const ref of f.evidence) {
        const p = document.createElement('pre'); p.className = 'log';
        p.textContent = ref.path + ':' + ref.line + '\\n' + ref.quote; article.append(p);
      }
      box.append(article);
    }
  }
  const heading = document.createElement('h3'); heading.textContent = 'Review limits'; box.append(heading);
  const ul = document.createElement('ul');
  result.limits.forEach((text) => { const li = document.createElement('li'); li.textContent = text; ul.append(li); });
  box.append(ul);
  ['This is a learning exercise, not financial advice.',
   'AI assistance: OpenAI Codex and ' + result.metadata.model + '. I verified the sources myself; the judgments are mine.',
   'Any remaining errors are my own.'].forEach((text) => { const p = document.createElement('p'); p.textContent = text; box.append(p); });
}

async function pollReview() {
  try {
    const r = await fetch('/review/status'); const state = await r.json();
    if (!state.done) { setTimeout(pollReview, 1000); return; }
    $('#review-start').disabled = false;
    $('#review-message').textContent = state.error || 'Review complete. Reports are in the run folder. Original research files were preserved.';
    if (state.result) { showReview(state.result); $('#review-downloads').hidden = false; }
  } catch (error) { $('#review-message').textContent = 'Cannot read review status.'; $('#review-start').disabled = false; }
}

$('#review-form').addEventListener('submit', async (e) => {
  e.preventDefault(); $('#review-downloads').hidden = true; $('#review-results').replaceChildren();
  $('#review-start').disabled = true;
  try {
    const r = await fetch('/review', { method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({folder: $('#review-folder').value, record_number: $('#review-number').value, model: $('#review-model').checked}) });
    const response = await r.json();
    if (!r.ok) { $('#review-message').textContent = response.error; $('#review-start').disabled = false; return; }
    $('#review-message').textContent = 'Review in progress. Original research files will remain unchanged.';
    pollReview();
  } catch (error) { $('#review-message').textContent = 'Cannot start the review.'; $('#review-start').disabled = false; }
});

(async () => {
  graph(); saved(); setup();
  const s = await (await fetch('/status')).json();
  if (s.running) { $('#command').textContent = 'python ' + s.command; listen(); }
})();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local group pipeline and read the final report")
    parser.add_argument("--port", type=int, default=PORT, help=f"The port to listen on (default {PORT}; the next free one if it is taken)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Page)
            break
        except OSError:
            continue
    if server is None:
        print(f"No free port from {args.port} to {args.port + 9}. Give one with --port.", file=sys.stderr)
        return 1
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"The agent team's page is at {url}\nKeep this window open while you use it. To stop the page, press Ctrl+C or close the window.")
    if not args.no_browser:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if RUN and not RUN.done:
            RUN.process.terminate()
        server.server_close()
    return 0


if __name__ == "__main__":
    import utf8_mode
    utf8_mode.ensure()
    raise SystemExit(main())
