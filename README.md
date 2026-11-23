# FIN 67110 research desk

An AI research desk for one client: an investor who seeks absolute return. You give it the ticker of a
U.S. company that files with SEC EDGAR. It finds the company's latest 10-K, latest 10-Q and latest
earnings release (the 8-K's Exhibit 99.1), reads the statements as XBRL data, computes eleven core
claims in code, and has four roles write a five-part report. A Verifier then marks every sourced number
against the saved filings, and the worksheet gives the client's view. Nothing in the code names a
company: the ticker is an argument.

Team: gkotsivi-ui, jcleeper65 and lee4276 (the team's name is to be added). The thing we own: the
intelligent error review application. How the parts are joined: [docs/group-pipeline.md](docs/group-pipeline.md).

## Run the desk: the quick start

The desk is one command, `desk.py`. Give it the ticker of any U.S. company that files with SEC EDGAR. It
runs the pick, the agent team with its Verifier, the worksheet and the final report, in an order that
code fixes, with the hook checking every number each part saves. A company the spinoff seeker never saw
runs too: its spinoff parts say "not applicable".

**What you need.** Python 3.13 (CrewAI 1.15 needs 3.10 to 3.13), git, your name and email for SEC EDGAR
(no account), and one model key with a model of the same provider that your account can use. Anthropic has
been run end to end; Google AI Studio and OpenAI keys go through the same CrewAI calls but have not been run end
to end yet. A run costs a few dollars of model use. Practice runs on 2026-11-19 and 2026-11-20 took from about
10 to 35 minutes, the longer ones when a role needed its repairs.
Prices are optional: without one, the report has no P/E and the worksheet's view says "not computed".

1. **Get the code.** On Windows keep the folder's full path short, under about 100 characters.

   ```
   git clone https://github.com/gkotsivi-ui/fin67110-desk.git
   cd fin67110-desk
   ```

2. **Make the environment and install the tested versions.**

   Windows:

   ```
   py -3.13 -m venv .venv-desk
   .venv-desk\Scripts\python -m pip install -r requirements-pipeline.txt -c constraints-pipeline.txt
   ```

   Mac:

   ```
   python3.13 -m venv .venv-desk
   .venv-desk/bin/python -m pip install -r requirements-pipeline.txt -c constraints-pipeline.txt
   ```

3. **Make `.env`.** Copy `.env.example` to `.env` and fill in three lines. The key and the model must be of
   the same provider: `anthropic/`, `gemini/` or `openai/`, then a model ID your account can use.

   ```
   SEC_USER_AGENT=Your Name your.email@university.edu
   API_KEY=your model key
   MODEL=anthropic/claude-opus-5-5
   ```

   Then check the setup. No line may say `FIX`; a `note` line is information (on a Mac, type `.venv-desk/bin/python`):

   ```
   .venv-desk\Scripts\python check_pipeline.py
   ```

4. **Run it on a ticker.** `LOW` is an example; use any ticker. On a Mac, type `.venv-desk/bin/python`.

   ```
   .venv-desk\Scripts\python desk.py LOW
   ```

   Each part prints its name and its seconds. The last lines give the run folder, under `runs/practice/`.
   Read `final_report.md` there: the agent team's verified report, with the Verifier's marks under its
   first line, and the worksheet's view under the report.

   **Without a terminal:** double-click `start_page.bat` (Windows) or `start_page.command` (Mac), open
   http://127.0.0.1:8765, type a ticker and press Run.

**When something stops.** A part that fails stops the command, prints which part and the error, and keeps
the run folder. A claim the Verifier does not mark correct does not stop it: that line is left out of the
published report, the marks table still lists it, and a line under the table names it. A claim that still
fails the code's check after two repairs is left out the same way, and the run prints which. A model call
whose connection drops, or that the provider answers with a server error, is made once more after thirty
seconds, and one the provider limits (429) once more after sixty. SEC EDGAR is asked for a page up to three
times. A role that has not answered in twenty minutes stops the run and is not called again. A setting that
is empty or still the example, or a key and a model of two providers, stops the run at its first step,
before anything is fetched; whether the key is valid and has credit is found only by the first model call.

A run that stops in its worksheet or its final report, after the team's report is finished and checked, can
be finished without running the team again:

```
.venv-desk\Scripts\python desk.py --resume runs\practice\<the run folder>
```

The command prints this line when it applies. A run that stops earlier is run again from the start.
Ctrl+C stops a run and records the part it was in.

**The spinoff screen (optional, slow).** `desk.py screen --refresh-screen YYYY-MM-DD` runs the seeker
first and takes the top name of its screen. By default it reads EDGAR's quarterly indexes from 1994 on,
about 130 large files, so bound it: `--index-start 2025-10-01 --max-candidates 10` read five quarters and
ten candidates in about six minutes on 2026-11-19. A bounded screen says that its coverage is partial.

**Prices from LSEG (optional).** Follow [the Mac and Windows setup instructions](docs/lseg-setup.md).
Install `requirements-lseg.txt` in a local `.venv-lseg`; the reader selects its platform-specific Python.
Set your own `LSEG_APP_KEY` in `.env`, start Workspace, and sign in. Run `check_lseg.py` for the offline
import check and `check_lseg.py --session` for the desktop connection check. `LSEG_PYTHON` is only needed
for an intentional custom interpreter. An export file outside this folder can use `LSEG_CLOSES_FILE`.
Missing prices or valuation inputs produce a `not computed` view.

**A live run** for the live record adds `--live`; it is saved under `runs/live/`. Read
[runs/live/README.md](runs/live/README.md) first. Before the push, `python check_public.py` reads what git
tracks or would add and fails on a key, a value of `.env`, a data file, a list of closes or a home-folder
path. More: [docs/group-pipeline.md](docs/group-pipeline.md).

## Intelligent error review

The extra application is `desk-error-review`: a saved-run reviewer that connects prior error patterns
with current evidence. It creates a human report and one AI prompt, each grouped into **Confirmed
errors** and **Unconfirmed errors**. It appends review reports without editing original research artifacts or repairing the desk.
It uses code for calculations and the desk's configured model for semantic review. Model confidence
alone never confirms an error. A missing optional component is a review limit, not an automatic failure.

Review a saved run with the configured provider:

```bash
.venv-desk/bin/python desk_error_review.py runs/live/CSCO_20261113_093231 --history runs/live --model
```

Use `--offline` instead of `--model` for code checks without network access. This leaves model checks
of conclusions and repeated patterns incomplete. For a coding-agent review without a separate API call,
use `--proposals FILE --model-name ACTUAL_MODEL_NAME`; the proposal contract is in
`skills/desk-error-review/references/proposals.md`. The review key and model settings are the desk's
existing settings in `.env`; `--model` can incur provider charges, and it runs on an Anthropic or a Google
model only (with an OpenAI key or model it stops and says so). Unknown artifacts, raw exports, and
secrets are excluded. Long model inputs are clipped with explicit review limits. No SEC requests are made.

Use `--record-number N` for a new record without an existing error report. Existing records keep their
number. For practice, use a folder under `runs/practice` or `output` and add `--practice`.
Both reports are saved directly inside the selected run folder, beside `report.md` and the saved filings:
`Error Documentation [Company name, live record number].md` and
`AI Error Prompt [Company name, live record number].md`. Shared findings remain in
`docs/error-review-findings`. The command saves a new numbered revision when a report already exists.
Original research artifacts are checked for changes; appended review reports are excluded from that
research-artifact hash check. History defaults to `runs/live` and discovers human reports recursively.
Past reports were moved without content changes; `docs/error-review-report-migration.json` records their locations and hashes.
Review a completed, stable snapshot of an active run later.

The Cisco review used this coding-agent session with saved evidence and no provider call. It found
one confirmed error (an empty saved partner-check field) and two unconfirmed errors (a valuation
assertion and the earlier runtime failure without its raw traceback). It does not establish that the
investment recommendation is wrong. The existing original error report and saved Cisco run were preserved.

Run the checks and the labelled synthetic evaluation:

```bash
.venv-desk/bin/python -m unittest discover -s tests
.venv-desk/bin/python live_record.py --offline --no-save
.venv-desk/bin/python error_review_evaluation.py
```

The evaluation prints detected errors, false alarms, missed errors, and citation validity. Confirmed
and unconfirmed findings are counted separately. Its temporary practice runs never enter `runs/live`.
Results are saved to `docs/error-review-evaluation.json`. These results measure synthetic rules, not
live accuracy or model semantic accuracy. Full ASD-STE100 vocabulary compliance is not certified.

Start `.venv-desk/bin/python page.py`, then use **Review a saved run**. Enter the run folder and its record
number if necessary. Enable the model option to review patterns and conclusions. The page shows both
error groups and their cited evidence, with separate downloads for the human report and AI prompt.
It waits for an active desk job and has no repair execution action.

The skill source is versioned in `skills/desk-error-review`. This computer's discoverable copy is
installed at `~/.codex/skills/desk-error-review`. Invoke it as `$desk-error-review`.

## Hit-rate table

Run `.venv-desk/bin/python hit_rate.py runs/live` on Mac (Windows:
`.venv-desk\Scripts\python hit_rate.py runs/live`). Replace `runs/live` with a practice folder to score
practice runs separately. Each immediate subfolder is one run, including incomplete runs. The command
prints one row per run and a final agreement count. Errors are reported on stderr, leave an error row,
and produce exit status 1; other runs are still read.

The reaction is the percentage change from the last official close at or before the filing's acceptance
time to the first official close strictly after it. The XNYS calendar supplies US equity holidays and
early closes. Prices come from the legacy closes reader (`closes.py`): LSEG Workspace, or a file named by `CLOSES_FILE`
in `.env` or, when that is absent, by `LSEG_CLOSES_FILE`, the group desk's name for the same file. A RIC
for this table is given as `LSEG_RICS`, not as the desk's `LSEG_RIC_MAP`.
Keep exports outside the repo and do not use WRDS exports with this command. Both exact session prices
must be available; another day's price is never substituted. A reaction is unavailable until the
post-filing session has closed and its prices are available from the source.

A completed worksheet should save `view.json` in its run folder when the view is actually produced:

```json
{
  "ticker": "EXAMPLE",
  "filing_time": "2026-11-25T17:00:00-05:00",
  "time": "2026-11-27T12:00:00-05:00",
  "direction": "up"
}
```

Directions are `up`, `down`, `flat`, or `not computed`; timestamps must include a UTC offset.
Future worksheets write canonical `up`, `down`, `flat`, or `not computed`, a code-generated `time`,
the compatible `view_time` alias, and an explicit `reaction_window`. Reports repeat the stored values.
The reader still accepts older saved schemas without modifying them. Do not backdate or reconstruct a
missing view from a recommendation or run start time. Existing reports without a saved view display
`not computed`. When `filing_time` is absent, the command reads the earnings 8-K acceptance time from
the saved report's first line; ticker can also come from `facts.json`.

Use `--run RUN_FOLDER_NAME` to show only one run inside the folder you named.
The command creates only a new `reaction.json` in each run once the reaction becomes available,
recording both closes, session times, filing time, ticker, price source, retrieval time, and the saved view hash. It never
overwrites an existing reaction, view, report, or timestamp. `--offline` reads saved reactions and
writes nothing. The saved price pair is recomputed in code for the table on every invocation.

Agreement means the view's direction matches the sign of the reaction (zero means `flat`). The
`after` flag means the view's timestamp is strictly later than the first post-filing close. The final
line counts agreements over runs with a reaction, excluding `after` rows and views `not computed`.
Missing or invalid evidence is excluded and never counted as a correct prediction.

## What works today, and what does not

Checked on 2026-11-19 to 2026-11-21, on Windows 11.

| Part | State |
|---|---|
| The one command, `desk.py`: the pick, the agent team with its Verifier, the worksheet, the final report, and the hook after each part | a practice run on Lowe's (LOW) reached its final report on 2026-11-20, before the audit's fixes; each stop the earlier runs found is fixed and has a test, as the decision log records. With the fixes, the data steps have run on Lowe's (2026-11-21); the roles, the Verifier and the worksheet have not run since |
| The 11 core claims | printed by code under the Overview from the saved facts; the quarter's three from the release's table. Tested; not yet seen in a whole run's report |
| The worksheet's values | reads three years of owner cash flow and the cover page's share count from the filings; Lowe's and Walmart's low and mid values pass the hook (2026-11-21) |
| The page: run the desk and read the report without a terminal | starts a run. On 2026-11-21 two runs from the page on Lowe's passed the inputs, the pick, the seven data steps and every hook check, then stopped at the first model call: the provider refused it because the model account was out of credit. A whole run from the page is still to be checked |
| The closes reader, for one price | reads LSEG Workspace, or a file of closes named by `LSEG_CLOSES_FILE`. With neither there is no price: the report has no P/E and the worksheet's view is "not computed". The worksheet's daily closes and volumes stay in `sources/licensed/` of the run folder, which is never committed; the report prints the liquidity result only |
| The live record | two reports inside their 24-hour windows, Week 4 (Cisco) and Week 5 (NVIDIA), both written by the legacy desk below |
| The hit-rate table | runs; both live reports predate the worksheet and have no view, so it scores none yet |
| The intelligent error review | built; a review of each live report is saved beside it |
| Tests | `check_all.py`: 928 tests in four folders, no failure, four symlink tests skipped (Windows 11, 2026-11-22). The macOS run is to be redone |

Known limits are listed under [What can go wrong](#what-can-go-wrong). Read them before you trust a number.

## What the legacy desk needs

The sections from here to [Read the report](#read-the-report) are the base desk that produced the Week 4
and Week 5 live reports, kept to reproduce them. To run the desk, use the [quick start](#run-the-desk-the-quick-start).

- A computer with Python 3.11 or newer, and git.
- Your name and your email. SEC EDGAR asks every program for them. You need no account.
- One model key: an Anthropic key (it starts with `sk-ant-`) or a Google AI Studio key (it starts with
  `AIza`). An OpenAI key does not work yet.
- About five minutes for each run, and a small charge on your model key. One run on a large company
  took 290 seconds and used about 102,000 input tokens and 38,000 output tokens (claude-opus-5-5,
  2026-11-11).
- Optional: a source of closing prices. Without one, the report has no P/E. Read
  [Prices and licensed data](#prices-and-licensed-data) first.

## Legacy team setup, one time

1. Get the code, and open a terminal in its folder.

   ```
   git clone https://github.com/gkotsivi-ui/fin67110-desk.git
   cd fin67110-desk
   ```

   On Windows, keep the folder's full path short: under about 100 characters. One of the packages
   has very long file names, and Windows refuses a path longer than 260 characters.

2. Make a virtual environment and install the packages. The environment keeps this desk's exact package
   versions apart from the ones your own work uses.

   Windows (if `python` is not found, type `py` in its place on the first line):

   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

   Mac:

   ```
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

3. Make `.env` and fill it in. The program asks for each value and saves it. `.env` is never committed.

   Windows:

   ```
   .venv\Scripts\python set_keys.py
   ```

   Mac:

   ```
   .venv/bin/python set_keys.py
   ```

   Or copy `.env.example` to `.env` and edit it in a text editor. Two lines are required:
   `SEC_USER_AGENT` (your name and email) and `API_KEY` (your model key).

4. Check the setup. Each line says `ok`, `note` or `FIX`, and a `FIX` line says what to do.

   Windows:

   ```
   .venv\Scripts\python check_env.py
   ```

   Mac:

   ```
   .venv/bin/python check_env.py
   ```

## Run the desk

Use the complete group command and page described at the top of this README. Both use only this repo's
`desk.py`, local skills, local hook, `.env`, and run folders. The finished report is `final_report.md`.

### Legacy team commands

These reproduce the original team-only workflow. They do not run the worksheet or final pipeline gate.
Keep their original environment separate from `.venv-desk`.

**Run from the terminal.** Give the ticker. `CSCO` is an example; use any ticker.

Windows:

```
.venv\Scripts\python team.py CSCO
```

Mac:

```
.venv/bin/python team.py CSCO
```

The names of the parts print in their fixed order: the steps, the Research Analyst, the Financial
Analyst, the Investment Advisor, the Strategy Manager, the Verifier. The last lines give the run folder
and the path of the verified report.

More options, after the ticker:

| Option | What it does |
|---|---|
| `--peers AAA,BBB` | adds peer companies to the comparison |
| `--price 123.45` | gives the close for P/E by hand |
| `--filed 2026-11-12T16:07:06` | gives the release's filing time, Eastern, when you do not want the 8-K's own |
| `--verify-only output/<run folder>` | in place of the ticker: runs the Verifier on a saved run and nothing else |

The data steps alone need no model key and cost nothing. They print every fact with its XBRL tag, its
period and its filing. On a Mac, type `.venv/bin/python` in place of `.venv\Scripts\python`:

```
.venv\Scripts\python lab02_desk.py CSCO
```

## Read the report

Each run writes one folder, `output/<TICKER>_<date>_<time>/`, and never writes over an earlier run.

| File | What it holds |
|---|---|
| `verified_report.md` | the report, with the Verifier's table of marks under its first line. Read this one. |
| `report.md` | the report before the Verifier marked it |
| `10K_*.txt`, `10Q_*.txt`, `8K_*.txt` | the three documents as plain text; the 8-K file is Exhibit 99.1 |
| `facts.json`, `ratios.json`, `peer_facts.json` | each fact with its tag, period and filing; each ratio with its arithmetic |
| `nodes/` | what each part received and returned, numbered in the order the parts ran |
| `audit.md` | a blank audit table for a person to fill in against the filings |

The report's first line names every filing the desk read, with each accession number and "Accepted"
time. The table "Core figures from the desk's steps" holds the eleven core claims of the course's
report audit. Code reads and computes them; no model writes them. The roles write the text around
them, and the Verifier marks each number in that text correct, wrong or unsupported.

## Prices and licensed data

The desk needs one market number: the last close before the release was filed. It takes it from
`--price`, or from LSEG Workspace (`LSEG_APP_KEY`), or from an exported file (`CLOSES_FILE`), or from
financialdatasets.ai (`FINANCIAL_DATASETS_API_KEY`). `.env.example` describes each setting.

For LSEG Workspace the desk needs one more package, LSEG's own library. Install it into the same
environment (on a Mac, type `.venv/bin/python` in place of `.venv\Scripts\python`):

```
.venv\Scripts\python -m pip install -r requirements-lseg.txt
```

Then start the Workspace desktop app and sign in before each run. `check_env.py` says whether the
library is there. It cannot tell whether Workspace is running. When Workspace does not answer, the desk
takes the close from financialdatasets.ai if that key is set. The report's second line always names the
source of its price, so read that line.

Today the desk sends that one close to the Financial Analyst role, which is a model call, and prints it
on the report's second line. If the terms of your price source do not allow its data in an AI tool,
leave the price settings empty. The desk then runs without a price and the report has no P/E.

Keep export files outside this folder. `.gitignore` refuses data files as a second guard.

## What can go wrong

Run the setup check first. For the group desk it is `check_pipeline.py`: Python, the packages, the desk's
files and the settings in `.env`, with no network call. For the legacy desk it is `check_env.py`, which also
checks SEC EDGAR and the model key.

| What you see | What to do |
|---|---|
| `There is no .env file` | Do step 3 of the setup, and run the commands from the repository folder. If Windows saved the file as `.env.txt`, rename it to `.env`. |
| `API_KEY ... is an OpenAI key` (the legacy desk) | The legacy desk's roles run on Anthropic or Google. Use a key that starts with `sk-ant-` or `AIza`. |
| `Could not install packages due to an OSError`, with a hint about Windows Long Path support | The folder's path is too long for Windows. Move the folder to a short path, for example `C:\fin67110-desk`, and do step 2 of the setup again. |
| `ModuleNotFoundError` | The command did not use the virtual environment. Start the command with `.venv\Scripts\python` (Windows) or `.venv/bin/python` (Mac). |
| `python` is not found, or the Microsoft Store opens | On Windows, type `py`. On a Mac, type `python3`. |
| `SEC request failed: 403`, or `SEC EDGAR refused the request (403)` | `SEC_USER_AGENT` needs your own name and email. |
| `MODEL in .env is empty`, or `API_KEY and MODEL in .env are of two providers` | The group desk stops at its first step, before it fetches anything. Write `MODEL` with its provider (`anthropic/`, `gemini/` or `openai/`) and a key of the same provider. |
| `.env is not saved as UTF-8` | Windows PowerShell wrote the file as UTF-16. Open it in a text editor and save it as UTF-8. |
| `the model did not answer in 20 minutes` | One role's call ran past its time limit. Run again. If the run had reached its worksheet, use the `--resume` line the command printed. |
| `The earnings 8-K ... has no Exhibit 99 that the desk can read` | The newest earnings 8-K has no release the desk can read. The desk does not go back to an older one. Choose another company. |
| `To finish this run without running the team again:` followed by a command | The run stopped in its worksheet or final report. Fix what the error names (credit, the key, the connection) and run the printed command from the repository folder. |
| `credit balance is too low` | Add credit to the Anthropic account, or use a Google AI Studio key. |
| `The Gemini API is limiting this key` | Wait a minute and run again. |
| `Could not locate an Exhibit 99 with the earnings release` | The 8-K has no Exhibit 99 that the desk can read. Choose another company. |

Known limits, as of 2026-11-22. The details are in [docs/decision-log.md](docs/decision-log.md).

1. The quarter's revenue, growth and diluted EPS (claims 9 to 11) are read from the release's income
   statement by rules. When the rules cannot read a claim, the report says "not found" or "not computed",
   with the reason. The figures are not yet checked against XBRL, so check them against the release.
2. Debt to equity says "not computed" when the 10-K does not tag both parts of its long-term debt in
   the way the desk reads. That is a missing claim, not an error.
3. When SEC EDGAR's company facts are not yet the facts of the 10-K the desk read, the report states no
   annual figure and says why. The quarter's claims and the rest of the report are still written.
4. The desk needs all three filings. A company with no 10-K yet, or one that files 20-F and 6-K, stops the run.
5. The group desk's price is the last close before the release, and it takes every session to close at
   16:00 Eastern. On a day the market closes at 13:00, a release accepted between 13:00 and 16:00 gets the
   close of the day before, not that day's. The next such days are 2026-11-27 and 2026-12-24. The hit-rate
   table uses the exchange's calendar and is not affected.
6. The checks on what a role may type were tightened on 2026-11-22. The replies saved from the real runs of
   2026-11-19 and 2026-11-20 pass them as before, but no new run has been made since: the model account had
   no credit. A real run on another company or model may leave out more lines than the runs before it.

## Tests

One command runs every check. It needs no network and no key (on a Mac, type `.venv-desk/bin/python`):

```
.venv-desk\Scripts\python check_all.py
```

It runs the four test folders (`tests`, `hooks/tests`, `skills/spinoff-worksheet/tests` and
`skills/us-spinoff-seeker/tests`), the two seeded checks that drive the real CrewAI roles on a stand-in model,
the offline live record, and `check_public.py`. Each prints one line; the last line gives the count. To run one
folder alone: `.venv-desk\Scripts\python -m unittest discover -s hooks/tests`.

On Windows 11 on 2026-11-22 it ran 928 tests with no failure. Four tests that create a symlink were
skipped: Windows lets an account create one only with administrator rights or Developer Mode. Python needs no
`-X utf8` for them any more: every file is read and written as UTF-8 by name.

They cover the XBRL tag choice, the full-year filter, each formula of the eleven core claims, the release's
tables (a loss, change columns, three dated columns, a non-GAAP table), the facts of the chosen 10-K, the
quote and number checks, the calculator, the fixed order of the parts, the single send-back, and the
Verifier's marks on a seeded EPS, an invented growth rate, a price and an unsourced number. They also cover
the setup, the page, the closes reader on made-up files, a model call that fails on the way, a run that stops
and is resumed, the live record on a made-up repository, and one whole run from a ticker to its final report
on made-up SEC pages (`tests/test_whole_desk.py`).

## The live record

Each week the desk runs on a company that filed its earnings release that week, and the report is
committed and pushed here within 24 hours of the filing's "Accepted" time on SEC EDGAR. Each live run
is one folder in [runs/live](runs/live). The table is [docs/live-record.md](docs/live-record.md), and
this command makes it from SEC EDGAR and the commit times (on a Mac, type `.venv/bin/python` in place
of `.venv\Scripts\python`):

```
.venv\Scripts\python live_record.py
```

## More

- [AGENTS.md](AGENTS.md): the rules every coding agent follows in this repository.
- [PLAN.md](PLAN.md): what is left to build, in order, and who owns it.
- [docs/decision-log.md](docs/decision-log.md): what AI got wrong, and how we caught it.

This is a learning exercise, not financial advice.

AI assistance: Claude Code and OpenAI Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
