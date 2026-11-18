"""Offline tests of the worksheet skill and of the facts the steps save for it. Made-up data; no network, no key.

Run from the repository folder: python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import worksheet  # noqa: E402
from lab02_desk import FACT_ORDER, fiscal_years  # noqa: E402
from test_desk import LAST_YEAR_END, YEAR_END, company_facts, desk_after_steps_4_and_5, fact  # noqa: E402
from test_team import FakeModel  # noqa: E402

ENDS = ["2026-08-30", "2025-08-31", "2024-09-01"]
STARTS = ["2025-09-01", "2024-09-02", "2023-09-04"]
# A made-up worksheet file. The team's own file is written by hand and is not in the tests.
METHOD = {"method": worksheet.METHOD, "owner_cash_flow_years": 3, "low_rate": 0.10, "mid_rate": 0.05, "purchase_size": 100000,
          "liquidity_days": 3, "liquidity_share_of_daily_volume": 0.10,
          "conviction_rule": "High when the price is below the low case. Low in every other case."}
GOOD_REPLY = {"why": "The price is 150.00% above the low case, so the name is not cheap on owner cash flow.",
              "what_would_change_the_view": "A fall in owner cash flow in the next 10-Q.",
              "view": "less", "deciding_label": "Price against the low case", "conviction": "low",
              "conviction_reason": "The price is not below the low case."}


def years(values: list[float], unit: str = "USD") -> list[dict[str, Any]]:
    return [fact(start, end, value, unit) for start, end, value in zip(STARTS, ENDS, values)]


def saved_run(price: float | None = 50.0, inputs: dict[str, Any] | None = None, not_stated: str = "") -> Path:
    """A made-up run folder, as the agent team saves one: the facts, the price, the steps' record and the release."""
    folder = Path(tempfile.mkdtemp()) / "EXM_20260924_170000"
    (folder / "nodes").mkdir(parents=True)
    sheet_inputs = {
        "net_income": {"tag": "NetIncomeLoss", "unit": "USD", "years": years([1000e6, 900e6, 800e6])},
        "depreciation": {"tag": "DepreciationDepletionAndAmortization", "unit": "USD", "years": years([200e6, 190e6, 180e6])},
        "capex": {"tag": "PaymentsToAcquirePropertyPlantAndEquipment", "unit": "USD", "years": years([300e6, 290e6, 280e6])},
        "diluted_shares": {"tag": "WeightedAverageNumberOfDilutedSharesOutstanding", "unit": "shares", "years": years([400e6], "shares")},
    }
    sheet_inputs.update(inputs or {})
    facts: dict[str, Any] = {"company": "Example Corp", "ticker": "EXM", "facts": {}, "worksheet": sheet_inputs}
    if not_stated:
        facts = {"company": "Example Corp", "ticker": "EXM", "facts": {}, "not_stated": not_stated}
    (folder / "facts.json").write_text(json.dumps(facts), encoding="utf-8")
    (folder / "verified_report.md").write_text("Filings read: 10-K 0000000001-26-000003\n", encoding="utf-8")
    note = "$50.00, the close of 2026-09-23, the last close before 2026-09-24 16:05:00 ET, when the release was accepted, from a test"
    (folder / "price.json").write_text(json.dumps({"price": price, "note": note if price is not None else "none; no close"}), encoding="utf-8")
    quarter = {"revenue": 95723.0, "revenue_shown": "95,723", "revenue_prior_shown": "86,156", "revenue_growth": 95723 / 86156 - 1,
               "revenue_line": "Total revenue | 95,723 | 86,156", "eps": 6.75, "eps_shown": "$6.75", "eps_line": "Diluted | $6.75 | $5.87",
               "period": "August 30, 2026", "units": "millions"}
    steps = {"output": {"quarter": quarter, "filings": {"8-K": {"accessionNumber": "0000000001-26-000004", "accepted_index": "2026-09-24 16:05:00"}}}}
    (folder / "nodes" / "01_steps.json").write_text(json.dumps(steps), encoding="utf-8")
    (folder / "8K_2026-09-24_release.txt").write_text("Total revenue | 95,723 | 86,156\nDiluted | $6.75 | $5.87\n", encoding="utf-8")
    return folder


def bars(ticker: str, last_day: date, days: int) -> Any:
    return [(date(2026, 9, 21), 50.0, 1e6), (date(2026, 9, 22), 50.0, 2e6), (date(2026, 9, 23), 50.0, 4e6)], "a test source"


def sheet(folder: Path, reply: dict[str, Any] | None = None, method: dict[str, Any] | None = None, registry: dict[str, Any] | None = None,
          reader: Any = bars) -> tuple[worksheet.Worksheet, str, FakeModel]:
    model = FakeModel({"Worksheet (persona)": lambda packet: dict(reply or GOOD_REPLY)})
    made = worksheet.Worksheet(folder, model, dict(method or METHOD), "A made-up persona for the tests.", Path("worksheet.json"), Path("persona.md"),
                               registry=registry, bars=reader, now=datetime(2026, 9, 24, 17, 30).astimezone())
    made.build()
    made.save()
    return made, (folder / "worksheet.md").read_text(encoding="utf-8"), model


class StepFourSavesTheWorksheetsInputs(unittest.TestCase):
    """Step 4 saves the parts of owner cash flow apart from the core facts, for three fiscal years at most."""

    def facts(self, drop: str = "") -> dict[str, Any]:
        made = company_facts({})

        def concept(values: list[dict[str, Any]], unit: str = "USD") -> dict[str, Any]:
            return {"label": "a label", "units": {unit: values}}

        made["facts"]["us-gaap"].update({
            "NetIncomeLoss": concept(years([1000e6, 900e6, 800e6])),
            "DepreciationDepletionAndAmortization": concept(years([200e6, 190e6, 180e6])),
            "PaymentsToAcquirePropertyPlantAndEquipment": concept(years([300e6, 290e6, 280e6])),
            "WeightedAverageNumberOfDilutedSharesOutstanding": concept(years([400e6, 410e6, 420e6], "shares"), "shares"),
        })
        made["facts"]["us-gaap"].pop(drop, None)
        return made

    def saved(self, drop: str = "") -> dict[str, Any]:
        desk, _ = desk_after_steps_4_and_5({}, facts=self.facts(drop))
        return json.loads((desk.outdir / "facts.json").read_text(encoding="utf-8"))

    def test_three_fiscal_years_newest_first_with_each_tag(self) -> None:
        saved = self.saved()
        inputs = saved["worksheet"]
        self.assertEqual([y["end"] for y in inputs["net_income"]["years"]], [YEAR_END, LAST_YEAR_END, "2024-09-01"])
        self.assertEqual([y["val"] for y in inputs["depreciation"]["years"]], [200e6, 190e6, 180e6])
        self.assertEqual(inputs["capex"]["tag"], "PaymentsToAcquirePropertyPlantAndEquipment")
        self.assertEqual(inputs["diluted_shares"]["unit"], "shares")
        # The core facts are what they were: the roles and the Verifier receive nothing new.
        self.assertEqual(list(saved["facts"]), FACT_ORDER)

    def test_a_part_the_10k_does_not_tag_is_none_and_never_filled(self) -> None:
        self.assertIsNone(self.saved(drop="DepreciationDepletionAndAmortization")["worksheet"]["depreciation"])

    def test_a_missing_year_ends_the_list(self) -> None:
        vals = [fact("2025-09-01", "2026-08-30", 3.0), fact("2023-09-04", "2024-09-01", 1.0)]  # the year between is missing
        self.assertEqual([v["val"] for v in fiscal_years(vals, "2026-08-30", 3)], [3.0])


class WorksheetTests(unittest.TestCase):
    def test_owner_cash_flow_the_range_and_the_price_with_the_arithmetic_printed(self) -> None:
        _, text, _ = sheet(saved_run())
        for line in (
            "- Net income, fiscal year ended 2026-08-30: $1,000.0M [fact: us-gaap:NetIncomeLoss, 2025-09-01 to 2026-08-30]",
            "- Owner cash flow, fiscal year ended 2026-08-30: $900.0M [computed: 1,000.0 + 200.0 - 300.0]",
            "- Owner cash flow, the average of the fiscal years above: $800.0M [computed: (900.0 + 800.0 + 700.0) / 3]",
            "- Rate of the low case: 10.00% [rate: low_rate]",
            "- Low case, value: $8,000.0M [computed: 800.0 / 0.1]",
            "- Mid case, value: $16,000.0M [computed: 800.0 / 0.05]",
            "- Low case, per share: $20.00 [computed: 8,000.0 / 400.0]",
            "- Price against the low case: 150.00% above the low case [computed: 50.00 / 20.00 - 1]",
            "- Price: $50.00 (the close of 2026-09-23, the last close before 2026-09-24 16:05:00 ET, when the release was accepted, from a test) [price: price.json]",
            '- Revenue of the quarter (August 30, 2026), in millions: 95,723 [line: 8K_2026-09-24_release.txt, "Total revenue | 95,723 | 86,156"]',
        ):
            self.assertIn(line, text)
        self.assertTrue(text.splitlines()[1].startswith("Screens to look at, not a recommendation."))

    def test_the_view_is_the_personas_and_its_number_is_a_printed_line(self) -> None:
        made, text, _ = sheet(saved_run())
        self.assertIn("- View: the company is worth less than the price.", text)
        self.assertIn("- The number that decides it: 150.00% [worksheet: Price against the low case]", text)
        self.assertIn("- Conviction: low, by the rule in the worksheet file.", text)
        view = json.loads((made.run_dir / "view.json").read_text(encoding="utf-8"))
        self.assertEqual((view["view"], view["number"], view["conviction"]), ("less", "150.00%", "low"))
        self.assertEqual(view["release"], "0000000001-26-000004")
        # What hit_rate.py reads: the ticker, two times with their UTC offsets, and the direction.
        self.assertEqual((view["ticker"], view["direction"]), ("EXM", "down"))
        self.assertEqual(view["filing_time"], "2026-09-24T16:05:00-04:00")  # EDGAR's Eastern time, with its offset
        self.assertEqual(view["time"], made.now.isoformat(timespec="seconds"))
        self.assertIsNotNone(datetime.fromisoformat(view["time"]).tzinfo)

    def test_the_persona_receives_the_worksheets_lines_and_nothing_from_the_reader(self) -> None:
        _, text, model = sheet(saved_run())
        sent = model.exchanges[0]["sent"]
        self.assertEqual(sorted(sent["context"]), ["conviction_rule", "worksheet_lines"])
        given = "\n".join(sent["context"]["worksheet_lines"])
        self.assertIn("Price against the low case", given)
        self.assertNotIn("dollar volume", given)  # the liquidity line is added after the call, in code
        self.assertIn("- Trading days the reader gave: 3 [reader: liquidity.json, days]", text)
        self.assertIn("- Median daily dollar volume of those days, to 2026-09-23, from a test source: $100.0M [reader: liquidity.json, median_dollar_volume_millions]", text)
        self.assertIn("- The most the client may buy in one day: $10.0M [computed: 100.0 * 0.1]", text)
        self.assertIn("buyable in one day", text)

    def test_the_series_of_closes_is_not_saved_only_the_median(self) -> None:
        made, _, _ = sheet(saved_run())
        saved = json.loads((made.run_dir / "liquidity.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, {"median_dollar_volume_millions": 100.0, "days": 3, "from": "2026-09-21", "to": "2026-09-23", "source": "a test source"})

    def test_a_number_the_worksheet_does_not_print_leaves_the_judgment_out(self) -> None:
        reply = dict(GOOD_REPLY, why="Owner cash flow will grow 12% next year, so the name is cheap.")
        made, text, _ = sheet(saved_run(), reply=reply)
        self.assertIn("- Not written: the persona wrote a number that the worksheet does not print.", text)
        self.assertIn("- View: not computed, because the persona wrote a number that the worksheet does not print.", text)
        self.assertNotIn("12%", text)  # the number is not repeated: every number in the worksheet has a source
        view = json.loads((made.run_dir / "view.json").read_text(encoding="utf-8"))
        self.assertEqual((view["view"], view["direction"], view["numbers_left_out"]), ("not computed", "not computed", ["12%"]))

    def test_a_score_written_as_a_digit_is_a_number_too_and_the_persona_is_told_so(self) -> None:
        # On 2026-11-16 a persona that scores its criteria wrote the scores as digits, and its judgment was left out.
        made, text, _ = sheet(saved_run(), reply=dict(GOOD_REPLY, why="Criterion 4 scores 2, so the name is not cheap."))
        self.assertIn("- Not written: the persona wrote a number that the worksheet does not print.", text)
        self.assertEqual(json.loads((made.run_dir / "view.json").read_text(encoding="utf-8"))["numbers_left_out"], ["2", "4"])

        class Recording(FakeModel):
            def ask(self, role: str, instructions: str, packet: dict[str, Any]) -> dict[str, Any]:
                self.instructions = instructions
                return super().ask(role, instructions, packet)

        model = Recording({"Worksheet (persona)": lambda packet: dict(GOOD_REPLY)})
        worksheet.Worksheet(saved_run(), model, dict(METHOD), "A made-up persona for the tests.", Path("worksheet.json"), Path("persona.md"), bars=bars).build()
        # The persona's own text comes first, and the worksheet's rules after it. One rule is about digits.
        self.assertTrue(model.instructions.startswith("A made-up persona for the tests."))
        self.assertIn("A score, a count or the number of a criterion is written as a word.", model.instructions)

    def test_a_year_alone_names_a_period_and_a_comma_ends_a_number(self) -> None:
        self.assertEqual(worksheet.numbers_in("Revenue of the quarter (2026), in millions: 96,221"), ["96,221"])
        self.assertEqual(worksheet.numbers_in("It scored 0, then 4."), ["0", "4"])
        self.assertEqual(worksheet.numbers_in("$2,026.0M in 2026, and 2026.5 or $2026"), ["$2,026.0M", "2026.5", "$2026"])

    def test_a_deciding_line_that_is_not_printed_gives_no_view(self) -> None:
        _, text, _ = sheet(saved_run(), reply=dict(GOOD_REPLY, deciding_label="The growth I expect"))
        self.assertIn("- View: not computed, because the persona named a deciding line that the worksheet does not print.", text)

    def test_no_close_means_no_price_lines_and_no_view(self) -> None:
        made, text, _ = sheet(saved_run(price=None))
        self.assertIn("- Price: not computed.", text)
        self.assertIn("- Price against the low case: not computed. The run has no close.", text)
        self.assertIn("- View: not computed, because the run has no close.", text)
        self.assertIn("- Median daily dollar volume: not known.", text)
        self.assertFalse((made.run_dir / "liquidity.json").exists())

    def test_fewer_years_than_the_method_asks_is_not_computed(self) -> None:
        short = {"depreciation": {"tag": "DepreciationDepletionAndAmortization", "unit": "USD", "years": years([200e6, 190e6])[:2]}}
        _, text, _ = sheet(saved_run(inputs=short))
        self.assertIn("- Owner cash flow: not computed. The method asks for more fiscal years with net income, depreciation and capital spending than the run saved.", text)
        self.assertNotIn("Low case, value", text)
        self.assertIn("## Not known", text)

    def test_owner_cash_flow_that_is_not_above_zero_gives_no_range(self) -> None:
        heavy = {"capex": {"tag": "PaymentsToAcquirePropertyPlantAndEquipment", "unit": "USD", "years": years([1500e6, 1400e6, 1300e6])}}
        _, text, _ = sheet(saved_run(inputs=heavy))
        self.assertIn("- Low case and mid case: not computed. Owner cash flow is not above zero, and the method divides it by a rate.", text)

    def test_a_run_with_no_annual_facts_says_so(self) -> None:
        _, text, _ = sheet(saved_run(not_stated="the facts are another year's"))
        self.assertIn("- The annual facts: not known. The run states none: the facts are another year's.", text)

    def test_a_name_the_seeker_never_saw_is_not_applicable_and_the_rest_runs(self) -> None:
        _, text, _ = sheet(saved_run())
        self.assertIn("## Facts of the spinoff\n- Not applicable. The ticker is not in the seeker's registry", text)
        self.assertIn("## Value range", text)

    def test_a_name_in_the_registry_states_its_facts_with_their_filing(self) -> None:
        registry = {"EXM": {"ticker": "EXM", "parent": {"value": "Parent Corp", "filing": "0000000009-26-000001", "section": "Summary"},
                            "ratio": {"value": "", "filing": "", "section": ""}}}
        _, text, _ = sheet(saved_run(), registry=registry)
        self.assertIn("- Parent: Parent Corp (registry: 0000000009-26-000001, Summary)", text)
        self.assertIn("- Distribution ratio: not known. The seeker's registry holds no value for it.", text)


class HandWrittenFiles(unittest.TestCase):
    """The method and the persona are a team member's. Code stops when one is missing, and fills nothing."""

    def write(self, method: dict[str, Any]) -> Path:
        path = Path(tempfile.mkdtemp()) / "worksheet.json"
        path.write_text(json.dumps(method), encoding="utf-8")
        return path

    def test_a_missing_file_names_itself_and_who_writes_it(self) -> None:
        with self.assertRaises(worksheet.WorksheetError) as caught:
            worksheet.load_method(Path(tempfile.mkdtemp()) / "worksheet.json")
        self.assertIn("A team member writes it by hand; no AI writes it.", str(caught.exception))
        with self.assertRaises(worksheet.WorksheetError):
            worksheet.load_persona(Path(tempfile.mkdtemp()) / "persona.md")

    def test_a_missing_value_and_an_unknown_method_stop(self) -> None:
        with self.assertRaises(worksheet.WorksheetError) as caught:
            worksheet.load_method(self.write({k: v for k, v in METHOD.items() if k != "low_rate"}))
        self.assertIn("low_rate", str(caught.exception))
        with self.assertRaises(worksheet.WorksheetError) as caught:
            worksheet.load_method(self.write(dict(METHOD, method="a multiple of EBITDA")))
        self.assertIn("knows one method", str(caught.exception))
        with self.assertRaises(worksheet.WorksheetError):
            worksheet.load_method(self.write(dict(METHOD, low_rate=10)))  # a rate is a fraction, not a percent
        self.assertEqual(worksheet.load_method(self.write(METHOD))["mid_rate"], 0.05)

    def test_the_repository_holds_no_method_or_persona_that_code_wrote(self) -> None:
        # The team's own files are added by a member. Until then client/ holds the README alone.
        for name in ("worksheet.json", "persona.md", "factors.json"):
            path = ROOT / "client" / name
            if path.exists():
                self.assertNotIn("made-up", path.read_text(encoding="utf-8").lower(), name)

    def test_the_worksheet_code_names_no_company(self) -> None:
        source = (ROOT / "worksheet.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b(COST|WMT|TGT|BJ|AAPL|MSFT|CSCO|NVDA)\b", source))


if __name__ == "__main__":
    unittest.main()
