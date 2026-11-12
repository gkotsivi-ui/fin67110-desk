# Live-record error documentation

Keep one error documentation file per live record in this folder, separate from the saved run artifacts.
Name it `Error Documentation [Company name, live record number].md`, replacing the bracketed contents
with the actual company name and live record number. Use the same wording as the document title.
Use the record's established number; if none exists, assign the next unused sequential number in this
folder and record the saved run path so that the association is unambiguous. Different runs of the same
company receive separate files.

Document observed errors without fixing them or changing the saved report, filings, facts, or logs.
Let the live run proceed according to its existing behavior. If it stops, preserve that result and
document the failure; do not bypass the stop. Fixes require a separate user request.

Review the full process. Examples include selecting the wrong SEC table or period based on a heading,
incorrect calculations or conclusions, parsing failures in the verifier, either skill or the hook,
numerical claims without evidence, type errors, value errors, and other unexpected failures. This list
is guidance, not a fixed set of permitted error types. An intentional omission with an accurate reason
is not automatically an error.

Each file identifies the company, ticker, live record number, run date, saved run folder, and outcome
(completed, stopped, or incomplete). State what was reviewed and what could not be checked. Do not
claim an unexecuted component passed. If no errors were observed, say so and describe the review's limits.

List every observed error separately using these four fields:

1. **Type of error:** a specific, plain-language classification.
2. **Where in the process:** the stage and relevant saved file, function, or output location.
3. **Description:** what happened, what the evidence supports instead, and the affected output. Include
   saved file references and filing identifiers, table headings, periods or traceback locations as relevant.
4. **Why it happened:** the cause supported by evidence. Label suspected causes as hypotheses; write
   "Unknown" when the available evidence does not establish the cause.

Keep licensed WRDS values out of these files and model sessions, including derived values. Do not
include secrets or personal credentials. Error documentation does not itself certify a report as correct.

End each document with the course footer, naming the tools actually used. Do not claim personal source
verification that has not occurred.

This is a learning exercise, not financial advice.

AI assistance: OpenAI Codex. Documentation setup only; no live-record source verification was performed.

Any remaining errors are my own.
