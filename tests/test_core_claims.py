"""The course's 11 core claims, printed by code under the Overview (desk_role_contracts.core_claims_table).

On 2026-11-20 a report left out revenue growth that the desk had computed, because the roles chose which numbers
to state. The amounts below are made up.
"""
import json
from pathlib import Path
import tempfile
import unittest

from desk_role_contracts import core_claims_table


def fact(value, tag):
    return {"value": value, "tag": tag, "period_end": "2026-06-30", "filing": "0000000001-26-000010"}


class CoreClaims(unittest.TestCase):
    def run_folder(self, quarter=True):
        run = Path(tempfile.mkdtemp())
        facts = {"revenue": fact(100e9, "Revenues"), "operating_income": fact(20e9, "OperatingIncomeLoss"),
                 "net_income_attributable_to_parent": fact(15e9, "NetIncomeLoss"), "diluted_eps": fact(3.33, "EarningsPerShareDiluted")}
        metrics = {"revenue_growth": {"value": 11.774985, "unit": "%", "formula": "(100 - 89.5) / 89.5"},
                   "operating_margin": {"value": 20.0, "unit": "%", "formula": "20 / 100"},
                   "return_on_average_equity": {"value": -55.110154, "unit": "%", "formula": "15 / ((-30 + -24) / 2)"},
                   "debt_to_equity": {"value": -4.025511, "unit": "ratio", "formula": "(37 + 3) / -10"},
                   "free_cash_flow": {"value": 12e9, "unit": "USD", "formula": "14 - 2"},
                   "quarter_revenue_growth": {"value": 9.335511, "unit": "%", "formula": "(22756 - 20813) / 20813 * 100"}}
        q = {"total_revenue": 22756.0, "revenue_source": 'earnings_release_Ex99-1.txt:L99-L101; quote: "Net sales\\n$\\n22,756"',
             "diluted_eps": 2.98, "diluted_eps_source": 'earnings_release_Ex99-1.txt:L218-L221; quote: "Diluted"'} if quarter else {}
        (run / "facts.json").write_text(json.dumps({"facts": facts}), encoding="utf-8")
        (run / "calculated_facts.json").write_text(json.dumps({"metrics": metrics, "quarter_results": q}), encoding="utf-8")
        return run

    def test_every_core_claim_has_a_row_with_its_value_and_source(self):
        table = core_claims_table(self.run_folder())
        rows = [line for line in table.splitlines() if line.startswith("| ") and not line.startswith("| #")]
        self.assertEqual([row.split(" | ")[0][2:] for row in rows], ["1", "2", "3", "3", "4", "5", "6", "7", "8", "9", "10", "11"])
        for expected in ("$100 billion", "11.77%", "-55.11%", "| -4.026 |", "$12 billion", "22,756, as the release table prints it",
                         "earnings_release_Ex99-1.txt:L99-L101 |", "9.34%", "$2.98", "XBRL tag Revenues, period end 2026-06-30"):
            self.assertIn(expected, table)
        self.assertNotIn("quote:", table)

    def test_a_claim_the_code_could_not_read_says_so(self):
        table = core_claims_table(self.run_folder(quarter=False))
        self.assertIn("| 9 | Latest quarter's revenue | not established by code | the release reader found no table row |", table)

    def test_a_run_without_saved_facts_prints_no_table(self):
        self.assertEqual(core_claims_table(tempfile.mkdtemp()), "")


if __name__ == "__main__":
    unittest.main()
