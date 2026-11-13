# The live record

Made by `python live_record.py` on 2026-11-13 13:17 Eastern. One row for each report in `runs/live`. The release and its Accepted time are the 8-K that the report's first line names, checked on its SEC EDGAR index page. The commit is the one that first added the report, and its time is the record. A report is inside its window when the commit is no more than 24 hours after the Accepted time.

| Week | Ticker | Release the report read | Accepted (ET) | Window closes (ET) | Commit | Commit time (ET) | After the release | Inside the window |
|---|---|---|---|---|---|---|---|---|
| Week 4 | CSCO | 8-K 0000858877-26-000170, Exhibit 99.1 [exhibit991pressrelease-q1f.htm](https://www.sec.gov/Archives/edgar/data/858877/000085887726000170/exhibit991pressrelease-q1f.htm) | 2026-11-12 16:06:24 | 2026-11-13 16:06:24 | `88015f7` | 2026-11-13 13:17:26 | 21.2 hours | yes |

Weeks with a report inside its window: 1 of 4 (Week 4). The top tier needs 3.

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
