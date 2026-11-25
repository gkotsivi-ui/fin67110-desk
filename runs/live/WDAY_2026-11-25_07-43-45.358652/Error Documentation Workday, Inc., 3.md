# Error Documentation Workday, Inc., 3

Observed 2 confirmed errors and 4 unconfirmed errors.
Confirmed errors have code evidence. Unconfirmed errors require more evidence.
Conclusion effects are stated per finding; this review does not certify the report.

- **Company:** Workday, Inc.
- **Ticker:** WDAY
- **Record Number:** 3
- **Run Folder:** runs/live/WDAY_2026-11-25_07-43-45.358652
- **Run Time:** 2026-11-25T07:43:45.358652-05:00
- **Outcome:** completed
- **Outcome Limit:** Artifact state only; historical stops need a saved log or separate attestation.
- **Record Type:** live
- **Review Time:** 2026-11-25T13:38:01.221853+00:00
- **Model:** Claude Code with claude-opus-5-5
- **Previous revision:** None

## Confirmed errors

### E-1cc9aef45ea2: Recorded stage failure

1. **Type of error:** Recorded stage failure
2. **Where in the process:** worksheet. Code location: Unknown.
3. **Description:** A part failed in a run that ended complete. The run was finished by a resume from this part, so the published output of this part comes from a later attempt.
   Observed: worksheet: FAIL; resumed at 2026-11-25T07:58:28.061402-05:00
   Expected: The part passes, or the run keeps its failure as the result.
4. **Why it happened:** Unknown

**Effect:** The published output of this part comes from a later attempt.
**Uncertainty:** Cause certainty is separate from error certainty.
**Previous error pattern:** none

**Evidence:**
  - `run/desk_run.json:619`:       "status": "FAIL",

### E-93b8994c2a14: Hook refusal

1. **Type of error:** Hook refusal
2. **Where in the process:** Hook. Code location: Unknown.
3. **Description:** The hook refused a saved output. The record does not establish whether the output or the hook's rule was at fault.
   Observed: Spinoff worksheet, WDAY, 2026-11-25, 07-43-45.358652.md | 39 | Spelled-out number needs an explicit sourced numeric claim: zero | Next filing: If the next quarterly report's cover page states an actual shares-outstanding count, and its condensed consolidated balance sheet states cash and total debt explicitly, the worksheet can compute the low case. If the price then sits at or below the low case, the price-against-value criterion would move off zero. Separately, any insider report showing open-market purchases would give the insider criterion something to score, though without a distribution it would not restore a spinoff thesis.
   Expected: The output passes the hook, or the run keeps the refusal as its result.
4. **Why it happened:** Unknown

**Effect:** The part whose output was refused stopped.
**Uncertainty:** Cause certainty is separate from error certainty.
**Previous error pattern:** none

**Evidence:**
  - `run/hook/00056.json:62`:       "Spelled-out number needs an explicit sourced numeric claim: zero",
  - `run/hook/00057.json:67`:       "Spelled-out number needs an explicit sourced numeric claim: zero",

## Unconfirmed errors

### E-7f58a246ee45: Verifier finding

1. **Type of error:** Verifier finding
2. **Where in the process:** Verification. Code location: Unknown.
3. **Description:** The saved Verifier flags a claim. Its mark is not independent proof of an error.
   Observed: $2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014]: wrong. The Verifier's reason: $2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014] is LongTermDebtNoncurrent as of 2026-01-31 (FY2026 10-K, filing 0001327811-26-000014), labeled excluding current maturities. The Funding risk paragraph dates it correctly. The Insight, however, sets it against liquidity of $5.643 billion [earnings_release_Ex99-1.txt:L31] as of October 31, 2026 as if both described the current funding position. The debt figure predates the $2.5 billion [earnings_release_Ex99-1.txt:L71] of senior notes issued in Q3 FY2027 (earnings_release_Ex99-1.txt:L71), so this comparison mixes periods.
   Expected: In the Insight, date $2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014] as noncurrent long-term debt at January 31, 2026, before the $2.5 billion [earnings_release_Ex99-1.txt:L71] of senior notes issued in Q3 FY2027. Do not present it as current debt against the October 31, 2026 liquidity of $5.643 billion [earnings_release_Ex99-1.txt:L31]. Debt at October 31, 2026 is not established by the supplied evidence.
4. **Why it happened:** Unknown

**Effect:** Effect unknown
**Uncertainty:** Check the claim, its source, and its period independently.
**Previous error pattern:** none

**Evidence:**
  - `run/nodes/Verifier/output.json:2718`:         "reason": "$2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014] is LongTermDebtNoncurrent as of 2026-01-31 (FY2026 10-K, filing 0001327811-26-000014), labeled excluding current maturities. The Funding risk paragraph dates it correctly. The Insight, however, sets it against liquidity of $5.643 billion [earnings_release_Ex99-1.txt:L31] as of October 31, 2026 as if both described the current funding position. The debt figure predates the $2.5 billion [earnings_release_Ex99-1.txt:L71] of senior notes issued in Q3 FY2027 (earnings_release_Ex99-1.txt:L71), so this comparison mixes periods.",

### E-86fb87822f51: Verifier finding

1. **Type of error:** Verifier finding
2. **Where in the process:** Verification. Code location: Unknown.
3. **Description:** The saved Verifier flags a claim. Its mark is not independent proof of an error.
   Observed: $2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014]: wrong. The Verifier's reason: $2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014] is LongTermDebtNoncurrent as of 2026-01-31 (filing 0001327811-26-000014). The Advisor gives it without a date, right after saying $2.5 billion [earnings_release_Ex99-1.txt:L71] of senior notes was issued in the latest quarter. That placement implies it is current debt that reflects the issuance, but the figure predates the Q3 FY2027 notes.
   Expected: Noncurrent long-term debt was $2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014] at January 31, 2026 (FY2026 10-K), before the $2.5 billion [earnings_release_Ex99-1.txt:L71] of senior notes issued in Q3 FY2027. Debt at October 31, 2026 is not established by the supplied evidence.
4. **Why it happened:** Unknown

**Effect:** Effect unknown
**Uncertainty:** Check the claim, its source, and its period independently.
**Previous error pattern:** none

**Evidence:**
  - `run/nodes/Verifier/output.json:3400`:         "reason": "$2.987 billion [XBRL tag LongTermDebtNoncurrent, period end 2026-01-31, filing 0001327811-26-000014] is LongTermDebtNoncurrent as of 2026-01-31 (filing 0001327811-26-000014). The Advisor gives it without a date, right after saying $2.5 billion [earnings_release_Ex99-1.txt:L71] of senior notes was issued in the latest quarter. That placement implies it is current debt that reflects the issuance, but the figure predates the Q3 FY2027 notes.",

### E-2074dcd31099: Formatting error

1. **Type of error:** Formatting error
2. **Where in the process:** Worksheet judgment, as printed in the final report. Code location: Unknown.
3. **Description:** The worksheet section of the published report prints its label twice: 'Insight: Insight:'.
   Observed: Insight: Insight: the annual report's consolidated statements of cash flows show depreciation and amortization ...
   Expected: One label, 'Insight:', followed by the sentence.
4. **Why it happened:** Suspected: the worksheet's model began its insight with 'Insight:', and the worksheet code adds the label again (skills/spinoff-worksheet/scripts/worksheet.py, line 538)

**Effect:** Wording only. No number, mark or view changes.
**Uncertainty:** The worksheet's saved model output, which shows the label at the start of the model's own text, is not in this review's evidence list. The code location was read in the repository, not in the run folder.
**Previous error pattern:** none

**Evidence:**
  - `run/final_report.md:401`: Insight: Insight: the annual report's consolidated statements of cash flows show depreciation and amortization

### E-2ef1f613b9a3: A check rule that read a score as an amount (suspected false refusal)

1. **Type of error:** A check rule that read a score as an amount (suspected false refusal)
2. **Where in the process:** Hook: the worksheet's number check. Code location: Unknown.
3. **Description:** The hook refused the word 'zero' in the worksheet's 'Next filing' line, which said that the price-against-value criterion 'would move off zero'. There 'zero' is that criterion's score, which the worksheet's own table states as 0, computed in code. The hook treats a number word as a financial amount when a financial word stands in the 50 characters before it in the same sentence, and 'price-against-value' contains 'price'.
   Observed: Spelled-out number needs an explicit sourced numeric claim: zero
   Expected: A criterion score that code computed and the worksheet prints is not refused as an unsourced amount, or the worksheet's prose does not spell out numbers.
4. **Why it happened:** Suspected: hooks/worksheet_numbers.py, financial_word_numbers(): its FINANCIAL_CONTEXT words include 'price', which also matches inside 'price-against-value'

**Effect:** The run stopped after the team's report was finished and checked. It was finished with desk.py --resume; the second worksheet text says 'move off absent' and passed.
**Uncertainty:** Whether a score word should pass the hook is a design decision for the team. The record alone does not show whether the worksheet's wording or the hook's rule was at fault.
**Previous error pattern:** none

**Evidence:**
  - `run/hook/00056.json:62`: Spelled-out number needs an explicit sourced numeric claim: zero
  - `run/hook/00056.json:63`: Next filing: If the next quarterly report's cover page states an actual shares-outstanding count
  - `run/final_report.md:397`: Criterion 3 — Price against value: 0 (computed in code)
  - `run/final_report.md:394`: the price against value criterion would move off absent

## Completed checks and review limits

- Runtime logs: not checked. No saved run log. Historical failures cannot be independently reconstructed.
- Calculations: not checked. No valid saved ratios list.
- Annual filing provenance: partly checked. 0 current fact accession numbers compared; filing selection not certified.
- SEC selection: not checked. No saved steps output with quarter selection provenance.
- Verifier and numerical evidence: partly checked. 260 saved Verifier checks read (correct 258, wrong 2). Existing Verifier marks are not accepted as independent proof.
- Hook: checked. 60 saved hook records read; 2 record a refusal.
- Seeker: not checked. No saved output. Absence is not proof of an error.
- Worksheet: available for model review. view.json
- Conclusions: not checked. Requires model or agent review of cited evidence; price reactions are not proof.
- Previous error patterns: leads collected. 17 historical leads. New evidence is required for every repeated error.
- Agent-declared scope: attested. Claude Code (claude-opus-5-5) compared the eleven core claims in run/final_report.md with the saved filings. Claims 1 to 6 and 8 match the 10-K's statements: total revenues 9,552 and 8,446 (10-K.txt lines 1855-1857), operating income 721 (1890-1891), net income 693 (1908-1910), diluted EPS 2.59 (1922-1924), total stockholders' equity 7,805 and 9,034 (1824-1826), cash from operations 2,939 (2344-2345) and capital expenditures 162 (2367-2369). Claims 9 to 11 match the release: total revenues 2,705 and 2,432 (earnings_release_Ex99-1.txt lines 265-267) and diluted EPS 0.96 (346-348). Code recomputed the growth, margin, return and free cash flow from these lines, and each agrees with the report.
- Agent-declared scope: attested. Claim 7, debt to equity, is left out with its reason. The 10-K's balance sheet has one debt line, 'Debt, noncurrent' 2,987 (10-K.txt lines 1746-1747), and its XBRL facts hold no current debt line and no LongTermDebt total, which the desk's rule needs before it states a zero current portion. This is an omission with an accurate reason, not an error.
- Agent-declared scope: attested. The Verifier's two 'wrong' marks were read against the saved texts. The $2.987 billion is the 10-K's noncurrent debt at January 31, 2026 (the balance sheet's dates are at 10-K.txt lines 1669-1671), and the release reports $2.5 billion of senior notes issued since then (earnings_release_Ex99-1.txt line 71). The saved filings support both marks, and both sentences were left out of the published report.
- Agent-declared scope: attested. The resume was the team's decision after the stop. The failed worksheet attempt is kept unchanged in earlier_attempt/; its files are outside this review's evidence list, and the hook record quotes the refused line.
- Agent-declared scope: attested. The view is 'not computed' because the 10-K's cover gives no exact share count (known limit 7 in the README). That is the worksheet's rule working, not an error.
- Model review: completed with limits. Proposals have checked citations; semantic claims remain unconfirmed without independent code proof.

## Unavailable evidence and incomplete checks

- Saved artifacts only. No SEC network requests were made.
- Closes, exports, credentials, and unknown artifacts are excluded from model input.
- Agreement with saved facts does not independently establish that the original filing selection was correct.
- The report is not certified correct by the absence of findings.

Evidence paths beginning with `run/` refer to the saved run folder.
Evidence paths beginning with `history/` refer to the supplied previous-report folder.

This is a learning exercise, not financial advice.

AI assistance: OpenAI Codex and Claude Code (review software) and Claude Code with claude-opus-5-5 (review analysis). I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
