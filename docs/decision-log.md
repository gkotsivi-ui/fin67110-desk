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
- **Status.** Open. PLAN.md, fix F2.
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
- **Status.** Open. PLAN.md, fix F1.
- **What we will not delegate again.** (the team writes this)

### 3. The run stopped on a release labelled EX-99

- **What the desk printed.** For 8-K 0001740332-26-000029 (Resideo, accepted 2026-11-10 16:12:00 ET):
  `Desk stopped: Could not locate the 8-K's Exhibit 99.1 in the SEC filing directory.`
- **What the filing says.** The filing's index page lists the release with the type `EX-99`.
- **How we caught it.** The run ended with exit code 1 and no report.
- **Cause.** The desk looks for the label `EX-99.1` only.
- **Status.** Open. PLAN.md, fix F3.
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
- **Status.** Open. PLAN.md, fix F4.
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

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
