# The live record

Made by `python live_record.py` on 2026-11-25 08:11 Eastern. One row for each report in `runs/live`. The release and its Accepted time are the 8-K that the report's first line names, checked on its SEC EDGAR index page. The commit is the one that first added the report, and its time is the record. A report is inside its window when the commit is no more than 24 hours after the Accepted time.

| Week | Ticker | Release the report read | Accepted (ET) | Window closes (ET) | Commit | Commit time (ET) | After the release | Inside the window |
|---|---|---|---|---|---|---|---|---|
| Week 4 | CSCO | 8-K 0000858877-26-000170, Exhibit 99.1 [exhibit991pressrelease-q1f.htm](https://www.sec.gov/Archives/edgar/data/858877/000085887726000170/exhibit991pressrelease-q1f.htm) | 2026-11-12 16:06:24 | 2026-11-13 16:06:24 | `88015f7` | 2026-11-13 13:17:26 | 21.2 hours | yes |
| Week 5 | NVDA | 8-K 0001045810-26-000088, Exhibit 99.1 [q3fy27pr.htm](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/q3fy27pr.htm) | 2026-11-17 16:20:51 | 2026-11-18 16:20:51 | `f55b170` | 2026-11-18 08:52:43 | 16.5 hours | yes |
| Week 6 | WDAY | 8-K 0001327811-26-000057, Exhibit 99.1 [wday-10312026x991.htm](https://www.sec.gov/Archives/edgar/data/1327811/000132781126000057/wday-10312026x991.htm) | 2026-11-24 16:01:55 | 2026-11-25 16:01:55 | `ec23d8c` | 2026-11-25 08:11:10 | 16.2 hours | yes |

Weeks with a report inside its window: 3 of 4 (Week 4, Week 5, Week 6). The top tier needs 3.

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
