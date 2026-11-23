# Code audit, November 2026

A full audit of the team desk, made 2026-11-21 and 2026-11-22 on branch `full-audit`. The branch was cut
from `origin/main` at `140c4b3`. The audit was committed as `086a312`. Six independent reviewers then read
that commit, and what they found is fixed in the commit after it, `0226521` (section 4, "Found by an
independent review"). On 2026-11-22 `main` was merged in at `1d94e2a`, with two commits a member had made
meanwhile; they closed two items this file had listed as open, and it says so where they stood. The
branch is pull request 12 of the team's repository. A member decides on the merge.

**Result.** `python check_all.py` runs 928 tests with no failure, 4 skipped, and every other check
passes, on Windows 11 without UTF-8 mode. Before the audit the four test folders held 663 tests, and the
required check, as `AGENTS.md` wrote it, failed on Windows. The audit fixed 56 findings, nine of them
critical. The review of its commit then returned 50 findings, each reproduced: 26 had come with the audit's
own commit (one critical, six high), 13 were older than the audit, and 11 were rules with no test that could
fail. They are fixed in 27 groups, each with a test on made-up data. 21 findings are open and listed with
the reason in section 4. No model was called and no real run was made: the model account has had no credit
since 2026-11-21 (section 5).

**Read first, before the next live run:** section 6, items 1 to 4.

## 1. System map

Two desks live in this repository. Until this audit they shared the closes reader's worker and little
else, and that was the audit's first finding: a rule fixed in one desk was often not fixed in the other.
The rules both must follow are now in two shared files, `desk_rules.py` and `model_calls.py`.

| | The group desk (the one command) | The base desk (legacy; wrote the Week 4 and Week 5 reports) |
|---|---|---|
| Command | `desk.py TICKER [--live]`, `desk.py --resume RUN`, `desk.py --replay RUN`, or the page (`page.py`, `start_page.bat`, `start_page.command`) | `team.py TICKER`; `lab03_app.py` (no Verifier); `lab02_desk.py` (data steps only) |
| Environment | `.venv-desk`, Python 3.13, `requirements-pipeline.txt` with `constraints-pipeline.txt` | `.venv`, `requirements.txt` |
| Data steps and numbers | `equity_research_desk.py` (steps 1 to 7), `quarterly_cash_flow.py` | `lab02_desk.py` (steps 1 to 7), `release.py` |
| Rules both share | `desk_rules.py`: the facts of the chosen 10-K, the release among the 8-K's exhibits, the course footer. `release.py`: what an income statement is | the same two files |
| Roles | `equity_research_agent_team.py` on CrewAI: five model roles, text in `pipeline_roles/` | `lab03_app.py` and `team.py` on LangGraph: three model roles and a code Strategy Manager, personas in `roles/` |
| Model calls | `model_calls.py`: one retry rule and the time limits, for the team and the worksheet | its own client in `lab03_app.py`; no retry |
| Checks on model text | `desk_claims.py` (the claim ledger), `desk_role_contracts.py`, `desk_hook.py` after every part | the Strategy Manager's code checks (`lab03_app.py`), then `verifier.py` |
| Price | `closes_reader.py`: a file named by `LSEG_CLOSES_FILE`, or LSEG Workspace through `.venv-lseg`. No other source | `closes.py` (LSEG, or a CSV), then `prices.py` (financialdatasets.ai) |
| Run folder | `runs/practice/` or, with `--live`, `runs/live/` | `output/`, moved by hand into `runs/live/` |

**The group desk, in the order code fixes** (`desk.py`, `DeskRun.execute`). Before the first part the desk
checks the three settings (`check_pipeline.settings_problems`). The hook (`desk_hook.py`) checks the files
each part changed. A part that fails stops the run, records itself in `desk_run.json`, and keeps the folder.

| # | Part | Reads | Writes in the run folder | Model | Network |
|---|---|---|---|---|---|
| 1 | inputs | `spinoff-rules.md`, `persona-why-cheap.md`, `spinoff_factors.json`, `pipeline_roles/` | `inputs/` | no | no |
| 2 | seeker | a saved registry or screen; with `--refresh-screen`, EDGAR's indexes | `registry.json`, `seeker_status.json`, `screen.*` | no | SEC and LSEG, only on a refresh |
| 3 | pick | the screen or the ticker | `pick.json`, `spinoff_status.json` | no | no |
| 4 | team | SEC company facts and the three filings | `filings.json`, `filing_time.json`, the three `.txt` files, `facts.json`, `calculated_facts.json`, `market_price.json`, `nodes/`, `report.md`, `verified_report.md` | five roles, at most two calls each, plus repairs | SEC, LSEG, the model provider |
| 5 | worksheet | the saved filings, the registry, the rules and the persona | `view.json`, `Spinoff worksheet, ….md` and `.json`; the daily rows of the liquidity test in `sources/licensed/`, which git ignores | one call | SEC and LSEG, the model provider |
| 6 | final report | the verified report and the worksheet | `final_report.md`, ending with the course footer, then `artifacts.json` | no | no |

Every SEC request of the group desk goes through `Sources.response` (`desk_sources.py`): SEC hosts only, the
User-Agent from `.env`, 0.23 seconds between requests, up to three requests for a page, each answer saved
once under `sources/http/` and read from there afterwards. A single close is saved under `sources/prices/`;
a list of closes under `sources/licensed/`. `desk.py --replay RUN` rechecks a saved run with the network
blocked. `desk.py --resume RUN` finishes a run that stopped in its worksheet or final report.

**Where numbers are computed.** The eight annual claims: `equity_research_desk.py` `compile_facts`, `debt_pair`
and `step5`, from SEC company facts, only when those facts are the facts of the 10-K the first line names.
The quarter's three: `step6`, from the release's HTML tables, by two table readers that share one row
reader. Capital spending of the latest quarter: `quarterly_cash_flow.py`. The table of the eleven claims is
printed by `desk_role_contracts.core_claims_table`. The worksheet's values:
`skills/spinoff-worksheet/scripts/`. No model computes a number; `desk_claims.check` renders every number in a
role's text from a cited line or a computed fact.

**Other programs.** `check_all.py` (every check, one command); `check_public.py` (what must not go public);
`live_record.py` (the live-record table, from the reports' first lines, the runs' state, EDGAR and git);
`hit_rate.py` (the reaction to each release, from `view.json` and the legacy `closes.py`); `desk_error_review.py`
and its page (the error documents beside each live run); `check_pipeline.py`, `check_env.py`, `check_lseg.py`,
`set_keys.py` (setup); `utf8_mode.py` (starts a program again in UTF-8 mode on Windows).

## 2. Catalog of past failures

Every failure on record before this audit: `docs/decision-log.md` ("DL" with the entry's number or date),
the error documents beside the two live runs, `audits.md`, `PLAN.md` and the commit history. The last two
columns were filled by searching the code and the test files for each fix, and then corrected for what this
audit changed ("audit" with a finding's ID from section 4). A test named here was found by its text; the
audit did not run each one alone.

Classes: **layout** = a reader assumes one filing layout; **missing** = a missing fact read as zero or as
another fact; **formula** = differs from the checklist; **one desk** = fixed in one desk only; **model
text** = model text adds or changes a number; **false flag** = a check flags a correct number; **setting**
= a missing key or setting with an unclear message; **network** = a drop with no second try; **Windows** =
a path or an encoding; **docs** = documents differ from code; **weak test** = a test that cannot fail;
**public** = private or licensed things near a public file; **process** = not a fault of the code.

| # | Date | What failed | Class | Fixed in | Regression test |
|---|---|---|---|---|---|
| 1 | 11-11 | Quarter growth printed as 1950%: the guidance row was read as revenue (DL 1) | layout | base desk `release.py`; group desk by audit Q1 | `tests/test_release.py`; `tests/test_quarter_readers.py` |
| 2 | 11-11 | Debt to equity printed 0.000: a missing debt fact read as zero (DL 2) | missing | both desks | `tests/test_debt_pairs.py`, `tests/test_desk.py` |
| 3 | 11-11 | Run stopped on a release labelled EX-99, not EX-99.1 (DL 3) | layout | both, one rule since audit X1 | `tests/test_desk.py`; `tests/test_release_exhibit.py` |
| 4 | 11-11 | The Verifier marked 9 correct numbers: "fell 3.92%", named arithmetic, "less than 2%" (DL 4) | false flag | base desk only (`verifier.py`); the group Verifier is another design | `tests/test_team.py` |
| 5 | 11-11 | A coding agent reported a count of marks as real errors (DL 5) | process | a working rule | none |
| 6 | 11-11 | README called each `roles/` file a six-part persona; they are rule lists (DL 6) | docs | open; members write personas | none |
| 7 | 11-11 | `tests/test_page.py` failed in a fresh clone: it wrote into an ignored folder (DL 7) | Windows | the test | the test itself; by audit, page tests write to a temporary folder |
| 8 | 11-11 | A fresh install gave other package versions (DL 7) | process | `requirements.txt` pins; group: `constraints-pipeline.txt`, now on every install line (audit F3) | none |
| 9 | 11-11 | First clone did not install: a path over 260 characters (DL 8) | Windows | README only | none |
| 10 | 11-11 | Caught before shipping: a debt rule that would drop a correct ratio in 3 of 8 filings (DL 9) | missing | both | `tests/test_debt_pairs.py` |
| 11 | 11-11 | Caught before shipping: a tag accepted from a model's memory (DL 10) | process | a working rule | none |
| 12 | 11-11 | Quarter EPS read from the "continuing operations" row (DL 11) | missing | base desk; group desk by audit Q1 | `tests/test_release.py`; `tests/test_quarter_readers.py` |
| 13 | 11-11 | Columns chosen by position, not by their dates (DL 12) | layout | base desk; group desk by audit Q1 | `tests/test_release.py`; `tests/test_quarter_readers.py` |
| 14 | 11-11 | No EPS read when the release prints `$ (0.04)` (DL 12) | layout | base desk; the group reader's loss forms by audit Q1 | `tests/test_release.py`; `tests/test_quarter_readers.py` |
| 15 | 11-11 | A restated number keeps its source whatever the sentence says (DL 11) | false flag | open, a known limit of the base Verifier | none |
| 16 | 11-11 | The listing model gave 155 numbers in one run and 150 in the next (DL 11) | model text | open, base desk | none |
| 17 | 11-11 | A ratio redone from printed inputs can differ in its last digit (DL 11) | formula | open | none |
| 18 | 11-11 | Net income "growth" offered when a net loss widened (DL 13) | formula | base desk (`team.py`); the group desk computes growth for revenue only, on a positive base (audit Q1) | `tests/test_team.py`; `tests/test_quarter_readers.py` |
| 19 | 11-12 | Another fiscal year's facts written under the new 10-K's name (DL 14, "F8") | missing | base desk; group desk by audit N1; one rule | `tests/test_annual_facts.py` |
| 20 | 11-12 | Debt under tags of two families; a bank with six of eleven claims missing (DL 14) | layout | open (the first half has a test) | `tests/test_debt_pairs.py` |
| 21 | 11-12 | `check_env.py`: "lseg-data is not installed" after a README rewrite dropped the line (DL 15) | docs | docs, `requirements-lseg.txt` | none |
| 22 | 11-12 | A coding agent started the individual desk's page (DL 15) | process | caught by reading | none |
| 23 | 11-12 | The price came from financialdatasets.ai and the page did not say why (DL 15; both live runs) | setting | open in the base desk | none |
| 24 | 11-13 | Week 4 live run stopped in the Verifier: a connection reset, a traceback, no verified report (Cisco error 1) | network | group desk (one more try; `model_calls.py` by audit M1, M2); the base desk still has none | `tests/test_dropped_connection.py`; `tests/test_model_calls.py` |
| 25 | 11-13 | The stopped run's folder held no record of the stop (Cisco error 2) | process | group desk (`desk_run.json`; Ctrl+C by audit R4); base desk only on an unmerged branch | `tests/test_joined_desk.py`; `tests/test_run_control.py` |
| 26 | 11-13 | The page showed terminal colour codes in a traceback (Cisco error 3) | Windows | open, never tested | none |
| 27 | 11-13 | "Partner's check" is empty in the filed report; `audit.md` is blank (Cisco error 4) | process | open in the base desk | none |
| 28 | 11-16 | The live runs have no dated view, so the hit-rate table scores none | process | `view_record.py`, `hit_rate.py` for later runs | `tests/test_view_record.py`, `tests/test_hit_rate.py` |
| 29 | 11-17 | The thesis says the price "prices in" growth because P/E is near EPS growth (Cisco, revision 2) | model text | unconfirmed; a review never repairs | none |
| 30 | 11-18 | Two true numbers marked unsupported: the heading above the quoted line names the segment (NVIDIA error 1) | false flag | group desk (the Verifier sees eight lines each side) | not looked up |
| 31 | 11-18 | The table names the quarter's column "the column for 2026" (NVIDIA error 2) | layout | base desk: only on the unmerged branch `one-desk` | none |
| 32 | 11-19 | NVIDIA's capital spending includes intangible assets (`audits.md`) | formula | open, a team decision | none |
| 33 | 11-16 | Six test modules could not import: the check ran in system Python | setting | README | none |
| 34 | 11-16 | Caught before shipping: a fixed 4 PM cutoff misclassifies an early close | formula | `hit_rate.py`, `view_record.py`; **not** the desk's price (open D1) | `tests/test_hit_rate.py`; `tests/test_last_close_before.py` holds today's rule |
| 35 | 11-17 | The error-review evaluation reported a false alarm: a fixture held a second error | process | the fixture | `tests/test_error_review.py` |
| 36 | 11-17 | A test assumed a document order | process | the test | `tests/test_error_review.py` |
| 37 | 11-17 | A page launched the team alone and read its intermediate report | one desk | `page.py` | `tests/test_page.py` |
| 38 | 11-19 | The group page launched a neighbouring repository's desk | process | every part copied in; paths outside refused | `tests/test_pipeline_independence.py` |
| 39 | 11-19 | A path test failed on macOS: a resolved path against its alias | Windows | the test | `tests/test_error_review.py` |
| 40 | 11-19 | The NVIDIA record had no AI prompt | process | made by format conversion, and says so | none |
| 41 | 11-19 | Five integration errors when the pipeline was copied in | process | group desk | `tests/test_pipeline_independence.py` |
| 42 | 11-19 | A run on a named ticker stopped at the seeker: the screen ranked nothing | process | group desk | `tests/test_joined_desk.py` |
| 43 | 11-19 | A practice run stopped: the Verifier refused "approximately $500" for its unit | model text | group desk, by the leave-out of row 45 | not looked up |
| 44 | 11-19 | The reaction lookup had no prices: `lseg-data` missing in the desk's Python | setting | both (`closes.py` asks the worker); the base desk's own missing package by audit D3 | `tests/test_closes.py`, `tests/test_lseg_setup.py`, `tests/test_one_rule_one_place.py` |
| 45 | 11-19 | One Verifier flag stopped the run with no report (7 of 92 flagged; 3 real, 4 true) | model text, false flag | group desk: a flagged line is left out; by audit C7 it is also left out where another role repeats it | `tests/test_all_role_contracts.py`, `tests/test_desk_claims.py`, `tests/test_published_report.py` |
| 46 | 11-19 | The run did not start: no `MODEL` line, and the worksheet took only a Claude model | setting | group desk; by audit M4 and M6 the desk stops at its first step and names the setting | `tests/test_setup_checks.py` |
| 47 | 11-19 | No run on Windows: `fcntl` | Windows | group desk (`msvcrt`) | `tests/test_file_locks.py` |
| 48 | 11-19 | On Windows the hook skipped its checks and gave no error: `\` against `/` | Windows, weak test | group desk (`.as_posix()`) | the existing tests, which failed on Windows |
| 49 | 11-19 | No close on Windows: a Mac path for the LSEG worker | Windows | group desk | `tests/test_windows_portability.py`, `tests/test_lseg_setup.py` |
| 50 | 11-19 | A claim "sixth consecutive quarter" was sent back twice with a message the model could not act on | process | `desk_claims.py` | `tests/test_desk_claims.py` |
| 51 | 11-19 | On Windows the worksheet could not read its own rule "÷ 10%" | Windows | `utf8_mode.py`; by audit F1 every file is opened as UTF-8 by name | `tests/test_utf8_mode.py`; `tests/test_text_encoding.py` |
| 52 | 11-19 | The worksheet stopped: the model's reply was JSON plus one sentence | layout | `worksheet.py` | `skills/spinoff-worksheet/tests/test_worksheet.py` |
| 53 | 11-19 | The run stopped: the Verifier wrote "fy 2025" and the check read a number | false flag | `desk_claims.py` | `tests/test_desk_claims.py` |
| 54 | 11-19 | A practice run lost its connection five minutes into the Verifier's call | network | as row 24 | `tests/test_dropped_connection.py`, `tests/test_model_calls.py` |
| 55 | 11-20 | The worksheet stopped at the hook with no price | docs, missing | `hooks/` | `hooks/tests/test_worksheet_format.py` |
| 56 | 11-20 | Two reasons written by the worksheet's own code held a digit the hook cannot trace | false flag | `worksheet.py` | not looked up |
| 57 | 11-20 | The worksheet printed a raw `None` as its price evidence | missing | `worksheet.py` | not looked up |
| 58 | 11-20 | The hook refused a correct return on equity: a float against a decimal | false flag | `desk_hook.py` | `tests/test_hook_calculations.py` |
| 59 | 11-20 | The error-review files saved a member's home-folder path in the public repository | public | `desk_error_review.py`; by audit G1 and G2 the run's own files and the pre-push scan | `tests/test_error_review.py`; `tests/test_check_public.py`, `tests/test_run_control.py` |
| 60 | 11-20 | Debt to equity -4.015 where the definition gives -4.03; 0.449 where it gives 0.383 | one desk, formula | both | `tests/test_debt_pairs.py` |
| 61 | 11-20 | The group desk's first line had no CIK; `live_record.py` read no 8-K from it | one desk, docs | both; by audit D5 a run with no such line makes no final report | `tests/test_live_record.py`, `tests/test_joined_desk.py`, `tests/test_one_rule_one_place.py` |
| 62 | 11-20 | The analysts were given risk factors as Item 7 | layout | group desk | `tests/test_filing_extraction.py` |
| 63 | 11-20 | The group release reader read no quarter for any company | layout | group desk; rewritten by audit Q1 | `tests/test_quarter_table.py`, `tests/test_quarter_readers.py` |
| 64 | 11-20 | The worksheet read no owner cash flow | layout | `statements.py`, `hooks/` | `hooks/tests/test_worksheet_layouts.py` |
| 65 | 11-20 | A report left out revenue growth the desk had computed | one desk | both: the 11 claims are printed by code | `tests/test_core_claims.py` |
| 66 | 11-20 | A report printed "11.766682891778505%" and "$-9.917 billion" | process | `desk_claims.py` | `tests/test_desk_claims.py` |
| 67 | 11-20 | The analysts got net sales as "USD as shown" | layout | group desk | `tests/test_quarter_table.py` |
| 68 | 11-21 | Two runs from the page stopped at the first model call: no credit | setting | not a fault of the code; by audit R1 a finished team report is no longer lost when the stop comes later | `tests/test_run_control.py` |
| 69 | 11-20 | Six tests still failed on Windows: symlinks, the code page, loopback sockets | Windows | `tests/portable.py` | `tests/test_windows_portability.py` |
| 70 | 11-21 | A role skipped its structured files and the run stopped with no recovery | process | `desk_files.py` | `tests/test_assigned_read_recovery.py` |
| 71 | 11-21 | Two real values assembled into a false guidance range | model text | `desk_claims.py` (narrow on purpose) | `tests/test_guidance_ranges.py` |
| 72 | 11-21 | `FileNotFoundError` for the absent LSEG worker | setting | `check_lseg.py`, `docs/lseg-setup.md` | `tests/test_lseg_setup.py` |
| 73 | 11-21 | `check_lseg.py --session` passed with Workspace closed | weak test | `check_lseg.py` | `tests/test_lseg_setup.py` |
| 74 | 11-21 | Four outputs ended with their own footer or none | docs | all four; by audit H2 the group desk's final report too | `tests/test_footers.py`, `tests/test_run_control.py` |

**What the catalog shows.** Counting a row in each of its classes: layout 11, process 16, Windows 9, false
flag 7, missing 6, setting 6, formula 5, model text 5, docs 5, one desk 4, network 2, weak test 2, public 1.
The four "one desk" rows understate that class: six more fixes were in one desk only and nobody had
noticed (rows 3, 12, 13, 18, 19, 24). That is where this audit found three of its data errors (N1, N2,
X1).

**Decisions on record that this audit kept.** A missing claim is better than a wrong one. Debt to equity
uses the balance sheet's two parts as one pair, and the total tag is never the amount. A run stops only when
no report can be made. A claim the Verifier does not mark correct is left out, and the run goes on. A reply
that came is never asked again; a reply that never came is asked once more. Claims 9 to 11 come only from
the release's GAAP income statement. The guidance-range check is narrow on purpose. Live-run folders are the
record and are not edited. No view is made later and dated earlier. History is not rewritten.

## 3. Baseline and result

Measured on Windows 11, Python 3.13.15, `.venv-desk`, with no `.env` in the folder.

**Before**, on a clean checkout of `origin/main` at `12b1711` (2026-11-21):

| Command | As AGENTS.md wrote it | With `-X utf8`, as the README wrote it for Windows |
|---|---|---|
| `python -m unittest discover -s tests` | 443 run, **13 errors**, 4 skipped | 443 run, 0 failures, 4 skipped |
| `python -m unittest discover -s hooks/tests` | 74 run, **31 errors** | 74 run, 0 failures |
| `python -m unittest discover -s skills/spinoff-worksheet/tests` | 38 run, 0 failures | 38 run, 0 failures |
| `python -m unittest discover -s skills/us-spinoff-seeker/tests` | 103 run, 0 failures | 103 run, 0 failures |
| `python live_record.py --offline --no-save` | exit 0, 2 of 4 weeks | exit 0, same output |

- 658 tests in four folders; 663 at `140c4b3`, once the LSEG session check was merged.
- The 44 errors were all `UnicodeDecodeError` or `UnicodeEncodeError`: files read or written with no
  `encoding=`, so Windows used cp1252. `-X utf8` hid this; it did not fix it.
- The required command ran 448 of the 663 tests. It did not run `hooks/tests` or either `skills/*/tests`
  folder, and it skipped the two seeded checks in `tests/` (their names do not start with `test`).
- The four skipped tests create a symlink, which Windows allows only with Developer Mode or administrator
  rights.

**After**, on this branch (2026-11-22), one command, no `-X utf8`:

| Check of `python check_all.py` | Result |
|---|---|
| `tests` | 713 tests, 4 skipped |
| `hooks/tests` | 74 tests |
| `skills/spinoff-worksheet/tests` | 38 tests |
| `skills/us-spinoff-seeker/tests` | 103 tests |
| seeded check `tests/desk_tool_smoke.py` | ran |
| seeded check `tests/desk_all_roles_smoke.py` | ran |
| `live_record.py --offline --no-save` | ran, 2 of 4 weeks, as before |
| `check_public.py` | nothing private in what git tracks or would add |

928 tests, 265 more than before, in 17 new test files. On 2026-11-22 the same command was run in a
fresh clone of `origin/main` at `140c4b3`, with the audit's first commit applied and a new `.venv-desk` made
from `requirements-pipeline.txt` and `constraints-pipeline.txt` (`pip check`: no broken requirements), with no
`.env` in the folder: 839 tests, every check passed. The fixes after the review were checked in a worktree
with the first `.venv-desk`, not in a second fresh clone.

**Replays on real saved data** (2026-11-22, no network, no model). The practice runs of 2026-11-19 and
2026-11-20 saved the SEC pages they read and every reply their models gave. They are not in the repository
(`runs/practice/` is ignored), so these are measurements, not tests; each form they showed is in a test on
made-up data.

| Replay | Result |
|---|---|
| The seven data steps, old code and new, on the saved pages of one Lowe's run and one Walmart run | All seven steps ran in both. Every amount, ratio and quarter figure is the same. What differs: each prior-year value now cites the 10-K the desk read, not last year's (N2); the filings carry the exhibit's label (X1); a footnote mark is gone from one row's label |
| 17 replies of the three analyst roles, from three runs, through the old ledger and the new | The same errors for every reply, and the replies the old ledger accepted are rendered to the same text, line for line. The first form of two new rules refused honest sentences in them (a claim in parentheses; "percent" after a bare table cell): 18 errors the old ledger did not give. Both rules were loosened, test first |
| 548 reasons and corrections the Verifier wrote, against the audit's first one-line rule (C5) | None refused. The rule no longer refuses: a reason is put on one line |
| After the review's fixes: the same two data-step replays and the 17 replies again, and 20 saved reports through the page | The data steps give the same values as the first commit. The ledger gives the same errors and the same rendered text as the code before the audit; one real Walmart reply that typed "billion" after a number, where the filing prints "billion" on the next saved line, passes again. All 20 reports are rendered the same as by the first commit |
| The Strategy Manager's and the Verifier's stages as a whole | Not replayed: the saved drafts were rendered by the code of their day, and old and new code alike answer "rendering differs" |

## 4. Findings

"Fixed" means: reproduced with a failing test on made-up data, fixed at the cause, and every check passing
after. "Open" means found and not fixed, with the reason. Line numbers are those of `origin/main` at
`12b1711`, before any change. Severity: critical = a wrong number or licensed data can reach a public
report; high = a run is lost or a check does not check; medium and low = the rest.

### Fixed

| ID | Severity | Class | Where | Evidence: what was wrong | The fix | Test | Status |
|---|---|---|---|---|---|---|---|
| Q1 | critical | layout | `equity_research_desk.py` step 6; `desk_role_contracts.py` `core_claims_table` | On made-up release tables: a loss in parentheses or with a minus sign made the year-ago EPS the quarter's; three dated columns gave the prior quarter; two change columns gave a growth of 900%; "Revenue from services" was read as total revenue; EPS from continuing operations was read as the quarter's EPS; "Aug 30, 2026" raised `ValueError` and stopped the run; a table in billions ("18.5") was printed as "18". Three of the four readers had no test | One `row_amounts` for every reader (signs kept, a dash keeps its column, percentages left out); a row is read only with one amount for each period column; columns chosen by date; non-GAAP tables, headings and rows refused; a table that cannot be read is skipped. Two readers replace four. The saved Lowe's and Walmart releases give the same figures as before | `tests/test_quarter_readers.py` (22) | fixed |
| N1 | critical | one desk | `equity_research_desk.py` `compile_facts` | Nothing checked that EDGAR's company facts were those of the 10-K the first line names. The base desk had the rule (DL 14); the group desk did not, so a 10-K filed days ago could be reported with last year's eight annual claims. A filer with no revenue under the desk's tags stopped the run | `desk_rules.annual_problem`, shared by both desks; no annual fact is stated, each says why, the claims table prints the reason, the run goes on | `tests/test_annual_facts.py` | fixed |
| N2 | high | formula | `equity_research_desk.py` `get_fy_fact` | Last year's value came from last year's 10-K. The checklist computes growth "from the two years in the same filing"; a restated comparative made claims 2 and 6 differ from the 10-K | The prior value is the row of the same accession, 350 to 380 days earlier; none is stated without one. On the saved Lowe's facts every prior value now comes from the 10-K itself, with the same amounts | `tests/test_annual_facts.py` | fixed |
| X1 | critical | one desk | `equity_research_desk.py` step 2 | The release was the first index file matching "99.1": a slide deck in 99.1 was read as the release, and when the newest earnings 8-K typed its exhibit "EX-99" the desk went back, without a word, to last quarter's 8-K, whose Accepted time set the price and the live-record window. The sort key was a field the rows do not have | `desk_rules.release_among` and `exhibit_99_label`, shared by both desks; the newest Item 2.02 8-K only, found from EDGAR's item list; an 8-K with no Exhibit 99 stops with its accession; the first line prints the exhibit's real number | `tests/test_release_exhibit.py` (7) | fixed |
| H4 | high | a company's wording as a rule | `equity_research_desk.py:907-925` | Step 6 turned one release's sentence, "non-recurring benefit of $X per diluted share", into a metric named for a fourth quarter and a refund, divided by the annual EPS, whatever the quarter was | Removed | `tests/test_one_rule_one_place.py` | fixed |
| L1 | critical | public | `worksheet.py:462`, `:512-518`; `desk_sources.py:130-138`; `hooks/worksheet_format.py:321-423`; `.gitignore` | With LSEG Workspace open, every run asked for a year of daily closes and volumes, saved the rows in `sources/prices/` and in the worksheet's JSON, and printed the last 60 days in the worksheet, so in `final_report.md`. A `--live` run commits its folder. No practice run showed it: Workspace was closed each time | A member's decision of 2026-11-22: the report prints the result only. The rows are written to `sources/licensed/`, which git ignores; the worksheet names the file's hash and date range; the hook reads the rows there, and in a copy without them accepts the line only under a saved PASS for the same bytes | `skills/spinoff-worksheet/tests/test_worksheet.py`, `tests/test_joined_desk.py`, `tests/test_check_public.py`, `tests/test_whole_desk.py` | fixed |
| G1 | high | public | new `check_public.py` | Nothing checked what was about to go public | Fails on a key, a value of `.env`, a `.env` file, a data file, a saved list of closes, the worksheet's "Liquidity day" rows, or a home-folder path, in what git tracks or would add. Prints names, never values | `tests/test_check_public.py` | fixed |
| G2 | medium | public | `equity_research_agent_team.py`, `worksheet.py` | Three saved files of a run held the member's home-folder path | Names, not paths | `tests/test_run_control.py` | fixed |
| H2 | high | docs | `desk_hook.py:286-292` `compose`; `desk.py:139` | `final_report.md`, the public file of a live run, had the course footer in its middle and the worksheet after it | The final report ends with the three lines, naming the tools and the model; the line is saved with the run, so a replay on another computer writes the same | `tests/test_run_control.py` | fixed |
| C1 | critical | code changes a number | `desk_claims.py:169-196` | Any "$" value cited in an Item under "(amounts in millions...)" got "million": "$1.16 million" for a dividend, "$20 million" for an hourly wage | The scale goes only on whole dollars with a thousands separator; a per-share or per-hour amount keeps its unit; anything else in doubt is refused with the reason | `tests/test_ledger_gaps.py` | fixed |
| C2 | critical | layout | `desk_claims.py:34` | "(in millions, ...)", the wording of both saved live filers, was not read: "$93,900" was printed bare | The header is read in both wordings | `tests/test_ledger_gaps.py` | fixed |
| C3 | critical | model text | `desk_claims.py:384-400` | A scale, a sign or a multiplier typed next to a placeholder passed: "$9,200 [cited] billion", "-$4.1 billion", "twice $4.1 billion" | Refused; the claim's own value must hold its scale and sign. A rate typed after a bare table cell ("32.95 [cited] percent of sales") and a claim in parentheses are not refused: a real model's replies hold both, and the first form of this fix refused them (section 3, the replays). Whether the label fits the cell is C8 | `tests/test_ledger_gaps.py` | fixed |
| C4 | critical | model text | `desk_claims.py:64-65`, `:395` | Spelled and non-ASCII numbers passed with no claim: "eleven per cent", "two bn", superscripts, fractions, Roman numerals | Refused. The first form also refused every multiplier in words ("doubled", "twice", "twofold"), and with them "double taxation", "a third party" and three real Verifier reasons: the review found it, and such a word alone is no longer refused (V23) | `tests/test_ledger_gaps.py` | fixed |
| C5 | critical | model text | `desk_role_contracts.py:288-295` | A Verifier reason with line breaks published free text and a heading in `verified_report.md`, outside the marks table | A reason or correction is put on one line, and the table writes it into one cell. The first form refused such a reply, which could stop a run at its last model stage (V25) | `tests/test_published_report.py` | fixed |
| C6 | high | a negative read as a positive | `desk_claims.py:105` | "(1,234)" and an en-dash minus were accepted as "1,234" and "0.4" | A value cannot be cut out of its parentheses or from behind a dash | `tests/test_ledger_gaps.py` | fixed |
| C7 | high | model text | `desk_role_contracts.py:240-262` | A number the Verifier marked wrong was left out of its own part and printed two parts later through the Advisor's reference to it; a reference could point at a draft the Manager sent back | A line that repeats a flagged claim, or a claim whose author has since changed its value, is left out and listed | `tests/test_published_report.py` | fixed |
| C10 | high | model text | `desk_claims.py` `check` | A typed citation ("[10-K.txt:L999]") was never checked; a draft could hold a table that reads as the desk's own claims table or marks table | Both refused; a role's own numbered heading still passes | `tests/test_ledger_gaps.py` | fixed |
| C11 | high | model text | `desk_claims.py:386-394`, `:108` | A reference followed by a scale passed as text ("Sales of Item 12 million", "Insiders filed Form 4 billion", "Debt rose from 2019 bn"); "9999-99-99" passed as a date; "5.2" could be cut from "5.2 per cent" | A reference followed by a scale or a rate is an amount; a date must be a date; "per cent", "bp" and "points" are units | `tests/test_ledger_gaps.py` | fixed |
| M1 | high | network | `equity_research_agent_team.py`, `worksheet.py` | Two copies of the retry rule that disagreed. Neither tried a rate limit (429) again. The team's copy read only `status_code`, so Google's "model is overloaded" (its errors carry `code`) ended a run | `model_calls.py`, one rule for both: 429 after 60 seconds, a dropped connection or a server error after 30, once | `tests/test_model_calls.py` | fixed |
| M2 | high | network | the same two files | No time limit on a request to an Anthropic or a Google model: a stalled call hung the run for good | 600 seconds for a request where the client takes a limit, and each role call under `within_time_limit` (20 minutes) | `tests/test_model_calls.py` | fixed |
| M3 | high | network | `desk_sources.py` `Sources.response` | One 429, 503 or dropped connection from SEC EDGAR ended a run; the seeker's own back-off was replaced by this fetch | Up to three requests for a page, 2 and 8 seconds apart or SEC's Retry-After, each with the User-Agent and the spacing; a 403 says to fix `SEC_USER_AGENT` | `tests/test_setup_checks.py`, `tests/test_sources_requests.py` | fixed |
| M4 | high | setting | `check_pipeline.py`, `desk_parts.py`, `desk.py` | The setup check printed "ok" for the README's own example lines, for an Anthropic key with an OpenAI model, and for a model with no provider. The run found out at its first model call, after the data steps | `check_pipeline.settings_problems`, also run as the desk's first step | `tests/test_setup_checks.py` | fixed |
| M5 | high | setting | `worksheet.py` `judge_once` | A Claude model took `ANTHROPIC_API_KEY` from the shell before the team's `API_KEY`: one run on two accounts. A refusal printed only "400 Client Error" and saved nothing | `API_KEY` only; the provider's own message in the error, and the answer saved | `tests/test_model_calls.py` | fixed |
| M6 | medium | setting | `equity_research_agent_team.py` `Runtime` | With no `MODEL` line the team ran on a Gemini model, whatever the key | No default; the error names `MODEL` | `tests/test_model_calls.py` | fixed |
| M7 | high | Windows | `desk_claims.py` `parse_response` | A reply whose draft used CR LF passed the checks, was saved, read back with doubled line ends, and stopped the run at the hook | Line ends made one kind when the reply is parsed | `tests/test_model_calls.py` | fixed |
| M8 | medium | setting | `check_pipeline.py`, `desk_parts.py`, `desk.py` | A `.env` that Windows PowerShell wrote as UTF-16 stopped the group desk with a traceback | The message names the cause and the cure. The first fix reached the setup check only: `desk.py` itself still printed the codec error and left an empty run folder (V16) | `tests/test_one_rule_one_place.py`, `tests/test_run_control.py` | fixed |
| M9 | high | setting | `desk_error_review.py:670-680`; `lab03_app.py:40-46`, `:280` | The error review's `--model` replaced `anthropic/MODEL` with another model without a word, and sent an OpenAI key to Anthropic | The model written with its provider is the model used; an OpenAI key or model is refused before any request | `tests/test_one_rule_one_place.py` | fixed |
| R1 | high | no way back | `desk.py` | A failure in the worksheet's model call, the last of a run, threw away the finished, paid-for team report | `desk.py --resume RUN`, for a stop in the worksheet or the final report; saved files are checked against their hashes first; the view keeps its first time | `tests/test_run_control.py` | fixed |
| R2 | medium | a name given too early | `desk.py:138-141` | `final_report.md` was written, then checked, and stayed when the check failed | A final report that fails its check is renamed `final_report.rejected.md` | `tests/test_run_control.py` | fixed |
| R3 | high | the record counts a failed run | `live_record.py:128-158` | It never read `desk_run.json`: the report of a failed or killed run was read as a live report | The run's state is read. A run stopped after its team report was checked is listed with a note; one stopped earlier is a problem row | `tests/test_run_control.py` | fixed |
| R4 | medium | a stopped run looks alive | `desk.py:90` | Ctrl+C left `desk_run.json` at "running" for good; nothing named the part; `--replay` refused the folder | The part in progress is saved before it runs; Ctrl+C records "stopped" and the part; the command ends with 130 | `tests/test_run_control.py` | fixed |
| R5 | low | docs | `desk.py` `main` | The line that says how to resume named `python`, which on a member's computer is often not the desk's environment, and the folder's whole path | It names the Python that ran the desk and the folder as typed from the repository; it is printed after Ctrl+C too | `tests/test_run_control.py` | fixed |
| D2 | medium | one desk | `hit_rate.py:39`, `:68` | The hit-rate table did not read `final_report.md`, passed no CIK, and read its closes under other setting names than `.env.example` gives | It reads the reports `live_record.py` reads and passes the CIK; `closes.py` reads `LSEG_CLOSES_FILE` too | `tests/test_one_rule_one_place.py` | fixed |
| D3 | high, base desk | a package the file does not list | `closes.py:98`; `requirements.txt` | With `LSEG_APP_KEY` set, the base desk's price step imported `dotenv`, which `requirements.txt` did not list, and stopped with a traceback | The package is listed; without it the step goes on with no price and says what to install | `tests/test_one_rule_one_place.py` | fixed |
| D5 | medium | a second writer of the first line | `desk_sources.py:148-152` | A fallback first line with no CIK, exhibit or Accepted time, which `live_record.py` cannot read | Removed; a verified report without the line makes no final report | `tests/test_one_rule_one_place.py` | fixed |
| P1 | high | the page | `page.py:178-183` | A report's link or image became live markup: `javascript:` and `data:` links, images fetched from any host | Images become their text; only http and https links stay | `tests/test_page_findings.py` | fixed |
| P2 | high | the page | `page.py:178-183` | `2*3*4` was displayed as 234 | A single `*` is shown as typed | `tests/test_page_findings.py` | fixed |
| P3 | medium | the page | `page.py:180` | A report that is not UTF-8 dropped the connection, and the page kept the previous report under the new name | It gets an answer | `tests/test_page_findings.py` | fixed |
| P4 | high | the page | `page.py:146-153`, `:132-133`, `:79-81` | A network (UNC) path in the address reached the filesystem, so a website could make this computer contact a host | Refused before any filesystem call | `tests/test_page_findings.py` | fixed |
| P5 | low | the page | `page.py:154-159` | `/report` served drafts that never passed the audit | Only verified reports and complete final reports | `tests/test_page_findings.py` | fixed |
| P6 | medium | the page | `page.py:412-419`, `:607-611` | The setup banner said "passed" when the setup check itself crashed | A crash is shown as a FIX line; the banner reads the result | `tests/test_page_findings.py` | fixed |
| P7 | medium | Windows | `page.py:708-713` | On Windows two page processes shared one port | The port is taken exclusively | `tests/test_page_findings.py` | fixed |
| P8 | medium | the page | `page.py:38`, `:136-140`; `desk.py:234` | The form accepted impossible filing times; the desk refused them only in the team part | Refused by the form and by `--filed` | `tests/test_page_findings.py` | fixed |
| P9a | low | the page | `page.py:289-293` | `/stop` answered "stopped: true" for a run that had ended | True only for a run that was going | `tests/test_page_findings.py` | fixed |
| P10 | medium | the page | `page.py:194-210` | GET routes had no origin check: a website could start setup subprocesses | Origin and `Sec-Fetch-Site` are checked on GET too. The page itself still opens from a link on another website (the README on GitHub shows its address as one): the first form of this fix refused that click | `tests/test_page_findings.py` | fixed |
| P11 | low | the page | `page.py:113`, `:117` | JSON `null` and `true` became the tickers NONE and TRUE | String fields only | `tests/test_page_findings.py` | fixed |
| P12 | low | the page | `page.py:266-270`, `:297-315` | Deeply nested JSON got no answer; a wrong length blocked a thread | A length limit, a time limit, an answer | `tests/test_page_findings.py` | fixed |
| P13 | medium | the page | `page.py:183` | A table row with more cells than its header was cut, and the cells left stood under the wrong headings | Such a table is shown as text | `tests/test_page_findings.py` | fixed |
| F1 | high | Windows | 341 calls in 45 files | Text read and written with no `encoding=`. The required check failed on Windows as AGENTS.md wrote it | `encoding="utf-8"` at every call | `tests/test_text_encoding.py` reads every file's syntax tree and fails on the next one | fixed |
| F2 | high | weak test | `AGENTS.md` | `discover -s tests` ran 448 of 663 tests and neither seeded check | `check_all.py`: four folders, two seeded checks, the offline live record and `check_public.py`. A test fails when a test folder or a seeded check is not in it | `tests/test_check_public.py` | fixed |
| T1 | high | weak test | `equity_research_desk.py` `step5` | 20 of 21 deliberate changes to the group desk's formulas passed every test: the formula tests were the base desk's | A test for each formula of the eleven claims, on made-up company facts | `tests/test_group_formulas.py` (11) | fixed |
| T2 | medium | weak test | `closes_reader.py:258` | The rule behind the price had no test | Tests of the rule as it is today, including a filing at 16:00:00 exactly | `tests/test_last_close_before.py` (5) | fixed |
| T3 | medium | weak test | `desk_sources.py` | Nothing tested the User-Agent header, the spacing, https only, or the refusal of a redirect off SEC's hosts | Tests | `tests/test_sources_requests.py` (6) | fixed |
| T4 | high | weak test | the whole desk | No test ran the desk from a ticker to its final report | One run on made-up SEC pages and a stand-in model: all 11 claims, the footer, no licensed rows, a replay, and `check_public` on the folder | `tests/test_whole_desk.py` | fixed |
| T5 | low | weak test | `desk.py` `main` | No test held the ticker pattern | Tests | `tests/test_run_control.py` | fixed |
| F3 | low | docs | `README.md`, `docs/group-pipeline.md`, `docs/lseg-setup.md`, `.env.example`, `AGENTS.md`, `manual.md` | Test counts and the required command; three install lines without the constraints file; "refresh a screen first" for a fresh checkout; "every line must say ok"; "the reader reads LSEG only"; a default model that no longer exists; settings the code reads and no document named | Corrected, and the stops a member can now see are in the README's table | read against the code; no test | fixed |

### Found by an independent review of the first commit, and fixed

On 2026-11-22, after the audit was committed as `086a312`, six reviewers read the commit, one part each, with
no share in writing it. Each had to prove a finding on made-up data. They returned 50 findings. Every one was
reproduced again before any change, and each fix has a test that failed first. "Regression" means the code
before the audit was right and the audit made it wrong. Line numbers are those of `086a312`.

| ID | Severity | Class | Where | Evidence: what was wrong | The fix | Test | Status |
|---|---|---|---|---|---|---|---|
| V1 | critical, regression | layout | `equity_research_desk.py:104-112` `row_amounts` | A negative change is printed "(5" then ")%". Only a next cell that starts with "%" marked a percentage, so "(5" was an amount, the row held one too many and was dropped, and another row was published in its place: a part of revenue for total revenues, a count of shares for EPS | A percent sign behind a closing parenthesis marks a percentage too | `tests/test_quarter_layouts.py` | fixed |
| V2 | high, regression | layout | `:86`, `:284-295`, `:843` | The four pieces of text above a table were its "title": a GAAP statement under a paragraph that says "outlook", "guidance" or "non-GAAP", under the footnote of the table before, or with a title line "amounts adjusted for the stock split", was skipped, and the quarter's three claims were missing | A title is read by block of the page, up to eight lines, in order; a sentence or a footnote ends it; "adjusted for" is not "adjusted results" | `tests/test_quarter_layouts.py` | fixed |
| V3 | high | layout | `:284-295`, `:841-853` | A non-GAAP statement was read as GAAP when its title was a row of its own table, five lines above it, or cut in pieces by bold tags; a section "Non-GAAP" inside a table was read too. The code before the audit did the same | A table's own title rows are read; rows under a heading "Non-GAAP" or "Adjusted" are skipped until a heading says GAAP | `tests/test_quarter_layouts.py` | fixed |
| V4 | high | layout | `:90-91`, `:228-232` | "Shares used in computing net income per share:" says "per share", so its rows "Basic" and "Diluted", a count of shares, were published as GAAP diluted EPS ("$204"). The code before the audit did the same | A heading that counts shares heads no EPS; labels that end with "diluted" and loss-per-share labels are read | `tests/test_quarter_layouts.py` | fixed |
| V5 | high | layout | `:206` | Two change columns ("% Change", "% Change in Constant Currency") made the reader pair each amount with a percentage: last year's revenue became 11.1 and growth 8,909%. The code before the audit did the same | Only a share-of-sales column pairs; a change column never does | `tests/test_quarter_layouts.py` | fixed |
| V6 | medium | a reader that guesses | `:916-938` | With no table read, a fallback stated the first amount after "Diluted net income per common share": last year's when the older column stands first, the nine months' when that group does | Removed: no table read, no figure | `tests/test_quarter_layouts.py` | fixed |
| V7 | medium | layout | `:304-306` | One row's own unit, "Weighted average shares (in thousands)", was printed as the unit of the whole table. The first fix then lost a unit printed beside the years, which a replay of a saved release showed | The unit is read from the table's title rows, down to the row of periods, then from the lines above | `tests/test_quarter_layouts.py` | fixed |
| V8 | medium, regression | layout | `release.py:24`, `desk_rules.py:53-66` | A release whose statement is titled "Statement of Results of Operations" did not count as holding an income statement, and a slide deck in the next exhibit with a slide "Income Statement" was read as the release | That title is known | `tests/test_release_exhibit.py` | fixed |
| V9 | low | weak test | `tests/test_annual_facts.py`, `tests/test_release_exhibit.py` | The test of a 53-week year used a 52-week year; nothing held the lower bound of "a year earlier", the 10-K's year end taken from EDGAR's list, or the file type of an exhibit | Tests. Each bound was then broken on purpose and a test failed | the same files | fixed |
| V10 | high, regression | network | `model_calls.py:44-84`, `equity_research_agent_team.py:279-294` | The desk's own time limit raised `TimeoutError`, which the retry rule read as a dropped connection: a role past twenty minutes was called a second time, for twenty more, while the first call was still running and still reading the role's files | The limit raises `TimeLimitPassed`, which is never tried again | `tests/test_model_calls.py` | fixed |
| V11 | medium | Windows | `.gitattributes`, `desk.py:242-244`, `hooks/worksheet_format.py:358-371` | A run seals the hash of every file. On Windows the desk writes CR LF, and git stored LF: a clone of a live run held other bytes than the run sealed, so `--replay` and the hook's recheck failed there at the first file. A saved SEC page with CR LF had the same fate on any computer | The desk's run folders are stored byte for byte (`-text`); the two graded records keep the old rule | `tests/test_run_control.py` | fixed |
| V12 | medium | network | `desk_sources.py:114-121`, `model_calls.py:50` | A page cut off while it was read was not asked for again; a `Retry-After` of "¹" ended the run; a refusal for lack of credit that comes as HTTP 429 was tried again | Each fixed; the documents say the wait is at most a minute | `tests/test_setup_checks.py`, `tests/test_model_calls.py` | fixed |
| V13 | high, regression | no way back | `desk.py:293-312` | A second `--resume` was refused for the files the first had set aside; a resume that could not start left the run "running" with files moved; an edited `view.json` was published, because only the parts' records were checked; a stop in the final report called the worksheet's model again | The whole folder as the stop sealed it is checked, the view with it; nothing changes before the settings are ready; the folder is sealed again; a finished worksheet is kept | `tests/test_run_control.py` | fixed |
| V14 | medium, regression | docs | `desk.py:87-90`, `:306-309` | After a resume on another model the footer still named the first model for the worksheet's judgment | The run saves its model; a resume on another names both | `tests/test_run_control.py` | fixed |
| V15 | medium, regression | setting | `check_pipeline.py:16`, `:42-59` | The setup check looked for "fill" and "paste" anywhere in a value: a member named Fillmore or Pasternak was told to write a name and email on every run. It passed `anthropic/MODEL_ID`, a key that is only "sk-ant-", and "@" for a name and email. An empty value in the terminal hid the one in `.env` | Whole example phrases; a model after its provider; a key longer than its start; a name and an email; one reading order | `tests/test_setup_checks.py` | fixed |
| V16 | medium | setting | `desk.py:58-81` | A UTF-16 `.env` still stopped `desk.py` with "'utf-8' codec can't decode byte 0xff" and left an empty run folder, in `runs/live` with `--live`. The audit had listed this as fixed (M8) | The same message as the setup check's, before any folder is made | `tests/test_run_control.py` | fixed |
| V17 | medium | public | `check_public.py:27-33`, `:65-95` | The scan knew one shape of a list of closes; a series keyed by date, pandas' forms, another column name, a `.jsonl`, a `.tsv` and a Markdown table passed. A file that was not UTF-8 was skipped whole, a key in it unseen. A web address with `/home/` and a long dashed name were called a home path and a key | Each shape, any encoding, and the two false alarms; the docstring says other shapes are not seen | `tests/test_check_public.py` | fixed |
| V18 | low | the record counts a failed run | `live_record.py:135-139` | A `desk_run.json` that could not be read was taken for "no state", so a failed run's report became a row | A state file that is there and cannot be read is a problem row | `tests/test_run_control.py` | fixed |
| V19 | medium, regression | the page | `page.py:163` | A repository on a network drive has a path that starts with two backslashes. The page refused every such path, its own included: it listed no run of the desk and called a finished run stopped | A network path is refused unless it is the repository's own | `tests/test_page_findings.py` | fixed |
| V20 | low | the page | `page.py:136-137`, `:207-229` | An image vanished with its words; a star inside code gained a backslash; "2**3**4" was shown as 234; a list written with stars was plain lines; a table with a short separator still lost cells and a good table with an empty last cell was shown as text; a line "[1]: address" vanished; a numbered list with a gap was renumbered; the registry field still asked the file system about a network path; on port 80 every request was refused; the page inside an editor's preview frame was refused | Tables are judged by the Markdown library's own reader; stars, source lines and list numbers are kept as typed; the rest each fixed | `tests/test_page_findings.py` | fixed |
| V21 | medium | weak test | `page.py:323-327`, `tests/test_page_findings.py` | The page answered an over-long request without reading it, so Windows dropped the connection and the sender sometimes got no answer: the test of it failed about one run in eight, in the required check | The body is read and thrown away before the answer; the nesting and the length limit have tests of their own | `tests/test_page_findings.py` (25 runs of 25) | fixed |
| V22 | high, regression | code changes a number | `desk_claims.py:39`, `:265-268` | The new scale rule published three amounts at a wrong scale: "$43,440 a year ago" bare (read as an amount "a year"), "$1,980" bare after "per diluted share, compared with", and "$4,828 thousand" for millions, because a row's own unit, "Membership cardholders (in thousands)", was taken for the section's header | The per-unit patterns are exact; a header is a header by its place and wording, not any parenthesis | `tests/test_ledger_gaps.py` | fixed |
| V23 | medium, regression | false refusals | `desk_claims.py:48-50`, `:147-148`, `:474` | Honest text was refused: "a third party", "double taxation", "twice in the filing", "Basel III points to", "in 2026 thousands of members", "the core claims above", "CO₂", "the second half {c1}", a percentage in a sentence's parentheses, the upper end of a range written with a dash. "Double-digit" had no way through at all | Multipliers in words are not amounts; the other rules are narrowed. Of 147 honest sentences the first commit refused 50 that the old code accepted; 11 remain, each a typed sign, scale, citation or number in words | `tests/test_ledger_gaps.py` | fixed |
| V24 | medium, regression | false refusals | `desk_claims.py:46` | A scale typed after a claim was refused even where the filing prints it on the next saved line ("approximately $", "99.6", "billion"), which is the only way that scale can reach the reader. A real reply of 2026-11-19 does this | The typed scale passes when it is the first word the filing prints after the number, and only then | `tests/test_ledger_gaps.py` | fixed |
| V25 | low, regression | a stop that no repair covers | `desk_role_contracts.py:142-143` | The one-line rule for a Verifier's reason was a refusal no mend covers: three replies with a line break in a reason stopped the run at its last model stage | The reason is put on one line; the table keeps it in one cell | `tests/test_published_report.py` | fixed |
| V26 | medium | a crash in place of a repair | `desk_role_contracts.py:80`, `:91` | An author's reply with no draft raised `KeyError`, and a Manager's failure whose part is a list raised `TypeError`, out of the check and past every repair. The code before the audit did the same | Both are errors the role is sent back with | `tests/test_published_report.py` | fixed |
| V27 | medium | weak test | several | Rules of the first commit that could be deleted with no test failing: the dash half of C6, the words before a claim, the per-unit exemptions of the scale rule, the time limit on the worksheet's call, the view through a resume, a stopped run's row in the live record, the replay of a stopped run | A test for each | `tests/test_ledger_gaps.py`, `tests/test_model_calls.py`, `tests/test_run_control.py` | fixed |

### Open

| ID | Severity | Class | Where | Evidence: what is wrong | Why it is open | Status |
|---|---|---|---|---|---|---|
| C8 | high | a label the code never checks | `desk_claims.py:344-376` | A correct number can stand under a wrong label. On made-up lines the ledger accepts: "Operating income was $93.9 billion" cited to the net sales line; a prior-year cell as this year's; a peer's fact with no peer named; one claim id under two different sentences; a range built from two table cells when the sentence says "expects" and not "guidance"; "percent" typed after a bare table cell that holds another measure | Checking a label means reading meaning, which is the Verifier's job and a model's. A stricter rule in code (the cited line must hold the sentence's metric word) would refuse honest sentences. A member decides how strict | open, section 6 item 5 |
| C9 | high | model text | `worksheet.py:448`; `hooks/worksheet_numbers.py:37-54` | The worksheet's judgment lines accept a number written in words | The worksheet's method and persona are files no AI writes, and the rule sits beside them. The ledger's word test (`desk_claims.WORD_AMOUNT`) can be reused | open, section 6 item 6 |
| C12 | medium | model text | `desk_claims.py:386-394` | Typed with no source and accepted: a date ("payable 2027-02-15"), a year with a noun ("2010 locations"), a fiscal label ("FY2031"), a clock time, a numbered heading ("45. That is the operating margin, in percent") | A role must be able to write dates, years and numbered lists. The cure is to check each against the dates and periods the run saved, which is a new rule and needs a real run to tune | open |
| C13 | medium | model text | `desk_claims.py:503-529`, `:560-573` | When repairs run out, the failing line is dropped; a line below it can lose its qualifier ("the figures below are for the prior year") | Dropping the whole paragraph loses more good claims; a team choice between the two | open |
| C14 | medium | model text | `desk_hook.py:54-61`, `:104-112` | The hook's own number check lets the same masked forms through. It is the gate only for a run with no `team_report.json`; the ledger is the gate otherwise | Not on the group desk's path | open |
| D1 | medium | one rule, several copies | `closes_reader.py:258`; `view_record.py:23`; `hooks/worksheet_format.py:354`; `worksheet.py:276` | The desk's price takes every session to close at 16:00 Eastern; the hit-rate table uses the exchange's calendar. On a half day a release accepted between 13:00 and 16:00 gets the close of the day before | The worksheet and its hook hold the same 16:00 rule: changing one makes them disagree. All four must change together, with a real close to check. The limit is in the README | open, section 6 item 2 |
| D4 | low | two readers of `.env` | `lab02_desk.py:32-63` and python-dotenv | An inline comment and `${NAME}` are read differently by the two desks | Low; the base desk's reader is in three programs | open |
| D8 | low | docs | `check_env.py:81-86` | With `LSEG_APP_KEY` set and no `lseg-data` in the calling Python, the base desk's setup check prints FIX and an unpinned install line, though the reader uses the `.venv-lseg` worker | Base desk only | open |
| P9b | low | a stopped run looks alive | `page.py:289-293` | On Windows the page's Stop ends the desk at once, so the folder still says "running". The part it was in is saved, `--resume` and the live record read it, and `--replay` says the run was killed there | Marking the folder from the page needs the page to know the run's folder before the run ends | open |
| T6 | low | weak test | `desk_claims.py` `with_repairs` | The re-check of a reply after its failing lines are cut has no test of its own | Covered only through the seeded role tests | open |
| B1 | high, base desk | network | `lab03_app.py:327-336`; `team.py` | The base desk has no retry and no saved record of a stop (the Week 4 failure). A fix is on the unmerged branch `stopped-run-record` | The group desk is the live path now; merging the branch is a member's call | open, section 6 item 8 |
| B2 | medium, base desk | layout | `lab02_desk.py:678`; `lab03_app.py:815` | The quarter's column is named "the column for 2026" (NVIDIA error 2). A fix is on the unmerged branch `one-desk` | as B1 | open, section 6 item 8 |
| B3 | medium, base desk | setting | `prices.py`; the page | When LSEG does not answer, the price comes from financialdatasets.ai and only the report's second line says so (open since 2026-11-12) | Base desk only; the group desk has no second source | open |
| H3 | medium | docs | `docs/checkpoint-3.md:29-33` | The course footer stood in the middle of the file, with notes after it | A member's checkpoint document. A member finished the page on `main` (`1d94e2a`, 2026-11-22): it ends with the footer | closed by a member |
| S1 | low | docs | `skills/us-spinoff-seeker/SKILL.md:8`, `:12`, `:49`, `:79`; `desk_error_review.py:653-655` | An empty code span where a path was removed; "eight", "five" and "six" factors in one file; `--practice` changes nothing | The skill files came with the copied pipeline and are tracked by hash in `docs/pipeline-import.json` | open |
| X2 | medium | layout | `equity_research_desk.py` step 2 | The quarter's claims (9 to 11) are still not checked against XBRL (known since 2026-11-11, "F2b") | A design the team has not chosen | open |
| W1 | medium | layout | `desk_rules.py` `release_among`, `release.py` `has_income_statement` | An exhibit counts as the release when one short line of it is a statement's title. A slide deck in Exhibit 99.1 with a slide titled "Income Statement", before the release in 99.2, would be read as the release | Telling a statement from its title alone needs the table under it; not built | open |
| W2 | low | network | `model_calls.py` `no_credit` | One provider sends both a rate limit and a used-up quota as 429 with the same words; the desk cannot tell them apart and tries once more after a minute | Costs a minute and one refused call | open |
| W3 | low | the page | `page.py` `literal_stars` | Text in single stars is shown with its stars, not in italics; two saved practice reports have six or seven such places | Chosen: a star between numbers must not vanish | open |
| W4 | low | false refusals | `desk_claims.py` `WORD_AMOUNT` | "A one-two punch" and "a five-member committee" are refused as numbers in words | The first is an idiom; the second is a count with no source | open |
| W5 | low | weak test | `desk_role_contracts.py` `core_claims_table`, `published_sections` | The quarter-growth line of the claims table and the second pass of the left-out rule have no test of their own | Covered only through whole-report tests | open |
| W6 | low | no way back | `desk.py` `resume` | `--resume` has been run only with stand-in parts: with the real worksheet it needs a model call | Needs credit (section 6, item 1) | open |

## 5. What could not be verified

1. **No real model run.** The model account has had no credit since 2026-11-21. Every model call in the
   tests is a stand-in. The replies saved from the real runs of 2026-11-19 and 2026-11-20 pass the tighter
   ledger as they passed the old one (section 3), but those are two companies and one model. Not seen at
   all: the 429 and time-limit rules against a real provider; `--resume` after a real refusal. The last
   whole run of the group desk on a real model was Lowe's on 2026-11-20, before these fixes.
2. **No new SEC EDGAR request by the changed code.** The data steps were run on made-up pages and on the
   pages two practice runs saved (section 3), which give the same figures as before. The rule for the newest 8-K
   (X1) and the facts of the chosen 10-K (N1) have not met a filing they refuse.
3. **No LSEG run.** The liquidity rows (L1) were tested with made-up rows. The rows file, its hash and the
   hook's reading of it have not been seen with Workspace open.
4. **macOS.** Every result is from one Windows 11 computer. The Mac run of the test folders was last done on
   2026-11-21, before this branch.
5. **The page in a browser.** A reviewer opened the page of the first commit in one browser (Chromium), on a
   made-up folder: it loads, the setup banner shows, a report is shown. The form's Run and Stop buttons were
   not clicked there: their requests were sent with the headers that browser sends. Firefox, Safari and a
   Mac were not tried, and the page after the review's fixes was tested through its routes only.
6. **Google and OpenAI keys.** Their error shapes were tested on stand-ins. No such key has run the desk end to end.
7. **The proposed GitHub workflow** (section 7) has never run.
8. **The course site's Week 6, 7 and 8 pages** were placeholders on 2026-11-21, so nothing here was checked
   against them.
9. **Each regression test of section 2** was found by its text, not run alone.

## 6. Needs a team member

In order of what threatens the next live run first.

1. **One practice run on a real model before the live run.** It costs money, and the credit ran out, so the
   audit made none. Add credit, then `.venv-desk\Scripts\python check_pipeline.py`, then
   `.venv-desk\Scripts\python desk.py TICKER` without `--live`. Read what it leaves out: the ledger is
   stricter than on 2026-11-20, though the replies saved that day still pass it. If the worksheet or the
   final report stops, use the `--resume` line it prints. The group desk has no cheap test of the key or
   of the credit: `check_pipeline.py` asks no one, and a run's first model call comes after its data steps.
   A practice run finds an empty account there, as the two runs of 2026-11-21 did, and leaves its failed
   folder in `runs/practice/`; a `--live` run that finds it leaves a failed folder in `runs/live/`. So make the practice run first, on
   the same day.
2. **Do not make the live run on a release accepted between 13:00 and 16:00 Eastern on 2026-11-27 or
   2026-12-24** (the exchange closes at 13:00). The desk would use the close of the day before (D1).
3. **With LSEG Workspace open, look at one run folder before it is committed.** `sources/licensed/` must
   hold the liquidity rows and git must not list it; `python check_public.py` must print ok. This is the
   first run that will have real rows (L1).
4. **Before the push:** `python check_all.py`, then `git status`, then `python check_public.py`.
5. **How strict the ledger should be about labels** (C8). Today a correct number under a wrong label reaches
   the Verifier, which may or may not flag it. The auditing team marks such a claim "unsupported".
6. **Numbers in words in the worksheet's judgment** (C9): whether the worksheet should refuse them as the
   ledger now does.
7. **`manual.md:16`.** The audit changed one sentence of fact there ("It needs a price from LSEG Workspace"
   became "from LSEG Workspace or from a file of closes exported from it"). If the manual's prose is a
   member's own, take the change back or rewrite it.
8. **Three branches are not merged:** `one-desk` (the quarter column's label, base desk), `openai-key`,
   `stopped-run-record` (the base desk's retry and stop record). Merge or close each. Nothing was deleted.
9. **Files no AI writes, where the audit saw something and changed nothing:** `AGENTS.md` rule 5 names
   `roles/` and not `pipeline_roles/`, which the group desk reads; `persona-why-cheap.md`, `spinoff-rules.md`
   and `roles/*.md` have no footer, and a footer there would enter a prompt; `spinoff-rules.md:24` says
   "Placeholder assumption". (`docs/checkpoint-3.md` had its footer in the middle, H3; a member has since
   finished that page.)
10. **Under `runs/live/`, nothing was changed.** Seen there: `runs/live/README.md:20` and `:31` give commands
    with no environment (`desk.py TICKER --live`, `python live_record.py`); the two `audit.md` files have no
    footer; three review files end with another second footer line. Document them the way `AGENTS.md` says.
11. **Where the repository and the course site disagree** (the site was read on 2026-11-21):
    - A run takes 10 to 35 minutes (README); the presentation is 11 minutes with a live run and one retry.
    - The two live reports have no worksheet view under them; Labs 07 and 09 ask for one. The hit-rate table
      can score at most Weeks 6 and 7.
    - `manual.md` is mostly placeholders: the diagram, the joins, the audit counts, the hit-rate table, the
      base rate, "what we will not delegate again", the three-column table, the roles paragraphs. The
      drawing itself is in the repository since 2026-11-22 (`docs/desk-diagram.png`); the manual does not
      show it yet.
    - Closed since the site was read: the README's top had no line that says who joined what under whose
      part. A member added the team's name and the join line on `main` (`1d94e2a`).
    - "A missing claim costs nothing" (`AGENTS.md`) is stronger than the site, which says "Every desk states
      them" and shows the missing count.
    - `audits.md` is an AI draft whose footer says "I verified the sources myself"; it uses "Correct*",
      which is not one of the five marks; its exchange tables are empty. The site says the audits are by hand.
    - No code reads WRDS for the base rate under the hit-rate table.
    - Both live reports took their price from financialdatasets.ai; the site says live closes come from LSEG.
    - `reaction.json` will save two closes in a committed live folder; the site says a list of closes never
      goes in the repository. Two closes may or may not be "a list": ask.
    - `PLAN.md:168` gives Week 6 as Nov 25 to 29; the site says Nov 23 to 29.
12. **History.** Commits before 2026-11-19 hold a teammate's macOS home-folder path in review files. History
    on `main` is not rewritten, so it stays. It shows a login name and folder names, no key.
13. **This file's footer.** It says "I verified the sources myself". A member has to do that before it is
    public: the audit was made by a coding agent, and its checks are the tests named above.

## 7. How to keep this fixed

1. **One command before every change is called done:** `python check_all.py`, in `.venv-desk`. It runs every
   test folder, the two seeded checks, the offline live record and `check_public.py`. A new test folder that
   is not in it fails a test.
2. **One command before every push:** `python check_public.py`. It reads what git tracks or would add.
3. **A rule lives in one file.** A rule both desks need goes in `desk_rules.py`; a rule about model calls in
   `model_calls.py`. Before fixing a rule in one desk, search the other for its copy.
4. **A reader that cannot read refuses.** It returns "not found" with the reason; it never returns its best
   cell. Each new layout gets a made-up table in `tests/test_quarter_readers.py`.
5. **A test must be able to fail.** After writing one, change the code it tests and watch it fail. The audit
   found three kinds that could not: a mock in place of the thing tested, a test of the other desk's
   function, and a command that did not run the folder.
6. **Every file is opened with `encoding="utf-8"`.** `tests/test_text_encoding.py` fails on the next call
   without it.
7. **No model text carries a number.** When a new form gets through, add its sentence to
   `tests/test_ledger_gaps.py` first.
8. **Check a setting where the run starts**, not where it is first used (`check_pipeline.settings_problems`).
9. **Nothing licensed in a tracked folder.** A list of closes goes under `sources/licensed/`.
10. **Write what AI got wrong, and how it was caught**, in `docs/decision-log.md`, with the test's name.
11. **Have someone who did not write a fix read it.** The audit's own tests passed, and a review of its
    commit still found 26 defects that had come with it: the tests were sentences and tables the author had
    thought of. A reader with no share in the fix thinks of others.
12. **After changing a reader or the ledger, replay what real runs saved.** The pages and the replies of the
    practice runs are on the computer that made them (`runs/practice/`). The same values and the same
    accepted text as before is the result to look for; a difference is either the fix or a new fault.

**Proposed, not added: checks on every push.** The file below would be `.github/workflows/checks.yml`. It is
not in the repository: adding it creates something on GitHub, which waits for a member's yes. It needs no
key and no secret. It has never run, so the first run has to be watched. `fetch-depth: 0` is there because
the live record reads commit times.

```yaml
name: checks
on:
  push:
    branches: [main]
  pull_request:
jobs:
  checks:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: python -m pip install -r requirements-pipeline.txt -c constraints-pipeline.txt
      - run: python check_all.py
```

A live report goes straight to `main`, so this check runs after the push, not before it. It must never
block one: do not make it a required check on `main`.

**Proposed, not added: git runs the scan before a push.** A `pre-push` hook that calls
`python check_public.py` would make item 2 automatic. It is not added, because a hook that cannot find
Python refuses every push, and a refused push inside a 24-hour window costs a week.

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
