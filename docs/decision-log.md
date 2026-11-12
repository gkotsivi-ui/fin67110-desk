# Decision log

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

## 2026-11-12: the OpenAI key

### 16. A path built with no key to prove it

- **What we built.** With a key that starts with `sk-`, the roles and the Verifier call OpenAI's Responses
  API by a plain web request, as the desk calls Gemini. The request asks OpenAI not to store the response.
- **What is checked.** Tests on made-up replies in the API's shape. The text is found wherever the message
  stands in the reply. A refusal, an empty reply and a reply cut off at the token limit each stop the role
  with the reason. A bad key, a model the key cannot use, an account with no credit and too many requests
  each give a message that says what to do. One request with a made-up key went to the real API through
  the desk's own code. It got HTTP 401, and the desk's message said to paste a valid key.
- **What is not checked.** No report has been written on OpenAI. We had no OpenAI key on 2026-11-12. The
  shape of a real reply comes from OpenAI's reference pages and from a teammate's working desk, which
  reads the reply through OpenAI's own library. Our code reads the raw reply, so the first real run may
  show a difference. `EFFORT` is not sent to OpenAI.
- **What AI got wrong: a date it could not support.** The coding agent wrote in the code that the default
  model was one "that one of this team's desks ran on, on 2026-11-08". That desk names the model as its
  default, and its repository holds two runs of that date. No file in those runs says which model served
  them. The agent read the run folders before it committed the line, and the comment now says only what
  the code shows. OpenAI's models page listed the model on 2026-11-12. Whether a key can use it is for
  `check_env.py` to say: it asks OpenAI.
- **What AI got wrong: a rule with no test.** OpenAI's message for a bad key shows the key with stars in
  the middle. The desk cuts anything that looks like a key out of an error before it prints or saves it.
  The agent's first test of a bad key used a made-up message with no key in it, so that rule had no test.
  The request to the real API showed the stars. The test now seeds a message that shows the key.
- **A change to the plan.** The plan said to move the Anthropic call to a plain web request in the same
  work, to drop the package with the long path. We did not. The live runs use the Anthropic path, and it
  changes only with a run of its own to prove it.
- **What we will not delegate again.** (the team writes this)

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
