"""Check the setup before a run: Python, the packages, .env and each setting, then SEC EDGAR and the model key.

Run it from the repository folder: python check_env.py
Add --offline to skip the two network checks. It never prints a full key.
"""

from __future__ import annotations

import importlib.metadata
import os
import sys

OFFLINE = "--offline" in sys.argv[1:]
PYTHON = "python" if os.name == "nt" else "python3"
fixes: list[str] = []


def report(ok: bool | None, text: str) -> None:
    """ok, FIX or note, then what was found. A FIX line also says what to do."""
    if ok is False:
        fixes.append(text)
    print(f"{'ok  ' if ok else 'note' if ok is None else 'FIX '}  {text}")


new_enough = sys.version_info >= (3, 11)
report(new_enough, f"Python {sys.version.split()[0]} ({sys.executable})" + ("" if new_enough else ": the desk needs Python 3.11 or newer"))
installed, missing = [], []
for package in ("requests", "anthropic", "langgraph", "markdown"):
    try:
        installed.append(f"{package} {importlib.metadata.version(package)}")
    except importlib.metadata.PackageNotFoundError:
        missing.append(package)
if missing:
    report(False, f"Not installed for this Python: {', '.join(missing)}. Run: {PYTHON} -m pip install -r requirements.txt")
else:
    report(True, ", ".join(installed))
if "requests" in missing:
    raise SystemExit(1)

import requests  # noqa: E402

from lab02_desk import (  # noqa: E402
    api_key_problem,
    env_path,
    is_placeholder,
    load_dotenv,
    no_env_message,
    provider_of,
    user_agent_problem,
)

where = env_path()
values = load_dotenv()


def setting(name: str) -> str:
    value = os.environ.get(name) or values.get(name) or ""
    return "" if is_placeholder(value) else value


report(where is not None, f".env: {where}" if where else no_env_message())
agent = setting("SEC_USER_AGENT")
key = setting("API_KEY") or setting("ANTHROPIC_API_KEY")
agent_ok = False
model = ""
if where is not None or agent:
    problem = user_agent_problem(agent, where)
    agent_ok = problem is None
    report(agent_ok, problem or f"SEC_USER_AGENT: {agent}")
if where is not None or key:
    problem = api_key_problem(key, where)
    if problem:
        report(False, problem)
    else:
        provider = provider_of(key)
        if "anthropic" not in missing:
            from lab03_app import DEFAULT_MODEL, GEMINI_API, model_for

            model = model_for(provider, setting("MODEL") or DEFAULT_MODEL)
        kind = "an Anthropic key" if provider == "anthropic" else "a Google AI Studio key"
        report(True, f"API_KEY: {kind} ({key[:4]}..., {len(key)} characters)" + (f"; the roles will run on {model}" if model else ""))
lseg_key, closes_file = setting("LSEG_APP_KEY"), setting("CLOSES_FILE")
if lseg_key:
    try:
        lseg_version = importlib.metadata.version("lseg-data")
        report(True, f"LSEG_APP_KEY: set, and lseg-data {lseg_version} is installed. Start the Workspace desktop app before a run.")
    except importlib.metadata.PackageNotFoundError:
        report(False, f"LSEG_APP_KEY is set, but lseg-data is not installed. Run: {PYTHON} -m pip install lseg-data")
if closes_file:
    # Only whether the file is there: the export's contents stay out of every tool but your own code.
    found = os.path.exists(os.path.expanduser(closes_file))
    report(found, "CLOSES_FILE: the file is there" if found else f"CLOSES_FILE names {closes_file}, which does not exist.")
prices = setting("FINANCIAL_DATASETS_API_KEY")
if not (lseg_key or closes_file or prices):
    report(None, "No source of closes (LSEG_APP_KEY, CLOSES_FILE or FINANCIAL_DATASETS_API_KEY). That is fine: give --price on each run.")
else:
    report(True if prices else None, "FINANCIAL_DATASETS_API_KEY: set" if prices else "FINANCIAL_DATASETS_API_KEY: not set")

if not OFFLINE and agent_ok:
    try:
        # The file step 1 reads; only the answer's status is read here, not the file.
        with requests.get("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": agent}, timeout=20, stream=True) as r:
            report(r.status_code == 200, "SEC EDGAR answers requests with this SEC_USER_AGENT" if r.status_code == 200
                   else f"SEC EDGAR refused the request ({r.status_code}). Check SEC_USER_AGENT and the network.")
    except requests.RequestException as exc:
        report(False, f"Could not reach SEC EDGAR ({exc.__class__.__name__}). Check the network.")
if not OFFLINE and model:
    # Free calls that read one model's details: they show that the key works and the model exists.
    google = provider_of(key) == "google"
    url = f"{GEMINI_API}/models/{model}" if google else f"https://api.anthropic.com/v1/models/{model}"
    headers = {"x-goog-api-key": key} if google else {"x-api-key": key, "anthropic-version": "2023-06-01"}
    vendor, console = ("Google", "aistudio.google.com") if google else ("Anthropic", "platform.claude.com")
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 200:
            report(True, f"{vendor} accepts API_KEY, and {model} is available")
        elif r.status_code == 404:
            report(False, f"{vendor} accepts API_KEY, but has no model {model}. Set MODEL in .env to a current model ID.")
        else:
            report(False, f"{vendor} refused API_KEY ({r.status_code}). Paste a valid key from {console} into .env.")
    except requests.RequestException as exc:
        report(False, f"Could not reach {vendor} ({exc.__class__.__name__}). Check the network.")

print()
if fixes:
    print(f"{len(fixes)} thing(s) to fix. Each FIX line above says what to do.")
    raise SystemExit(1)
print("All set. Next: the first command in the README's Run section.")
