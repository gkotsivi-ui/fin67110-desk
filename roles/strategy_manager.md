The Strategy Manager is a checklist in code; it makes no model call.

It sends each analyst one JSON message with the task, the context and the expected output, and checks what comes back:

1. Research Analyst: every part has at least one claim; every claim quotes a line that appears word for word in the 10-K or the earnings release; a claim states no number that its quote does not contain.
2. Financial Analyst: the statement analysis, the latest quarter, the peer comparison and the valuation are present; every number appears in the context as the desk gave it; the valuation states the P/E when there is a price; every peer appears in the peer comparison. A ratio the analyst asks for is computed in code and sent back.
3. Investment Advisor: the recommendation is exactly Buy, Hold or Sell; the deciding number appears in the analysts' outputs; the thesis is present; every number appears in the analysts' outputs.

A part that fails goes back to its role one time only, with the problems listed. No role runs more than two times in one run. Then the Manager compiles the five parts (Overview; Market Positioning and Growth Outlook; Valuation Insights; Future Developments and Strategic Recommendations; Investment Recommendation) into the report, with the filings and their accession numbers on the first line and the run time on the second, and lists any problem still open at the end.
