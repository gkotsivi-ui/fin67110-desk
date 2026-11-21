# Team [the team writes its name] — gkotsivi-ui, jcleeper65, lee4276

Client: an investor seeking absolute return.

The desk: [the hand-drawn diagram goes here: the agent team, the seeker, the worksheet, the hook and the one
command, with one arrow for each file that passes between them. Photograph it, save it in `docs/`, and link it
on this line. No AI draws it.]

The joins: [one paragraph in the team's words: which join the desk uses where. The facts are under "Notes".]

We own: the intelligent error review application, `desk_error_review.py` with its skill `desk-error-review`.
[The team confirms this line.]

Roles:
- gkotsivi-ui: [one line, written by this member]
- jcleeper65: [one line, written by this member]
- lee4276: [one line, written by this member]

Live record so far: https://github.com/gkotsivi-ui/fin67110-desk/tree/7285544/runs/live

| Week | Ticker | Release the report read | Filing time, "Accepted" on EDGAR (ET) | Commit, and its time (ET) | Inside the 24-hour window |
|---|---|---|---|---|---|
| Week 4 | CSCO | 8-K 0000858877-26-000170, Exhibit 99.1 | 2026-11-12 16:06:24 | `88015f7`, 2026-11-13 13:17:26 | yes, 21.2 hours after the release |
| Week 5 | NVDA | 8-K 0001045810-26-000088, Exhibit 99.1 | 2026-11-17 16:20:51 | `f55b170`, 2026-11-18 08:52:43 | yes, 16.5 hours after the release |

The table is made by `python live_record.py` from each report's first line, the 8-K's "Accepted" time on SEC
EDGAR, and the time of the commit that first added the report ([docs/live-record.md](live-record.md)).

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.

---

## Notes for the team (delete this section before the upload)

**What the page must hold** (Lab 09, Checkout): the team's name; the desk's design as one diagram; which join
it uses where; the thing the team owns; each member's role in one line; the live record so far. One Markdown
page, one upload per team, Brightspace → Checkpoint 3, by Thu Nov 19, 11:59 PM ET.

**For the diagram.** Lab 09 checks that "the files in a run folder match the arrows in the diagram, one to
one". These are the files each part of `desk.py` saved in a real run on 2026-11-19, in the order code fixes:

| Part | Reads | Saves in the run folder |
|---|---|---|
| The one command | the ticker, or `screen` | `desk_run.json`, `artifacts.json`, `timings/` |
| Inputs | the hand-written files | `inputs/`: the persona, the worksheet rules, the factor list, the role prompts |
| The seeker, only when asked (`--refresh-screen`) | SEC EDGAR's quarterly indexes and filings | `registry.json`, `seeker_status.json`, `screen.json`, `screen.md` |
| The pick | the ticker, or the screen | `pick.json`, `spinoff_status.json` |
| The agent team: the seven data steps | SEC EDGAR; the closes reader | `10-K.txt`, `10-Q.txt`, `earnings_release_Ex99-1.txt`, `filings.json`, `filing_time.json`, `facts.json`, `calculated_facts.json`, `market_price.json` |
| The agent team: three analyst roles | those files and the pick, by a file tool | `nodes/<role>_N/`: each role's input, claims, draft and the files it read |
| The agent team: the Strategy Manager | the roles' saved drafts | `nodes/Strategy_Manager_N/`, `team_report.json`, `report.md` |
| The agent team: the Verifier | the report and the cited filing lines | `verifier_input.json`, `nodes/Verifier_N/`, `verified_report.md` |
| The worksheet | the team's saved facts, the price, the registry, the rules and the persona | `Spinoff worksheet, TICKER, DATE, TIME.md` and `.json`, its model input and output, `view.json` |
| The final report | the verified report and the worksheet | `final_report.md` |
| The hook, after every part | that part's saved files | `hook/` |

**For the joins paragraph.** Facts from the code, for the team to put in its own words:
- Every part is joined as a **pipeline**: each reads the files the part before it saved in one run folder.
  Nothing calls another part.
- The roles read the seeker's saved files (`pick.json`, `spinoff_status.json`) with a file tool. That is
  still the pipeline; no role calls the seeker or the worksheet as a tool.
- The **hook** is the guard. It checks each part's saved files before the next part starts. It refuses a
  number that has no source, and it rebuilds the published report from the saved role files.

**For the roles.** The commit history on `main` on 2026-11-19:
- **gkotsivi-ui:** the base desk and its data steps, the Verifier's fixes, the Week 4 and Week 5 live runs,
  and the Windows fixes.
- **jcleeper65:** the live-record error documentation, the hit-rate table, the error review application,
  and the group pipeline (`desk.py`, the seeker, the worksheet, the hook).
- **lee4276:** no commit yet. The lab checks that every member is named beside a part that exists in the
  repository.
