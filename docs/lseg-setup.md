# LSEG setup for the group

Each member creates environments on their own computer. Do not copy a virtual environment between
computers. Share these setup files, not `.env`, credentials, environments, or market-data exports.
These instructions apply to the independent `fin67110-desk` repository.

The research desk uses Python 3.13 in `.venv-desk`. The LSEG worker uses Python 3.13 in `.venv-lseg`.
`requirements-lseg.txt` pins the SDK and the dependencies installed and checked on the Mac.
On 2026-11-21 the Windows steps below also ran on one member's Windows 11 computer: the install,
`pip check`, both checks with Refinitiv Workspace signed in, and one close from the closes reader.
Each member still runs the checks on their own computer.

## Windows members: PowerShell

Receive the updated repository files first. Open PowerShell in the repository root. Install Python 3.13
if `py -3.13 --version` fails. Use a short clone path such as `C:\fin67110-desk`.

First-time setup (keep an existing working `.venv-desk`):

```powershell
py -3.13 -m venv .venv-desk
.\.venv-desk\Scripts\python.exe -m pip install -r requirements-pipeline.txt -c constraints-pipeline.txt
py -3.13 -m venv .venv-lseg
.\.venv-lseg\Scripts\python.exe -m pip install -r requirements-lseg.txt
.\.venv-lseg\Scripts\python.exe -m pip check
```

Create `.env` only if you do not already have one:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set your own `SEC_USER_AGENT`, `API_KEY`, `MODEL`, and `LSEG_APP_KEY` locally. Use the explicit supported
Anthropic model/provider configuration described in the README. Do not send keys in chat or commit them.
Leave `LSEG_PYTHON` absent or commented out to use automatic platform selection. Remove a copied Mac path.
An intentional custom override must name an existing Python with the pinned LSEG dependencies.

Run the offline checks:

```powershell
.\.venv-desk\Scripts\python.exe -X utf8 check_pipeline.py
.\.venv-desk\Scripts\python.exe -X utf8 check_lseg.py
```

Start the LSEG Workspace desktop application and sign in. Then check the desktop connection:

```powershell
.\.venv-desk\Scripts\python.exe -X utf8 check_lseg.py --session
```

Expect `ok` with `Desktop session opened and closed; no prices requested.` before a price-enabled run.
Then run the desk (replace `TICKER` with the requested symbol):

```powershell
.\.venv-desk\Scripts\python.exe -X utf8 desk.py TICKER
```

This saves a practice run. Add `--live` only for an intended live record. The page launcher also uses
`.venv-desk`. Each member must run their own Workspace session and use their own credentials.

## Mac setup

The Mac used for the November 21 setup already has both environments installed. For a new Mac:

```bash
python3.13 -m venv .venv-desk
.venv-desk/bin/python -m pip install -r requirements-pipeline.txt -c constraints-pipeline.txt
python3.13 -m venv .venv-lseg
.venv-lseg/bin/python -m pip install -r requirements-lseg.txt
.venv-lseg/bin/python -m pip check
```

Create your local `.env` from `.env.example` if missing. Configure the same four keys listed above.
Leave `LSEG_PYTHON` absent unless you intentionally need a custom interpreter.

```bash
.venv-desk/bin/python check_pipeline.py
.venv-desk/bin/python check_lseg.py
# Open Workspace and sign in before this check:
.venv-desk/bin/python check_lseg.py --session
.venv-desk/bin/python desk.py TICKER
```

## What selection and checks do

The reader selects `.venv-lseg/bin/python` on macOS/Linux and `.venv-lseg\Scripts\python.exe` on Windows.
`LSEG_PYTHON` overrides either default. Relative overrides resolve from the repository root.
The legacy closes reader used by `hit_rate.py` delegates its existing query to this worker when the
calling Python lacks the SDK. CSV handling and cached reactions retain their existing behavior.

`check_lseg.py` checks the executable, SDK version, and timezone import without a network session.
`check_lseg.py --session` opens and closes a desktop session with a 45-second process deadline.
It requests no prices, prints no credentials or raw SDK errors, and changes no run files.
A session success does not prove that every instrument or price field is licensed or available.
`check_pipeline.py` includes the offline LSEG check as optional: research without prices remains allowed.
Use the standalone LSEG check's nonzero exit status to require readiness before a price-enabled run.

If imports fail, reinstall `requirements-lseg.txt` using the selected environment's Python. If the
session fails, check Workspace sign-in, the local App Key, and account access. Do not bypass a desk stop
or rewrite an old view after installing the environment. Use a new practice run for validation.

References: [LSEG desktop-session quick start](https://developers.lseg.com/en/api-catalog/lseg-data-platform/lseg-data-library-for-python/quick-start),
[LSEG package metadata](https://pypi.org/project/lseg-data/2.1.1/).

This is a learning exercise, not financial advice.

AI assistance: OpenAI Codex and Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
