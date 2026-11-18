# The client's files: written by hand

The desk reads three files that a team member writes by hand. The course says that no AI writes them, and no
code in this repository fills them in. Until a member adds them, the worksheet stops and names the file it needs.

| File | Who reads it | What it holds |
|---|---|---|
| `client/worksheet.json` | `worksheet.py`, and `hook.py` through the copy saved with each run | the method of the value range, its rates, the client's purchase size, the liquidity limit and the conviction rule |
| `client/persona.md` | `worksheet.py`, in its one model call | the persona that writes the judgment and chooses the view, in the six parts from the Week 3 page |
| `client/factors.json` | the seeker | each factor with its weight and its direction, and the window in days |

To keep your own copies elsewhere, give their places in `.env`: `WORKSHEET_FILE` and `PERSONA_FILE`.

## The shape of `client/worksheet.json`

The keys are fixed, because code reads them. Every value is yours. The values below are placeholders that show
the form of each value. They are not a method, and the file is not valid until you replace each one.

```
{
 "method": "owner cash flow divided by a rate",
 "owner_cash_flow_years": <1, 2 or 3: how many fiscal years of owner cash flow are averaged>,
 "low_rate": <the rate of the low case, as a fraction, for example 0.12 for 12%>,
 "mid_rate": <the rate of the mid case, as a fraction>,
 "purchase_size": <the client's purchase size, in dollars>,
 "liquidity_days": <how many trading days of dollar volume the liquidity line reads>,
 "liquidity_share_of_daily_volume": <the largest share of one day's dollar volume the client may buy, as a fraction>,
 "conviction_rule": "<in your words: what makes a conviction high, and what makes it low>"
}
```

What code does with them, so that you can defend each number:

- **Owner cash flow** of a fiscal year is net income plus depreciation and amortization minus capital spending,
  each from the 10-K's XBRL facts. The worksheet averages the number of years you state.
- **The low case and the mid case** are that average divided by your two rates. Per share, each is divided by
  the weighted-average diluted shares of the latest fiscal year. The method does not subtract debt and does not
  add cash. If your method should, say so, and the code changes after its test does.
- **The price against the low case** is the close the run saved, divided by the low case per share, minus one.
- **The liquidity line** is the median of close times volume over your number of trading days. The most the
  client may buy in one day is that median times your share.
- **The conviction rule** is given to the persona word for word. The persona applies it and says high or low.

This code knows one method, "owner cash flow divided by a rate". A file that names another method stops the
worksheet. It never guesses a method.

## What the persona receives

The lines of the worksheet above the judgment, and your conviction rule. Nothing else: no filing, no price
series, no volume. It may quote a number only as a worksheet line prints it. If it writes any other number, the
worksheet leaves the judgment out and prints "not computed" for the view.

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
