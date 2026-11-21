# Live runs

One folder for each live run: the report, and the filings and facts it was written from.

The rule, from the course's project page: each week in Weeks 4 to 7, the desk runs on a company that filed
its earnings release (or another SEC report) that week, and the report is committed and pushed here within
24 hours of the filing's "Accepted" time on SEC EDGAR. The report names the filings it read. The commit's
time is the record.

| Live-record week | Dates |
|---|---|
| Week 4 | Mon Nov 9 to Sun Nov 15, 2026 |
| Week 5 | Mon Nov 16 to Sun Nov 22, 2026 |
| Week 6 | Mon Nov 23 to Sun Nov 29, 2026 |
| Week 7 | Mon Nov 30 to Sun Dec 6, 2026 |

How to file a live run:

1. Open LSEG Workspace and sign in, so the report has a price and the worksheet a view (see `.env.example`
   for `LSEG_APP_KEY` and `LSEG_PYTHON`). Then run `desk.py TICKER --live` from `main`, soon after the release:
   a view saved after the first market close that follows the filing is marked "after" and is left out of the
   hit rate. The run folder appears in this folder. (The base desk, `team.py`, writes it to `output/`: move the
   whole folder here without renaming it or editing its files.)
2. Check the eleven core claims, printed under the Overview, against the filings named on the report's first line.
   Save the human error report and AI prompt directly inside this run's folder, following
   `docs/live-record-errors/README.md`. Keep their company names, record numbers, and numbered revisions.
   Preserve the original run and document errors without fixing them unless requested. Create a file
   for each live record, including a stopped run or a run with no observed errors.
3. Do not edit the run's files.
4. Commit it to `main`, with the ticker and the release's Accepted time in the message.
5. Run `python live_record.py`, and commit `docs/live-record.md`.
6. Look at what is going public, scan it for keys, and push.

A live run's original research artifacts are never changed after its commit. New review reports may be
appended inside its folder. Never overwrite an earlier review report. A correction is a new commit that says what it corrects.
Never rebase, squash, amend or force-push `main`.

This is a learning exercise, not financial advice.

AI assistance: Claude Code and OpenAI Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
