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

1. Run the desk on the ticker. The run folder appears in `output/`.
2. Check the eleven core claims against the filings named on the report's first line.
   Document observed errors in a separate file under `docs/live-record-errors/`, following its README.
   Preserve the original run and document errors without fixing them unless requested. Create a file
   for each live record, including a stopped run or a run with no observed errors.
3. Move the whole run folder from `output/` into this folder. Do not rename it and do not edit its files.
4. Commit it to `main`, with the ticker and the release's Accepted time in the message.
5. Run `python live_record.py`, and commit `docs/live-record.md`.
6. Look at what is going public, scan it for keys, and push.

A live run is never changed after its commit. A correction is a new commit that says what it corrects.
Never rebase, squash, amend or force-push `main`.

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
