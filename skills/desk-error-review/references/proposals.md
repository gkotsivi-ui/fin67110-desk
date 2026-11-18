# Agent proposal contract

The current coding agent can review saved artifacts without a separate provider call. Save its proposals
outside the original run, for example under `docs/error-review-inputs/`. Supply the actual model identifier
when known. Otherwise state that the session identifier is unavailable; never invent it.

```json
{
  "findings": [
    {
      "type": "Conclusion conflict",
      "stage": "Investment conclusion",
      "description": "The conclusion may conflict with the cited evidence.",
      "observed": "A growth claim appears beside declining reported revenue.",
      "expected": "The conclusion must agree with the cited period and metric.",
      "cause": "Unknown",
      "effect": "Effect unknown",
      "uncertainty": "The comparison period needs independent confirmation.",
      "evidence": [
        {"path": "run/report.md", "line": 12, "quote": "Exact text from that line"}
      ],
      "prior_pattern": "none"
    }
  ]
}
```

`run/` paths are relative to the selected run. `history/` paths are relative to the history folder.
Quote the exact cited line or a nonempty substring. The publisher validates the path, line, and quote.
At least one reference must cite the current run. Historical reports alone cannot establish a current finding.
When relevant, set `prior_pattern` to the exact `history/filename.md` that motivated the check.

All model-only proposals remain unconfirmed, regardless of supplied status or confidence.
An optional `proof_id` can associate a proposal with an existing confirmed code finding. Its ID comes
from `Review.findings` after `deterministic()`. The model cannot change that finding's proof or cause.

Do not submit repair instructions for unconfirmed findings. Do not convert a missing optional stage,
an intentional omission, or a later stock price movement into an error. Explain missing evidence in limits.

Use `Review.packet()` to inspect the exact allowlist and numbered model context. Long documents use
selected windows. The metadata records omitted material. Read necessary saved evidence directly when
performing an agent review; state the review's actual scope in the published limits.
