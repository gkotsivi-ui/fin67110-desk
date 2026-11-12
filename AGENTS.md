# Rules for coding agents in this repository

This is a team project for FIN 67110 (Purdue, Fall 2026): an AI research desk that reads a U.S. company's
10-K, 10-Q and earnings release from SEC EDGAR and writes a report for one client. The course site is the
source of truth: https://cinderzhang.github.io/FIN67110-Fall2026/ (project, grading, schedule, audit checklist, data).

## Hard rules

1. **Secrets.** Keys, names and emails live only in `.env`, which is never committed. Before every push, show
   the team what is going public and scan it for keys. Ask before you create or change anything on GitHub.
2. **Licensed data.** Never read, print or paste WRDS (CRSP, Compustat) values into a session or a model
   prompt, and that includes tables that code derives from them. For WRDS, checks print counts and PASS or
   FAIL, not values, and a team member runs any command that would print values. LSEG is different: on
   2026-11-11 a team member confirmed that its terms allow its data in AI tools, so an LSEG price may enter a
   prompt and a report. For every source, raw pulls and exports stay out of the repository.
3. **SEC EDGAR.** Send the User-Agent from `.env` on every request and stay well under 10 requests a second.
4. **History.** Live reports go straight to `main`. Never rewrite history on `main`: no rebase, squash, amend
   or force-push. Commit times are the team's evidence.
5. **What no AI writes.** The desk diagram, the role personas in `roles/`, the seeker's factor list, the
   worksheet's method file and persona, any member's roles paragraph, and any peer evaluation.
6. **The footer.** Anything public ends with the course's three lines, with the tools actually used.
7. **Never invent** a number, a filing, a date or a source. When you cannot verify something, say so.

## How the desk must work

- Numbers come from code, not from a model. Code computes the 11 core claims from XBRL company facts and the
  filings, on the audit checklist's definitions: operating margin = operating income / total revenue; return
  on average equity; debt to equity = long-term debt including its current portion / equity; free cash flow =
  cash from operations - additions to property and equipment; GAAP diluted EPS only.
- When a claim is in doubt, omit it and say why. A missing claim costs nothing; a wrong one fails the audit.
- Roles receive numbers as files. They quote; they never recompute or recall.
- Accuracy must not depend on the model. Another team may run the desk on a different one.
- Code fixes the order of the parts. One run folder per run; save each filing once and read the saved copy.
  A part that fails stops the run, names itself and the error, and keeps the folder.
- Nothing in the code names a company. Every rule has a test on made-up data, and a rule changes only after
  its test does.
- Keep the code simple and explain each change. All three members must be able to defend every part.

## Live-record error documentation

For each live record, create a separate Markdown file in `docs/live-record-errors/`, following that
folder's README. Observe and document errors; do not fix them unless the user asks. Preserve the live
run's original files and results. Let the run continue where its existing behavior permits; do not bypass
an existing stop or failure to force completion. Document stopped and incomplete runs too.

Look across the whole process, including SEC parsing, calculations, conclusions, verification, skills,
the hook, numerical evidence, and runtime errors. These are examples, not an exhaustive checklist.
For each error record its type, where it happened, a description, and why it happened. Cite saved
evidence, distinguish confirmed causes from hypotheses, and say when the cause is unknown.

## Required checks for changes

```
python -m unittest discover -s tests
python live_record.py --offline --no-save
```

Write what AI got wrong, and how it was caught, in `docs/decision-log.md`.

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
