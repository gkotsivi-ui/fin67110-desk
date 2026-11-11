# Plan

Draft of 2026-11-11, for the team to approve. Until it is approved, nothing below is built. The base is
gkotsivi-ui/equity-analyst-project at commit 3908d6d. The course site is the source of truth:
https://cinderzhang.github.io/FIN67110-Fall2026/

## 1. Where we stand

Measured on 2026-11-11. The details are in [docs/decision-log.md](docs/decision-log.md).

| What | Evidence |
|---|---|
| The desk runs end to end | One company from a terminal: 290 seconds, six parts and one send-back, a verified report |
| The 11 core claims come from code | On that run the Verifier marked all of them correct |
| The tests | 87 pass with no network and no key (69 from the base desk, 18 for the live record) |
| A stranger's install | A clean virtual environment with the pinned packages installs, and the tests pass there |
| The data steps on six companies | 1 clean; 1 with wrong quarter revenue and growth; 1 with a wrong debt to equity; 1 with an unsupported debt to equity; 1 that stopped; 1 that ran with awkward ratios |
| The Verifier | It marked 9 correct numbers wrong or unsupported on the clean company |
| Not built | The seeker, the worksheet with its view, the hook, the one command, the replay, the hit-rate table, the audits, the manual |

## 2. What the grade rewards, in the order we protect it

1. **Not zero.** A live report in this repository, and a product manual.
2. **Checkpoint 3 (Thu Nov 19) and Checkpoint 4 (Thu Dec 3).** Each is 17.5% of the course, pass or fail.
3. **85, not 70.** All five parts exist, and another team runs the desk from the README with no help.
4. **95.** A report inside its window in three of Weeks 4 to 7, and no wrong or unsupported number in the
   two reports another team audits on Tue Nov 24. Then the ranking: our audit marks hold; the desk runs
   on the instructor's pick; the manual claims no more than the evidence; each member explains a number.

Returns never count. A missing claim never fails the audit. A wrong one does. So the rule for every
number is: state it with its source, or omit it and say why. Never guess.

## 3. Gaps, ranked

Size: S is half a day or less, M is one to two days, L is three days or more.

### G1. A wrong or unsupported number can reach the report (the Nov 24 gate)

| Fix | What changes | Size |
|---|---|---|
| F1 | Debt to equity: when no debt fact is found, the claim is "not stated", never 0.000. A short list of accepted debt tags, each with a test. When the total and its parts both exist, they must agree. | S |
| F2 | Claims 9 to 11: read the revenue and EPS rows only inside the release's income statement. Find the two quarter columns by their dates, not by position. Read the units from the statement's header. | M |
| F2b | Check the release against XBRL: the year-ago quarter must equal last year's filed fact, and the new quarter must equal the 10-Q's fact when the 10-Q is already filed. A claim that fails is omitted. | M |
| F3 | Find the release by what it holds, not only by the label EX-99.1: accept EX-99 and EX-99.x, and take the exhibit that has an income statement. | S |
| F6 | One claims file for each run, written by code: each claim's value, period, definition, source and status (stated or omitted, with the reason). The report's table is printed from it. | M |
| F7 | The roles' text may hold a number only when code finds it in the claims file or in the line the text quotes. Code removes a sentence that fails and lists what it removed. | M |
| F8 | Stop when the facts do not belong to the 10-K the desk chose. Today the desk prints MISMATCH and goes on. | S |

### G2. Another team cannot run it (85 becomes 70)

- **An OpenAI key does not work.** Add it as a plain web request, as the Gemini path is. Size M.
- **Accuracy must not depend on the model.** Run one company on each provider's cheapest model. The
  claims table must be the same on all of them, and the hook must pass. Size S, after F6 and F7.
- **A long folder path stops the install on Windows.** One package needs a path of 138 characters
  inside the repository folder, and Windows allows 260 in all. The README now says to keep the path
  short. Calling Anthropic by a plain web request, as the desk calls Gemini, would remove that
  package. Do it with the OpenAI key.
- **Only the direct packages are pinned.** Add a constraints file from a clean install, tested on a Mac. Size S.
- **Nobody outside has followed the README.** Each teammate does it on their own computer this week, with
  the README alone, and writes down every place they had to guess. One Windows and one Mac at least.
- **Run the tests on each push** on Windows, macOS and Linux with GitHub Actions. Size S. Needs your OK.
- **A run takes about five minutes.** That is long for an 11-minute talk with one retry. Measure a faster
  model before the talk, and decide the model for the room.

### G3. Parts that do not exist yet (any missing part is 70)

| Part | Course page | Size |
|---|---|---|
| The spinoff seeker, with its registry and ranked screen | Lab 06 | L |
| The worksheet, with owner cash flow, a value range and the view | Lab 07 | L |
| The hook: code that refuses "done" over a number with no support | Lab 07, Lab 08 | M |
| One command, in a fixed order, through one run folder; each part prints its seconds; a failing part stops the run and names itself | Lab 08 | M |
| Replay of a saved run with the network off | Lab 08 | S, after the one command |
| The page runs the one command | Lab 08 | S |
| The hit-rate table | Lab 07 | S |
| `audits.md`: four tables, by hand | Project page | by hand |
| `manual.md` | Project page | by hand, with tables from code |

The team writes these by hand, and no AI writes them: the three personas in `roles/`, the factor list,
the worksheet's method file and its persona, the diagram, each member's roles paragraph.

### G4. The live record (three of four weeks)

- Each Monday, pick the release and the member who runs it. Pick a second company in the same window.
- Run the tests and `python live_record.py` before each push. The script shows the hours that are left.
- If the desk fails inside a window, the course's fallback report counts: paste the statements and the
  release into a chat, save the answer with "fallback" on its second line, and push it.

### G5. A price reaches a model

Today the desk sends the close to the Financial Analyst and prints it on the report's second line, and
the Verifier's model reads that line. The team's rule is that no licensed value enters a model prompt.

- **If LSEG's terms allow it:** no change.
- **If they do not, or we do not know:** code computes P/E and the view after the roles have run and adds
  them to the report. No role and no Verifier call receives a price. Size M.

The WRDS base rate for the manual is run by a team member, and its output is pasted by a team member.

### G6. The Verifier flags correct numbers

F4: read a decline as a negative change; print a calculator result with its numbers, so it can be
redone; keep "less than" with its figure. Each with a test on made-up data. Size S each.

### G7. Small things a reader would notice

- Every report has an empty line "Partner's check", left from an earlier lab.
- The three closing lines print as one paragraph in a report. They should be three.
- The desk has no pause between its requests to SEC EDGAR. It is under the limit today, by timing only.
- The base README says the role files are six-part personas. They are not yet.

## 4. Companies that do not fit (others pick the names)

Each claim has three outcomes: stated with its source; omitted with the reason; or, when no report can
be made at all, the run stops and names the part and the cause. The desk never fills a gap with a guess.

| Case | What the desk does |
|---|---|
| The release is labelled EX-99, or the release is not the first exhibit | F3: choose by content; name the exhibit on the first line |
| The newest Item 2.02 8-K is not a quarterly release (a pre-announcement, monthly figures) | Use the newest one with an income statement; else omit claims 9 to 11 |
| A fiscal year that does not end in December; a 52 or 53 week year | Already handled; every period is printed with its dates |
| A fourth-quarter release, when the latest 10-K is a year older | State both periods with their dates; never call the 10-K's year "this year" |
| Three quarter columns, or last year first | F2: columns by date; F2b: check against XBRL |
| A release in thousands; a loss in parentheses; a space between the dollar sign and the number | F2: units from the header; tests for each form |
| Adjusted EPS beside GAAP EPS | Read the GAAP income statement only; never a reconciliation table |
| No operating income fact | Omit claim 3 |
| A noncontrolling interest | Net income and equity on the parent's tags only; else omit |
| Debt under another tag, or no debt at all | F1: an accepted tag, or "not stated" |
| A bank, an insurer or a REIT | Omit the claims that do not apply (operating margin, debt to equity, free cash flow) and say why; jcleeper65/Analyst has a check to port |
| A recent IPO or spinoff with one year of statements | Omit growth and return on average equity |
| No 10-K yet, or no 10-Q yet | Today the run stops. Change: run on what exists and omit the rest |
| A 10-K/A, a 10-KT after a change of fiscal year, a late filer | Use the latest full-year 10-K and say on the first line that a newer form exists |
| A share split after the 10-K's year | Do not compute P/E from that year's EPS |
| A company that files 20-F and 6-K | Out of scope: stop and say so. The README says so too |
| A ticker with a dash or a dot; two share classes | Tests on made-up tickers; resolve by SEC's own ticker file |
| A very long 10-K | Cap the text each role receives, so a small model does not overflow |

How we test it: a sweep command runs the data steps, with no model and no price, on a list of tickers
given in a file, and prints stated, omitted or stopped for each claim. Each member then checks two
companies a week against the filings by hand. The first list is the course's build-out set, because
other teams must pick at least one of them on Nov 19: Oracle, Microsoft, Alphabet, Amazon, Meta,
CoreWeave, NVIDIA, AMD, Broadcom, Dell, Super Micro, Vertiv.

## 5. Milestones

| Date | What must be true |
|---|---|
| Wed Nov 11 | This plan approved. The repository is on GitHub. Each teammate clones it and follows the README. |
| Thu Nov 12 | Lab 07. The team names the thing we own. After the close: the Week 4 live run (section 7). |
| Fri Nov 13, about 4:07 PM ET | Week 4 window closes: the Accepted time plus 24 hours. |
| Mon Nov 16 | F1, F3, F4 and F8 done. F2 done or claims 9 to 11 omitted when in doubt. Week 5 release and runner chosen. |
| Tue Nov 17 | Lab 08: the one command, the replay, the seconds. Arrive with the hand-drawn diagram and the base rate. |
| Wed Nov 18 | Checkpoint 3 page drafted. The live record table in it comes from `live_record.py`. |
| **Thu Nov 19, 11:59 PM ET** | **Checkpoint 3 uploaded.** Lab 09: two names from another team, and the three-column table. |
| Sun Nov 22 | Week 5 live report inside its window. F6, F7 and the hook done. OpenAI key works. |
| Mon Nov 23 | Freeze. The sweep on the build-out set shows no wrong number in the companies we checked by hand. Two people who did not write the README have run the desk from it, one on Windows and one on a Mac. |
| **Tue Nov 24** | **The exchange.** They run ours. We run theirs and audit both reports. |
| Nov 25 to 29 | Week 6 live report if a release is convenient. Start `audits.md`. Ask one reader outside the course to run the desk from the README and write what they used it for: the project page counts that as adoption evidence too. |
| **Thu Dec 3, 11:59 PM ET** | **Checkpoint 4**: the first draft. The desk runs from the README; the manual's tables so far; the client paragraph; the decision log; each member's roles paragraph. |
| Sun Dec 6 | Week 7 live report inside its window. |
| Dec 4 to 7 | Talk rehearsal: a live run from the page on five recent filers; the time of a run; each member explains any number on the slides. |
| Tue Dec 8 or Thu Dec 10 | The talk. Thu Dec 10, 11:59 PM ET: each member's peer evaluation, written alone. |
| **Fri Dec 11, 11:59 PM ET** | **The project upload**: one Markdown file of permalinks. |

The Week 6, 7 and 8 pages of the course site were not published on Nov 11. Read them when they are,
and change this table.

## 6. Who owns what

A proposal. The team decides, and each member writes their own role.

| Owner | Work |
|---|---|
| A: the numbers | F1, F2, F2b, F3, F8; the claims file (F6); the sweep and the list of awkward companies |
| B: the skills and the client | The seeker; the worksheet and the view; the closes reader and the hit-rate table; the thing we own; the base rate from WRDS |
| C: the run and the proof | The one command and the replay; the hook (F7); the page; the OpenAI key; the README and the stranger tests; the live record; `audits.md`; putting `manual.md` together |
| Everyone | Their own persona and roles paragraph; one live run each; the audit of one report each; a decision-log entry for each thing they catch; a review of each change by a member who did not write it |

## 7. Thursday's run (Week 4)

Cisco reports its first quarter after the close on Thu Nov 12. Its last five releases were accepted
between 4:06 and 4:16 PM ET. Applied Materials reports in the same hour and is the second choice,
once F2 is done.

1. Before 4 PM: `git pull`; run the tests; run `check_env.py`.
2. From about 4:10 PM: `python lab02_desk.py CSCO --step 2` prints the newest earnings 8-K and its
   Accepted time. Wait until it shows the Nov 12 filing. Do not ask more than once every few minutes.
3. Run the desk from the page, so the page is proved on a live run too.
4. Two members check the eleven core claims against the filings. Look hardest at the column headers of
   claims 9 to 11.
5. Move the run folder into `runs/live/`, commit it to `main`, run `python live_record.py`, commit the table.
6. Look at what is going public, scan it for keys, and push. Aim for Thursday evening. The hard limit is
   the Accepted time plus 24 hours.

What to decide before Thursday: whether the run uses a price (G5), and whether F4 goes in first, so the
live report does not show false "wrong" marks.

## 8. The thing we own, and the decision we serve

| Option | For | Against |
|---|---|---|
| A second seeker: stocks below net current asset value | All from XBRL facts, in code, no model. No licensed data except one price in code. Small enough for one member. | It adds a second screen to explain. It does not make the report more accurate. |
| The factor check on past spinoffs | The strongest finance. | It needs CRSP returns from WRDS, so no AI may see its data or its results. It is slow to build blind. |
| The desk as a plugin, with an evaluation | It helps another team run the desk. Its evaluation is the three-column table for every name. | Each coding agent packages a plugin in its own way. The desk already runs with one command and no agent. |
| A mandate skill for an institution | A second client. | It needs quarterly data, positions and a benchmark return: more licensed data and more numbers to audit. |

**Recommendation: the second seeker.** It is the one extra that needs no new data source and no model,
and one member can build and defend it in the time we have. Take the plugin only if the exchange goes
well and time is left. Leave the factor check and the mandate.

**The decision we serve: the company's stock,** for the investor who seeks absolute return. The view
says worth more or less than the price, with one number that decides it. The labs, the closes reader
and the hit-rate table are all built for the stock. Bonds would need bond prices and new claims. A
portfolio would need the mandate skill.

**The join: the pipeline, everywhere.** Each part reads the files the part before it saved. Nothing
calls anything else. It is the easiest to test, to replay and to explain. The team writes this
choice in its own words.

## 9. What we need to decide

1. Approve this plan, or change it.
2. Do LSEG's terms allow its prices in an AI tool? (G5)
3. Who is the third member, and which model keys does each member have?
4. The thing we own, by Thursday's lab.
5. May code changes go through pull requests with tests on each push? (G2)

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
