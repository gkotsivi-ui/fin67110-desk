# Team [the team writes its name] — gkotsivi-ui, jcleeper65, lee4276

DRAFT for Checkpoint 3, due Thu Nov 19, 11:59 PM Eastern: one Markdown page, uploaded by one member to
Brightspace → Checkpoint 3. A line in square brackets is for the team to write. The notes at the end are for
the team and are removed before the upload.

Client: an investor seeking absolute return.

The desk: [the team's own drawing goes here, drawn by hand: the agent team, the seeker, the worksheet, the hook
and the one command, with one arrow for each file that passes between them. Save a photo of it in `docs/` and
link it on this line.]

The joins: [the team writes this paragraph in its own words: which join the desk uses where.]

We own: [the team names the one thing it owns.]

Roles: [each member's role in one line, written by the team: each member beside a part that exists in the
repository.]

Live record so far: https://github.com/gkotsivi-ui/fin67110-desk/tree/1511680/runs/live

| Week | Ticker | Release the report read | Filing time, "Accepted" on EDGAR (ET) | Commit, and its time (ET) | Inside the 24-hour window |
|---|---|---|---|---|---|
| Week 4 | CSCO | 8-K 0000858877-26-000170, Exhibit 99.1 | 2026-11-12 16:06:24 | `88015f7`, 2026-11-13 13:17:26 | yes, 21.2 hours after the release |
| Week 5 | NVDA | 8-K 0001045810-26-000088, Exhibit 99.1 | 2026-11-17 16:20:51 | `f55b170`, 2026-11-18 08:52:43 | yes, 16.5 hours after the release |

The table is made by `python live_record.py`, from each report's first line, the 8-K's "Accepted" time on SEC
EDGAR and the time of the commit that first added the report. It is in
[docs/live-record.md](live-record.md).

This is a learning exercise, not financial advice.

AI assistance: [the tools the team used; this repository names Claude Code and OpenAI Codex]. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.

---

## Notes for the team (remove before the upload)

**What the page must hold**, from the Lab 09 page: the team's name; the desk's design as one diagram; which
join it uses where; the thing the team owns; each member's role in one line; the live record so far.

**Refresh before the upload.** After the Week 5 report is filed, run `python live_record.py`, add its row, and
change the permalink above to the newest commit of `main` (on github.com: open `runs/live`, press `y`, copy
the address).

**For the drawing.** The lab checks that the files in a run folder match the arrows in the diagram, one to
one. This is what each part reads and writes today, as the code on the branch `one-desk` does it:

| Part, in the order the one command runs them | Reads | Writes into the run folder |
|---|---|---|
| The pick | the ticker on the command line, or the seeker's latest report | `pick.json` |
| The agent team: the steps | SEC EDGAR; the closes reader | `10K_*.txt`, `10Q_*.txt`, `8K_*.txt`, `facts.json`, `ratios.json`, `peer_facts.json`, `price.json` |
| The agent team: the three analyst roles | what the Strategy Manager's code gives each of them from those files | `nodes/` |
| The agent team: the Strategy Manager, in code | the three roles' parts | `report.md`, `audit.md` |
| The agent team: the Verifier | `report.md`, `facts.json`, `peer_facts.json`, the three filing texts | `verified_report.md`, `verification.json` |
| The hook on the team's report | `verified_report.md`, `verification.json` | nothing |
| The worksheet | `facts.json`, `price.json`, `nodes/01_steps.json`, the client's two hand-written files; the closes reader, for volumes | `worksheet.md`, `view.json`, `worksheet_file.json`, `liquidity.json` |
| The hook on the worksheet | `worksheet.md`, `facts.json`, `price.json`, `worksheet_file.json`, `liquidity.json`, the release's text | nothing |
| The final report | `verified_report.md`, `worksheet.md` | `final_report.md` |
| The hook on the final report | `final_report.md` and the same files as the two hooks before it | nothing |
| The one command | what each part did | `desk.json` |

The seeker is not built. When it is, it runs first and only when the command asks for it, and the pick reads
its report.

**For the joins paragraph.** These are facts about the code, for the team to put in its own words. Every part
is joined as a pipeline: a part reads the files that the part before it saved, and nothing calls another part.
No role calls a skill as a tool. The hook is the guard: it runs on the team's report, on the worksheet and on
the final report. The persona in the worksheet receives the worksheet's lines as text in one model call; the
sentence that lets it quote and forbids it to recompute is in `worksheet.py`, in the rules that code adds to
the persona.

**For "We own".** On 2026-11-17 jcleeper65 wrote in the README: "The thing we own: the intelligent error review
application" (`desk_error_review.py`, `skills/desk-error-review/`). The team confirms it here in its own words.

**For the roles.** What the repository shows on 2026-11-16, for the team to check against what each member
did: commits on `main` by gkotsivi-ui (the desk's data steps and their fixes, the Verifier's fixes, the Week 4
and Week 5 live runs) and by jcleeper65 (the error documentation for live records, the hit-rate table, the
error review application); none yet by lee4276. The worksheet, the hook and the one command are in pull request
for the branch `one-desk`. The lab checks that every member is named beside a part that exists in the repository.
