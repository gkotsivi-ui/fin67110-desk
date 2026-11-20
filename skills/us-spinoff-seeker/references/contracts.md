# Input, evidence, scoring and output contracts

## Current user configuration

`spinoff_factors.json` is authoritative. It contains:

```json
{
  "window_days": 365,
  "early_return_days": 20,
  "factors": {
    "insider_ownership": {"weight": 0.25, "direction": "higher"},
    "relative_size": {"weight": 0.20, "direction": "lower"},
    "insider_buying": {"weight": 0.15, "direction": "higher"},
    "early_return": {"weight": 0.125, "direction": "lower"},
    "debt_to_assets": {"weight": 0.125, "direction": "lower"},
    "market_cap": {"weight": 0.10, "direction": "lower"},
    "analyst_count": {"weight": 0.00, "direction": "lower"},
    "unwanted_selling": {"weight": 0.00, "direction": "higher"}
  }
}
```

The loader also supports the original list of factor objects. PDF mode is available only when selected directly or by a JSON source_pdf pointer. It reads the PDF table, window and horizon every time, records the path/SHA-256, and stops if parsing fails. It never falls back to an example model. The supplied PDF's 180-day variant is an alternative, not the selected 365-day default.

Internal names differ from display names:

| Configured name | Internal observation |
|---|---|
| insider_ownership | insider_ownership_pct |
| relative_size | size_relative_to_parent |
| insider_buying | insider_buying |
| early_return | early_price_performance |
| debt_to_assets | debt_to_assets |
| market_cap | absolute_market_cap |
| analyst_count | analyst_recommendations |
| unwanted_selling | unwanted_selling_pressure |

Reports use the configured names. Snapshots preserve both names. Unknown factors remain missing; do not invent an observation. Add tests before adding another extraction rule.

## Evidence and calculations

Core facts have value, filing URL, accession, form, filed date, section and quote. Unknown facts are null. Parsed dates retain the full explicitly stated year. Ratios stay literal. Same-day conflicts remain blank; a newer filing can resolve them, with the old observations retained in history.

The factor engine accepts clear HTML tables, including a single ownership percentage column and a single pro-forma column. Complex spans, multiple pro-forma entities, missing totals, bounds rather than values, ambiguous share classes, and unsupported layouts stay unavailable. PDFs are a manual-review limitation. Form 4 XML is retained with its original content.

| Factor | Observation and source requirement |
|---|---|
| Insider ownership | Group percentage explicitly reported in the Form 10 information statement. Do not add individual holdings or turn `<1%` into 1%. |
| Relative size | `(child shares × child first close) / (parent shares × parent close on the child's first-close date)`. Use the latest eligible reported count for each company on or before that valuation date; disclose its observation date, filing date and filing. |
| Insider buying | Count of disclosed code-P transactions, transaction date on/after distribution and no later than as-of, across the complete scanned issuer history. Duplicated exhibits of the same accession are deduplicated by transaction position. Amended or malformed filings require review. |
| Early return | `close at interval 20 / first close - 1`, requiring first close plus 20 later source trading observations. No substitution of a shorter or latest return. |
| Debt/assets | `explicit total debt / explicit total assets` from one pro-forma column in the registration; denominator must be positive. Never use only long-term debt as total debt. |
| Market cap | Latest eligible reported common-share count on or before the price date × first regular-symbol close after distribution. Disclose the count’s observation date, filing date and filing. |

Both cap calculations retain share-count quotations and dated prices. Prices are in the source's units; no FX conversion is performed. A known currency mismatch leaves relative size unavailable. Missing quote-currency/share-class details are data limitations, not a license to infer them. The reader supplies first/last/horizon/parent price dates; all used dates appear on the report's first line.

Code P can represent private as well as open-market purchases, of derivative or non-derivative securities. The factor is a disclosed-P count, not a certification that every transaction was an open-market common-share purchase. Zero requires complete scanned coverage and means zero observed transactions, not zero possible late disclosures. A failed history/filing read cannot be turned into zero.

## Scoring

Retained names with trading evidence and distribution-day offsets 1 through window_days enter the window. Only a missing distribution date makes a name unranked. A missing factor or source gives that factor zero points; print its value as blank with the reason. A missing record date alone does not block a known distribution window. No values are imputed; weights are not redistributed.

The report prints each configured weight and whether it requires an observation. Use the actual run configuration: the current analyst_count and unwanted_selling weights are zero, need no source and appear under “What the data cannot show.” A positive-weight factor with a blank value still receives zero points without blocking the name’s ranking. A blank extraction result means the pipeline did not establish a usable observation; it does not prove that the filing lacks the fact. Report unsupported layouts, ambiguous evidence, coverage gaps and incompatible dates as review limits.

Group ownership can use an explicit terminal percentage split across number and percent-sign cells when the table has one percentage heading. Bounds and multiple share-class percentage columns remain unresolved. For Form 4 and 4/A, read ownership XML rather than index-header HTML or the combined submission wrapper; missing XML leaves coverage incomplete. An unresolved amendment still prevents a transaction count.

An incorporation date or a record date is not a distribution date merely because it is the only date in a distribution-related paragraph. Recognize explicit date-then-record-date wording. For an 8-K release that says completion was "today," resolve the date only from one unambiguous, explicitly dated release dateline; never substitute the filing date. A reviewed distribution-date correction invalidates the previously selected first close and its dependent factors until they can be recomputed.

For each factor, compare a name with an observed value with every other name that has an observed value for that factor. Count wins in the configured direction and one-half per tie. Divide by the number of other names and multiply by the factor weight. A sole name receives its full factor weight. Zero-weight factors receive zero points without requiring observations. Sum points; highest total ranks first, equal totals share a rank, and CIK breaks display-order ties only. Scores are relative to the observed-value cohort for each factor. Blank values receive zero points and do not enter numerical comparisons; do not estimate values or redistribute weights.

## Coverage, bounded runs and resume

The distribution start date is inclusive and is not the registration cutoff. Default index discovery starts at 1994Q3; `--index-start` can narrow that history but must be disclosed as partial discovery. Parent and child 8-K reads are restricted to the distribution-search date range; older registrations remain available. This avoids repeatedly reading decades of unrelated 8-Ks. The first full-discovery index scan may still be large.

`--max-candidates 25` caps the number of newly processed names in one invocation. It saves a PARTIAL report and pending CIKs. Repeat the identical dated command with `--resume` to continue. Use an explicit `--as-of` when resuming across calendar days. Completed candidates are skipped only for matching start, as-of, factors, reader mode and source-code hashes. Remove --resume for a fresh intraday refresh. The checkpoint is a processing checkpoint, not a statement that every fact was found. Changed source data without changed dates/configuration requires a refresh rather than reusing the checkpoint.

Current index/submissions requests refresh. Historical responses cache for seven days. A shared gate spaces all seeker requests, redirects and bounded retries below five requests/second. Other tools' SEC traffic is not managed; avoid simultaneous bulk SEC jobs. Only HTTPS SEC hosts are permitted. SEC request headers always carry the configured User-Agent.

`--no-prices` suppresses reader calls. A historical --as-of rebuild is not a perfect historical replay: later SEC corrections and current issuer identity can affect what is accessible. The report states unreadable indexes, exhibits, histories, unconfirmed parent CIKs, unsupported patterns and source gaps.

## Outputs

- `registry.json`: core facts, histories, exclusions, stages, factor facts, calculated observations, dated prices and checkpoint metadata.
- `progress.json`: total candidate count, newly processed/resumed counts, last completed CIK and update timestamp.
- `Spinoffs, YYYY-MM-DD, HH-MM-SS.ffffff, start YYYY-MM-DD.md`: actual run/price/index dates on line one; as-of separately; partial notice when needed; window ranks with parent, distribution date, window end, dated prices and factor points; unranked names; watch list; other stages; excluded names with sources; observed facts/inputs and limitations.
- Corresponding `.json`: exact run settings, registry snapshot, index URLs and limitations.

Last report line: `screens, not recommendations`.

## Rule coverage

`tests/test_seeker.py` covers indexes/forms and column offsets, older registrations, headers and request gating, retries/redirect limits, SEC-only requests, folder exhibits/XML/PDF limitations, registry provenance/blanks/conflicts, exclusion classes and reinstatement, parent CIK resolution, own-list trading proof, U.S. listing evidence, stages and inclusive boundaries, price dates and when-issued rejection (child and parent), user weights/aliases/horizon/zero weights, scoring/ties/missing values, header/row/disclaimer layout, registry persistence, bounded/resumed runs and full synthetic six-factor scoring.

`tests/test_factor_data.py` covers group ownership, bounds, source-date ambiguity, pro-forma column selection, periodic-report exclusions, missing totals, eligible earlier child/parent share counts, publication cutoffs and same-date prices for caps, known currency mismatch, Form 4 issuer/range/code filters, derivatives, duplicate exhibits, incomplete coverage/zero counts, unresolved amendments and parent ticker evidence.

Before changing a rule, change or add its made-up failing test, then implement the rule. Tests never use live EDGAR filings, companies or closes.

## Share-count selection

Select the latest observation date on or before the price date among counts filed on or before that price date; resolve repeated observations using the latest eligible filing, and leave same-date unresolved conflicts blank. Do this independently for child and parent. Disclose the count, its observation date, filing date and source filing. Do not estimate changes between the observation date and price date. The two requested zero weights leave the other weights unchanged; their total is 0.95 and is not normalized.

Report and JSON snapshot names share exactly the same base: `Spinoffs, YYYY-MM-DD, HH-MM-SS.ffffff, start YYYY-MM-DD`. Dates and runtime come from run metadata, not file modification times. A reviewed copy retains the original run identity and adds `, reviewed` to both files. Microseconds distinguish runs started in the same second. Registry/progress files are shared state, and standalone audits retain their descriptive matching names.

This is a learning exercise, not financial advice.

AI assistance: OpenAI Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
