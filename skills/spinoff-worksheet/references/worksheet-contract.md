# Worksheet input contract

## Authored Markdown rules (default)

The default files are `spinoff-rules.md` and `persona-why-cheap.md`. No conversion or editing of those files is needed. The parser reads their explicit 10%/7% yields, three-fiscal-year average, depreciation **and amortization**, portfolio/position arithmetic, 60 trading observations, daily participation limit and maximum trading days. None of those financial constants is invented by the skill. A FILL field causes an input error before any model or reader call.

Automatic extraction handles unambiguous saved annual statement rows, exact period columns and filed cover-page share counts. Print each year's earnings, depreciation/amortization and spending with the statement basis and source. Historical cash outflows in parentheses are converted to positive capital spending with the sign conversion stated. Pro-forma columns that cannot be resolved remain unknown rather than being replaced silently. Explicit selectors remain available as optional layout adapters.

For this Markdown method, price is the last completed close before the worksheet timestamp, not the earnings filing. The lookback fetch is a one-year buffer; only the actual last 60 completed weekday/trading observations enter the median. Younger listings with fewer observations have unknown liquidity, not an estimated 60-day median. Daily capacity = participation fraction × median daily dollar volume; minimum trading days = ceiling(purchase / daily capacity). Buyability requires that result within the author's limit. Required figures without citations or unbuyability give no conviction.

The six 0/1/2 criterion scores are computed in code from cited evidence, not by the model. Code P alone does not establish open-market buying; that requires linked footnotes for non-derivative purchases. Meaningful stake and seller evidence need a direct cited fact, never a guessed size threshold. The persona receives these computed assessments with filing facts and code values. It uses digit-free fact aliases, which code expands to the exact source. Code appends the numeric scores, liquidity and the final view/conviction.

Negative average owner cash flow has no operating value. Low is cited net cash divided by actual shares; mid is unknown. Net cash requires matching cash and explicit total-debt lines; long-term debt alone or a missing line is not assumed to be total debt or zero.


The command requires a saved run directory and reads the authored default files unless paths are overridden. Relative filing selectors resolve inside the saved run. The input JSON is configuration, not permission to fill a missing fact with an assumed value. Filings must establish the figures. `facts.json` supplies identity only; the model's report and even saved calculated facts are not used as numerical evidence.

## Optional worksheet JSON

For an explicit alternate JSON method, start with `worksheet.example.json`. Nulls deliberately select no method, rate, client size, figure or conviction threshold. Fill it with your own choices before a real call. A missing choice is listed as not known; it is never silently defaulted.

- `price_filed`: optional Eastern timestamp `YYYY-MM-DDTHH:MM:SS`. Otherwise the saved `filing_time.json` field `effective_filed_eastern` is used. This is the strictly pre-filing close, not a current quote. A timezone-bearing saved timestamp is converted to Eastern before calling the reader.
- `price_currency`: only set `USD` when the reader/source establishes that unit. If the close already includes currency, that value takes precedence. Unknown/non-USD units prevent the low-case price comparison.
- `liquidity`: `start`, `end`, `purchase_size`, `currency`. Inclusive ISO dates, client purchase in USD. Closes and volumes must refer to the same dated rows; missing rows/volume, conflicting dates and unknown/non-USD units are not estimated. Reader gaps cannot prove complete exchange coverage; the worksheet prints the actual dates and sample count.
- `insider_start` and `insider_end`: explicit Form 4 window; when omitted/null, use the supplied liquidity interval. Only saved/fetched issuer code-P transactions in that interval enter the observed purchase consideration. Code P can include private purchases and derivatives; it is not a claim of open-market common-share buying. Units are reported monetary units. Amended or malformed transactions leave the fact unknown. Zero observed purchases in saved XML is not proof of no undisclosed or later-filed purchases.
- `facts`: named filing selectors. The financial calculation needs `after_tax_earnings`, `depreciation`, `capital_spending` and, if the valuation method uses it, `shares_outstanding`. Add separate fact names for each liability, restriction or cash use. Configured spinoff fact names are ignored for a ticker absent from the registry, so those parts remain not applicable.
- `valuation.low` and `valuation.mid`: an explicit `formula` and `rates` dictionary. There is no selected valuation method unless the file supplies one. Numbers in `rates` are authored assumptions, always printed. They cannot override a sourced fact. The code performs the arithmetic; it does not create growth, discount or terminal rates. Arithmetic allows names, numeric constants, parentheses, addition, subtraction, multiplication, division and powers; no Python calls, imports, attributes or indexing. Input names are the sourced numeric facts and `owner_cash_flow`. Expressions are per-share methods only when their authored formula uses the correct share denominator; the worksheet author owns that method.
- `conviction.high_if`: an explicit comparison/and/or expression over sourced numeric facts, `owner_cash_flow`, `price`, `low_value`, `mid_value` and constants in `parameters`. True means high, false means low. Missing inputs or an absent/invalid rule yield not known, never a guessed low. Constants cannot overwrite a sourced/computed input.

For example, an author may select capitalized owner cash flow with `owner_cash_flow / discount_rate / shares_outstanding`. That is an illustration, not a default or a recommended method. Enter your own rates. Finite-horizon discounted methods can be expressed as explicit annuity/terminal arithmetic with authored parameters.

## Filing selectors

Each fact selector supplies:

```json
{
  "file": "10-K.txt",
  "section": "CONSOLIDATED STATEMENTS",
  "end_section": "NOTES TO FINANCIAL STATEMENTS",
  "pattern": "Net income \\$(?P<amount>[0-9,]+)",
  "period": "Year ended December 31, 2026",
  "kind": "historical",
  "unit": "USD",
  "scale": 1
}
```

This invented layout is only a selector example. Use your actual filing's labels, statement boundaries and column layout. A regex must match exactly one figure and have named capture `amount`, or capture `value` for a compact qualitative fact. Source files must be saved filing text, not report Markdown or JSON claims. A period must appear within the selected statement. Set `kind` from that statement, not from the fact that a Form 10 was filed. `kind` accepts historical, pro forma, or reported after the spin. Make the regex identify the chosen period column; the parser rejects multiple matches and does not choose an adjacent figure for you. The citation includes the original file line, selected section, period and matched text. A scale other than one requires `units_pattern` that matches the actual filing unit heading. Do not select total depreciation-and-amortization as depreciation unless your worksheet explicitly adopts that definition and labels the fact accordingly. Do not substitute EBITDA or operating cash flow for after-tax earnings.

For Q2/Q3 or Q4 quarter capital spending, set `cumulative: true`, `fiscal_start`, `period_end`, `quarter_period`, and `prior` to another filing selector with the same fiscal start, an earlier cumulative `period_end`, same unit and same statement basis. The end-date gap must be one fiscal quarter (65–110 days). The code subtracts the prior cumulative amount and prints both filing lines. This also accepts annual minus nine-month data for Q4. Q1 needs no subtraction. Use one genuinely comparable quarter label for earnings, depreciation and the resulting capital-spending amount.

Without custom spinoff selectors, the default extractor accepts unambiguous information-statement scalar labels: Parent, Distribution ratio, Record date, Distribution date, Debt raised, Cash paid to parent, Retained liabilities, and Tax restriction in years. Explicit thousand/million/billion suffixes are preserved numerically. Unsupported wording, units or multiple conflicting figures stay unknown. Never treat that as a filing-level absence finding. Add exact section/column selectors for other layouts; no model performs extraction or fills a blank. Figures whose statement basis cannot be established have an unknown amount with the original evidence and a classification reason in the unknown list.

## Saved sources and output

`Form10/manifest.json` records source URLs, accessions, filed dates, raw copies, plain-text copies, information-statement markers and read failures. The registry selects accessions; current ticker metadata does not replace them. Form 4 XML and its coverage record are saved separately. The SEC client uses `SEC_USER_AGENT` from `.env` on every request and the seeker's existing 0.21-second serial gate. PDF/unsupported exhibits remain incomplete coverage.

For a worksheet time `YYYY-MM-DD HH-MM-SS.ffffff`, output files share the base `Spinoff worksheet, TICKER, YYYY-MM-DD, HH-MM-SS.ffffff`. The `, model input.json` companion records exactly what the one judgment call received, including the user's persona. The `, model output.json` companion preserves the returned JSON before numeric/citation validation; rejected content never supplies worksheet figures. The main JSON retains all calculation inputs, sources, unknown reasons and model error type. No secrets or API headers are saved.

The financial report's graph, roles and CLI remain unchanged. No live services are used by the tests. The configured current Claude provider is supported directly; other providers require an explicit future adapter rather than a hidden fallback.

## Primary API references

- [LSEG Data Library access-layer reference](https://developers.lseg.com/en/article-catalog/article/the-data-library-for-python-quick-reference-guide-access-layer).
- [LSEG field examples showing TR.PriceClose and TR.Volume](https://developers.lseg.com/content/dam/devportal/api-families/eikon/eikon-data-api/documentation/eikon_data_api_for_python_v1.pdf).
- [LSEG staff example of TR.PriceClose.Currency](https://community.developers.lseg.com/discussion/108522/workspace-with-api-refinitiv-data-rd-get-history-does-not-give-unadjusted-prices).
- [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create).

The current Markdown file explicitly includes depreciation and amortization; its three-year average therefore uses both. The depreciation-only selector example applies only to an explicit alternate JSON method. Do not change the authored file or switch its method. The saved raw model output is a separate companion; a rejected response never supplies worksheet numbers.

The default authored rules are read-only inputs. The implementation leaves their placeholder portfolio assumption exactly as written, records the parsed arithmetic, and never treats it as a verified fact about a client. The model receives only filing facts/criterion evidence, the value range and the single price comparison; daily price/volume inputs and purchase size remain out of its envelope.
