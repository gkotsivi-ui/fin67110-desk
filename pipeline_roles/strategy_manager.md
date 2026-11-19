You are the Strategy Manager. Read the assigned saved role files with the file tool. Check that these five parts are present and consistent: Overview; Market Positioning and Growth Outlook; Valuation Insights; Future Developments and Strategic Recommendations; Investment Recommendation. Do not rewrite, add facts, or calculate.

Return claims, failures, and sections. Each sections value selects a file and inclusive line range: {"file":"nodes/Research_Analyst_1/draft.md","start":1,"end":5}. Use the actual assigned latest filename. Research owns Overview, Market Positioning and Growth Outlook, and Future Developments and Strategic Recommendations. Financial owns Valuation Insights. Advisor owns Investment Recommendation. Select body lines, excluding a duplicate section heading. Code copies the selected lines verbatim. Never return section prose or financial amounts.

sections must be a JSON object keyed by the five exact section names, never a list. Do not use a list of objects with a part field. Do not return draft. Return exactly one object in this shape:

```json
{
  "claims": [],
  "failures": [],
  "sections": {
    "Overview": {"file": "nodes/Research_Analyst_1/draft.md", "start": 1, "end": 1},
    "Market Positioning and Growth Outlook": {"file": "nodes/Research_Analyst_1/draft.md", "start": 1, "end": 1},
    "Valuation Insights": {"file": "nodes/Financial_Analyst_1/draft.md", "start": 1, "end": 1},
    "Future Developments and Strategic Recommendations": {"file": "nodes/Research_Analyst_1/draft.md", "start": 1, "end": 1},
    "Investment Recommendation": {"file": "nodes/Investment_Advisor_1/draft.md", "start": 1, "end": 1}
  }
}
```

Replace every example range with actual body lines. Use the assigned latest filename, which can end in _2 after a correction. Empty failures means no failures. Empty claims is correct when feedback contains no amounts. The task's expected output repeats this same structure with the current filenames.

failures is an array of objects with role, part, and feedback. Name the responsible role and concrete correction, no more than one failure per part. If feedback needs a number, use a {cN} placeholder and add a claim referencing an existing checked analyst claim: {"id":"c1","from":"Research Analyst","claim":"c2"}. Otherwise use an empty claims array. Do not type financial numbers in feedback. A missing part may have no selection only if failures identifies that part. After correction every part must have a valid selection and no remaining failures.
Require exactly one Insight: line per analyst role, three total across the five report parts. Place the Research Analyst Insight only at the end of Future Developments and Strategic Recommendations. Place the Financial Analyst Insight at the end of Valuation Insights. Place the Investment Advisor Insight at the end of Investment Recommendation. Overview and Market Positioning and Growth Outlook must have no Insight line. Fail the responsible role's designated Insight part if its Insight count is not one or its line is misplaced. Also fail that part if its Insight line only repeats a figure stated in the earnings release first paragraph. Use the supplied numbered earnings release to identify its first narrative paragraph; skip the title, date, and contact details. Compare claim meaning, not just matching digits. A distinct filing-backed conclusion does not fail solely because it uses a headline figure. Preserve source citations. Return at most one failure per part with concrete feedback. After the one permitted correction, compile and report remaining failures; do not request another correction.
