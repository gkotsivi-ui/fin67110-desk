# Independent group pipeline

The group owns the implementation in this repo. `docs/pipeline-import.json` records the source revision
and file hashes used for the initial copy. It is provenance metadata, not a runtime dependency.
No symlink, import, subprocess, default setting, or page route points to the personal repo.
Personal credentials, saved runs, registry results, market exports, and the personal manual were not copied.

## Setup

CrewAI 1.15.34 requires Python below 3.14. Keep the old `.venv` intact and create the pipeline environment:

```bash
python3.13 -m venv .venv-desk
.venv-desk/bin/python -m pip install -r requirements-pipeline.txt
```

On Windows, use `py -3.13 -m venv .venv-desk` and `.venv-desk\Scripts\python` in place of the Mac path.
The inherited seeker and standalone hook use Unix file locks; Windows portability is not verified.
The automated tests in this change ran on macOS and Python 3.13.

Configure only this repo's `.env`. It needs `SEC_USER_AGENT`, `API_KEY`, and an explicit `MODEL`.
Use the CrewAI model prefix, such as `anthropic/` followed by a model ID available to your account.
The copied worksheet supports Anthropic judgment calls only. This inherited limitation is not changed.
The closes reader uses this repo's `.env` too. No price or volume source is copied from the personal repo.
Its optional LSEG worker defaults to this repo's `.venv-lseg`, not a workspace environment.

```bash
.venv-desk/bin/python check_pipeline.py
```

This command prints setup status, not identity or secret values. It makes no external requests.

## One command

For a fresh group checkout, refresh a screen and run the requested ticker:

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

Do not use a personal registry path. A fresh checkout has no cached registry. The command stops if it
cannot find the requested registry or screen. It never fills the gap with personal run data.
CLI registry, screen, authored-input, run-storage, and replay paths must stay inside this repository.
The path check rejects outside locations and symlinks that resolve outside the group checkout.

Add `--live` only for a real live run. New runs otherwise go to `runs/practice/`.
The command fixes this order: input snapshots, seeker, ticker pick, team with Verifier, worksheet,
and final report. The hook checks each stage's saved outputs. A failed stage stops later stages and
preserves its run folder. It does not repair an inherited calculation, parsing, or judgment error.

The final report is published only after the hook accepts it. `view.json` is written by worksheet code
at view computation and preserves its first timestamp. The hit-rate reader accepts that schema while
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

```bash
.venv-desk/bin/python -m unittest discover -s tests
.venv-desk/bin/python -m unittest discover -s skills/us-spinoff-seeker/tests
.venv-desk/bin/python -m unittest discover -s skills/spinoff-worksheet/tests
.venv-desk/bin/python -m unittest discover -s hooks/tests
.venv-desk/bin/python live_record.py --offline --no-save
```

The isolation test creates a temporary group-only checkout, imports each copied component, and runs
the seeded pipeline there. It has no neighboring personal repo or workspace skills. Other tests use
invented data, stubbed models, and injected readers. This does not prove live provider availability
or correct behavior on every real filing. No real live run was launched to validate this integration.

The legacy `team.py`, `lab03_app.py`, and `verifier.py` remain available. They are not the new command's
team path. Use the original `.venv` and `requirements.txt` when reproducing legacy behavior. The SDK
constraints of CrewAI and the legacy environment differ; do not install both requirements files together.

This is a learning exercise, not financial advice.

AI assistance: OpenAI Codex. Integration and offline tests only; no human source verification is claimed.

Any remaining errors are my own.
