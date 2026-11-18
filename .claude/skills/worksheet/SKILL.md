---
name: worksheet
description: Writes the worksheet for one saved run of the research desk - owner cash flow, a value range against the price, and a view on the earnings release. Use it when the user asks for a worksheet, a value range or a view on a ticker that the desk has run. Screens to look at, not recommendations.
---

# The worksheet

The worksheet runs on a saved run of the agent team. Code fills its facts and does its arithmetic. One model
call, with the persona a team member wrote, writes the judgment and chooses the view. No model computes a number.

## Run it

From the repository folder, with the virtual environment's Python (`.venv\Scripts\python` on Windows,
`.venv/bin/python` on a Mac):

1. The whole desk on a ticker, which runs the agent team, this worksheet and the hook in a fixed order:
   `python desk.py TICKER`
2. The worksheet alone, on a run that is already saved:
   `python worksheet.py output/TICKER_DATE_TIME`
3. The hook on what the worksheet wrote. It prints nothing when every number has its source:
   `python hook.py output/TICKER_DATE_TIME/worksheet.md`

## Rules

- Never write or change `client/worksheet.json`, `client/persona.md` or `client/factors.json`. A team member
  writes them by hand. If one is missing, say which, and stop.
- Never compute a number yourself and never state one from memory. Quote a number only as a line of the
  worksheet prints it, with the source in its square brackets.
- If the hook refuses a line, do not say that the work is done. Report the line and its reason.
- A name that is not in the seeker's registry is not an error: the spinoff part says "not applicable" and the
  rest runs.
- The worksheet ends with what is not known. Do not fill a gap with an estimate.
