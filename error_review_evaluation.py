#!/usr/bin/env python3
"""Evaluate review rules on labelled, synthetic practice runs. No network or model key."""
import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path

from desk_error_review import Review, ROOT, snapshot


def put(folder, name, value):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) if not isinstance(value, str) else value, encoding="utf-8")


def cases(root):
    """Each label is explicit ground truth for this small test set, not a live accuracy claim."""
    base_facts = {"company": "Example Research", "ticker": "EXM", "ten_k": "0000000001-26-000001", "facts": {
        "revenue": {"current": {"val": 200}, "prior": {"val": 100}},
        "operating_income": {"current": {"val": 40}}}}
    release = ("CONSOLIDATED STATEMENTS OF OPERATIONS\n(In millions, except per-share amounts)\n"
               "Three Months Ended\nSeptember 30, 2026 | September 30, 2025\n"
               "Total revenue | 200 | 100\nCost of revenue | 120 | 60\n"
               "Operating income | 80 | 40\nNet income per share:\nDiluted | $2.00 | $1.00\n")
    from release import read_quarter
    quarter = read_quarter(release.splitlines())
    specs = []
    def make(name, expected, uncertain=()):
        folder = root / name
        folder.mkdir(parents=True)
        put(folder, "facts.json", base_facts)
        put(folder, "report.md", "# Example report\nRun time: synthetic\nRevenue increased.\n")
        specs.append((folder, set(expected), set(uncertain)))
        return folder
    folder = make("correct", [])
    put(folder, "ratios.json", [{"name": "Operating margin", "value": .2}])
    folder = make("bad-calculation", ["ratio"])
    put(folder, "ratios.json", [{"name": "Operating margin", "value": .8}])
    folder = make("forecast-selection", ["forecast-selection"])
    put(folder, "8K_synthetic.txt", release)
    put(folder, "nodes/01_steps.json", {"output": {"quarter": dict(quarter, statement="Business Outlook")}})
    for name, key, value in [("wrong-period", "period", "September 30, 2025"),
                             ("wrong-units", "units", "thousands"), ("wrong-value", "revenue", 999)]:
        folder = make(name, [], ["selection"])
        put(folder, "8K_synthetic.txt", release)
        selected = dict(quarter, **{key: value})
        if key == "revenue":
            selected["revenue_growth"] = value / selected["revenue_prior"] - 1
        put(folder, "nodes/01_steps.json", {"output": {"quarter": selected}})
    folder = make("type-error", ["runtime"])
    put(folder, "run.log", "TypeError: a synthetic value has the wrong type\n")
    folder = make("value-error", ["runtime"])
    put(folder, "run.log", "ValueError: synthetic input cannot be parsed\n")
    folder = make("json-error", ["json-parse"])
    put(folder, "hook.json", "{broken json")
    folder = make("hook-reported-failure", ["component-failure"])
    put(folder, "hook.json", {"status": "failed", "error": "ValueError: synthetic parser failure"})
    folder = make("skill-reported-failure", ["component-failure"])
    put(folder, "worksheet.json", {"status": "failed", "error": "TypeError: synthetic skill failure"})
    folder = make("unsupported", [], ["unsupported"])
    put(folder, "verification.json", {"records": [{"line": 3, "number": "400", "mark": "correct", "source": {"type": "none"}}],
                                       "counts": {"correct": 1}})
    folder = make("incomplete-no-log", [])
    (folder / "report.md").unlink()
    put(folder, "run_status.json", {"status": "incomplete"})
    folder = make("intentional-omission", [])
    put(folder, "ratios.json", [{"name": "Operating margin", "value": None, "why": "input missing"}])
    folder = make("resolved-previous-pattern", [])
    put(folder, "8K_synthetic.txt", release)
    put(folder, "nodes/01_steps.json", {"output": {"quarter": quarter}})
    return specs


def evaluate(root):
    root.mkdir(parents=True, exist_ok=True)
    history = root / "history"
    history.mkdir()
    put(history, "Error Documentation Previous, 1.md", "# Previous errors\n### Error 1\nType of error: wrong outlook table\n")
    rows = []
    for folder, expected, uncertain in cases(root / "runs"):
        before = snapshot(folder)
        review = Review(folder, history)
        review.deterministic()
        actual = {f["rule"] for f in review.findings if f["status"] == "confirmed"}
        suspected = {f["rule"] for f in review.findings if f["status"] == "unconfirmed"}
        references = [r for f in review.findings for r in f["evidence"]]
        rows.append(dict(run=folder.name, confirmed_detected=sorted(expected & actual),
                         false_alarms=sorted(actual - expected), missed=sorted(expected - actual),
                         unconfirmed_detected=sorted(uncertain & suspected),
                         unconfirmed_false_alarms=sorted(suspected - uncertain),
                         unconfirmed_missed=sorted(uncertain - suspected),
                         valid_references=sum(review.valid_ref(r) for r in references), references=len(references),
                         original_unchanged=before == snapshot(folder)))
    totals = {key: sum(len(row[key]) for row in rows) for key in
              ("confirmed_detected", "false_alarms", "missed", "unconfirmed_detected", "unconfirmed_false_alarms", "unconfirmed_missed")}
    totals.update(valid_references=sum(row["valid_references"] for row in rows), references=sum(row["references"] for row in rows))
    return {"scope": "Synthetic rule evaluation only. This does not measure live accuracy or model semantic accuracy.",
            "cases": rows, "totals": totals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/error-review-evaluation.json")
    args = parser.parse_args()
    # Temporary practice runs never enter runs/live. The labelled generator is kept in source control.
    with tempfile.TemporaryDirectory(prefix="desk-review-practice-") as temp:
        result = evaluate(Path(temp))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["totals"], indent=2))
    print(result["scope"])
    return int(any(result["totals"][key] for key in ("false_alarms", "missed", "unconfirmed_false_alarms", "unconfirmed_missed")))


if __name__ == "__main__":
    raise SystemExit(main())
