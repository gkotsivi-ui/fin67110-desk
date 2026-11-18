"""Offline tests of the three-column table: two saved runs compared row by row. Made-up data.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import three_columns  # noqa: E402

REPORT = """Filings read: 10-K 0000000001-26-000003
## 1. Overview
### Core figures from the desk's steps (read and computed in code)

| # | Claim | Value | Source |
|---|---|---|---|
| 1 | Total revenue, fiscal year ended 2026-08-30 | $303,154.0M | us-gaap:Revenues, 2025-09-01 to 2026-08-30, 10-K 0000000001-26-000003 |
| 3 | Operating income | $11,685.0M | us-gaap:OperatingIncomeLoss, 2025-09-01 to 2026-08-30 |
| 3 | Operating margin (operating income / total revenue) | 3.85% | 11,685.0 / 303,154.0 ($ millions) |
| 9 | Latest quarter's revenue | 95,723 | release line: Total revenue \\| 95,723 \\| 86,156 |
| - | P/E (price / diluted EPS) | unavailable | no price |

## 2. Market Positioning
| 1 | a row of another table | 5 | none |
"""


def run_folder(report: str = REPORT, view: dict | None = None, final: bool = False) -> Path:
    folder = Path(tempfile.mkdtemp()) / ("EXM_joined" if final else "EXM_alone")
    folder.mkdir()
    (folder / "verified_report.md").write_text(report, encoding="utf-8")
    if final:
        (folder / "final_report.md").write_text(report + "\n# The worksheet's view\n", encoding="utf-8")
    if view is not None:
        (folder / "view.json").write_text(json.dumps(view), encoding="utf-8")
    return folder


VIEW = {"view": "less", "number": "150.00%", "number_label": "Price against the low case", "why_not": ""}


class ThreeColumns(unittest.TestCase):
    def test_the_core_rows_are_read_with_their_sources_and_a_quoted_bar(self) -> None:
        rows = three_columns.core_rows(run_folder() / "verified_report.md")
        self.assertEqual([row[0] for row in rows], ["1", "3", "3", "9", "-"])  # the table of another part is not read
        self.assertEqual(rows[3], ("9", "Latest quarter's revenue", "95,723", "release line: Total revenue | 95,723 | 86,156"))

    def test_a_join_that_changed_nothing_says_so(self) -> None:
        lines = three_columns.table(run_folder(view=VIEW), run_folder(view=VIEW, final=True))
        self.assertEqual(sum(line.endswith("| same |") for line in lines), 7)  # five core rows, the view and the one number
        self.assertIn("Rows that differ: 0. The join changed nothing in these rows: it is a pipeline.", lines)
        self.assertIn("| - | The view | worth less than the price | worth less than the price | the worksheet's view, by its persona | same |", lines)
        self.assertIn("| - | The one number | 150.00% | 150.00% | worksheet line: Price against the low case | same |", lines)

    def test_a_row_that_differs_is_marked_for_a_check_against_the_filing(self) -> None:
        changed = REPORT.replace("| $303,154.0M |", "| $303,155.0M |")
        lines = three_columns.table(run_folder(view=VIEW), run_folder(changed, view=dict(VIEW, view="more"), final=True))
        marked = [line for line in lines if "DIFFERS: check it against the filing" in line]
        self.assertEqual(len(marked), 2)
        self.assertIn("$303,154.0M | $303,155.0M | us-gaap:Revenues, 2025-09-01 to 2026-08-30, 10-K 0000000001-26-000003", marked[0])
        self.assertIn("worth less than the price | worth more than the price", marked[1])
        self.assertIn("Rows that differ: 2. Check each marked row against the filing.", lines)

    def test_a_run_with_no_worksheet_and_a_view_that_was_not_computed(self) -> None:
        not_computed = {"view": "not computed", "number": None, "number_label": None, "why_not": "the run has no close"}
        lines = three_columns.table(run_folder(), run_folder(view=not_computed, final=True))
        self.assertIn("| - | The view | no worksheet ran | not computed (the run has no close) | the worksheet's view, by its persona | DIFFERS: check it against the filing |", lines)


if __name__ == "__main__":
    unittest.main()
