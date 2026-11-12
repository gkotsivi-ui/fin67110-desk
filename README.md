# FIN 67110 research desk

An AI research desk for one client: an investor who seeks absolute return. You give it the ticker of a
U.S. company that files with SEC EDGAR. It finds the company's latest 10-K, latest 10-Q and latest
earnings release (the 8-K's Exhibit 99.1), reads the statements as XBRL data, computes eleven core
claims in code, and has four roles write a five-part report. A Verifier then marks every sourced number
against the saved filings. Nothing in the code names a company: the ticker is an argument.

Team: to be added. The thing we own: not decided yet. The joins: not built yet.

## What works today, and what does not

Checked on 2026-11-11.

| Part | State |
|---|---|
| The seven data steps, from SEC EDGAR, with no model | ran on six companies; see the known limits |
| The agent team: three analyst roles, a Strategy Manager in code, a Verifier on every run | ran end to end from a terminal on one company |
| The page: run the desk and read the report without a terminal | loads, and its tests pass; a full run from the page was not repeated on this date |
| The closes reader, for one price | built; tested on made-up files only on this date |
| The live record table | built and tested on a made-up repository; no live report yet |
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

**From the page, without a terminal.** On Windows, double-click `start_page.bat`. On a Mac,
double-click `start_page.command` (the first time, right-click it and choose Open). The page opens in
your browser at http://127.0.0.1:8765. Type a ticker and press Run. Each part's name appears as it
runs. When the run ends, the verified report shows on the page.

**From a terminal.** Give the ticker. `CSCO` is an example; use any ticker.

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
