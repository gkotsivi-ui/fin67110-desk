"""The hook's recheck of calculated facts: exact arithmetic against a value the desk saved as a float.

On 2026-11-19 a correct return on average equity was refused, and the run stopped: the saved float, printed to
15 significant digits, ended in 9 where the exact arithmetic rounds to 8. Run: python -m unittest discover -s tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desk_hook import check_calculations  # noqa: E402


def saved(metrics: dict) -> Path:
    folder = Path(tempfile.mkdtemp())
    path = folder / "calculated_facts.json"
    path.write_text(json.dumps({"metrics": metrics, "quarter_results": {}}), encoding="utf-8")
    return path


class CalculatedFacts(unittest.TestCase):
    # The real case: net income over the average of two years of negative stockholders' equity.
    FORMULA = "6654000000 / ((-9917000000 + -14231000000) / 2)"

    def test_a_float_that_differs_only_in_its_last_digit_passes(self) -> None:
        value = 6654000000 / ((-9917000000 + -14231000000) / 2) * 100  # as the desk computes it
        path = saved({"return_on_average_equity": {"formula": self.FORMULA, "value": value, "unit": "%"}})
        check_calculations(path.parent, path)  # no error

    def test_a_value_that_is_really_different_is_still_refused(self) -> None:
        for wrong in (-55.11, -55.2, 55.11015405002485, -55.110154051):
            path = saved({"return_on_average_equity": {"formula": self.FORMULA, "value": wrong, "unit": "%"}})
            with self.assertRaisesRegex(ValueError, "differs from its input arithmetic"):
                check_calculations(path.parent, path)

    def test_a_ratio_that_is_not_a_percent(self) -> None:
        value = 39819000000 / -9917000000
        path = saved({"debt_to_equity": {"formula": "(39819000000) / -9917000000", "value": value, "unit": "ratio"}})
        check_calculations(path.parent, path)
        path = saved({"debt_to_equity": {"formula": "(39819000000) / -9917000000", "value": value * 1.001, "unit": "ratio"}})
        with self.assertRaises(ValueError):
            check_calculations(path.parent, path)


if __name__ == "__main__":
    unittest.main()
