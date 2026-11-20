# Audits

Four tables: two of our own live reports, then the two reports our run of another team's desk produced at
the exchange. Each report is audited against the filings it names on its first line, as the course's
[report audit](https://cinderzhang.github.io/FIN67110-Fall2026/reference/audit-checklist.html) says. Marks:
Correct, Wrong, Unsupported, Missing, Not in filings. Errors are wrong plus unsupported.

> **Draft, 2026-11-19. Delete this box before the upload.** Claude Code read every "Filing says" figure
> from the filing text saved in the run folder (the "Where" column gives the statement and the line of
> that text) and recomputed every ratio in code at the report's rounding. All 46 recomputed numbers agree.
> Before the upload a member checks each row against the filing on EDGAR: two wrong marks in one table
> fail "Audits hold". Three things are for the team to settle, each marked * below:
> 1. Each P/E uses a close, which is not a filing number. The course's data page says "the filing and the
>    exchange decide": check the official close in LSEG Workspace or on the exchange, then remove the *.
> 2. NVIDIA's cash flow statement has one capital-spending line, "Purchases related to property and equipment
>    and intangible assets". The audit defines free cash flow with additions to property and equipment. The
>    filing has no separate figure, so the draft marks claim 8 correct and names the definition; the team decides.
> 3. The counts at the top of each table hold only if the team agrees with every mark.

## 1. Week 4 live report: Cisco Systems (CSCO)

Errors: 0. Missing: 0. (Draft counts; see the box above.)

Report: [`runs/live/CSCO_20261113_093231/report.md`](runs/live/CSCO_20261113_093231/report.md), committed
in `88015f7`. Filings: 10-K 0000858877-26-000132 (fiscal year ended 2026-07-25) and the 8-K
0000858877-26-000170, Exhibit 99.1 (quarter ended 2026-10-24). "10-K L" and "release L" are line numbers of
the saved text `10K_2026-09-02_csco-20260725.txt` and `8K_2026-11-12_exhibit991pressrelease-q1f.txt` in the
run folder. Amounts in $ millions, except per share.

| # | Claim | Report said | Filing says | Mark | Where |
|---|---|---|---|---|---|
| 1 | Total revenue, FY2026 | $63,325.0M | $63,325 | Correct | 10-K Consolidated Statements of Operations, "Total revenue", L1076 |
| 2 | Revenue growth | 11.77% | 63,325 / 56,654 − 1 = 11.77% | Correct | Computed, 10-K L1076 |
| 3 | Operating income and operating margin | $15,368.0M; 24.27% | $15,368; 15,368 / 63,325 = 24.27% | Correct | 10-K Statements of Operations, "OPERATING INCOME", L1089 |
| 4 | Net income attributable to Cisco | $13,267.0M | $13,267 | Correct | 10-K Statements of Operations, "NET INCOME", L1096; no noncontrolling interest |
| 5 | Diluted EPS, GAAP | $3.33 | $3.33 | Correct | 10-K Statements of Operations, "Net income per share:", "Diluted", L1099 |
| 6 | Return on average equity | 27.32% | 13,267 / ((50,285 + 46,843) / 2) = 27.32% | Correct | 10-K Consolidated Balance Sheets, "Total equity", L1064 |
| 7 | Debt to equity | 0.455 | (19,372 + 3,500) / 50,285 = 0.455 | Correct | 10-K Balance Sheets, "Long-term debt", L1052; Note 11 Borrowings, "Current portion of long-term debt", L1826 |
| 8 | Free cash flow | $12,767.0M | 14,177 − 1,410 = 12,767 | Correct | 10-K Consolidated Statements of Cash Flows, L1147 and "Acquisition of property and equipment", L1155 |
| 9 | Quarter revenue | 18,517 | 18,517 | Correct | Release, Consolidated Statements of Operations, "Total revenue", L94 |
| 10 | Quarter growth | 24.42% | 18,517 / 14,883 − 1 = 24.42% | Correct | Computed, release L94 |
| 11 | Quarter diluted EPS, GAAP | $1.14 | $1.14 | Correct | Release, "Net income per share:", "Diluted", L117 |
| - | Total revenue, FY2025 (report L55) | $56,654.0M | $56,654 | Correct | 10-K L1076 |
| - | Operating income, FY2025 (L58) | $11,760.0M | $11,760 | Correct | 10-K L1089 |
| - | Operating income growth (L60) | 30.68% | 15,368 / 11,760 − 1 = 30.68% | Correct | Computed, 10-K L1089 |
| - | Net income, FY2025 (L61) | $10,180.0M | $10,180 | Correct | 10-K L1096 |
| - | Net income growth (L63) | 30.32% | 13,267 / 10,180 − 1 = 30.32% | Correct | Computed, 10-K L1096 |
| - | Diluted EPS, FY2025 (L64) | $2.55 | $2.55 | Correct | 10-K L1099 |
| - | Diluted EPS growth (L66) | 30.59% | 3.33 / 2.55 − 1 = 30.59% | Correct | Computed, 10-K L1099 |
| - | Operating margin, FY2025 (L70) | 20.76% | 11,760 / 56,654 = 20.76% | Correct | Computed |
| - | Net margin, FY2026 and FY2025 (L71) | 20.95%; 17.97% | 20.95%; 17.97% | Correct | Computed, 10-K L1076 and L1096 |
| - | Stockholders' equity, both year-ends (L75) | $50,285.0M; $46,843.0M | $50,285; $46,843 | Correct | 10-K Balance Sheets, L1064 |
| - | Return on year-end equity (L78) | 26.38% | 13,267 / 50,285 = 26.38% | Correct | Computed; labelled the alternative measure |
| - | Long-term debt and its current portion, both years (L83 to L85) | $19,372.0M, $3,500.0M; $22,861.0M, $1,750.0M | the same | Correct | 10-K Note 11 Borrowings, L1826 and L1827 |
| - | Debt to equity, FY2025 (L86) | 0.525 | (22,861 + 1,750) / 46,843 = 0.525 | Correct | Computed |
| - | Cash from operations, both years (L90) | $14,177.0M; $14,193.0M | $14,177; $14,193 | Correct | 10-K Statements of Cash Flows, L1147 |
| - | Cash from operations growth (L92) | −0.11% | −0.11% | Correct | Computed |
| - | Additions to property and equipment, both years (L93) | $1,410.0M; $905.0M | (1,410); (905) | Correct | 10-K Statements of Cash Flows, L1155 |
| - | Growth of those additions (L95) | 55.80% | 1,410 / 905 − 1 = 55.80% | Correct | Computed |
| - | Free cash flow, FY2025 (L96) | $13,288.0M | 14,193 − 905 = 13,288 | Correct | Computed |
| - | Free cash flow growth (L97) | −3.92% | 12,767 / 13,288 − 1 = −3.92% | Correct | Computed |
| - | Free cash flow margin (L98) | 20.16% | 12,767 / 63,325 = 20.16% | Correct | Computed |
| - | Free cash flow / net income (L99) | 0.96 | 12,767 / 13,267 = 0.96 | Correct | Computed |
| - | Quarter revenue, same quarter last year (L108) | 14,883 | 14,883 | Correct | Release L94 |
| - | The release's rounded growth (L110) | 24% | "Increase of 24% year over year" | Correct | Release L16 |
| - | Quarter diluted EPS, same quarter last year (L113) | $0.72 | $0.72 | Correct | Release L117 |
| - | Quarter diluted EPS growth (L114) | 58.33% | 1.14 / 0.72 − 1 = 58.33% | Correct | Computed |
| - | The release's EPS growth (L115) | 58% | "Diluted Earnings per Share (EPS) \| $1.14 \| $0.72 \| 58%" | Correct | Release L35 |
| - | Quarter operating margin, GAAP and non-GAAP (L118) | 30.2%; 37.8% | "GAAP: 30.2%; Non-GAAP: 37.8%" | Correct | Release L17 |
| - | Non-GAAP EPS, labelled (L119) | $1.40 | $1.40 | Correct | Release L18 |
| - | P/E (L133) | 30.6 | 102.01 / 3.33 = 30.6; EPS from the 10-K | Correct* | 10-K L1099; the price is item 1 of the box |
| - | Price (L136) | $102.01, the close of 2026-11-12 | not a filing number | Correct* | The exchange's official close decides |
| Template | the five parts present | Overview (L9); Market Positioning and Growth Outlook (L40); Valuation Insights (L131); Future Developments and Strategic Recommendations (L158); Investment Recommendation (L180) | - | Correct | - |
| Recommendation | Hold, on free cash flow growth of −3.92% (L182 to L184) | The thesis (L186) uses numbers marked correct above, the release's Networking 43% (L48) and $9B (L13), the 10-K's inventory 80% and commitments 126% (L824), and the release's product gross margin 61.8% from 64.5% (L49) | - | Correct | - |

## 2. Week 5 live report: NVIDIA (NVDA)

Errors: 0. Missing: 0. (Draft counts; see the box above.)

Report: [`runs/live/NVDA_20261118_084439/report.md`](runs/live/NVDA_20261118_084439/report.md), committed
in `f55b170`. Filings: 10-K 0001045810-26-000021 (fiscal year ended 2026-01-25) and the 8-K
0001045810-26-000088, Exhibit 99.1 (quarter ended 2026-10-25). "10-K L" and "release L" are line numbers of
the saved text `10K_2026-02-25_nvda-20260125.txt` and `8K_2026-11-17_q3fy27pr.txt` in the run folder.
Amounts in $ millions, except per share.

| # | Claim | Report said | Filing says | Mark | Where |
|---|---|---|---|---|---|
| 1 | Total revenue, fiscal 2026 | $215,938.0M | $215,938 | Correct | 10-K Consolidated Statements of Income, "Revenue", L880 |
| 2 | Revenue growth | 65.47% | 215,938 / 130,497 − 1 = 65.47% | Correct | Computed, 10-K L880 |
| 3 | Operating income and operating margin | $130,387.0M; 60.38% | $130,387; 130,387 / 215,938 = 60.38% | Correct | 10-K Statements of Income, "Operating income", L887 |
| 4 | Net income attributable to NVIDIA | $120,067.0M | $120,067 | Correct | 10-K Statements of Income, "Net income", L894 |
| 5 | Diluted EPS, GAAP | $4.90 | $4.90 | Correct | 10-K Statements of Income, "Net income per share:", "Diluted", L897 |
| 6 | Return on average equity | 101.49% | 120,067 / ((157,293 + 79,327) / 2) = 101.49% | Correct | 10-K Consolidated Balance Sheets, "Total shareholders' equity", L957 |
| 7 | Debt to equity | 0.054 | (7,469 + 999) / 157,293 = 0.054 | Correct | 10-K Balance Sheets, "Short-term debt" L944 and "Long-term debt" L946; Note 11 Debt: net carrying amount 8,468, "Less short-term portion (999)", L1430 |
| 8 | Free cash flow | $96,676.0M | 102,718 − 6,042 = 96,676 | Correct* | 10-K Consolidated Statements of Cash Flows, L1016 and "Purchases related to property and equipment and intangible assets", L1024; the definition is item 2 of the box |
| 9 | Quarter revenue | 115,844 | $115,844 | Correct | Release, Condensed Consolidated Statements of Income, "Revenue", L95 |
| 10 | Quarter growth | 103.21% | 115,844 / 57,006 − 1 = 103.21% | Correct | Computed, release L95 |
| 11 | Quarter diluted EPS, GAAP | $2.70 | $2.70 | Correct | Release, "Net income per share:", "Diluted", L109 |
| - | Total revenue, fiscal 2025 (report L63) | $130,497.0M | $130,497 | Correct | 10-K L880 |
| - | Operating income, fiscal 2025, and its growth (L64) | $81,453.0M; 60.08% | $81,453; 130,387 / 81,453 − 1 = 60.08% | Correct | 10-K L887 |
| - | Net income, fiscal 2025, and its growth (L65) | $72,880.0M; 64.75% | $72,880; 64.75% | Correct | 10-K L894 |
| - | Diluted EPS, fiscal 2025, and its growth (L66) | $2.94; 66.67% | $2.94; 4.90 / 2.94 − 1 = 66.67% | Correct | 10-K L897 |
| - | Cash from operations, both years, and its growth (L67) | $102,718.0M; $64,089.0M; 60.27% | $102,718; $64,089; 60.27% | Correct | 10-K Statements of Cash Flows, L1016 |
| - | Capital spending, both years, and its growth (L68) | $6,042.0M; $3,236.0M; 86.71% | (6,042); (3,236); 86.71% | Correct* | 10-K L1024; the report calls the line "Additions to property and equipment"; the filing's line includes intangible assets (item 2) |
| - | Operating margin, fiscal 2025 (L77) | 62.42% | 81,453 / 130,497 = 62.42% | Correct | Computed; the 10-K states 60.4 and 62.4 (L640) |
| - | Net margin, both years (L78) | 55.60%; 55.85% | 55.60%; 55.85% | Correct | Computed, 10-K L880 and L894 |
| - | Return on year-end equity (L87) | 76.33% | 120,067 / 157,293 = 76.33% | Correct | Computed; labelled beside the average-equity figure |
| - | Stockholders' equity, both year-ends (L91) | $157,293.0M; $79,327.0M | $157,293; $79,327 | Correct | 10-K Balance Sheets, L957 |
| - | Total debt, and its two lines (L96 to L99) | $8,468.0M = 7,469.0 + 999.0 | $8,468 = 7,469 + 999 | Correct | 10-K L944, L946; Note 11, L1430 |
| - | Debt to equity, fiscal 2025 (L101) | 0.107 | (8,463 + 0) / 79,327 = 0.107 | Correct | 10-K L946; short-term debt "—" at 2025-01-26, L944 |
| - | Free cash flow, fiscal 2025 (L109) | $60,853.0M | 64,089 − 3,236 = 60,853 | Correct* | Computed; same definition as claim 8 |
| - | Free cash flow growth (L110) | 58.87% | 96,676 / 60,853 − 1 = 58.87% | Correct* | Computed |
| - | Free cash flow margin (L111) | 44.77% | 96,676 / 215,938 = 44.77% | Correct* | Computed |
| - | Free cash flow / net income (L112) | 0.81 | 96,676 / 120,067 = 0.81 | Correct* | Computed |
| - | Quarter revenue, same quarter last year (L129) | $57,006M | $57,006 | Correct | Release L95 |
| - | The release's rounded growth (L131) | 103% | "up 103% from a year ago" | Correct | Release L6 |
| - | Quarter diluted EPS, same quarter last year, and growth (L135, L136) | $1.30; 107.69% | $1.30; 2.70 / 1.30 − 1 = 107.69% | Correct | Release L109 |
| - | Non-GAAP diluted EPS, labelled (L137) | $2.68 | "$2.70 and $2.68, respectively" | Correct | Release L6 |
| - | Quarter gross margins, GAAP and non-GAAP (L140) | 74.8%; 74.9% | "74.8% and 74.9%, respectively" | Correct | Release L6 |
| - | Nine-month diluted EPS, both years (L141) | $7.55; $3.14 | $7.55; $3.14 | Correct | Release L109 |
| - | Nine-month revenue, both years (L142) | $293,681M; $147,811M | $293,681; $147,811 | Correct | Release L95 |
| - | P/E (L161) | 31.7 | 155.46 / 4.90 = 31.7; EPS from the 10-K | Correct* | 10-K L897; the price is item 1 of the box |
| - | Price (L162) | $155.46, the close of 2026-11-17 | not a filing number | Correct* | The exchange's official close decides |
| - | Earnings yield (L167) | 3.15% | 4.90 / 155.46 = 3.15% | Correct* | Computed; same price |
| Template | the five parts present | Overview (L9); Market Positioning and Growth Outlook (L40); Valuation Insights (L156); Future Developments and Strategic Recommendations (L190); Investment Recommendation (L211) | - | Correct | - |
| Recommendation | Buy, on a P/E of 31.7 (L213 to L215) | The thesis (L217) uses numbers marked correct above, the 10-K's customer shares 22% and 14% (L670), and the release's guidance "$130.0 billion, plus or minus 3%" (L31) | - | Correct* | Depends on the price behind the P/E |

## 3. The exchange: [the other team's name], [company 1]

[One line, written as it happened: the command we ran, the date, and whether we needed that team's help.]

Errors: [ ]. Missing: [ ].

[The same table, for the report our run of that team's desk produced on 2026-11-24.]

## 4. The exchange: [the other team's name], [company 2]

Errors: [ ]. Missing: [ ].

[The same table.]

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
