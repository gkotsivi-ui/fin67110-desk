---
name: us-spinoff-seeker
description: Find U.S. spinoffs on SEC EDGAR from a distribution start date, maintain filing-sourced registry facts, and rank the post-distribution window using the user's factor file. Use for spinoff discovery, registry refreshes, watch lists and dated screening reports, not recommendations.
---

# U.S. spinoff seeker

Use `scripts/seeker.py`. Keep EDGAR and prices out of tests: use invented documents and injected clients/readers. No source is accessed at import. The default `.env`, closes reader and output directory are in ``. Never add a real company name or a known answer to code or fixtures.

## Inputs and commands

Require an inclusive distribution start date and a user-authored factor specification. The current `spinoff_factors.json` is the user's explicit configuration: window 365 calendar days, early return 20 trading-day intervals, and eight named factors with their supplied weights/directions. Preserve it. Accept direct JSON, a PDF, or a JSON `source_pdf` pointer. Do not silently replace missing input with demonstration weights. See [contracts](references/contracts.md) for sources, calculations, aliases and limitations.

From this repository root:

```bash
.venv-desk/bin/python skills/us-spinoff-seeker/scripts/seeker.py --start YYYY-MM-DD --factors spinoff_factors.json
```

Full discovery scans form indexes from 1994Q3, so registrations before the distribution start date are not silently excluded. A first scan may be large. To process a bounded batch, add `--max-candidates 25`. To continue the same dated snapshot, add `--resume` and use the same start, as-of date, output directory, and factor file. Resume skips completed candidates, not unread candidates. Source-code or factor changes invalidate checkpoints. `--resume` is not a fresh intraday refresh; omit it for a refresh. The report labels a stopped batch PARTIAL and records pending CIKs. `progress.json` holds counts and the last completed CIK. Each candidate is saved atomically before moving on.

`--index-start YYYY-MM-DD` explicitly narrows discovery and can miss earlier registrations. Report that limit. `--as-of YYYY-MM-DD` restricts filings and closes to that date; this is not a perfect historical reconstruction of corrected SEC data. `--no-prices` suppresses reader calls and leaves price-dependent factors unavailable. Do not launch a scan or call the reader solely to validate this skill without the user's authorization.

## EDGAR rules

- Use `SEC_USER_AGENT` from `.env` on every SEC request. All requests, redirects and bounded retries pass through `Edgar` and a workspace-wide serial rate gate, spaced at least 0.21 seconds apart. This is below the SEC's current 10 requests/second maximum. Do not bypass blocks or add parallel downloaders. Other tools' traffic is not managed by this gate; avoid simultaneous bulk SEC jobs.
- Read quarterly/full form indexes for Form 10, 10-12B, 10-12G, amendments, CERT and 8-Ks. Parse data rows independently of header offsets. Retain only needed form types in memory. Failed or unparseable indexes are missing coverage, never empty successful searches. Current indexes and submissions refresh; historical responses cache for seven days.
- Read registration folders' textual primary documents and exhibits. HTML/text and Form 4 XML are supported. PDF exhibits require manual review and prevent an automated conclusion that an information statement is absent. Unsupported wording stays unresolved.
- Read the parent's 8-Ks through the registry's parent CIK. Limit candidate and parent 8-K reads to the distribution-search start through as-of; retain older registrations and amendments. Do not download decades of unrelated 8-Ks. Use issuer submissions history, including older-history files, for the child's own 10-Q/10-K/Form 4 trading evidence.

## Registry and exclusions

Store parent name/CIK, distribution ratio, record date, distribution date and regular ticker only when a filing establishes them. Attach document URL, accession, filed date, section and quotation. Missing facts are null and named in the report. Do not infer a missing year, ratio, parent identity, distribution completion, or price. Store literal ratios. Same-day conflicts stay blank; later explicit statements can resolve them while preserving history.

Resolve a missing parent CIK only by an exact unique parent-name match followed by confirmation in the parent's filing index. Otherwise leave it blank and report that parent-history coverage is incomplete.

Drop a fully readable registration dossier with no information statement, a fund, or a registrant explicitly registering existing shares. Save the reason and filing. Do not treat an unreadable exhibit as proof of absence. Revisit drops; a later filing establishing that the parent distributes this specific business restores the candidate and preserves its exclusion history. An unrelated parent transaction is not evidence.

## Stages, dates and prices

Without trading evidence, use `registered` or `listing approved` (CERT). A 10-Q, 10-K or Form 4 in the child's own filing list is trading evidence under this screen; an insider's independently indexed Form 4 is not a substitute. CERT alone does not prove trading. Report U.S.-exchange evidence and any listing uncertainty. Missing listing evidence alone does not make a retained window name unranked.

With trading evidence but no distribution date, use `trading`. With both, calendar-day offsets 1 through `window_days`, inclusive, are `in its window`; greater offsets are `past it`. Distribution day itself is outside the window. Only a missing distribution date makes a retained name unranked. Missing factor inputs do not block window ranking; they receive zero points with a blank value and a reason. A missing record date alone does not block an established distribution window.

Use the existing `closes_reader.daily_closes`. First price is the earliest supplied regular-symbol close strictly after distribution. Reject when-issued tickers, explicit when-issued rows and vendor mappings such as `_w` or `.WI`, for both child and parent. Do not substitute a quote or distribution-day close. Every displayed price must have its date. Source gaps cannot prove the absolute first trade, and must be disclosed.

## Factors

`scripts/factor_data.py` extracts sourced observations and computes the five filing-based factors. Only unambiguous supported layouts are accepted:

- Insider ownership: the officers/directors group percentage from a Form 10 information-statement table, not a sum of individual rows. A bound such as `<1%` is not an exact value.
- Debt/assets: explicit total debt divided by total assets from the same single pro-forma column in the registration. Do not substitute long-term debt or an unrelated periodic-report acquisition table.
- Market cap: the latest explicit common share count reported on or before the first-close date, multiplied by that close. Its observation date must also be on or before the price date. Print the count, observation date, filing date and filing. Never guess a share class, unit or intervening change.
- Relative size: child cap divided by parent cap on that same price date. Use the latest eligible reported share count for each company, and disclose each count’s date and filing. Both regular prices must use the child’s first-close date. No FX conversion; known incompatible quote currencies leave the ratio unavailable.
- Insider buying: count disclosed code-P transactions since distribution from the issuer's complete scanned Form 4 history. Code P includes private purchases and derivatives; it does not alone prove open-market common-stock buying. Label that limit. Unknown XML, issuer mismatch, incomplete coverage or unresolved amendments leave the count unavailable. Zero is a count of observed filings, not proof that no undisclosed purchases occurred.

Early return uses the first close and the close 20 trading intervals later: 21 valid close observations are required. It is not the latest available return. Exact definitions, formulas, factor aliases and equal-weight tie handling are in the contracts. A missing factor observation receives zero points and prints “blank” with the reason. Do not estimate the observation or redistribute its weight. Compare observed values only with other observed values for that factor; a blank is not an estimated numerical zero. Zero-weight analyst count and unwanted selling require no observation and are listed under data limits.

## Report and verification

Save `registry.json` and `Spinoffs, YYYY-MM-DD, HH-MM-SS.ffffff, start YYYY-MM-DD.md` with a JSON run snapshot. The first line must identify actual run date, all price dates used, and latest readable index update date. Unknown dates are explicitly blank. A historical as-of date is shown separately, not mislabeled as run date.

Include ranked window rows with parent, distribution date, computed window end, dated prices, total points and points per configured factor; unranked names/reasons; registered-not-trading watch list; other stages; exclusions with reasons and filing/section; observed facts/inputs and data limits. A limited batch must be labeled PARTIAL near the top. The final line is exactly:

```text
screens, not recommendations
```

Do not call an empty or partial run proof that no spinoffs exist. Do not describe offline tests as a successful live screen. Preserve the existing analyst team and closes reader.

## Tests before changes

Before changing a screening rule, add or change its made-up-data test, observe the expected failure, then change the rule and rerun the suite. Do not edit a test merely to accept current behavior. Run:

```bash
.venv-desk/bin/python -m unittest discover -s skills/us-spinoff-seeker/tests -v
```

Tests cover individual rules, the complete six-factor report, and bounded/resumed runs without live services. The factor file is user input, not a recommendation.

## References

- [SEC indexes, nightly updates, rate and User-Agent requirements](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- [SEC submissions API and older filing histories](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC Form 4 transaction codes and amendments](https://www.sec.gov/files/form4.pdf)

Report and JSON snapshot names share exactly the same base: `Spinoffs, YYYY-MM-DD, HH-MM-SS.ffffff, start YYYY-MM-DD`. Dates and runtime come from run metadata, not file modification times. A reviewed copy retains the original run identity and adds `, reviewed` to both files. Microseconds distinguish runs started in the same second. Registry/progress files are shared state, and standalone audits retain their descriptive matching names.
