---
name: spinoff-worksheet
description: Build a dated, filing-sourced investment worksheet from one saved equity-team run, with optional registry-linked spinoff filings, code-only cash-flow/valuation/liquidity calculations and one persona-guided judgment call.
---

# Spinoff worksheet

Use `scripts/worksheet.py` on one saved equity-team run folder. The run must contain `facts.json` with the ticker and CIK and its original filing texts. Do not rerun the agent graph, use its narrative report as a numerical source, or change the seeker's registry. Nothing in code or test fixtures names a real company.

The authored defaults are `spinoff-rules.md` and `persona-why-cheap.md`. Read them as inputs; never overwrite them or invent missing choices. The Markdown reader extracts the owner's stated rates, three-year averaging rule, combined depreciation/amortization definition, purchase size, liquidity sample and conviction policy. Stop before any external/model call if an actual FILL field is blank or the method is unsupported. An explicit JSON worksheet is also supported for a different authored method or exact statement selectors; see [the input contract](references/worksheet-contract.md). The JSON example is optional, not a replacement for the supplied Markdown rules.

From this repository root:

```bash
.venv-desk/bin/python skills/spinoff-worksheet/scripts/worksheet.py --run "PATH/TO/SAVED_RUN"
```

Override the authored files with `--worksheet PATH --persona PATH` only when the user supplies different files.

The default registry is `spinoff_output/registry.json`; override it with `--registry PATH`. Check the ticker and CIK against the registry. Fetch only Form 10 registration accessions already established by that registry. Read and save the primary documents, information statements and textual exhibits under the original run's `Form10/`, with a URL/accession manifest. Use the seeker's EDGAR client for the SEC User-Agent from `.env`, host checks and serial rate limit. Do not use a raw downloader. Save registry-matched issuer Form 4 XML in the configured insider interval under `Form4/`. An amendment stays unresolved until matched. If the ticker is not in the registry, the spinoff facts are `not applicable`, but financial calculations, saved Form 4 review and judgment still run.

## Facts and calculations

Fill facts in code, one scalar row per fact. Each accepted figure has a filing/line or filing/section citation and statement basis: historical, pro forma, or reported after the spin. When a value or its classification cannot be established, report `not known` with the reason; never turn an unsupported layout into a claim that a filing states nothing. Configured selectors can add separate liability, restriction and cash-use rows. Do not write a list of narrative claims in place of facts.

The authored Markdown method uses after-tax earnings plus depreciation and amortization minus capital spending, averaged over the last three consecutive fiscal years. Automatic statement parsing reads annual income/cash-flow rows and eligible cover-page share counts; it does not trust narrative-model outputs or saved numerical claims. Prefer a pro-forma figure where explicitly supplied; if its column cannot be established, do not silently substitute historical results. A post-spin report can supply actual reported figures. Print every component, basis, period, arithmetic and source. Disclose mixed historical/pro-forma bases by input and year. An explicit JSON method can instead select depreciation alone and a comparable quarter. Cumulative quarterly capital spending uses two different filings, the same fiscal-year start and compatible periods/units. Do not substitute zero for a missing earlier amount. Q1 is already a single quarter; select it directly.

Evaluate only the user's explicit valuation arithmetic, with their stated rates and sourced inputs. Compute both low and mid values in code. For the authored Markdown rules, price is the last completed close before the worksheet timestamp; print `(price - low) / low * 100`. Generic JSON can select a pre-filing cutoff. Negative average owner cash flow has no operating value: use cited net cash per actual share for low and mark mid unknown. Code applies the author's conviction policy after liquidity: high requires all five tests, low reflects missing thesis evidence, and no conviction applies to an unbuyable size or missing required numerical citations. No model supplies a number. Without a close, price lines, the deciding price-comparison number and the release view print `not computed`; other sections continue.

Use `closes_reader.daily_closes_and_volumes` for liquidity. It adds optional `TR.Volume` and quote currency while preserving existing close-only calls. CSV sources can supply `volume,currency` columns. Missing volume is not zero; an unknown or incompatible currency prevents a dollar comparison. Require the last 60 completed trading observations under the authored rules, not 60 calendar days and not an estimated fill for a new listing. Compute median(close * volume), not median(close) * median(volume). The authored purchase is portfolio/positions. State the daily participation cap, required trading days and the three-day limit. Save every daily input and source to the companion JSON. The price/volume retrieval window is only an operational buffer; use the actual last observations and disclose missing coverage.

## The single model call

Read the user's persona, then make one Claude Messages HTTP request using the configured `MODEL` and `API_KEY` or `ANTHROPIC_API_KEY` in `.env`. The implementation supports the current team's Claude provider; unsupported providers fail as an unavailable judgment without a second call. There are no tools, provider fallbacks, automatic retries or repair calls.

Save the persona and sole input envelope before the call. Its only data keys are `filing_facts`, `value_range`, and `price_vs_low`. No volume, liquidity history, purchase size or other raw reader output goes to the model. Compute all six criterion scores in code and supply them as evidence assessments; the model explains them without generating score numbers. Request JSON prose plus the persona Insight, with digit-free `[fact:field_name]` citations. Code validates the aliases, expands the original filing/section/line citations, and prints the numeric score list itself. Reject numeric or malformed model output without a repair call. An Insight without a valid source alias is unknown. Save both the sole input envelope and raw output for review. This validation checks provenance and numeric boundaries; the supported meaning and importance of a qualitative Insight still need human review.

After the call, calculate and append the liquidity line in code. End with the release's value relative to price, the deciding computed low-case number and its filing-input citations, high/low/no-conviction status by the worksheet rule, and a `not known` list. An exact equality is reported as equality rather than forced into more/less. Save matching dated `.md` and `.json` worksheet files in the original run. Keep earlier run artifacts intact.

## Offline tests

Use invented filings, injected readers and stubbed model/HTTP responses. Do not launch the live reader or a paid model call merely to validate this skill.

```bash
.venv-desk/bin/python -m unittest discover -s skills/spinoff-worksheet/tests -v
.venv-desk/bin/python -m unittest discover -s tests -v
```

## Saved-view hit rate

Future worksheets use `view_record.py` to save the first prediction as `up`, `down`, `flat`, or
`not computed`. Code maps the existing low-value versus price comparison to this label; this is not
an additional statistical price-reaction model. Do not change the authored valuation method.

The record includes ticker, actual EDGAR acceptance, `time`, the compatible `view_time` alias, and
`reaction_window`. The window identifies the last official close at or before filing and the first
close strictly after it, using the XNYS calendar with holidays and early closes. An explicit price
cutoff override does not replace the actual filing acceptance time.

Read the code clock immediately before saving the record, after window calculation. Do not use the
model's time or the run start. Save before the judgment call. The report must print the stored direction,
timestamp, filing acceptance, and window. Reuse the first saved record when rendering later outputs.
Do not overwrite or backfill historical views. If the filing time is unknown, save `not computed` and
explain the missing evidence. Failed new ticker runs also preserve a timestamped `not computed` record
when no prediction exists. Failure does not authorize a backdated or successful prediction.

Run `.venv-desk/bin/python hit_rate.py runs/live` to refresh available reactions. For one practice
result, run `.venv-desk/bin/python hit_rate.py PRACTICE_PARENT --run RUN_FOLDER_NAME`.
The command writes only a new reaction record. It never rewrites the view. Saved reaction records
include the view hash, and later changes to that view stop scoring. `after` means the view was saved
strictly later than the first post-filing close. Exclude late, not-computed, and unavailable-reaction
rows from the agreement count. Historical records without a timestamped view remain unscored.
