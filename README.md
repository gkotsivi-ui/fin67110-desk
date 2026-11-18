# FIN 67110 research desk

An AI research desk for one client: an investor who seeks absolute return. You give it the ticker of a
U.S. company that files with SEC EDGAR. It finds the company's latest 10-K, latest 10-Q and latest
earnings release (the 8-K's Exhibit 99.1), reads the statements as XBRL data, computes eleven core
claims in code, and has four roles write a five-part report. A Verifier then marks every sourced number
against the saved filings. A worksheet then puts a value range against the price and states a view, and a
hook refuses any number that has no source. One command runs all of it. Nothing in the code names a
company: the ticker is an argument.

Team: to be added. The thing we own: not decided yet. The joins: the team writes this line (Lab 09).

## What works today, and what does not

Checked on 2026-11-11, 2026-11-12 and 2026-11-16.

| Part | State |
|---|---|
| The seven data steps, from SEC EDGAR, with no model | ran on six companies; see the known limits |
| The agent team: three analyst roles, a Strategy Manager in code, a Verifier on every run | ran end to end on one company, on 2026-11-11 and again on 2026-11-12 |
| The page: run the desk and read the report without a terminal | ran one company end to end from the page on 2026-11-12, and showed the verified report |
| The closes reader, for one price | built; tested on made-up files. On 2026-11-12 LSEG Workspace was not running, and the price came from financialdatasets.ai |
| The live record table | built and tested on a made-up repository; no live report yet |
| The one command: the agent team, the worksheet and the hook in a fixed order, through one run folder | ran end to end on one company on 2026-11-16: 292 seconds for the agent team and 9 for the worksheet. It ended "Not done": the Verifier had marked three numbers of the report unsupported, and the hook refused it for that |
| The worksheet, with its value range and its view | ran on that company with a teammate's hand-written files kept outside this repository; the hook passed it. The team's own files are not in `client/` yet, so the command stops at the worksheet until a member adds them |
| The hook | refused one amount changed by one in a copy of that run's final report, and named the line, in the team's part and in the worksheet's part |
| The replay | gave the same final report for that run with every connection refused |
| The page behind the one command | changed and tested; not yet run on a company from the page |
| The spinoff seeker | not built yet. [seeker/README.md](seeker/README.md) says what the desk reads from it |

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

Before the first run, a team member adds the client's hand-written files: [client/README.md](client/README.md)
says which, and what each holds. Without them the agent team still writes its verified report, and the
command stops at the worksheet and names the file it needs.

**From the page, without a terminal.** On Windows, double-click `start_page.bat`. On a Mac,
double-click `start_page.command` (the first time, right-click it and choose Open). The page opens in
your browser at http://127.0.0.1:8765. Type a ticker and press Run. Each part's name appears as it
runs. When the run ends, the final report shows on the page.

**From a terminal: the one command.** Give the ticker. `CSCO` is an example; use any ticker.

Windows:

```
.venv\Scripts\python desk.py CSCO
```

Mac:

```
.venv/bin/python desk.py CSCO
```

The parts run in an order that code fixes, and no model chooses it: the pick, the agent team (the steps,
the Research Analyst, the Financial Analyst, the Investment Advisor, the Strategy Manager, the Verifier),
the hook on the team's report, the worksheet, the hook on the worksheet, the final report, and the hook
on the final report. Each part prints the seconds it took on its last line. The last lines give the run
folder and the path of the final report, and then "Done" or "Not done".

| Command, after `python` | What it does |
|---|---|
| `desk.py TICKER` | runs the whole desk on a ticker |
| `desk.py screen` | runs it on the top name of the seeker's latest report (the seeker is not built yet) |
| `desk.py --replay output/<run folder>` | rebuilds a saved run's final report from its saved outputs, and runs the hook on them again. It fetches nothing, calls no model and writes nothing; try it with the network off |
| `hook.py output/<run folder>/final_report.md` | checks every number in a saved output. It prints nothing when all have their source, and `refused: line N, ...` when one does not |
| `hook.py a_copy.md --run output/<run folder>` | the same on a copy kept elsewhere: change one amount by one in a copy, and the hook names the line |
| `worksheet.py output/<run folder>` | writes the worksheet alone, on a saved run of the agent team |
| `team.py TICKER` | runs the agent team alone, as before |
| `team.py --verify-only output/<run folder>` | runs the Verifier alone on a saved run |

Options after the ticker, for `desk.py` and `team.py`:

| Option | What it does |
|---|---|
| `--peers AAA,BBB` | adds peer companies to the comparison |
| `--price 123.45` | gives the close by hand |
| `--filed 2026-11-12T16:07:06` | gives the release's filing time, Eastern, when you do not want the 8-K's own |

When a part fails, the command stops, prints which part failed and the error, and keeps the run folder.
When the hook refuses a line, the parts after it still run, so that you have every output, and the
command ends "Not done" with exit code 2.

The data steps alone need no model key and cost nothing. They print every fact with its XBRL tag, its
period and its filing. On a Mac, type `.venv/bin/python` in place of `.venv\Scripts\python`:

```
.venv\Scripts\python lab02_desk.py CSCO
```

## Read the report

Each run writes one folder, `output/<TICKER>_<date>_<time>/`, and never writes over an earlier run.

| File | What it holds |
|---|---|
| `final_report.md` | the verified report with the worksheet's view under it. Read this one. |
| `verified_report.md` | the agent team's report, with the Verifier's table of marks under its first line |
| `report.md` | the report before the Verifier marked it |
| `worksheet.md` | the worksheet: the facts, owner cash flow with its arithmetic, the low and mid cases, the price against the low case, the persona's judgment, the liquidity line, the view and what is not known. Each number has its source in square brackets |
| `view.json` | the view as the hit-rate table reads it: the ticker, the release's filing time, the view's own time and its direction |
| `pick.json`, `price.json`, `worksheet_file.json`, `liquidity.json` | the ticker and where it came from; the one close; the worksheet file as this run read it; the median dollar volume. The series of closes and volumes is not saved |
| `desk.json` | the order of the parts, the seconds each took, and every line the hook refused |
| `10K_*.txt`, `10Q_*.txt`, `8K_*.txt` | the three documents as plain text; the 8-K file is Exhibit 99.1 |
| `facts.json`, `ratios.json`, `peer_facts.json` | each fact with its tag, period and filing; each ratio with its arithmetic |
| `nodes/` | what each part received and returned, numbered in the order the parts ran. A part that stopped leaves a file whose name ends in `_stopped.json`, with the time, the error and its causes |
| `audit.md` | a blank audit table for a person to fill in against the filings |

The report's first line names every filing the desk read, with each accession number and "Accepted"
time. The table "Core figures from the desk's steps" holds the eleven core claims of the course's
report audit. Code reads and computes them; no model writes them. The roles write the text around
them, and the Verifier marks each number in that text correct, wrong or unsupported.

The join is the pipeline: each part reads the files that the part before it saved in the run folder, and
no part fetches a filing that another part saved. The hook reads the saved outputs themselves. In the
worksheet it checks each number against the source in its square brackets. In the agent team's report it
does not judge the numbers again: it requires that the Verifier marked none wrong and none unsupported,
and that the text is the text the Verifier marked. It makes no model call.

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
| A line that ends a run, such as `Verifier stopped: ...` | The line names the part that stopped and the reason. The run folder is kept, and its `nodes/` folder holds a record of the stop. When the Verifier stopped, the report is already saved: run the command that the message gives, `team.py --verify-only` with the run folder. |
| `the connection was lost (...); trying this call once more` | Nothing to do. The connection to the model was cut, and the desk sends that one call again. A second cut stops the run. |
| `The worksheet file is missing`, or `The persona file is missing` | A team member writes these two files by hand: [client/README.md](client/README.md) gives their shape. The agent team's verified report is already in the run folder. |
| `refused: line N, ...` and then `Not done` | The hook found a number with no support in that line of a saved output. Open the output at that line. The reason says what the number claims and what the saved file holds. |
| `View: not computed` in the worksheet | The reason is on the same line: no close, or the persona wrote a number that the worksheet does not print, or it named no deciding line. The hit-rate table leaves that run out. |

Known limits, as of 2026-11-11. The details are in [docs/decision-log.md](docs/decision-log.md).

1. The quarter's revenue, growth and diluted EPS (claims 9 to 11) are read from the release's income
   statement by rules. When the rules cannot read a claim, the report says "not found" or "not computed",
   with the reason. The figures are not yet checked against XBRL, so check them against the release.
2. Debt to equity says "not computed" when the 10-K does not tag both parts of its long-term debt in
   the way the desk reads. That is a missing claim, not an error.
3. When SEC EDGAR's company facts are not yet the facts of the 10-K the desk read, the report states no
   annual figure and says why. The quarter's claims and the rest of the report are still written.
4. The desk needs all three filings. A company with no 10-K yet, or one that files 20-F and 6-K, stops the run.
5. The worksheet knows one method: owner cash flow divided by a rate, per diluted share, with no debt
   subtracted and no cash added. It reads volumes from financialdatasets.ai only, not yet from LSEG.
6. The seeker is not built. Every name is "not applicable" in the worksheet's spinoff part, and `desk.py
   screen` stops at the pick. For a name in a registry, the worksheet would state the parent, the ratio and
   the dates, and "not known" for what the parent left in it.
7. In the agent team's report the hook relies on the Verifier's marks. It does not check those numbers a
   second time.

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
page, the closes reader on made-up files, and the live record on a made-up repository. For the one desk
they cover the worksheet's arithmetic and its "not computed" cases, the hook's refusal of one amount
changed by one for each kind of source, the fixed order of the parts, the stop at a failing part, and
the replay with every connection refused.

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
