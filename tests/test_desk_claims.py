"""Claims-ledger checks against invented filing fragments (offline, no model calls)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desk_claims import (LEFT_OUT_REASON, ResponseFormatError, check, parse_response, verifier_without_failing,
                         verify_saved, with_repairs)

ER, K = "earnings_release_Ex99-1.txt", "10-K.txt"
# Invented source fragments and facts. No saved company run is required.
release_lines = ["Synthetic release"] * 50
release_lines[9] = "Net sales for the quarter increased 11.2 percent, to $93.9 billion, from $84.4 billion last year."
annual_lines = ["Synthetic annual filing"] * 725
annual_lines[237] = "Our member renewal rate was 92.3% in the U.S. and Canada"
annual_lines[699] = "Item 7 — Management discussion"
annual_lines[700] = "(amounts in millions, except per share data)"
annual_lines[714] = "Gross margin percentage decreased three basis points"
annual_lines[720] = "Net income increased 14% to $9,226, $20.76 per diluted share"
TEXTS = {ER: "\n".join(release_lines), K: "\n".join(annual_lines)}
FACTS = {"facts": {"net_income": {"value": 9226000000, "tag": "NetIncomeLoss",
          "period_end": "2026-08-30", "filing": "0000000001-26-000001"}}}

SALES = {"id": "c1", "file": ER, "line": 10,
         "quote": "Net sales for the quarter increased 11.2 percent, to $93.9 billion, from $84.4 billion last year.",
         "value": "$93.9 billion"}
GROWTH = {"id": "c2", "file": ER, "line": 10, "quote": SALES["quote"], "value": "11.2 percent"}


def run(claims, draft):
    return check({"claims": claims, "draft": draft}, TEXTS, FACTS)


class ClaimsLedger(unittest.TestCase):
    def test_invented_claims_render_with_citations(self):
        r = run([SALES, GROWTH], "Fourth-quarter net sales rose {c2} to {c1}.")
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.rendered, f"Fourth-quarter net sales rose 11.2 percent [{ER}:L10] "
                                     f"to $93.9 billion [{ER}:L10].")

    def test_written_basis_points_need_no_parser(self):
        c = {"id": "c1", "file": K, "line": 715,
             "quote": "Gross margin percentage decreased three basis points", "value": "three basis points"}
        r = run([c], "Gross margin percentage fell {c1}.")
        self.assertTrue(r.ok, r.errors)
        self.assertIn("three basis points [10-K.txt:L715]", r.rendered)

    def test_mdna_millions_header_scales_dollars_but_not_eps(self):
        quote = "Net income increased 14% to $9,226, $20.76 per diluted share"
        ni = {"id": "c1", "file": K, "line": 721, "quote": quote, "value": "$9,226"}
        eps = {"id": "c2", "file": K, "line": 721, "quote": quote, "value": "$20.76"}
        r = run([ni, eps], "Net income was {c1}, or {c2} per diluted share.")
        self.assertTrue(r.ok, r.errors)
        self.assertIn("$9,226 million [10-K.txt:L721]", r.rendered)
        self.assertIn("$20.76 [10-K.txt:L721] per diluted share", r.rendered)

    def test_xbrl_fact_claim(self):
        r = run([{"id": "c1", "fact": "net_income"}], "Fiscal 2026 net income was {c1}.")
        self.assertTrue(r.ok, r.errors)
        self.assertIn("$9.226 billion [XBRL tag NetIncomeLoss, period end 2026-08-30", r.rendered)

    def test_prose_allows_years_labels_and_ordinary_words(self):
        draft = ("(1) In fiscal 2026 and FY2026, Item 7 shows {c1}.\n"
                 "2. The renewal rate is the one to watch.")
        r = run([SALES], draft)
        self.assertTrue(r.ok, r.errors)

    # ---- failures that must still be caught ----
    def test_wrong_line_is_rejected_with_the_right_line(self):
        r = run([{**SALES, "line": 44}], "Sales were {c1}.")
        self.assertIn("appears on line 10", r.errors[0])

    def test_number_from_another_line_is_rejected(self):
        # The "up to 33 warehouses" failure: real explanation quote, number not in it.
        c = {"id": "c1", "file": K, "line": 238,
             "quote": "Our member renewal rate was 92.3% in the U.S. and Canada", "value": "89.8%"}
        r = run([c], "Worldwide renewal was {c1}.")
        self.assertIn("not in it", r.errors[0])

    def test_tampered_amount_and_scale_rejected(self):
        for bad in ("$93.8 billion", "$93.9 million", "11.3 percent"):
            self.assertFalse(run([{**SALES, "value": bad}], "Sales were {c1}.").ok, bad)
        tampered_quote = {**SALES, "quote": SALES["quote"].replace("93.9", "95.9"), "value": "$95.9 billion"}
        self.assertFalse(run([tampered_quote], "Sales were {c1}.").ok)

    def test_typed_numbers_and_word_amounts_in_prose_rejected(self):
        r = run([SALES], "Sales were {c1}, up 11.2% and three basis points of margin.")
        self.assertEqual(len(r.errors), 2, r.errors)

    def test_missing_and_unused_ids(self):
        r = run([SALES, GROWTH], "Sales were {c1} and {c9}.")
        self.assertTrue(any("c9" in e for e in r.errors))
        self.assertTrue(any("c2 is never used" in e for e in r.errors))

    def test_repair_message_lists_each_error(self):
        r = run([{**SALES, "line": 44}], "Sales were {c1}, up 11.2%.")
        msg = r.repair_message()
        self.assertIn("c1: quote is not on", msg)
        self.assertIn("'11.2%'", msg)


class RepairLoop(unittest.TestCase):
    def test_exhausted_attempts_keep_validation_errors_in_callback(self):
        records=[]
        bad={'claims':[SALES],'draft':'Sales {c1}, up 11.2%.'}
        with self.assertRaisesRegex(ValueError,'after repairs'):
            with_repairs(lambda feedback:bad,TEXTS,FACTS,on_attempt=lambda a:records.append(json.loads(json.dumps(a))))
        self.assertEqual(len(records[-1]),3)
        self.assertTrue(all(a['errors'] for a in records[-1]))

    def test_bad_line_is_repaired_on_the_second_call(self):
        sent = []
        replies = [{"claims": [{**SALES, "line": 44}], "draft": "Sales were {c1}."},
                   {"claims": [SALES], "draft": "Sales were {c1}."}]

        def ask(feedback):
            sent.append(feedback)
            return replies[len(sent) - 1]

        output, attempts = with_repairs(ask, TEXTS, FACTS)
        self.assertEqual(len(attempts), 2)
        self.assertIsNone(sent[0])
        self.assertIn("appears on line 10", sent[1])
        self.assertEqual(output["draft"], f"Sales were $93.9 billion [{ER}:L10].")
        self.assertEqual(output["template"], "Sales were {c1}.")

    def test_gives_up_after_repairs_with_the_remaining_errors(self):
        bad = {"claims": [SALES], "draft": "Sales were {c1}, up 11.2%."}
        with self.assertRaisesRegex(ValueError, "11.2%"):
            with_repairs(lambda feedback: bad, TEXTS, FACTS, repairs=2)


class ClaimBoundaryRegressions(unittest.TestCase):
    def test_filing_form_names_are_identifiers_and_do_not_need_paid_repairs(self):
        r=run([SALES],'The 10-K and 10-Q discuss {c1}. Read Form 4 and the 8-K next.')
        self.assertTrue(r.ok,r.errors)
        self.assertFalse(run([SALES],'The 10-K reports {c1} and $999 of debt.').ok)

    def test_short_quote_retains_per_share_exception_from_source_line(self):
        c={'id':'c1','file':K,'line':721,'quote':'$20.76','value':'$20.76'}
        r=run([c],'EPS was {c1} per diluted share.')
        self.assertTrue(r.ok,r.errors)
        self.assertNotIn('million',r.rendered)

    def test_partial_numbers_and_omitted_units_are_rejected(self):
        for quote,value in [(SALES['quote'],'$9'),('$9','$9'),('$93.9','$93.9'),(SALES['quote'],'93.9 billion'),(SALES['quote'],'11.2')]:
            with self.subTest(quote=quote,value=value):
                self.assertFalse(run([{**SALES,'quote':quote,'value':value}],'Sales were {c1}.').ok)

    def test_multiple_values_in_one_claim_are_rejected(self):
        self.assertFalse(run([{**SALES,'value':'$93.9 billion, from $84.4 billion'}],'Sales were {c1}.').ok)

    def test_brackets_do_not_hide_typed_financial_numbers(self):
        self.assertFalse(run([SALES],'Sales {c1} [debt $999].').ok)

    def test_written_amounts_missing_from_original_word_list_are_rejected(self):
        for word in ['zero','thirteen','sixteen','seventy','ninety']:
            self.assertFalse(run([SALES],f'Sales {{c1}}, up {word} basis points.').ok)

    def test_parenthesized_financial_amount_is_not_a_list_label(self):
        self.assertFalse(run([SALES],'Sales {c1}; loss ($99).').ok)

    def test_malformed_claims_return_repair_errors_instead_of_crashing(self):
        for claim in [None,[],{'id':None},{'id':[]},{**SALES,'quote':3},{**SALES,'value':10},{**SALES,'line':True}]:
            with self.subTest(claim=claim):self.assertFalse(run([claim],'Sales {c1}.').ok)

    def test_invalid_fact_field_is_rejected(self):
        self.assertFalse(run([{'id':'c1','fact':'net_income','which':'tag'}],'Income {c1}.').ok)

    def test_fact_rendering_keeps_exact_value(self):
        facts={'facts':{'net_income':{'value':1234567890,'tag':'NetIncomeLoss','period_end':'2026-08-30','filing':'invented'}}}
        r=check({'claims':[{'id':'c1','fact':'net_income'}],'draft':'Income {c1}.'},{},facts)
        self.assertTrue(r.ok,r.errors)
        self.assertIn('$1.23456789 billion',r.rendered)


class FinancialRepairFalseFlags(unittest.TestCase):
    def test_exact_saved_field_and_tag_identifiers_are_not_amounts(self):
        texts={**TEXTS,'calculated_facts.json':json.dumps({'quarter_results':{'latest_10q_capital_spending':{'value':80}}})}
        facts={'facts':{'example':{'tag':'SavedTag12'}}}
        raw={'claims':[],'draft':'calculated_facts.json latest_10q_capital_spending uses SavedTag12. Read calculated_facts.json#/quarter_results/latest_10q_capital_spending.'}
        self.assertTrue(check(raw,texts,facts).ok)
        for draft in ['unknown_10q_capital_spending is checked.','latest_10q_capital_spending999 is checked.',
                      'latest_10q_capital_spending was $999.','latest_10q_capital_spending rose 15%.',
                      'latest_10q_capital_spending was three million dollars.']:
            self.assertFalse(check({'claims':[],'draft':draft},texts,facts).ok,draft)

    def test_saved_numeric_values_are_not_treated_as_identifiers(self):
        texts={'calculated_facts.json':json.dumps({'metrics':{'value':999,'label':'made_up_10q_label'}})}
        for draft in ['Income 999.','made_up_10q_label is known.']:
            self.assertFalse(check({'claims':[],'draft':draft},texts,{}).ok,draft)

    def test_period_sequences_year_end_and_attributive_years_are_identifiers(self):
        draft='The periods are in the 2026, 2025, 2024 sequence. Capacity is at the end of 2026. The 2026 long-term debt disclosure applies.'
        self.assertTrue(check({'claims':[],'draft':draft},{},{}).ok)
        for amount in ['Income 2026.','There were 2026 warehouses.','Revenue USD 2026.','Income $2026.']:
            self.assertFalse(check({'claims':[],'draft':draft+' '+amount},{},{}).ok,amount)

    def test_explicit_clock_times_are_identifiers_not_financial_values(self):
        for time in ['before 16:00','at 4:00 PM','16:00 ET','the cutoff 16:00:00']:
            self.assertTrue(check({'claims':[],'draft':'Use the close '+time+'.'},{},{}).ok,time)
            self.assertFalse(check({'claims':[],'draft':'Use the close '+time+' and income $999.'},{},{}).ok)
        self.assertFalse(check({'claims':[],'draft':'Use the close at 24:00.'},{},{}).ok)

    def test_identifiers_cannot_hide_decimal_or_percentage_amounts(self):
        for prose in ['Line 15% improved with {c1}.','L1030% improved with {c1}.','August 30% improved with {c1}.',
                      'Line 15 million was spent with {c1}.','August 30 million was spent with {c1}.']:
            self.assertFalse(run([SALES],prose).ok,prose)

    """Saved identifier and numeric boundary checks."""

    def test_dates_and_line_identifiers_are_not_amounts(self):
        for prose in ("For the year ended August 30, sales were {c1}.",
                      "As of Aug. 30, 2026 and August 30th, sales were {c1}.",
                      "See L1030 and L2278: sales were {c1}.",
                      "Quarter revenue (L83–L85) and L83-85 show sales of {c1}.",
                      "The 10-K.txt:L1030 passage and lines 83 to 85 show sales of {c1}."):
            r = run([SALES], prose)
            self.assertTrue(r.ok, (prose, r.errors))

    def test_real_amounts_next_to_identifiers_still_fail(self):
        for prose, typed in (("On August 30 sales were 93.9 billion, or {c1}.", "93.9"),
                             ("L1030 shows capex of $6,435 and {c1}.", "$6,435"),
                             ("August 32 sales were {c1}.", "32"),
                             ("Lines rose 15% with {c1}.", "15%")):
            r = run([SALES], prose)
            self.assertTrue(any(typed in e for e in r.errors), (prose, r.errors))


class MalformedReplies(unittest.TestCase):
    GOOD = {"claims": [SALES], "draft": "Sales were {c1}."}

    def test_unmatched_fences_and_ambiguous_or_nonfinite_objects_are_rejected(self):
        text=json.dumps(self.GOOD)
        for raw in ['```json\n'+text,text+'\n```','{"claims":[],"claims":[{}],"draft":"x"}',
                    '{"claims":[],"draft":"x","n":NaN}','{"claims":[],"draft":"x","n":Infinity}']:
            with self.assertRaises(ResponseFormatError) as caught:parse_response(raw,'Strategy Manager')
            self.assertEqual(caught.exception.raw,raw)

    def test_one_object_with_or_without_a_fence_parses(self):
        text = json.dumps(self.GOOD)
        self.assertEqual(parse_response(text, "Manager"), self.GOOD)
        self.assertEqual(parse_response("```json\n" + text + "\n```", "Manager"), self.GOOD)

    def test_extra_data_after_the_object_is_a_repairable_error_not_a_guess(self):
        for text in (json.dumps(self.GOOD) + "\nI checked every section.",
                     json.dumps(self.GOOD) + json.dumps({"failures": []}),
                     "Here is my answer: " + json.dumps(self.GOOD),
                     '{"claims": [', "[]"):
            with self.assertRaises(ResponseFormatError) as caught:
                parse_response(text, "Strategy Manager")
            self.assertEqual(caught.exception.raw, text)          # raw reply is kept

    def test_malformed_reply_uses_a_repair_attempt_and_is_recorded(self):
        replies = [json.dumps(self.GOOD) + "\nDone.", json.dumps(self.GOOD)]
        sent = []

        def ask(feedback):
            sent.append(feedback)
            return parse_response(replies[len(sent) - 1], "Strategy Manager")

        output, attempts = with_repairs(ask, TEXTS, FACTS)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["output"], {"unparsed_response": replies[0]})
        self.assertIn("text outside its JSON object", sent[1])
        self.assertEqual(output["claim_attempts"], 2)

    def test_repeated_malformed_replies_stop_after_the_repair_limit(self):
        calls = []

        def ask(feedback):
            calls.append(feedback)
            return parse_response("not json", "Strategy Manager")

        with self.assertRaisesRegex(ValueError, "no JSON object"):
            with_repairs(ask, TEXTS, FACTS, repairs=2)
        self.assertEqual(len(calls), 3)


class SavedOutputCheck(unittest.TestCase):
    """What the hook runs on nodes/Research_Analyst_N/output.json."""

    def setUp(self):
        self.run = Path(tempfile.mkdtemp())
        for name in ("10-K.txt", "earnings_release_Ex99-1.txt", "facts.json"):
            (self.run / name).write_text(json.dumps(FACTS) if name == "facts.json" else TEXTS[name], encoding="utf-8")
        self.saved, _ = with_repairs(
            lambda f: {"claims": [SALES, GROWTH], "draft": "Net sales rose {c2} to {c1}."}, TEXTS, FACTS)

    def tearDown(self):
        shutil.rmtree(self.run)

    def test_untouched_output_passes(self):
        self.assertEqual(verify_saved(self.run, self.saved), [])

    def test_edited_rendered_draft_fails(self):
        edited = {**self.saved, "draft": self.saved["draft"].replace("93.9", "95.9")}
        self.assertIn("differs from the rendering", verify_saved(self.run, edited)[0])

    def test_edited_claim_fails(self):
        edited = {**self.saved, "claims": [{**SALES, "value": "$95.9 billion"}, GROWTH]}
        self.assertTrue(verify_saved(self.run, edited))

    def test_changed_source_file_fails(self):
        path = self.run / ER
        path.write_text(path.read_text(encoding="utf-8").replace("$93.9 billion", "$90.0 billion"), encoding="utf-8")
        self.assertTrue(verify_saved(self.run, self.saved))


try:
    from desk_hook import Hook  # uses repository-local hooks/worksheet_numbers.py
except ImportError:
    Hook = None


@unittest.skipIf(Hook is None, "local worksheet_numbers helper is missing")
class HookUsesClaims(SavedOutputCheck):
    def setUp(self):
        super().setUp()
        (self.run / "facts.json").unlink()  # facts.json triggers the SEC companyfacts recheck

    def check(self, data):
        node = self.run / "nodes" / "Research_Analyst_1"
        node.mkdir(parents=True)
        (node / "output.json").write_text(json.dumps(data), encoding="utf-8")
        sources = type("S", (), {"verify": lambda self: None, "data": {"responses": {}}})()
        return Hook(self.run, sources).check("Research Analyst 1", [node / "output.json"])

    def test_hook_passes_claims_output(self):
        self.assertEqual(self.check(self.saved)["status"], "PASS")

    def test_hook_rejects_edited_draft(self):
        from desk_hook import HookFailure
        with self.assertRaises(HookFailure):
            self.check({**self.saved, "draft": self.saved["draft"].replace("93.9", "95.9")})


class ReaderFormats(unittest.TestCase):
    """2026-11-20: a client report printed "11.766682891778505%", "-4.015226378945245 times" and "$-9.917 billion"."""

    def saved(self, **metrics):
        return {"calculated_facts.json": json.dumps({"metrics": metrics})}

    def test_computed_percentages_and_ratios_are_rounded_for_the_reader(self):
        texts = self.saved(
            operating_margin={"formula": "10153000000 / 86286000000", "value": 11.766682891778505, "unit": "%", "sources": ["XBRL tag A"]},
            debt_to_equity={"formula": "(37490000000 + 2431000000) / -9917000000", "value": -4.025511747504286, "unit": "ratio", "sources": ["XBRL tag B"]})
        result = check({"claims": [{"id": "c1", "computed": "operating_margin"}, {"id": "c2", "computed": "debt_to_equity"}],
                        "draft": "Margin {c1}; leverage {c2}."}, texts, {})
        self.assertTrue(result.ok, result.errors)
        self.assertTrue(result.rendered.startswith("Margin 11.77% ["), result.rendered)
        self.assertIn("; leverage -4.026 times [", result.rendered)
        self.assertNotIn("11.7666", result.rendered)

    def test_a_deficit_puts_its_sign_before_the_dollar(self):
        from desk_claims import format_fact
        self.assertEqual(format_fact("stockholders_equity", {"value": -9917000000}, "value"), "-$9.917 billion")
        self.assertEqual(format_fact("diluted_eps", {"value": -1.25}, "value"), "-$1.25")
        self.assertEqual(format_fact("revenue", {"value": 86286000000}, "value"), "$86.286 billion")


class ValueWithoutANumber(unittest.TestCase):
    """A practice run on 2026-11-19 cited "sixth consecutive quarter" as a claim's value."""

    TEXTS = {"r.txt": "We just delivered our sixth consecutive quarter of positive comp sales.\n"}
    QUOTE = "We just delivered our sixth consecutive quarter of positive comp sales"

    def test_the_repair_message_says_the_value_holds_no_number(self):
        claim = {"id": "c1", "file": "r.txt", "line": 1, "quote": self.QUOTE, "value": "sixth consecutive quarter"}
        result = check({"claims": [claim], "draft": "Comparable sales rose for the {c1}."}, self.TEXTS, {})
        self.assertEqual(len(result.errors), 1)
        self.assertIn("holds no number", result.errors[0])
        self.assertIn("state this fact in words without a claim", result.errors[0])

    def test_the_fact_in_words_passes(self):
        result = check({"claims": [], "draft": "Comparable sales rose for the sixth consecutive quarter."}, self.TEXTS, {})
        self.assertTrue(result.ok, result.errors)

    def test_a_number_word_is_still_a_number(self):
        texts = {"r.txt": "Sales rose for six consecutive quarters.\n"}
        claim = {"id": "c1", "file": "r.txt", "line": 1, "quote": "Sales rose for six consecutive quarters.", "value": "six"}
        result = check({"claims": [claim], "draft": "Sales rose for {c1} quarters in a row."}, texts, {})
        self.assertFalse(any("holds no number" in error for error in result.errors), result.errors)


class VerifierLeaveOut(unittest.TestCase):
    """A practice run on 2026-11-19 stopped at the Verifier: two of its 178 reasons and corrections still typed a
    year after two repairs. A reason is the Verifier's explanation; its mark is what the report needs."""

    TEXTS = {"10-K.txt": "Income was $100.\n"}
    A = {"role": "Research Analyst", "claim": "c1"}
    B = {"role": "Research Analyst", "claim": "c2"}

    def validator(self, raw):
        # What validate() does with a Verifier reply, in short: its prose is one draft, reason then correction.
        prose = "\n".join(t for c in raw["checks"] for t in (c.get("reason", ""), c.get("correction", "")))
        result = check({"claims": raw.get("claims", []), "draft": prose}, self.TEXTS, {})
        if result.ok:
            result.output = {"contract": "verification", "claims": raw.get("claims", []), "template_checks": raw["checks"]}
        return result

    def test_a_reason_that_still_fails_is_replaced_and_every_mark_stays(self):
        raw = {"claims": [], "checks": [
            {"target": self.A, "status": "correct", "reason": "The period agrees.", "correction": ""},
            {"target": self.B, "status": "wrong", "reason": "The filing says 1,234 for the year.", "correction": "Use the filing's line."}]}
        output, attempts = with_repairs(lambda feedback: raw, self.TEXTS, {}, validator=self.validator)
        checks = output["template_checks"]
        self.assertEqual([c["status"] for c in checks], ["correct", "wrong"])
        self.assertEqual((checks[0]["reason"], checks[1]["reason"]), ("The period agrees.", LEFT_OUT_REASON))
        self.assertEqual(checks[1]["correction"], "Use the filing's line.")
        self.assertEqual((attempts[-1]["left_out"], attempts[-1]["left_out_lines"]), ([], [3]))

    def test_a_reason_of_two_lines_is_found_by_its_second_line(self):
        raw = {"claims": [], "checks": [
            {"target": self.A, "status": "correct", "reason": "The period agrees.\nThe filing says 99.", "correction": ""},
            {"target": self.B, "status": "correct", "reason": "The unit agrees.", "correction": ""}]}
        mended, _, lines = verifier_without_failing(raw, ["draft line 2: number '99.' is typed directly; use a {cN} claim."])
        self.assertEqual(lines, [2])
        self.assertEqual([c["reason"] for c in mended["checks"]], [LEFT_OUT_REASON, "The unit agrees."])

    def test_a_failing_claim_of_the_verifier_takes_its_texts_with_it(self):
        bad = {"id": "c1", "file": "10-K.txt", "line": 1, "quote": "Income was $100.", "value": "$10"}
        raw = {"claims": [bad], "checks": [
            {"target": self.A, "status": "wrong", "reason": "The filing says {c1}.", "correction": "Use {c1}."},
            {"target": self.B, "status": "correct", "reason": "The unit agrees.", "correction": ""}]}
        output, attempts = with_repairs(lambda feedback: raw, self.TEXTS, {}, validator=self.validator)
        self.assertEqual(output["claims"], [])
        self.assertEqual([(c["reason"], c["correction"]) for c in output["template_checks"]],
                         [(LEFT_OUT_REASON, ""), ("The unit agrees.", "")])
        self.assertEqual(attempts[-1]["left_out"], ["c1"])

    def test_a_fiscal_year_label_is_not_a_typed_number(self):
        text = "facts.json revenue: period_end 2026-01-30, fy 2025, filing 0000060667-26-000029."
        self.assertTrue(check({"claims": [], "draft": text}, self.TEXTS, {}).ok)
        self.assertTrue(check({"claims": [], "draft": "Revenue for FY 2025 rose."}, self.TEXTS, {}).ok)
        self.assertFalse(check({"claims": [], "draft": "Revenue was 2025 million."}, self.TEXTS, {}).ok)


class LeaveOutAfterRepairs(unittest.TestCase):
    """On 2026-11-19 one claim of about forty still failed after two repairs, and the whole run stopped with no
    report. A missing claim costs nothing in the audit, so the failing claims and their lines are left out."""

    TEXTS = {"10-K.txt": "Income was $100.\nDebt was $20.\n"}
    GOOD = {"id": "c1", "file": "10-K.txt", "line": 1, "quote": "Income was $100.", "value": "$100"}
    BAD = {"id": "c2", "file": "10-K.txt", "line": 2, "quote": "Debt was $20.", "value": "$2"}  # a substring of $20

    def test_a_claim_that_still_fails_is_left_out_with_its_line(self):
        raw = {"claims": [self.GOOD, self.BAD], "draft": "Income was {c1}.\nDebt was {c2}.\nInsight: Income held at {c1}."}
        output, attempts = with_repairs(lambda feedback: raw, self.TEXTS, {})
        self.assertEqual([c["id"] for c in output["claims"]], ["c1"])
        self.assertNotIn("Debt", output["draft"])
        self.assertIn("Income was $100 [10-K.txt:L1].", output["draft"])
        self.assertEqual(len(attempts), 4)  # three tries, then the reply with the failing claim left out
        self.assertEqual((attempts[-1]["errors"], attempts[-1]["left_out"]), ([], ["c2"]))
        self.assertEqual((attempts[-1]["left_out_lines"], attempts[-1]["from_attempt"]), ([2], 3))
        self.assertEqual(output["claim_attempts"], 4)

    def test_a_typed_number_leaves_out_its_line(self):
        raw = {"claims": [self.GOOD], "draft": "Income was {c1}.\nSales rose 10 percent.\nInsight: Income held at {c1}."}
        output, attempts = with_repairs(lambda feedback: raw, self.TEXTS, {})
        self.assertNotIn("Sales rose", output["draft"])
        self.assertEqual((attempts[-1]["left_out"], attempts[-1]["left_out_lines"]), ([], [2]))

    def test_a_claim_used_only_beside_a_failing_one_goes_with_it(self):
        raw = {"claims": [self.GOOD, self.BAD], "draft": "Income was {c1} and debt was {c2}.\nInsight: Debt rose."}
        output, attempts = with_repairs(lambda feedback: raw, self.TEXTS, {})
        self.assertEqual((output["claims"], output["draft"]), ([], "Insight: Debt rose."))
        self.assertEqual(attempts[-1]["left_out"], ["c1", "c2"])

    def test_the_latest_reply_that_can_be_mended_is_used(self):
        replies = iter([{"claims": [self.GOOD, self.BAD], "draft": "Income was {c1}.\nDebt was {c2}."},
                        {"claims": [self.GOOD], "draft": "Income was {c1}, up 10%.\nInsight: Income held."},
                        {"unparsed_response": "not JSON"}])
        output, attempts = with_repairs(lambda feedback: next(replies), self.TEXTS, {})
        self.assertEqual(output["template"], "Insight: Income held.")
        self.assertEqual(attempts[-1]["from_attempt"], 2)

    def test_a_reply_of_the_wrong_shape_still_stops(self):
        with self.assertRaisesRegex(ValueError, "still fail after repairs"):
            with_repairs(lambda feedback: {"claims": "not a list", "draft": "Income."}, self.TEXTS, {})

    def test_nothing_left_still_stops(self):
        raw = {"claims": [self.BAD], "draft": "Debt was {c2}."}
        with self.assertRaisesRegex(ValueError, "still fail after repairs"):
            with_repairs(lambda feedback: raw, self.TEXTS, {})

    def test_the_saved_output_passes_the_hooks_check(self):
        run = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, run)
        (run / "10-K.txt").write_text(self.TEXTS["10-K.txt"], encoding="utf-8")
        raw = {"claims": [self.GOOD, self.BAD], "draft": "Income was {c1}.\nDebt was {c2}."}
        output, _ = with_repairs(lambda feedback: raw, self.TEXTS, {})
        self.assertEqual(verify_saved(run, output), [])


if __name__ == "__main__":
    unittest.main()
