# Product manual: [the team's name]'s research desk

> **Draft, 2026-11-19. Delete this box before the upload.** Claude Code wrote the facts below from the
> repository: the live record, the audit counts, the commands and what each report said. Every [bracket]
> is for the team. The course reserves the diagram and each member's roles paragraph for the members' own
> hands, and the "honest reading" question grades whether this manual claims more than the evidence shows,
> so the team writes the conclusions. Update the tables after each live run and after the exchange.

## The question and the client

Can an AI research desk our team built read any company's filings and its earnings release correctly,
serve one client's decision, and prove it live?

The client is an investor seeking absolute return. The desk's last step, the worksheet, values the company from
three years of owner cash flow in its filings and compares that value with the price: worth more or less than
the price, with the evidence. It needs a price, from LSEG Workspace or from a file of closes exported from
it; without one, its view is "not computed".

## Run the desk

The [README](README.md) is the manual for running it: one Python environment, a `.env` with three lines,
then one command, `desk.py TICKER`, or the page (`start_page.bat` on Windows, `start_page.command` on a Mac)
for a person who does not use a terminal. Practice runs on 2026-11-19 and 2026-11-20 took from about 10 to 35 minutes. It reads the company's latest
10-K, 10-Q and earnings release (the 8-K's Exhibit 99.1) from SEC EDGAR, and it runs on any U.S. company
that files them, whether or not the seeker has seen it.

## How the desk works

[The hand-drawn diagram: the agent team, the Verifier, the tools, the skills, the hook and the one command,
with one arrow for each file that passes between them. No AI draws it.]

The parts run in a fixed order, each reading only what the parts before it saved in one run folder:

| Part | Reads | Saves in the run folder |
|---|---|---|
| The one command, `desk.py` | the ticker | `desk_run.json`, `artifacts.json` |
| Inputs | the hand-written persona, rules, factor list and role prompts | `inputs/` |
| The seeker, only when asked | SEC EDGAR's indexes and filings | `registry.json`, `screen.json`, `screen.md` |
| The pick | the ticker, or the screen | `pick.json`, `spinoff_status.json` |
| The agent team: seven data steps | SEC EDGAR, the closes reader | the filings' text, `facts.json`, `calculated_facts.json`, `market_price.json` |
| The agent team: Research Analyst, Financial Analyst, Investment Advisor | those files, through a file tool | `nodes/<role>_N/`: each role's claims and draft |
| The agent team: Strategy Manager | the roles' saved drafts | `team_report.json`, `report.md` |
| The Verifier | the report and the cited filing lines | `nodes/Verifier_N/`, `verified_report.md` |
| The worksheet (the client's skill) | the team's saved facts, the price, the rules and the persona | the worksheet, `view.json` |
| The final report | the verified report and the worksheet | `final_report.md` |
| The hook, after every part | that part's saved files | `hook/` |

Every number in a report is a claim: a quoted line of a filing, a saved XBRL fact, or a value code computed
from them. Code renders each number into the text; the models choose which claims to use. A claim the code
cannot check after two repairs, and a claim the Verifier does not mark correct, are left out of the
published report, and the report says which. The details are in [docs/group-pipeline.md](docs/group-pipeline.md).

The joins: [one paragraph in the team's words: every part is joined as a pipeline, through the files the
part before it saved; no part calls another; the hook guards each step.]

## The live record

| Week | Ticker | Release the report read | Filing time, "Accepted" on EDGAR (ET) | Commit, and its time (ET) | Inside the 24-hour window |
|---|---|---|---|---|---|
| Week 4 | CSCO | 8-K 0000858877-26-000170, Exhibit 99.1 | 2026-11-12 16:06:24 | `88015f7`, 2026-11-13 13:17:26 | yes, 21.2 hours after the release |
| Week 5 | NVDA | 8-K 0001045810-26-000088, Exhibit 99.1 | 2026-11-17 16:20:51 | `f55b170`, 2026-11-18 08:52:43 | yes, 16.5 hours after the release |
| Week 6 | [ ] | | | | |
| Week 7 | [ ] | | | | |

`python live_record.py` makes this table from each report's first line, the 8-K's "Accepted" time on SEC
EDGAR, and the commit that first added the report ([docs/live-record.md](docs/live-record.md)). The reports
are in [runs/live](runs/live).

## The audits

| Report | Errors (wrong + unsupported) | Missing | Audited by |
|---|---|---|---|
| Week 4, Cisco (ours) | 0 [draft] | 0 [draft] | [member] |
| Week 5, NVIDIA (ours) | 0 [draft] | 0 [draft] | [member] |
| [Other team], [company 1] | [ ] | [ ] | us, at the exchange |
| [Other team], [company 2] | [ ] | [ ] | us, at the exchange |

The tables are in [audits.md](audits.md). Why these two of our own: [the team's reason; on 2026-11-19 they
were the only two live reports].

## What the desk told the client

| Week | Report | Recommendation, and the number it named | The worksheet's view |
|---|---|---|---|
| Week 4 | Cisco | Hold: free cash flow fell 3.92% while net income rose 30.32% | none: these reports came from the base desk, before the worksheet joined it |
| Week 5 | NVIDIA | Buy: a P/E of 31.7 on fiscal 2026 GAAP diluted EPS | none, for the same reason |

`python hit_rate.py runs/live` scores each saved view against the price's first reaction after the filing.
On 2026-11-19 it scored none: both live reports predate the worksheet, so neither has a view.

[The hit-rate table, from Week 6 on.]

[The base rate under it, from WRDS: Greg runs it; no WRDS value enters an AI tool.]

[What happened afterward, and what four weeks can and cannot show: the team writes this. Four reports
cannot measure a hit rate; the manual says only what they show.]

## The decision log

The full log is [docs/decision-log.md](docs/decision-log.md): what our AI agents got wrong, how we caught
each one, and what changed. Among them:

- The quarter's revenue came from a guidance table, not the income statement (a live probe, 2026-11-11).
- The Verifier marked nine correct numbers wrong, and the coding agent reported them as errors before reading them.
- Code written on a Mac ran wrong on Windows: file locks, paths, and text read in the Windows code page.
- One claim that failed the code's check, or one the Verifier flagged, stopped a whole run with no report.

What we would not delegate again: [the team writes this].

[The three-column table of what the join changed (Week 5).]

## The roles

[One paragraph per member, written by that member: the role and the contribution.]

- gkotsivi-ui: [ ]
- jcleeper65: [ ]
- lee4276: [ ]

This is a learning exercise, not financial advice.

AI assistance: Claude Code and OpenAI Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
