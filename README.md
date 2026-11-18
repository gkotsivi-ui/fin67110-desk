# FIN 67110 research desk

## Intelligent error review

The extra application is `desk-error-review`: a saved-run reviewer that connects prior error patterns
with current evidence. It creates a human report and one AI prompt, each grouped into **Confirmed
errors** and **Unconfirmed errors**. It does not repair the desk, rerun it, or edit saved live records.
It uses code for calculations and the desk's configured model for semantic review. Model confidence
alone never confirms an error. A missing optional component is a review limit, not an automatic failure.

Review a saved run with the configured provider:

```bash
.venv/bin/python desk_error_review.py runs/live/CSCO_20261113_093231 --history docs/live-record-errors --model
```

Use `--offline` instead of `--model` for code checks without network access. This leaves model checks
of conclusions and repeated patterns incomplete. For a coding-agent review without a separate API call,
use `--proposals FILE --model-name ACTUAL_MODEL_NAME`; the proposal contract is in
`skills/desk-error-review/references/proposals.md`. The review key and model settings are the desk's
existing settings in `.env`; `--model` can incur provider charges. Unknown artifacts, raw exports, and
secrets are excluded. Long model inputs are clipped with explicit review limits. No SEC requests are made.

Use `--record-number N` for a new record without an existing error report. Existing records keep their
number. For practice, use a folder under `runs/practice` or `output` and add `--practice`.
Save nothing inside the selected run. Reports live in `docs/live-record-errors` and
`docs/ai-error-prompts`; shared evidence and findings live in `docs/error-review-findings`.
The command saves a new numbered revision when a report already exists. It checks that original file
hashes did not change during the review. Review a completed, stable snapshot of an active run later.

The Cisco review used this coding-agent session with saved evidence and no provider call. It found
one confirmed error (an empty saved partner-check field) and two unconfirmed errors (a valuation
assertion and the earlier runtime failure without its raw traceback). It does not establish that the
investment recommendation is wrong. The existing original error report and saved Cisco run were preserved.

Run the checks and the labelled synthetic evaluation:

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python live_record.py --offline --no-save
.venv/bin/python error_review_evaluation.py
```

The evaluation prints detected errors, false alarms, missed errors, and citation validity. Confirmed
and unconfirmed findings are counted separately. Its temporary practice runs never enter `runs/live`.
Results are saved to `docs/error-review-evaluation.json`. These results measure synthetic rules, not
live accuracy or model semantic accuracy. Full ASD-STE100 vocabulary compliance is not certified.

Start `.venv/bin/python page.py`, then use **Review a saved run**. Enter the run folder and its record
number if necessary. Enable the model option to review patterns and conclusions. The page shows both
error groups and their cited evidence, with separate downloads for the human report and AI prompt.
It waits for an active desk job and has no repair execution action.

The skill source is versioned in `skills/desk-error-review`. This computer's discoverable copy is
installed at `~/.codex/skills/desk-error-review`. Invoke it as `$desk-error-review`.

## Hit-rate table

Run `.venv/bin/python hit_rate.py runs/live` on Mac (Windows:
`.venv\Scripts\python hit_rate.py runs/live`). Replace `runs/live` with a practice folder to score
practice runs separately. Each immediate subfolder is one run, including incomplete runs. The command
prints one row per run and a final agreement count. Errors are reported on stderr, leave an error row,
and produce exit status 1; other runs are still read.

The reaction is the percentage change from the last official close at or before the filing's acceptance
time to the first official close strictly after it. The XNYS calendar supplies US equity holidays and
early closes. Prices come from the existing closes reader: LSEG Workspace or `CLOSES_FILE` in `.env`.
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
This is an input contract, not an implemented worksheet integration. Do not backdate or reconstruct a
missing view from a recommendation or run start time. Existing reports without a saved view display
`not computed`. When `filing_time` is absent, the command reads the earnings 8-K acceptance time from
the saved report's first line; ticker can also come from `facts.json`.

The command creates only a new `reaction.json` in each run once the reaction becomes available,
recording both closes, session times, filing time, ticker, price source, and retrieval time. It never
overwrites an existing reaction, view, report, or timestamp. `--offline` reads saved reactions and
writes nothing. The saved price pair is recomputed in code for the table on every invocation.

Agreement means the view's direction matches the sign of the reaction (zero means `flat`). The
`after` flag means the view's timestamp is strictly later than the first post-filing close. The final
line counts agreements over runs with a reaction, excluding `after` rows and views `not computed`.
Missing or invalid evidence is excluded and never counted as a correct prediction.

An AI research desk for one client: an investor who seeks absolute return. You give it the ticker of a
U.S. company that files with SEC EDGAR. It finds the company's latest 10-K, latest 10-Q and latest
earnings release (the 8-K's Exhibit 99.1), reads the statements as XBRL data, computes eleven core
claims in code, and has four roles write a five-part report. A Verifier then marks every sourced number
against the saved filings. Nothing in the code names a company: the ticker is an argument.

Team: to be added. The thing we own: the intelligent error review application. The joins: not built yet.

## What works today, and what does not

Checked on 2026-11-11 and 2026-11-12.

| Part | State |
|---|---|
| The seven data steps, from SEC EDGAR, with no model | ran on six companies; see the known limits |
| The agent team: three analyst roles, a Strategy Manager in code, a Verifier on every run | ran end to end on one company, on 2026-11-11 and again on 2026-11-12 |
| The page: run the desk and read the report without a terminal | ran one company end to end from the page on 2026-11-12, and showed the verified report |
| The closes reader, for one price | built; tested on made-up files. On 2026-11-12 LSEG Workspace was not running, and the price came from financialdatasets.ai |
| The live record table | built and tested on a made-up repository; no live report yet |
| The hit-rate table | built; tested on synthetic runs; existing live report has no timestamped directional view |
| The intelligent error review | built; code and HTTP tests; one saved-run review; synthetic evaluation only |
| The spinoff seeker, the worksheet with its view, the hook, and one command for all of them | not built yet |

Known limits are listed under [What can go wrong](#what-can-go-wrong). Read them before you trust a number.

## What you need

- A computer with Python 3.11 or newer, and git.
- Your name and your email. SEC EDGAR asks every program for them. You need no account.
- One model key: an Anthropic key (it starts with `sk-ant-`) or a Google AI Studio key (it starts with
  `AIza`). An OpenAI key does not work yet.
- About five minutes for each run, and a small charge on your model key. One run on a large company
  took 290 seconds and used about 102,000 input tokens and 38,000 output tokens (claude-opus-5-5,
  2026-11-11).
- Optional: a source of closing prices. Without one, the report has no P/E. Read
  [Prices and licensed data](#prices-and-licensed-data) first.

## Set up, one time

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

**From Lab 05.** Keep `Analyst` next to this repository in the course workspace. Install
`../Analyst/requirements.txt` and this repository's `markdown` dependency in the Python
environment that starts the page. Configure the joined desk in `../Analyst/.env`. Start
`python page.py` in that environment, or use the double-click launcher if you set up
this repository's `.venv` with both sets of page and desk dependencies.

Open http://127.0.0.1:8765. Enter a ticker or `screen`. A seeker start date refreshes
the screen before ticker selection. A blank date uses the latest saved screen for
`screen`. The page shows each part and displays the final report after it passes the
hook. The joined desk uses the sourced pre-filing close for the team's valuation.
Joined page runs are saved in `../Analyst/runs/practice`.

From `../Analyst`, run the same command in the terminal:

```bash
python desk.py TICKER
python desk.py screen
python desk.py --replay 'runs/practice/SAVED_RUN_FOLDER'
```

Replace `TICKER` and `SAVED_RUN_FOLDER` with your inputs.
See [joined desk options](../Analyst/docs/desk-command.md) for screen refreshes and live runs.

**Run the original team alone.** Give the ticker. `CSCO` is an example; use any ticker.

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

Run `check_env.py` first. It checks Python, the packages, `.env`, SEC EDGAR and the model key.

| What you see | What to do |
|---|---|
| `There is no .env file` | Do step 3 of the setup, and run the commands from the repository folder. If Windows saved the file as `.env.txt`, rename it to `.env`. |
| `API_KEY ... is an OpenAI key` | The roles run on Anthropic or Google. Use a key that starts with `sk-ant-` or `AIza`. |
| `Could not install packages due to an OSError`, with a hint about Windows Long Path support | The folder's path is too long for Windows. Move the folder to a short path, for example `C:\fin67110-desk`, and do step 2 of the setup again. |
| `ModuleNotFoundError` | The command did not use the virtual environment. Start the command with `.venv\Scripts\python` (Windows) or `.venv/bin/python` (Mac). |
| `python` is not found, or the Microsoft Store opens | On Windows, type `py`. On a Mac, type `python3`. |
| `SEC request failed: 403` | `SEC_USER_AGENT` needs your own name and email. |
| `credit balance is too low` | Add credit to the Anthropic account, or use a Google AI Studio key. |
| `The Gemini API is limiting this key` | Wait a minute and run again. |
| `Could not locate an Exhibit 99 with the earnings release` | The 8-K has no Exhibit 99 that the desk can read. Choose another company. |

Known limits, as of 2026-11-11. The details are in [docs/decision-log.md](docs/decision-log.md).

1. The quarter's revenue, growth and diluted EPS (claims 9 to 11) are read from the release's income
   statement by rules. When the rules cannot read a claim, the report says "not found" or "not computed",
   with the reason. The figures are not yet checked against XBRL, so check them against the release.
2. Debt to equity says "not computed" when the 10-K does not tag both parts of its long-term debt in
   the way the desk reads. That is a missing claim, not an error.
3. When SEC EDGAR's company facts are not yet the facts of the 10-K the desk read, the report states no
   annual figure and says why. The quarter's claims and the rest of the report are still written.
4. The desk needs all three filings. A company with no 10-K yet, or one that files 20-F and 6-K, stops the run.

## Tests

The tests need no network and no key.

Windows:

```
.venv\Scripts\python -m unittest discover -s tests
```

Mac:

```
.venv/bin/python -m unittest discover -s tests
```

They cover the XBRL tag choice, the full-year filter, the release's table text, the quote and number
checks, the calculator, the fixed order of the parts, the single send-back, and the Verifier's marks on
a seeded EPS, an invented growth rate, a price and an unsourced number. They also cover the setup, the
page, the closes reader on made-up files, and the live record on a made-up repository.

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

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
