# Decision log

## 2026-11-21: independent LSEG environments for Mac and Windows

- The user requested shared setup, local provisioning, readiness checks, and Windows teammate instructions.
  The NVIDIA practice had confirmed FileNotFoundError for the absent group-local LSEG interpreter.
- Updated requirements-lseg.txt from its old same-environment installation guidance to an isolated
  Python 3.13 worker, pinning the SDK and installed dependencies. Created .venv-lseg on this Mac;
  installation, pip check, SDK import, and timezone import passed. The desk environment was not modified.
- Created a private, ignored group-local .env from the previously authorized credential source, copying
  only SEC_USER_AGENT, API_KEY, MODEL, and LSEG_APP_KEY. No credential values were displayed. Runtime
  commands now use the independent local copy; no runtime path was added to the personal repository.
- Added check_lseg.py: offline executable/import/version/timezone checks by default; --session opens
  and closes a desktop connection without requesting prices. SDK logs and raw errors are not printed.
  The process deadline is 45 seconds. check_pipeline.py reports the optional offline reader readiness.
- The Mac desktop session opened and closed successfully. This is not a price or entitlement test.
- The hit-rate command's legacy closes reader still imported the SDK in the main desk Python. It now
  delegates its unchanged query to the selected LSEG worker when that Python lacks the SDK. Tests
  check the date/source protocol, secret handling, and prevention of recursive worker launches.
  CSV behavior and cached reactions were not changed.
- Windows Python 3.13 binary dependency resolution passed. Windows execution and member-specific
  Workspace access still require each teammate's local validation. docs/lseg-setup.md contains exact
  Mac and Windows commands and notes the distinction between session readiness and price availability.
- Validation on macOS/Python 3.13: main 443, hooks 74, worksheet 38, seeker 103 tests passed (658 total).
  The required live_record.py --offline --no-save check and git diff --check passed. Existing saved
  records, views, and error reports were not changed. No research rerun was launched for this setup.
- AI assistance: OpenAI Codex. No human verification is claimed.


## 2026-11-21: Walmart required reads and guidance endpoints

- User authorized corrections for E-7d2edb79c27e and E-a057b27e8b54 after the Walmart practice stop.
  Original run: runs/practice/WMT_practice_20261121_145335/WMT_2026-11-21_14-53-35.304376.
  No original Walmart artifacts or error reports were changed and no new paid run was launched.
- The model's reasons for skipping the structured outputs and selecting a spending-increase figure
  remain unknown. These corrections address the observed behavior without assuming a hidden cause.
- AssignedFiles still rejects unread or changed files. A dedicated missing-read exception lets the
  caller send the exact omitted filenames back for one correction. Raw replies and read failures
  are saved. Repeated omissions and all other access failures still stop the run.
- Synthetic tests first reproduced rejection of drafts-only access and the absence of recovery.
  A seeded real CrewAI tool loop now reads three drafts, receives feedback, reads the three JSON
  files, and passes the unchanged completeness check. No provider or SEC call is needed.
- Literal citations previously allowed two individually real values to be assembled into a false
  guidance range. Synthetic tests first showed the mixed-endpoint range was accepted. Code now
  requires an explicit guidance pair to occur as a range on the same saved source line. It rejects
  mixed metrics, unrelated same-line values, reversed endpoints, and unsupported inherited claims.
  The existing repair loop can correct the range or omit the failing line. Actual period-to-period
  comparisons outside guidance sentences remain allowed.
- Scope limit: this checks explicit placeholder pairs in guidance/projection/outlook sentences.
  Valid ranges split across source lines may be rejected. It is not a general semantic verifier.
- Validation on macOS/Python 3.13: main 433, hooks 74, worksheet 38, and seeker 103 tests passed.
  The required live_record.py --offline --no-save check and git diff --check passed.
  No real-model rerun was used to claim that every future response will be correct.
- AI assistance for this change: OpenAI Codex. No human source verification is claimed.


## 2026-11-20: remaining Windows portability issues

- The November 19 teammate run documented six remaining Windows test failures. The Mac-only LSEG worker
  default also prevented the Windows helper from launching. This work addresses those compatibility
  issues, without changing financial rules, Verifier policy, or saved runs.
- Symlink security tests still create actual symlinks. Only permission/unsupported-operation errors
  skip those tests. Ordinary secret and excluded-file checks run independently. File and directory
  symlink exclusion remain separate checks.
- Seeded CrewAI child processes and the LSEG worker explicitly use UTF-8 for output. This avoids a
  Windows code-page mismatch between the parent and child.
- Offline test guards permit numeric loopback addresses for local event-loop sockets. Both connect
  and connect_ex reject external addresses and hostnames. Regression checks exercise a real loopback
  socket and event loop, plus blocked synthetic external addresses. No provider call is used.
- The LSEG helper selects this repository's .venv-lseg/Scripts/python.exe on Windows and
  .venv-lseg/bin/python on macOS/Linux. An explicit LSEG_PYTHON still takes precedence. Path-selection
  tests simulate both platforms without an LSEG connection or credential access.
- Validation: main suite 365 passed; hooks 69 passed; worksheet 30 passed; seeker 103 passed.
  The required live_record.py --offline --no-save check and git diff --check passed.
- Validation runs on macOS/Python 3.13 only. A real Windows test run remains necessary; simulated
  Windows path selection does not establish full Windows compatibility. No original run was changed.
- AI assistance for this change: OpenAI Codex. No human verification is claimed.


## 2026-11-19: timestamped predictions and COST practice

- Added a code-owned first prediction record with canonical direction, actual filing acceptance,
  save time, and an explicit close-to-close reaction window. The worksheet report repeats that record.
  Window calculation handles holidays, early closes, and UTC offsets. No historical view was backfilled.
  A failed new ticker run saves `not computed` when it has not produced a prediction.
- Tests establish the save-time clock, report consistency, first-record preservation, unavailable
  filing behavior, and reaction-refresh preservation. Saved reactions record the view hash. The table
  rejects a changed view instead of silently scoring a different prediction.
- The user authorized use of the personal `.env` for this practice. A temporary group copy was used
  without displaying credentials and was removed after each invocation. No personal code was called.
- First COST attempt stopped at the seeker: the bounded screen contained no ranked ticker. The
  limited screen was explicitly partial. It is not evidence that no spinoffs exist. A separate direct
  COST attempt used that saved local registry through the supported command; the first failure remains.
- The direct COST attempt stopped at the team hook after a Verifier rejection of the claim
  `approximately $500 [10-K.txt:L1022]`. The recorded reason is a missing millions-of-dollars unit.
  This is documented as a confirmed process failure and an unconfirmed financial units error.
  No claim, source, verification mark, or failed outcome was repaired.
- The run did not reach the worksheet. Its failed-run view is `not computed`, saved at
  `2026-11-19T16:31:21.623980-05:00`. The filed release was accepted at
  `2026-09-24T16:17:37-04:00`; the first post-filing close was September 25 at 16:00 Eastern.
  The table therefore flags `after` and excludes the run. Reaction lookup returned no prices because
  the closes reader reported that its optional `lseg-data` dependency was missing. That was documented,
  not corrected. The table is not a hit or miss and makes no prediction-accuracy claim.
- Human reports, AI prompts, source evidence, and the hit-rate table are saved with the practice
  attempts under `runs/practice/COST_prediction_check_20261119_162639/`. Original live records remain unchanged.
- **What we will not delegate again.** (the team writes this)

## 2026-11-19: copy the personal pipeline into the group repo

- The user clarified that the group needs independent copies of every component previously reached
  through the personal repo. Copied the joined command, team and Verifier, claim contracts, hook,
  saved-source helpers, closes reader, two skills, and their supporting tests. Source paths and hashes
  are recorded in `docs/pipeline-import.json`. No personal credentials, run results, or registry were copied.
- Copied the existing authored factors, worksheet method, worksheet persona, and pipeline role inputs
  without rewriting them. Tests compare their hashes with the source-copy manifest. The legacy group
  team and role inputs remain intact. New pipeline runs use the separate `pipeline_roles` snapshots.
- Replaced workspace-level skill/helper lookups and personal-repo configuration paths with group-local
  paths. The page and double-click launchers run this repo's `desk.py`. It shows a final report only
  after successful pipeline completion. Failed stages and their evidence remain saved.
- Integration errors caught offline: an edited help string needed different quoting; imported tests
  assumed a real `.env`; a claims test loaded a personal saved-company fixture; a copied smoke helper
  was missing; and a fixture's newly flattened rules path already had a parent directory. Corrected
  the integration and test setup without changing live financial outputs or financial decision rules.
- CrewAI 1.15.34 supports Python below 3.14 and has different Anthropic SDK constraints from the old
  environment. Created `.venv-desk` with Python 3.13 and `requirements-pipeline.txt`; left `.venv` intact.
  The new worksheet's provider limitation and Unix file locks are inherited, not claimed as resolved.
- Added an isolation test that runs the seeded pipeline in a temporary group-only checkout with no
  personal repo or workspace skills. Adapted the hit-rate reader to the copied worksheet's saved view
  schema without changing earlier views. The reviewer reads new failed pipeline status accurately.
- Validation: 346 group/pipeline tests, 103 seeker tests, 29 worksheet tests, and 69 hook tests pass
  (547 total). The CLI path rule was tested before implementation. It prevents command inputs and
  replay/storage paths from crossing the group repository boundary.
- No new real live run was launched. Original Cisco and NVIDIA research artifacts remain unchanged.
  The fact that offline tests pass does not establish a successful real-provider final report.
- **What we will not delegate again.** (the team writes this)

## 2026-11-19: restore repository independence

- Traced the cross-repository page integration to commit `110217d`. That change launched a neighboring
  repo's desk command, used its configuration, and exposed its completed runs through this page.
  The earlier decision-log entry describes the integration. The user explicitly requires separate repos.
- Restored the page to this repository's `team.py`, local setup checks, local report paths, and local
  run arguments. Preserved the Intelligent Review Assistant and its run-local report placement.
- The earlier implementation reused an external joined pipeline instead of keeping this repo independent.
  Repository path inspection and git history exposed the dependency. Tests now check the local subprocess
  target and reject review/report paths outside the repository. No neighboring repository was changed.
- The seeker, worksheet, hook, and full pipeline remain missing from this repo; the page no longer
  presents those external capabilities as available here. Original live records remain unchanged.
- **What we will not delegate again.** (the team writes this)

## 2026-11-19: keep review reports with each live record

- The user changed the location requirement: both the human error report and AI prompt now belong
  directly inside each live run folder. The reviewer appends these files and preserves original research
  artifacts. Existing reports get numbered revisions. Shared findings remain in `docs/error-review-findings`.
- Moved four existing report files without changing their contents. The migration manifest records
  their old and new paths and hashes. Shared findings metadata now points to the moved files. History
  discovery searches the live-run folders recursively and retains old citation aliases.
- NVIDIA lacked an AI companion. Created one from its existing human report, preserving its confirmed
  and unconfirmed classifications. It explicitly states that this was a format conversion, not a new
  factual review. No underlying desk error was repaired.
- A new path test initially compared a resolved macOS temporary path with its unresolved `/var` alias.
  The test now compares resolved paths. Tests cover colocated reports, recursive history, unchanged
  original bytes and timestamps, numbered revisions, and page downloads.
- **What we will not delegate again.** (the team writes this)

## 2026-11-17: intelligent error review

- Built a saved-run review command, one human report, one AI prompt, and shared findings. The installed
  `desk-error-review` skill explains the evidence and classification contract. The page starts a separate
  review and downloads both reports. No review action repairs or reruns the desk.
- AI mistake during implementation: one synthetic wrong-value fixture accidentally contained an
  additional wrong growth calculation. The evaluation reported an apparent false alarm. Inspection
  showed that the second calculation error was real. The fixture now keeps growth consistent to isolate
  value selection. This changed the practice fixture, not any live desk artifact.
- A second initial test assumed a fixed order for model documents. The documents are deliberately
  ordered by relevance. The test now selects the document by its identity instead of list position.
- The Cisco review confirms only the empty saved partner-check field. The valuation assertion and the
  historically reported connection failure remain unconfirmed. The original traceback is unavailable.
  Earlier report statements are leads, not automatically established current errors. The historical
  display failure could not be checked and was not promoted to a confirmed finding.
- Synthetic evaluation and HTTP tests cover calculations, parsing, missing evidence, evidence references,
  classifications, revisions, active-run behavior, downloads, and preservation of original files. The
  evaluation does not measure model semantic accuracy. No original live report or prior error file was changed.
- **What we will not delegate again.** (the team writes this)

## 2026-11-16: hit-rate command and missing view evidence

- The existing saved live report has a run timestamp and an advisor recommendation, but no explicit
  timestamped directional worksheet view. Neither field establishes when a directional view existed.
  `hit_rate.py` reports that view as `not computed`; it does not reconstruct or backdate it.
- The initial environment check used system Python rather than a project virtual environment. Six test
  modules could not import because anthropic, markdown, and langgraph were absent there. Creating `.venv`
  and installing the pinned requirements made all original 160 tests pass. This was an environment
  selection error, not evidence of a live desk calculation failure.
- During implementation, checked that a fixed 4 PM cutoff would misclassify a holiday-week early close.
  The hit-rate command uses an exchange calendar instead. Synthetic tests cover the holiday, early
  close, exact cutoff, future close, missing prices, exclusion rules, and unchanged saved view/reaction.
- Reaction definition used: percentage change from the last official close at or before acceptance to
  the first official close strictly after it. No live report or existing desk error was corrected.
- **What we will not delegate again.** (the team writes this)

What our AI agents got wrong, how we caught it, and what we changed. The product manual's decision log is
written from this file. Add an entry on the day you catch something. Name the filing, so a reader can open it.

The last line of each entry, "What we will not delegate again", is the team's judgment. A team member
writes it, not an AI.

## 2026-11-11: a live probe of the base desk on six companies

We ran the seven data steps, with no model and no price, on six companies that reported in the week of
November 9. Then we ran the full agent team on one of them. Entries 1 to 4 came from that.

### 1. The quarter's revenue came from a guidance table

- **What the desk printed.** For the earnings release in 8-K 0001628280-26-056699 (Applied Materials,
  Exhibit 99.1, accepted 2026-08-13 16:03:36 ET), step 6 chose the row `Total revenue | $10,250 | +/- | $500`
  and printed `Quarter revenue growth = 10,250 / 500 - 1 = 1950.00%`.
- **What the filing says.** That row is in the release's "Business Outlook": the midpoint and the range of
  the next quarter's guidance. The statement of operations in the same exhibit has
  `Revenue | $9,115 | $7,302 | $24,037 | $21,568`, under "Three Months Ended July 26, 2026 | July 27, 2025".
- **How we caught it.** Step 6 prints the lines above the row it chose. The lines said "Business Outlook".
- **Cause.** Step 6 looks for a row that starts with "Total revenue" in the whole release before it looks
  for a row that starts with "Revenue" in the income statement.
- **Status.** Fixed on 2026-11-11 (F2). The desk reads claims 9 to 11 only inside the release's income
  statement, and it chooses the columns by their dates. On this release it now reads
  `Revenue | $9,115 | $7,302 | $24,037 | $21,568` and prints growth of 24.83%. Entry 12 gives the check.
- **What we will not delegate again.** (the team writes this)

### 2. Debt to equity was printed as 0.000 for a company with debt

- **What the desk printed.** For the 10-K 0001049521-26-000045 (Mercury Systems, fiscal year ended
  2026-07-03), step 4 printed `Not found for that fiscal year: long_term_debt, current_debt`, and step 5
  printed `Debt to equity: 0.000`.
- **What the filing says.** The balance sheet in that 10-K has the row `Long-term debt | 441,500 | 591,500`
  (in thousands).
- **How we caught it.** The two printed lines do not agree: step 4 said it found no debt fact, and step 5
  printed a ratio. We then opened the balance sheet.
- **Cause.** Step 5 reads a missing fact as zero. The company tags that row `us-gaap:SecuredLongTermDebt`
  (441,500,000 at 2026-07-03 in its XBRL company facts), and that tag is not in the desk's list.
- **A second case.** The same 0.000 appeared for Sonos (10-K 0001314727-25-000090, fiscal year ended
  2025-09-27). There, the company facts hold no debt liability at that date. The only tags with "Debt" in
  their names are debt securities the company owns, which are assets. The 0.000 may be right, but no fact
  states it, so the desk had no support for it. A search for tags by the word "Debt" would be a new error.
- **Status.** Fixed on 2026-11-11 (F1). For both companies the desk now prints
  `Debt to equity: unavailable (no long-term debt fact at the fiscal year end under the tags the desk reads)`.
  Entry 9 gives the rule and the evidence for it.
- **What we will not delegate again.** (the team writes this)

### 3. The run stopped on a release labelled EX-99

- **What the desk printed.** For 8-K 0001740332-26-000029 (Resideo, accepted 2026-11-10 16:12:00 ET):
  `Desk stopped: Could not locate the 8-K's Exhibit 99.1 in the SEC filing directory.`
- **What the filing says.** The filing's index page lists the release with the type `EX-99`.
- **How we caught it.** The run ended with exit code 1 and no report.
- **Cause.** The desk looks for the label `EX-99.1` only.
- **Status.** Fixed on 2026-11-11 (F3). The desk takes the first Exhibit 99 that holds an income statement.
  On this filing it now reads `rezi-20261003prexhibit99.htm`, and the seven steps finish.
- **What we will not delegate again.** (the team writes this)

### 4. The Verifier marked nine correct numbers wrong or unsupported

- **What the desk printed.** A full run on Cisco (10-K 0000858877-26-000132, release in 8-K
  0000858877-26-000106) ended with `155 numbers: 146 correct, 1 wrong, 8 unsupported`.
- **What we found when we read the nine lines.** The numbers are right. The Verifier is wrong about them:
  - "free cash flow fell 3.92%" was marked wrong. The arithmetic is 12,767.0 / (14,193.0 - 905.0) - 1 =
    -3.92%. The Verifier compared the report's 3.92 with its own -3.92 and did not allow for the word "fell".
  - Six marks are on the change in operating margin (3.51 points = 24.27% - 20.76%) and in net margin
    (2.98 points = 20.95% - 17.97%). The desk's calculator computed them in code, but the report printed
    the calculation with names, not numbers, so the Verifier could not redo it.
  - One mark is on "less than 2%". The model that lists the numbers dropped "less than", and the model
    that checks the line then said the filing does not state "2%".
  - One mark is on a sentence that repeats 3.51.
- **How we caught it.** We opened each flagged line, read the source it quotes, and redid the arithmetic.
- **Why it matters.** A verifier that flags correct numbers costs as much as one that misses wrong ones.
  A reader who trusts the marks would correct a right number.
- **Status.** Fixed on 2026-11-11 (F4). On the same saved report the fixed Verifier marks 150 of 150 numbers
  correct. We also sent the first run's own list of 155 numbers through the fixed code, with no model call:
  154 correct and 1 unsupported. That one is the "less than 2%" line, which needs the model. Asked about
  "less than 2%" and not "2%", the model now answers that the line states it.
- **What we will not delegate again.** (the team writes this)

### 5. The coding agent reported those nine marks as errors before it read them

- **What happened.** Claude Code summarised the same run as "1 wrong, 8 unsupported" numbers that
  "stay in the report", and listed it as a threat to the audit. It had read the counts, not the lines.
- **How we caught it.** The agent read the nine lines for this log and found that the numbers were right.
- **What we changed.** A count of marks is not a finding. Open the lines before you report them.
- **What we will not delegate again.** (the team writes this)

### 6. The README described personas that the files do not contain

- **What happened.** The base desk's README said that each file in `roles/` states a persona in six
  parts. The three analyst files are short lists of rules.
- **How we caught it.** We read the README beside the files.
- **Status.** Open. The course says no AI writes a persona. Each member writes one by hand.
- **What we will not delegate again.** (the team writes this)

## 2026-11-11: setting up this repository

### 7. Two things worked only on the first computer

- **A test needed a folder that a fresh clone does not have.** `tests/test_page.py` wrote into `output/`,
  which the base repository committed and this one ignores. The test now makes the folder.
- **Version ranges gave a stranger different packages.** A fresh install from the base desk's
  `requirements.txt` gave anthropic 2.8.0 and langgraph 1.2.20; the computer the desk was built on had
  2.3.0 and 1.2.19. `requirements.txt` now names the exact versions of a run that ended well.
- **How we caught it.** We ran the tests in the new, empty folder, and we installed the packages into a
  clean virtual environment.
- **What we will not delegate again.** (the team writes this)

### 8. The first clone from GitHub did not install

- **What happened.** After the first push, the coding agent cloned the repository into a deeply nested
  folder and followed the README. The install stopped with `Could not install packages due to an OSError`
  and a hint about Windows Long Path support. Six test files then failed to load.
- **Cause.** One pinned package has a file whose path is 138 characters inside the repository folder.
  Windows allows 260 characters for a whole path. The clone folder's own path was 126 characters.
- **How we caught it.** We followed the README from a clone of the public repository, not from the
  folder the files were written in. In a folder with a 109-character path the same steps worked, and
  all 87 tests passed.
- **What we changed.** The README tells a Windows reader to keep the path short, and names the error.
- **What we will not delegate again.** (the team writes this)

## 2026-11-11: the three fixes before the first live run

### 9. The tag for total long-term debt is not always the total

- **What we planned.** Read long-term debt as the noncurrent part plus the current part, and stop when the
  tag for the total, `LongTermDebt`, does not equal that sum.
- **What real filings show.** Before we wrote the rule, we read the debt facts in the latest 10-K of 17
  companies: the six from entries 1 to 4, and the course's build-out set. Eight report all three tags. In five
  the total equals the two parts. In three it does not: the total is a figure from the debt note, and the two
  parts are the balance sheet's lines. The planned rule would have dropped a correct ratio for those three.
- **The rule now.** The two balance-sheet parts are the amount. A current portion of zero is a fact; a current
  portion that is missing is not zero. The total tag is never taken as the amount. It is used for one thing:
  when it equals the noncurrent part and no current part is reported, there is no current portion.
- **The result on the 17.** Debt to equity is stated for 12 and not stated for 5 (Mercury Systems, Sonos,
  Oracle, Dell, Super Micro). None is read as zero. Each of the five uses tags the desk does not accept, or
  reports one part only. A missing claim costs nothing in the audit; a wrong one fails it.
- **How we caught it.** We looked at real filings before we trusted a rule that sounded right.
- **What we will not delegate again.** (the team writes this)

### 10. The coding agent's memory of a tag's meaning was wrong

- **What happened.** Claude Code planned to accept `SecuredLongTermDebt` as a total that includes the
  current portion. SEC EDGAR's own description of the tag, in the company facts file, says "excluding the
  current portion".
- **How we caught it.** The survey for entry 9 printed EDGAR's description of every tag it found.
- **What we changed.** A tag enters the desk's list from EDGAR's description and from real filings, never
  from what a model remembers.
- **What we will not delegate again.** (the team writes this)

### 11. Found while we checked the fixes, and not fixed

- **EPS from continuing operations.** For the release in 8-K 0001740332-26-000029, the desk reads the row
  "Diluted earnings (loss) per share from continuing operations" as the quarter's diluted EPS. Claim 11 is
  GAAP diluted EPS. For a company with discontinued operations those are two numbers. Fixed with F2
  (entry 12): the desk now reads $0.08, the row for the whole company, not $0.14.
- **A restated number keeps its source whatever the sentence says.** The Verifier lets "fell 3.92%" take
  the source of "-3.92%" on another line. It would let "grew 3.92%" take it too. A known limit.
- **The list of numbers changes between runs.** From the same report, the model that lists the numbers gave
  155 in one run and 150 in the next. Both lists covered the same 68 lines.
- **Rounded inputs.** The desk prints amounts in $ millions with one decimal. For a company that reports in
  thousands, a ratio that a reader redoes from the printed inputs can differ in its last digit. Open.

## 2026-11-11: the quarter's rows (F2)

### 12. The release reader, checked on eight real releases

- **What was wrong.** The desk looked for a revenue row and a "Diluted" row anywhere in the release, and it
  took the first two figures of each row as this quarter and last year's quarter. Entries 1 and 11 are two
  of the errors that this made. A third: for one release it read no EPS at all, because the release prints
  `$ (0.04)` with a space after the dollar sign.
- **The rules now** (`release.py`, with no model). Find the income statement by its heading. Read the
  statement's header: its units, its periods, the date of each column. The quarter is the column with the
  newest date, and last year's quarter is the column one year before it. Read total revenue and diluted EPS
  for the whole company at those two columns. When a rule cannot be met, the claim is not stated, and the
  report gives the reason.
- **The check.** We ran the reader on the saved text of eight real releases: the six companies of the first
  probe, and two more from the course's build-out set. All eight gave the statement's own rows. Three
  changed: growth of 24.83% where the desk had printed 1,950.00%; EPS of $0.08 where it had printed $0.14;
  EPS of $(0.04) where it had found none. One release prints its own change column beside the figures, 58%
  for revenue, and the reader's 57.75% agrees with it.
- **What is still open.** The figures are not yet checked against XBRL (PLAN.md, fix F2b). A layout the
  eight did not have can still be misread, or more likely not read.
- **What we will not delegate again.** (the team writes this)

### 13. A wider loss was offered to the analyst as growth

- **What the code did.** For the Financial Analyst the desk computed "growth" as this year over last year
  minus one, for any last year that was not zero. From the facts of 10-K 0001769628-26-000104, a net loss
  of 1,167.0 after a net loss of 863.0 ($ millions), that rule gives "Net income growth: 35.23%". An analyst
  who copies it writes that net income grew.
- **How we caught it.** By reading `team.py` during the work for entry 12, and then doing the arithmetic on
  a real company's facts. No report had shown it yet.
- **What we changed.** The desk computes no growth rate on a base that is zero or negative, and no share of
  a net loss.
- **What we will not delegate again.** (the team writes this)

## 2026-11-12: the facts of the 10-K the desk chose (F8)

### 14. We planned to stop the run, and chose not to

- **The risk.** Step 2 chooses the latest 10-K. Step 4 takes the newest fiscal year in EDGAR's company facts.
  The two can differ: the facts file can lag a new 10-K, and a filer can move its revenue to a tag the desk
  does not read. The desk printed `MISMATCH` and then wrote another year's numbers under the new 10-K's name.
- **The plan said to stop the run.** The coding agent wrote that line of the plan, and it does not agree with
  the plan's own rule: a run stops only when no report can be made. Here a report can be made. A stopped run
  gives the other team no report, which costs more than eight missing claims.
- **What the desk does now.** When the two fiscal years differ, it states none of the annual facts and none
  of their ratios, and each of those claims gives the reason in the report. The quarter's claims and the rest
  of the report go on. The same happens when the company facts hold no revenue under the tags the desk
  reads; before, that stopped the run. A date on the 10-K's cover within 7 days of the statements' date is
  the same year.
- **How it was checked.** Tests on made-up facts, and one whole run of the team with no annual facts. On
  real data the guard did not fire: for a 10-K filed two days before (accession 0001260221-26-000077),
  EDGAR's facts already held the new year. We found no real case of a lag to test on.
- **Seen on the way, and not fixed.** That same 10-K reports its debt under tags from two families, so debt
  to equity is not computed for it either. One bank ran to the end with six of the eleven claims not stated;
  we did not check its five stated claims against its filings.
- **What we will not delegate again.** (the team writes this)

## 2026-11-12: the rehearsal before the first live run

### 15. A full run on main, and three slips it caught

- **What we ran.** `main` at commit 7cad05f, from the page, on the release in 8-K 0000858877-26-000106. It
  took 308 seconds: six parts and one send-back. The Verifier marked 116 numbers correct, none wrong and
  none unsupported, and left 3 prices unchecked. The eleven core claims are the same as on 2026-11-11.
- **Slip 1: the README did not say to install LSEG's library.** The coding agent dropped that line when it
  rewrote the README. `check_env.py` caught it on `main`: "LSEG_APP_KEY is set, but lseg-data is not
  installed." Now `requirements-lseg.txt` names the version, and the README says when to install it.
- **Slip 2: the first page the coding agent started was the old desk's.** Its tool starts a page from the
  folder the session began in, and that folder holds the individual desk. We caught it by reading the
  server's folder before we pressed Run. A rehearsal on that page would have proved the wrong code.
- **Slip 3: the price did not come from LSEG, and the page did not say why.** LSEG Workspace was not
  running. LSEG's library printed its errors where the page does not show them, and the desk took the close
  from financialdatasets.ai. We saw it only because the report's second line names the source of its price.
  Open: the desk should say so in one clear line.
- **What we will not delegate again.** (the team writes this)

## 2026-11-17: connect Lab 05 to the joined desk

The workspace has two desk pages. The Analyst page already used the joined command.
The Lab 05 page still launched the team alone and read its intermediate report.
The page test now checks the subprocess arguments and the final report path.
A server test checks that the page serves the joined report only after completion.

## 2026-11-19: the group pipeline on Windows, and a practice run

- **What we ran.** One practice run of `desk.py` on a company that released earnings that morning, on
  Windows 11, from `main` at 91ee189, with a member's own `.env`. It did not run until four things were
  found. The run then reached the Verifier and stopped there, as designed.
- **The `.env`.** The pipeline needs `SEC_USER_AGENT`, an Anthropic `API_KEY`, and `MODEL` written as
  `anthropic/` and a Claude model. Without `MODEL` the agent team falls back to a Gemini model, and the
  worksheet accepts only a Claude model. The member's `.env` had no `MODEL` line.
- **What AI got wrong: code that ran only on a Mac.** The seeker and the worksheet hook import `fcntl`,
  which Windows does not have. The seeker is loaded on every run, so no run could start. Run paths were
  written with `str()`, which gives `\` on Windows, and then compared with text that has `/`. So the hook
  skipped its checks of the Verifier's and the roles' outputs on Windows, and gave no error. The tests
  showed both: 17 failures and 15 errors in `tests/`, and two test folders that could not load. We caught
  them by running the tests on the second operating system before the run. The locks now use `msvcrt` on
  Windows, and the paths are written with `.as_posix()`, which gives the same text on a Mac.
- **What AI got wrong: a ticker run that needed the screen.** With `--refresh-screen`, the seeker part
  required a ranked name even when the command named a ticker. The bounded scan found ten registrants and
  could date none, so it ranked none, and the run on the requested ticker stopped. Only `desk.py screen`
  now needs a ranked name. A test covers both cases.
- **The price.** The new reader reads LSEG only. Workspace was closed, and on Windows the reader's helper
  points to a Mac path. The run had no close, so its view would have been "not computed".
- **Open: one flag stops the run.** The Verifier marked 7 of 92 numbers. Three were real errors in the
  roles' text: a projection for the current fiscal year called "next year", and a capital-spending
  increase used as if it were the whole gap between cash flow and free cash flow. Four were true
  numbers: their labels stand a few lines from the cited line, outside the lines the Verifier was given.
  Any flag stops the run with no report, and each of our earlier real runs had two or three flags. The
  team decides whether a flagged sentence is removed and the rest published, and how many lines the
  Verifier sees around a citation.
- **What we will not delegate again.** (the team writes this)

## 2026-11-19: leave out what fails, and the same desk on Windows as on a Mac

- **What the team decided.** Greg chose that a claim the Verifier does not mark correct is left out of the
  published report instead of stopping the run, that the Verifier sees more lines around each citation, and
  that the worksheet uses the agent team's own `MODEL` and `API_KEY`.
- **What changed.** A line that holds a flagged claim is left out; the marks table still lists the claim, and
  a line under the table names each part and claim left out. The hook rebuilds the published text from the
  saved role files, so a left-out line cannot come back. The Verifier sees eight lines on each side of every
  cited line. One step earlier, an analyst's claim that still fails the code's check after two repairs is left
  out with every draft line that uses it, and `claim_attempts.json` records what was left out. A ticker run
  with no seeker registry goes on, with its spinoff parts "not applicable".
- **What AI got wrong: a repair message the model could not act on.** In a practice run on Lowe's, one claim
  of 29 gave "sixth consecutive quarter" as its value. The check sent it back twice as "a substring of a
  larger value". The model sent the same claim each time, and the whole run would have stopped. With the
  leave-out it went on, but the paragraph that used the claim held seven good claims, and six of them left
  the report with it (the seventh is used elsewhere). The message now says the value holds no number and
  that the fact can be written in words. In the next run on Lowe's the model again gave "sixth" as a value,
  got the new message, and mended it in one repair, with nothing left out.
- **What AI got wrong: text in the Windows code page.** Code written on a Mac read and wrote files without
  naming UTF-8. On Windows the worksheet could not find its own rule "owner cash flow ÷ 10%", and stopped.
  We caught it when the test that copies the repository ran on Windows without UTF-8 mode. The desk's
  programs now start themselves in Python's UTF-8 mode on Windows (`utf8_mode.py`).
- **What AI got wrong: one sentence after the worksheet's JSON.** In the same run the agent team finished,
  the Verifier included, and the worksheet then stopped: its one model call returned the fenced JSON and one
  more sentence ("No Insight is offered..."), and the parser accepted nothing but the JSON. The worksheet
  now reads the first JSON object of the reply; the whole reply stays saved in the run folder, and code
  still checks the object's keys and that it holds no digit.
- **What AI got wrong: a fiscal-year label read as a number.** In the run after that, the Verifier wrote
  "fy 2025," in two of its 178 reasons and corrections, quoting the `fy` field of `facts.json`. The check
  allowed "fiscal 2025" and "FY2025" but not "fy 2025". Unlike the analysts, the Verifier had no leave-out,
  so the run stopped after all 89 of its marks were made. The check now reads "fy 2025" as a fiscal year,
  and a Verifier reason that still fails after its repairs is replaced by a fixed sentence; its mark stays.
- **What AI got wrong: no second try for a reply that never came.** The third run on Lowe's passed every
  check, and then its connection to Anthropic dropped five minutes into the Verifier's call. Nothing in the
  desk made the call again, so the run stopped with no report: the same failure as the Week 4 live run. Now
  a model call whose reply never came (a dropped connection, a timeout, or the provider's server error) is
  made once more after thirty seconds, and the role's `dropped_connections.json` records it. A reply that
  came, however bad, is never asked again. The worksheet's one call does the same.
- **What AI got wrong: no rule for a missing price.** In the run after that (2026-11-20), the agent team
  finished: the Verifier flagged one claim, and its line was left out as designed. The worksheet then stopped
  at the hook. LSEG was closed, so there was no price, and the price criterion scored 0; the hook had a rule
  for that criterion only when both the price and the low value were known, and refused the line. It now
  expects 0, the persona's score for absent evidence, as it does for the other five criteria; a 2 still needs
  both, verified. So the README's "prices are optional" was not true until this fix. Two reasons the
  worksheet's own code prints held a digit the hook cannot trace ("3 comparable fiscal years", and the count
  of trading days for liquidity); they are now written without one, and the counts stay in the worksheet's
  JSON. The worksheet also printed a raw `None` as its price evidence; it now says "not computed".
- **What AI got wrong: a float read as exact.** The hook compared a return on equity saved as a binary float
  with the exact decimal of its formula and refused a correct number. A practice run on Lowe's found it.
- **What AI got wrong: a home folder in the public repository.** The error-review files saved one member's
  full path to the repository. The audit found it; the paths are now relative to the repository.
- **Tests.** On Windows 11 and Python 3.13 on 2026-11-20, with Jackson's Windows changes of that day merged
  in, the four test folders ran 607 tests with no failure; the four that create a symlink were skipped.
  That is the Windows run his entry asks for. A Mac run of the merged folders is still to be done.
- **Open.** The worksheet reads its owner-cash-flow inputs from the 10-K's text and found none for Walmart.
  Without LSEG Workspace open, the closes reader has no price, and the view is "not computed". A leave-out
  removes the whole draft line, so good claims on the same line go with the bad one.
- **What we will not delegate again.** (the team writes this)

## 2026-11-20: an audit of the whole desk, and what it found

Greg asked for a full audit after the merge. It read the newest complete report (a practice run on Lowe's)
against its filings, re-checked the live record on EDGAR, and read the code behind each defect.

- **What AI got wrong: a rule the team had already written down.** Debt to equity used the `LongTermDebt` total
  tag. For Lowe's that was its debt maturity schedule's total, $39,819 million; the balance sheet's two lines
  give $39,921 million. The report printed -4.015 where the course's definition gives -4.03: an auditor marks
  that claim wrong, and one wrong claim fails the "Adopted" gate. Entry 9 of this log already said that the
  total tag is never the amount; the joined desk had not carried the rule over. It also added short-term
  borrowings, which the course's definition leaves out (Walmart: 0.449 where it should be 0.383). The desk now
  reads the balance sheet's noncurrent and current lines as one pair, as the base desk does.
- **What AI got wrong: a first line the live record could not read.** The joined desk wrote
  "Filings read: 10-K ..., 10-Q ..., 8-K ..." with no CIK, and `live_record.py` read no 8-K from it; the
  final report had a second, different first line. A Week 6 live run would have shown "names no 8-K". Both
  desks now write one line, with the release's exhibit, each Accepted time and the CIK.
- **What AI got wrong: reading the filings.** Three readers failed on real filings, each found by reading a
  report against its sources: the MD&A extractor took a split cross-reference ("see Item 7, ...") for the
  heading and gave the analysts Lowe's risk factors as Item 7; the release reader read no quarter for any
  company, because Lowe's says "Net sales" and Walmart's years sit under merged headers; and the worksheet
  read no owner cash flow, because Lowe's statement is "of Earnings" with a "% Sales" figure after each amount
  and Walmart prints "January 31," above columns of years. Each reader now handles those layouts, with tests
  on the filings' own shapes, and the hook reads the statements the same way the worksheet does.
- **What AI got wrong: a report that chose its own core claims.** The base desk printed the 11 core claims
  from code; the joined desk left them to the roles, and a report left out revenue growth that the desk had
  computed. The 11 are printed by code again, under the Overview.
- **Smaller fixes.** A client report printed "11.766682891778505%" and "$-9.917 billion"; percentages now
  show two decimals, ratios three, and a deficit "-$9.917 billion". A per-share value prints to the cent.
  `.env.example` names `MODEL` and the group desk's LSEG settings. The release readers took a table's unit
  only from its own cells; Lowe's prints "In Millions" just above its table, so the desk gave the analysts
  its net sales as "USD as shown" and left the unit to a guess. They now read the lines just above the
  table too, but never an earlier table's.
- **Not changed, on purpose.** The role prompts, the persona and the worksheet rules carry no course footer:
  members wrote them, the desk sends them to the model word for word, and a test checks that they are
  unchanged copies. A member's home folder path stays in commits made before 2026-11-19; removing it would
  rewrite `main`'s history, which this team does not do. Table values such as "(10,055)" keep the unit the
  filing prints beside them, because one release table mixes dollars, share counts and percentages.
- **The page, end to end.** On 2026-11-21 two runs started from the page passed the inputs, the pick and
  the seven data steps on Lowe's, with every hook check: debt to equity (37,490 + 2,431) / -9,917, in USD
  millions, from the balance sheet's two lines, and the quarter's net sales of 22,756 and 20,813 (USD
  millions) and diluted EPS of $2.98, each quoted from the release's table. Both stopped at the first model
  call, which the provider refused because the model account was out of credit. The roles, the Verifier,
  the worksheet and the final report have not run since the fixes.
- **Tests.** On Windows 11 and Python 3.13 on 2026-11-21, the four test folders ran 635 tests with no
  failure; the four that create a symlink were skipped. The new tests copy the layouts above from Lowe's and
  Walmart's filings. A Mac run is still to be done, and no Google or OpenAI key has run the desk end to end.
- **What we will not delegate again.** (the team writes this)

## 2026-11-21: the LSEG session check passed with Workspace closed

- **What AI got wrong: a check that could not fail.** On Windows, `check_lseg.py --session` printed
  "Desktop session opened and closed" while LSEG Workspace was closed and nothing listened on its API ports.
  The LSEG library's `open()` returns without an error when it cannot reach Workspace and leaves the session
  closed; the check caught only errors. Its tests replaced the worker with a mock, so the probe itself never
  ran in a test. A member who trusted it would have learned at the live run that there was no price.
- **The fix.** The probe passes only when the session reports `Opened`. Two tests run the probe itself on a
  stand-in library, one whose session stays closed and one whose session opens; against the old probe, the
  first test fails. With Workspace closed, the check now prints "Desktop connection failed".
- **Windows setup.** On 2026-11-21 `.venv-lseg` was created on Windows from `requirements-lseg.txt`: the
  install and `pip check` passed, and `check_pipeline.py` and the offline `check_lseg.py` printed ok. With
  Refinitiv Workspace open and signed in, the session check printed ok, and the closes reader returned
  Lowe's close for 2026-11-17 from LSEG.
- **Footers.** `docs/lseg-setup.md`, the error review, the hit-rate table and the page's review wrote their
  own second line ("No human source verification is claimed.", "Calculations use saved views and sourced
  closes.", or none), and the hit-rate table printed its footer before its agreement count. All four now
  end with the course's three lines word for word; a test checks each. The error documents already in the
  live-run folders keep their wording: those folders are the live record, and their files are not edited.
- **Tests.** On Windows 11 and Python 3.13 on 2026-11-21, the four test folders ran 663 tests with no
  failure; the four that create a symlink were skipped.

## 2026-11-22: the full audit

The whole desk was audited on branch `full-audit`: every part was driven with made-up filings, made-up
replies and failing networks, and the findings are in [code-audit-2026-11.md](code-audit-2026-11.md), each
with its test. No model was called and no real run was made: the model account had no credit. This entry
records what AI got wrong and how each thing was caught. Every item below was written or copied in by a
coding agent in the weeks before, and passed that agent's own tests.

- **What AI got wrong: a rule fixed in one desk and not in the other.** The group desk was built beside
  the base desk, and four rules that this log records as fixed were fixed in the base desk only. The group
  desk did not check that EDGAR's company facts were those of the 10-K it read (entry 14), so a 10-K filed
  days ago could be reported with last year's annual claims. It took the first index file named "99.1" as
  the release, without looking for an income statement (entry 3), and when the newest earnings 8-K had no
  such file it went back to last quarter's 8-K without a word. It took last year's amounts from last
  year's 10-K, where the checklist computes growth "from the two years in the same filing". **How it was
  caught:** a table of every past failure in this log was made, and each fix was looked for in both desks.
  The three rules are now in `desk_rules.py`, which both desks import, with tests on made-up facts.
- **What AI got wrong: a reader that returns a wrong cell instead of refusing.** Three of the group desk's
  four release readers had no test. On made-up tables, a loss in parentheses made last year's EPS this
  quarter's, a third dated column gave the prior quarter, two change columns gave a growth of 900%,
  "Revenue from services" was read as total revenue, EPS from continuing operations was read as the
  quarter's EPS, and "Aug 30, 2026" stopped the run. **How it was caught:** by writing the tables an
  earnings release can print and reading the output for each, before reading the code. One function now
  reads a row's amounts for every reader, a row is read only when it holds one amount for each period
  column, and a table that cannot be read is skipped. The saved Lowe's and Walmart releases give the same
  figures as before.
- **What AI got wrong: code that changed a number's scale.** Inside an Item under "(amounts in millions)",
  the ledger wrote "million" after every dollar value: "$1.16 million" for a dividend, "$20 million" for an
  hourly wage. A header worded "(in millions, ...)", which both live filers use, was not read at all. A
  loss in parentheses could be cut out of them and published as a gain. **How it was caught:** by sentence
  shapes a real filing holds, run through the ledger. The scale now goes only on whole dollars with a
  thousands separator; a per-share or per-hour amount keeps its own unit; anything else in doubt is refused
  with the reason.
- **What AI got wrong: checks on a model's text that a model's text could pass.** A scale, a sign or a
  multiplier typed next to a checked claim passed ("$9,200 [cited] billion", "twice $4.1 billion"). So did
  a number in words ("eleven per cent"), in other numerals, a typed citation, a table that reads as the
  desk's own, and a reference followed by a scale ("Sales of Item 12 million"). A Verifier reason with a
  line break published free text outside the marks table. A number the Verifier marked wrong was left out
  of its own part and printed two parts later through another role's reference to it. **How it was
  caught:** by writing replies meant to pass, not replies meant to be right. Each form is now refused, with
  a test. What is still open is listed in the audit file: the label beside a correct number is not checked.
- **What AI got wrong: tests that could not fail, and a required check that did not run them.** The
  required command ran 448 of 663 tests and neither seeded check, and on Windows it failed as written
  (44 errors) unless Python was started in UTF-8 mode. Each formula of the group desk was changed on
  purpose (operating margin to net income over revenue, average equity to year-end equity, and so on) and
  20 of 21 changes passed every test: the formula tests were the base desk's. **How it was caught:** by
  running the required command exactly as `AGENTS.md` wrote it, and by changing the code to see which
  test noticed. `check_all.py` now runs everything, a test fails when a test folder is left out of it,
  `tests/test_group_formulas.py` fails on each changed formula, and every file is opened as UTF-8 by name.
- **What AI got wrong: a run that could not survive ordinary trouble.** A rate limit (429) was never
  tried again, by either copy of the retry rule; Google's "model is overloaded" ended a run because its
  error carries `code`, not `status_code`; a stalled call to an Anthropic or Google model hung for good;
  one 429 or 503 from SEC EDGAR ended a run; a failure in the worksheet, the last model call, threw away a
  finished and paid-for team report; Ctrl+C left the folder "running" for good; and `live_record.py` read
  the report of a failed run as a live report. **How it was caught:** by a stand-in transport that fails
  in each way, for each provider. There is one retry rule (`model_calls.py`), a time limit, SEC back-off,
  `desk.py --resume`, a recorded stop, and a live record that reads the run's state.
- **What AI got wrong: settings found wrong late.** The setup check printed "ok" for the README's own
  example lines and for an Anthropic key with an OpenAI model. With no `MODEL` the team ran on a Gemini
  model whatever the key. The worksheet took `ANTHROPIC_API_KEY` from the shell before the team's
  `API_KEY`, so one run could use two accounts. The error review sent an OpenAI key to Anthropic. **How it
  was caught:** by reading where each program takes each setting, then running each with made-up keys and
  a stand-in for the network. The desk now checks the three settings as its first step.
- **What AI got wrong: licensed data on its way to a public folder.** With LSEG Workspace open, the
  worksheet printed the last 60 days of closes and volumes in the worksheet, which the final report
  includes, and a live run commits its folder. No practice run showed it, because Workspace was closed
  each time. **How it was caught:** by following what the closes reader returns to every file it reaches.
  A member decided on 2026-11-22: the report prints the result only, and the rows stay in a folder git
  ignores. `check_public.py` fails on rows, keys, values of `.env` and home-folder paths before a push.
- **What AI got wrong: the page.** A report's link could run script on the page; `2*3*4` was displayed as
  234; a network path in the address reached the filesystem; drafts that never passed the audit were
  served; the setup banner said "passed" when the check itself crashed; on Windows two pages shared one
  port. **How it was caught:** by sending the page requests no browser form sends. Thirteen tests. One of
  these fixes then went too far: the page refused every request that named another website, and a click
  on the page's address in the README on GitHub is such a request. It was caught by reading the check
  against the headers a browser sends for a clicked link, before the commit; a fourteenth test holds it.
- **What AI got wrong: one company's wording as a rule.** Step 6 turned the sentence "non-recurring
  benefit of $X per diluted share" into a metric. `AGENTS.md` says nothing in the code names a company.
  Removed, with a test.
- **What AI got wrong in this audit, and how it was caught.** Four fixes were too strict at first and
  refused honest text. Two were caught late, and not by a test: the rule against text typed next to a
  claim refused a claim in parentheses and "percent" after a bare table cell, and both stand in the
  replies a real model gave on 2026-11-20 ("gross margin was 32.95 percent of sales", from a table's
  percent-of-sales column). The tests of that rule were sentences the coding agent wrote itself. It was
  caught by replaying the 17 replies the practice runs saved through the old ledger and the new: the new
  one gave 18 more errors. The rule now refuses a scale, a sign and a multiplier only, the two honest
  forms are in the tests, and the replay gives the same errors and the same rendered text as before.
  The other two: a dash after a claim was read as a minus sign in a range ("$18 billion to $22
  billion" written with a dash), and every heading that starts with a number was refused with the forged
  table titles. A rule that left out a reference to a redrafted claim was too strict, and left out
  references whose value had not changed; it now compares the values. Each was caught by a test of honest text,
  which is why those tests were run after every change. One planned fix was not made: applying the
  half-day close to the price would have made the worksheet and its hook disagree, so the limit is
  written down instead (README, "What can go wrong", item 5).
- **What was not done.** No real model, SEC or LSEG run of the changed code. The saved pages and replies of
  two companies were replayed, which is not a new run on a new company. The files no AI writes were not touched,
  and nothing under `runs/live/` was changed.
- **Tests.** On Windows 11 and Python 3.13 on 2026-11-22, `python check_all.py` ran 840 tests with no
  failure, four skipped, without UTF-8 mode. Before the audit the four folders held 663.
- **What we will not delegate again.** (the team writes this)

## 2026-11-22: an independent review of the audit's own commit

The audit above was committed as `086a312`. Before anything was pushed, six reviewers that had no share in
writing it read the commit, one part each (the data steps, the ledger, the run's control, the model calls and
sources, the page, and the tests), and each had to prove a finding on made-up data. They returned 50
findings, all reproduced again before any change. 26 had come with the audit's own commit, one of them
critical and six high. The table is in [code-audit-2026-11.md](code-audit-2026-11.md), rows V1 to V27.

- **What AI got wrong: fixes that made a right answer wrong.** The audit's new row reader counted "(5" as
  an amount when a negative change is printed "(5" then ")%", dropped the row, and published another row's
  figure: a count of shares, "$204", as GAAP diluted EPS. Its new scale rule printed "$43,440" bare for
  $43,440 million, because "a year ago" read as "a year", and "$4,828 thousand" for millions, because a
  row's own unit read as a header. Its time limit was itself retried, so a stalled role was called a second
  time beside the first. Its `--resume` could be used once: a second was refused for the files the first
  had moved. Its page check refused the repository's own files on a network drive. **How it was caught:**
  each reviewer wrote the inputs the author had not thought of, and ran the code before the audit beside
  the new code, so that "worse than before" could be told from "still not right".
- **What AI got wrong: rules that refused honest text.** The ledger's new word rules refused "a third
  party", "double taxation", "twice in the filing" and "Basel III points to", and left "double-digit" no
  way through at all. Of 147 honest analyst sentences the first commit refused 50 that the old ledger
  accepted. The setup check told a member named Fillmore to write a name and email, on every run, because
  the example says "fill in". **How it was caught:** by writing sentences a person would write, not
  sentences that attack. The rules are narrowed to what changes a number; 11 of the 147 are still refused,
  each a typed sign, scale, citation or number in words.
- **What AI got wrong: "fixed" in the audit file, and not fixed.** A UTF-16 `.env` was listed as handled;
  `desk.py` itself still printed the codec error and left an empty run folder. The registry field was
  listed as refusing a network path; it did not. An image was listed as shown by its words; it vanished
  with them, and its test used an image with no words. **How it was caught:** the reviewers read each row
  of the audit's table against the code, not against the audit's tests.
- **What AI got wrong: tests that could not fail, again.** One page test failed about one run in eight
  on Windows and never reached the rule it named. The test of a 53-week year used a 52-week year. Several
  rules of the first commit could be deleted with no test failing. **How it was caught:** by deleting each
  rule in a copy and running its tests. Each now has a test, and each bound of the one-year rule was broken
  on purpose to see a test fail.
- **What was older than the audit and the audit had missed.** A non-GAAP statement read as GAAP when its
  title was a row of its own table; two change columns giving a growth of 8,909%; a run made on Windows
  that does not recheck from a clone, because git stored other line endings than the run had sealed; two
  reply shapes that crashed the run where a repair was due.
- **What AI got wrong in these fixes, and how it was caught.** The first fix of the table's unit lost the
  unit of a real release, which prints it beside its years: the replay of the saved Walmart pages showed
  "USD as shown" where the commit had read "USD millions". The widened scan for lists of closes called the
  one price a run saves a list, which would have failed the first live run that had a price: the test of a
  whole run caught it. A key-shaped string in a new test tripped the repository's own scan. All three were
  caught by checks the audit had added.
- **What was not done.** Still no real model, SEC or LSEG run. The fixes were checked in a worktree, not in
  a second fresh clone. Six things the review raised are left open, with the reason (rows W1 to W6).
- **Tests.** On Windows 11 and Python 3.13 on 2026-11-22, `python check_all.py` ran 928 tests with no
  failure, four skipped.
- **What we will not delegate again.** (the team writes this)

This is a learning exercise, not financial advice.

AI assistance: Claude Code and OpenAI Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
