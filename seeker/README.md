# The seeker's place in the desk

The spinoff seeker (Lab 06) is not built in this repository yet. This page says what the rest of the desk reads
from it, so that the seeker can be added without a change to the one command or to the worksheet. The join is
the pipeline: the seeker writes files, and the parts after it read them.

## What the one command reads: the latest screen

`python desk.py screen` takes the top name of the seeker's latest report. It reads the newest file named
`seeker/reports/screen_<date>_<time>.json`, and in it the list `in_window`: the names in their window, by rank,
the first one first. Each name needs a `ticker`. The seeker may add any other key.

```
{
 "in_window": [
  {"ticker": "<the top name's ticker>", "points": "<what the seeker gives it>"},
  {"ticker": "<the next name's ticker>"}
 ]
}
```

With no such file, or with an empty list, the command stops at the pick and says so. It never picks a name by
itself. `python desk.py screen --from YYYY-MM-DD` runs the seeker first: it calls `run(start_date)` in a file
`seeker.py` in the repository folder, and stops with a clear message when that file is not there.

## What the worksheet reads: the registry

The worksheet looks for the ticker in `seeker/registry.json`. A name that is not there is "not applicable" in
the worksheet's spinoff part, and the rest of the worksheet runs. For a name that is there, the worksheet prints
each fact with the filing and the section that the registry gives beside it, and "not known" for a fact that
the registry leaves blank. The registry is a list, one entry for each name:

```
[
 {
  "ticker": "<ticker>",
  "parent": {"value": "<the parent's name>", "filing": "<accession number>", "section": "<the section it came from>"},
  "ratio": {"value": "", "filing": "", "section": ""},
  "record_date": {"value": "", "filing": "", "section": ""},
  "distribution_date": {"value": "", "filing": "", "section": ""}
 }
]
```

A fact that the seeker could not find stays blank. The seeker never estimates a fact, and the worksheet never
fills one in.

## What the seeker reads: the factors, written by hand

The factors, each with its weight and its direction, and the window in days, are in `client/factors.json`. A
team member writes that file by hand. No AI writes it. [client/README.md](../client/README.md) says more.

This is a learning exercise, not financial advice.

AI assistance: Claude Code. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
