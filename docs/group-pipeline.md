# Independent group pipeline

The group owns the implementation in this repo. `docs/pipeline-import.json` records the source revision
and file hashes used for the initial copy. It is provenance metadata, not a runtime dependency.
No symlink, import, subprocess, default setting, or page route points to the personal repo.
Personal credentials, saved runs, registry results, market exports, and the personal manual were not copied.

## Setup

CrewAI 1.15.34 requires Python below 3.14. Keep the old `.venv` intact and create the pipeline environment:

```bash
python3.13 -m venv .venv-desk
.venv-desk/bin/python -m pip install -r requirements-pipeline.txt -c constraints-pipeline.txt
```

The constraints file pins every package the install brings in to the version the tests ran on. Without it
only the packages named in `requirements-pipeline.txt` are pinned.

On Windows, use `py -3.13 -m venv .venv-desk` and `.venv-desk\Scripts\python` in place of the Mac path.
The inherited seeker and standalone hook lock files with fcntl on macOS and Linux and with msvcrt on Windows.
The filings, the rules and the reports are UTF-8, and Windows would otherwise read and write them in its own
code page: the worksheet could not read its own rule "owner cash flow ÷ 10%". Since 2026-11-22 every file is
opened as UTF-8 by name, and a test fails when a new line of code leaves the encoding out, so neither the
desk nor its tests need `-X utf8`. The desk's programs still start themselves in Python's UTF-8 mode on
Windows (`utf8_mode.py`), which covers what they print. The test harness is portable (`tests/portable.py`):
symlink checks run only where the system permits a symlink, the ordinary secret and excluded-file checks
always run, and the seeded CrewAI tests allow loopback sockets, which Windows' event loop needs, while
blocking every external connection. On Windows 11 and Python 3.13 on 2026-11-25, `check_all.py` ran
991 tests with no failure; the four that create a symlink were skipped. The macOS run has not been
redone since 2026-11-21.

Configure only this repo's `.env`. It needs `SEC_USER_AGENT`, `API_KEY`, and an explicit `MODEL`.
Use the CrewAI model prefix, such as `anthropic/` followed by a model ID available to your account.
The worksheet's judgment uses the same `MODEL` and `API_KEY` as the agent team. A Claude model is one HTTP
request to Anthropic, as before; any other model goes through CrewAI's LLM, as the team's roles do.
The closes reader uses this repo's `.env` too. No price or volume source is copied from the personal repo.
Its optional LSEG worker defaults to this repo's `.venv-lseg`, not a workspace environment.
The default is `.venv-lseg/bin/python` on macOS/Linux and `.venv-lseg\Scripts\python.exe` on Windows.
Create that environment and install `requirements-lseg.txt`, or set `LSEG_PYTHON` in `.env` to an existing Python
that has the package, for example `.venv\Scripts\python.exe` on Windows. The override takes precedence. The reader has two sources and no other: a CSV of closes named by
`LSEG_CLOSES_FILE`, read first when it is set, and LSEG Workspace through `LSEG_APP_KEY`. With neither, or
with Workspace closed and no file, a run has no close, and its worksheet view is "not computed".

```bash
.venv-desk/bin/python check_pipeline.py
```

This command prints setup status, not identity or secret values. It makes no external requests. No line may
say `FIX`; `note` lines are information. It also checks that `SEC_USER_AGENT`, `API_KEY` and `MODEL` are
filled in, are not the example's words, and that the key and the model are of one provider. `desk.py` makes
the same check as its first step, before it fetches anything.

## One command

Run the requested ticker. A fresh checkout needs no screen and no registry:

```bash
.venv-desk/bin/python desk.py TICKER
```

With no saved registry the desk writes an empty one with a note, and the spinoff parts of the report say
"not applicable". To run the seeker's screen first, which is optional and slow:

```bash
.venv-desk/bin/python desk.py TICKER --refresh-screen YYYY-MM-DD
```

Replace `TICKER` and the distribution start date. The scan can take time; its inherited index start is
1994-07-01. `--index-start`, `--as-of`, and `--max-candidates` permit explicit bounded scans. A bounded
or incomplete screen retains its partial-coverage disclosure; do not present it as a full search.

Alternatively, choose the top ranked ticker:

```bash
.venv-desk/bin/python desk.py screen --refresh-screen YYYY-MM-DD
```

For a saved group registry, no screen refresh is needed:

```bash
.venv-desk/bin/python desk.py TICKER --registry runs/practice/SAVED_RUN/registry.json
```

Do not use a personal registry path. The command stops if it cannot find a registry or a screen that the
command line names. It never fills the gap with personal run data.
CLI registry, screen, authored-input, run-storage, and replay paths must stay inside this repository.
The path check rejects outside locations and symlinks that resolve outside the group checkout.

Add `--live` only for a real live run. New runs otherwise go to `runs/practice/`.
The command fixes this order: input snapshots, seeker, ticker pick, team with Verifier, worksheet,
and final report. The hook checks each stage's saved outputs. A failed stage stops later stages and
preserves its run folder. It does not repair an inherited calculation, parsing, or judgment error.

A claim the Verifier marks wrong or unsupported does not stop the run. Its line is left out of the published
report, the marks table still lists it, and a line under the table names each part and claim left out. The
hook rebuilds the published text from the saved role files, so a left-out line cannot come back. A missing
claim costs nothing in the audit; a wrong one fails it; a run that stops publishes nothing. The Verifier sees
eight lines on each side of every cited line.

The same holds one step earlier. Each analyst role gets two repairs for claims that fail the code's check. If a
claim still fails after them, the role's latest reply is kept without that claim and without every draft line
that uses it or types its own number, and the shortened reply is checked again from the start. The role's
`claim_attempts.json` keeps every reply, its errors, and what was left out. The Verifier's reasons and
corrections are checked the same way: one that still fails after its repairs is replaced by a fixed sentence
that says so, and its mark stays. A reply of the wrong shape, or one with nothing left, still stops the run.

A model call whose reply never came, because the connection dropped or timed out or the provider answered
with a server error, is made once more after thirty seconds. A call the provider limits (429) is made once
more after sixty. A refusal for lack of credit is not tried again, whatever status it comes with. The role's
`dropped_connections.json` records each retry. A second failure stops the run. The worksheet's one model
call is tried once more by the same rule, which both read from `model_calls.py`. The provider's client is
given ten minutes for a request, and may try a stalled request again on its own. One role's call is given
twenty minutes; past that the run stops and names the role, and that call is not made again. SEC EDGAR is
asked for a page up to three times, waiting two and then eight seconds, or as long as its `Retry-After`
header asks, up to a minute.

A run that stops in its worksheet or its final report, after the team's verified report is saved and
checked, can be finished without calling the team's models again:

```bash
.venv-desk/bin/python desk.py --resume runs/practice/SAVED_RUN
```

The command prints this line when it applies. It first checks the saved files against their recorded
hashes and moves what the stopped attempt left into `earlier_attempt/`. A run that stopped earlier is run
again from the start. Ctrl+C stops a run, records the part it was in, and marks the folder "stopped".

The final report is published only after the hook accepts it. `view.json` is written by code immediately when the prediction is saved. It records `up`, `down`,
`flat`, or `not computed`, actual filing acceptance, and the intended reaction window. The report prints
the same saved direction and timestamp. The first record is immutable; neither reaction refresh nor
a later report can change it. Failed new runs retain `not computed` when no prediction exists. The hit-rate reader accepts that schema while
leaving older runs without a view unscored. A worksheet view is relative value versus price; its
direction mapping measures agreement with the reaction, not proof of a correct investment decision.

## Files and evidence

- `desk.py`, `desk_parts.py`: group command and adapters.
- `equity_research_desk.py`, `equity_research_agent_team.py`: copied data layer, team, and Verifier.
- `desk_claims.py`, `desk_role_contracts.py`, `desk_quantities.py`: checked claims and numerical contracts.
- `desk_hook.py`, `hooks/`: blocking numerical checks and worksheet checks.
- `desk_sources.py`, `desk_files.py`, `desk_timing.py`: saved evidence, assigned files, and timing.
- `closes_reader.py`: local reader supporting the pipeline's price and volume contract.
- `skills/us-spinoff-seeker/`, `skills/spinoff-worksheet/`: group-local copies, including tests.
- `pipeline_roles/`: byte-for-byte copied role inputs. The legacy team's `roles/` is preserved.
- `spinoff_factors.json`, `spinoff-rules.md`, `persona-why-cheap.md`: unchanged authored inputs.

Existing Cisco and NVIDIA research artifacts remain unchanged. Human and AI review reports remain
beside each record's files. Shared review findings remain in `docs/error-review-findings/`.
The Intelligent Review Assistant can read new pipeline status and node outputs; absent independent
checks remain explicit limits. It does not treat a failed worksheet as a completed desk run.

See [LSEG setup for Mac and Windows](lseg-setup.md) for exact commands and the offline/session checks.

## Required reads and guidance ranges

A role response is accepted only after every assigned file has been read and its saved hash checked.
If the response omits files, the desk names the missing files and permits one additional response.
Both raw replies and the missing-file list are saved. A second omission, an access violation, or a
changed file still stops the run. This correction does not remove files from the assignment.

The claims checker also checks explicit guidance ranges written with two claim placeholders joined
by `to`, a dash, or `between ... and`. Both endpoints must form one range on the same cited filing
line. Unsupported endpoints go through the existing claim repair and omission rules. A real number
from a different metric cannot become an endpoint merely because its quote and value match.
This conservative check can reject a valid range split across source lines. It does not establish
that every metric, period, or conclusion is correct, and does not change the authored personas.

## Page and replay

```bash
.venv-desk/bin/python page.py
.venv-desk/bin/python desk.py --replay runs/practice/SAVED_RUN
```

The page launches this repo's `desk.py`, using the same environment. Both double-click launchers
select `.venv-desk`. The page shows the final report only after a successful run. It does not serve
another repo's files. Offline replay checks saved evidence without another model call or SEC fetch.
Failed runs remain failed during replay. Review reports can be appended without changing the saved
research outputs or their timestamps.

## Validation

On Windows, write `.venv-desk\Scripts\python` in place of `.venv-desk/bin/python`.

```bash
.venv-desk/bin/python check_all.py
```

One command runs the four test folders (`tests`, `hooks/tests` and the two skills' tests), the two seeded
checks that test discovery does not collect, `live_record.py --offline --no-save`, and `check_public.py`,
which looks for keys, values of `.env`, data files, lists of closes and home-folder paths in what git tracks
or would add. It needs no network and no key.

The isolation test creates a temporary group-only checkout, imports each copied component, and runs
the seeded pipeline there. It has no neighboring personal repo or workspace skills. `tests/test_whole_desk.py`
runs the whole desk, from a ticker to its final report, on made-up SEC pages and a stand-in model. Other
tests use invented data, stubbed models, and injected readers. This does not prove live provider availability
or correct behavior on every real filing. No real live run was launched to validate this integration.

The legacy `team.py`, `lab03_app.py`, and `verifier.py` remain available. They are not the new command's
team path. Use the original `.venv` and `requirements.txt` when reproducing legacy behavior. The SDK
constraints of CrewAI and the legacy environment differ; do not install both requirements files together.

This is a learning exercise, not financial advice.

AI assistance: Claude Code and OpenAI Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.
