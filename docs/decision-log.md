# Decision log

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

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
