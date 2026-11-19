import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS))
from worksheet_numbers import Auditor, audit_paths
import worksheet_gate as gate


class NumberTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / 'run'
        self.run.mkdir()
        self.worksheet = self.run / 'Spinoff worksheet, TEST.md'
        (self.run / 'facts.json').write_text(json.dumps({'facts': {
            'earnings': {'tag':'NetIncomeLoss', 'period_end':'2026-08-30', 'value':100,
                         'prior_period_end':'2025-08-31', 'prior_value':80}}}))
        (self.run / '10-K.txt').write_text('Depreciation 20\nCapital spending 30\nShares 10\nScale 1000000\n')
        rules = self.root / 'skills/spinoff-worksheet/SKILL.md'
        rules.parent.mkdir(parents=True)
        rules.write_text('Low rate: 10%\nWeight: 0.5\n')
        (self.run / 'reader response.json').write_text(json.dumps([
            {'ticker':'TEST','date':'2026-11-11','close':50,'volume':200}]))
        self.valid = '\n'.join([
            'Worksheet as of 2026-11-12T09:22:40.444799-05:00; accession 0000909832-26-000093',
            'earnings = 100 [fact tag=NetIncomeLoss period=2026-08-30]',
            'depreciation = 20 [filing path="10-K.txt" line=1]',
            'capex = 30 [filing path="10-K.txt" line=2]',
            'owner_cash_flow = 90 [calc expr="earnings + depreciation - capex"]',
            'rate = 0.1 [rule path="skills/spinoff-worksheet/SKILL.md" line=1 literal=10%]',
            'shares = 10 [filing path="10-K.txt" line=3]',
            'low = 90 [calc expr="owner_cash_flow / rate / shares"]',
            'price = 50 [reader path="reader response.json" ticker=TEST date=2026-11-11 field=close]',
            'volume = 200 [reader path="reader response.json" ticker=TEST date=2026-11-11 field=volume]',
            'turnover = 10000 [calc expr="price * volume"]',
        ])

    def check(self, text):
        self.worksheet.write_text(text)
        return Auditor(self.run, self.root).check(self.worksheet)

    def test_valid_sources_and_chained_calculations(self):
        self.assertEqual(self.check(self.valid), [])

    def test_worksheet_tamper_fails_even_when_other_files_are_unchanged(self):
        bad = self.valid.replace('owner_cash_flow = 90', 'owner_cash_flow = 91')
        failures = self.check(bad)
        self.assertTrue(any(f.line == 5 and '91' in f.text for f in failures))

    def test_tag_and_period_must_match_exactly(self):
        for old, new in [('NetIncomeLoss','WrongTag'), ('period=2026-08-30','period=2026-08-31'), ('earnings = 100','earnings = 101')]:
            with self.subTest(new=new):
                self.assertTrue(self.check(self.valid.replace(old,new)))

    def test_prior_period_exact_match(self):
        self.assertEqual(self.check('earnings = 80 [fact tag=NetIncomeLoss period=2025-08-31]'), [])

    def test_conflicting_tag_period_fails(self):
        path = self.run/'facts.json'
        data = json.loads(path.read_text())
        data['facts']['conflict'] = {'tag':'NetIncomeLoss','period_end':'2026-08-30','value':101}
        path.write_text(json.dumps(data))
        self.assertTrue(self.check(self.valid))

    def test_start_period_must_match_if_claimed(self):
        self.assertTrue(self.check('100 [fact tag=NetIncomeLoss period=2026-08-30 start=2025-08-31]'))

    def test_citation_checks_exact_line_not_nearby(self):
        self.assertTrue(self.check('30 [filing path="10-K.txt" line=1]'))
        self.assertTrue(self.check('30000000 [filing path="10-K.txt" line=2]'))

    def test_existing_table_citation_and_identifiers(self):
        self.assertEqual(self.check('depreciation | 20 | historical | [10-K.txt:L1]'), [])
        self.assertTrue(self.check('depreciation | 21 | historical | [10-K.txt:L1]'))

    def test_dates_accessions_and_line_identifiers_are_skipped(self):
        self.assertEqual(self.check('September 29, 2026; accession 000090983226000093; line 1204; L1660'), [])
        self.assertTrue(self.check('September 99, 2026'))

    def test_legacy_price_or_rate_cannot_pass_on_a_filing_match(self):
        self.assertTrue(self.check('price | 20 | [10-K.txt:L1]'))
        self.assertTrue(self.check('weight | 20 | [10-K.txt:L1]'))

    def test_filing_quote_is_checked(self):
        self.assertTrue(self.check('Quote: "20 and 999" [10-K.txt:L1]'))

    def test_rate_and_weight_match_authored_file(self):
        self.assertTrue(self.check('rate = 0.11 [rule path="skills/spinoff-worksheet/SKILL.md" line=1 literal=10%]'))
        self.assertEqual(self.check('weight = 0.5 [rule path="skills/spinoff-worksheet/SKILL.md" line=2]'), [])

    def test_arbitrary_rate_source_is_rejected(self):
        self.assertTrue(self.check('rate = 20 [rule path="run/10-K.txt" line=1]'))

    def test_reader_price_date_ticker_and_value_are_exact(self):
        for old,new in [('price = 50','price = 51'), ('ticker=TEST','ticker=OTHER'), ('date=2026-11-11','date=2026-11-10')]:
            with self.subTest(new=new): self.assertTrue(self.check(self.valid.replace(old,new)))

    def test_duplicate_reader_date_fails(self):
        path = self.run/'reader response.json'
        data = json.loads(path.read_text())
        path.write_text(json.dumps(data+data))
        self.assertTrue(self.check(self.valid))

    def test_companion_worksheet_is_not_a_reader_source(self):
        (self.run/'Spinoff worksheet.json').write_text((self.run/'reader response.json').read_text())
        self.assertTrue(self.check(self.valid.replace('reader response.json','Spinoff worksheet.json')))

    def test_unclassified_numeric_prose_and_code_fail(self):
        for text in ['Worth 999 dollars.', 'Score: 2', '```\n999\n```', 'Hidden 1e9', '<!-- 123 -->', 'Worth one billion dollars', 'Revenue was one billion']:
            with self.subTest(text=text): self.assertTrue(self.check(text))

    def test_filing_form_identifiers_are_not_financial_values(self):
        for text in ['Form 4', 'Form 4/A', 'Form 10-K', 'Form 10-Q', 'Form 8-K', 'Form 10', 'Form S-1', 'Form 13F', 'No saved Form 4 XML; coverage is not established']:
            with self.subTest(text=text): self.assertEqual(self.check(text), [])

    def test_ordinary_counts_and_period_labels_are_not_financial_values(self):
        for text in ['At least one condition is missing.', 'Review the next one.', 'Fiscal year 2026', 'FY2026', 'Q1 2026', 'Criterion 1 — Forced seller: not known', '1. Review the filing.']:
            with self.subTest(text=text): self.assertEqual(self.check(text), [])

    def test_financial_values_beside_identifiers_remain_checked(self):
        for text in ['Form 4: purchase price $20', 'Fiscal year 2026: revenue 999', 'Criterion 1 — Forced seller: 2', 'Form 10-K reports revenue of one billion dollars', 'At least one condition: debt $999']:
            with self.subTest(text=text): self.assertTrue(self.check(text))

    def test_calculation_cannot_introduce_unverified_constants(self):
        self.assertTrue(self.check('value = 100 [calc expr="50 + 50"]'))
        self.assertTrue(self.check('value = 100 [calc expr="missing + missing"]'))

    def test_rounding_applies_only_to_calculation_results(self):
        text = self.valid+'\nratio = 0.556 [calc expr="price / owner_cash_flow"]'
        self.assertEqual(self.check(text), [])
        self.assertTrue(self.check(text.replace('ratio = 0.556','ratio = 0.557')))
        self.assertTrue(self.check('100.01 [fact tag=NetIncomeLoss period=2026-08-30]'))

    def test_duplicate_input_name_fails(self):
        self.assertTrue(self.check(self.valid+'\nearnings = 100 [fact tag=NetIncomeLoss period=2026-08-30]'))

    def test_median_count_and_ceil_use_printed_inputs(self):
        text = self.valid+'\nmedian_value = 40 [calc expr="median(price, capex)"]\nobservations = 2 [calc expr="count(price, capex)"]\ndays = 2 [calc expr="ceil(price / capex)"]'
        self.assertEqual(self.check(text), [])
        self.assertTrue(self.check(text.replace('median_value = 40','median_value = 41')))

    def test_numeric_sign_and_fraction_are_not_lost(self):
        (self.run/'10-K.txt').write_text('Negative −20\nFraction .5\n')
        self.assertEqual(self.check('−20 [filing path="10-K.txt" line=1]'), [])
        self.assertTrue(self.check('20 [filing path="10-K.txt" line=1]'))
        self.assertEqual(self.check('.5 [filing path="10-K.txt" line=2]'), [])
        self.assertTrue(self.check('5 [filing path="10-K.txt" line=2]'))

    def test_market_price_and_rate_cannot_use_wrong_source_kind(self):
        self.assertTrue(self.check('price = 100 [fact tag=NetIncomeLoss period=2026-08-30]'))
        self.assertTrue(self.check('rate = 20 [filing path="10-K.txt" line=1]'))

    def test_other_skill_is_not_the_active_skill(self):
        path = self.root/'skills/other/SKILL.md'
        path.parent.mkdir(parents=True)
        path.write_text('Rate 10%')
        self.assertTrue(self.check('rate = 0.1 [rule path="skills/other/SKILL.md" line=1]'))

    def test_malformed_reader_output_reports_original_worksheet_line(self):
        (self.run/'reader response.json').write_text('["not a price row"]')
        failures = self.check(self.valid)
        self.assertTrue(any(f.line == 9 and 'price = 50' in f.text for f in failures))

    def test_paths_cannot_leave_the_run(self):
        (self.root/'outside.txt').write_text('20')
        self.assertTrue(self.check('20 [filing path="../outside.txt" line=1]'))

    def test_malformed_annotation_cannot_hide_a_number(self):
        for text in ['20 [filing path="10-K.txt" line=1 extra=999]', '[calc expr="999"]', '20 [unknown line=999]']:
            with self.subTest(text=text): self.assertTrue(self.check(text))

    def test_cli_pass_and_fail_exit_status_and_original_line(self):
        self.check(self.valid)
        cmd = [sys.executable, str(HOOKS/'worksheet_numbers.py'), '--run', str(self.run), '--workspace', str(self.root)]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.worksheet.write_text('Bad price 999')
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Bad price 999', result.stderr)
        self.assertIn(':1:', result.stderr)


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.output = self.root/'equity_research_output'
        self.run = self.output/'run'
        self.run.mkdir(parents=True)
        self.path = self.run/'Spinoff worksheet, TEST.md'
        self.patchers = [patch.object(gate,'WORKSPACE',self.root), patch.object(gate,'OUTPUT',self.output), patch.object(gate,'STATE',self.root/'.state')]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)

    def event(self,name,**kwargs):
        return gate.handle({'hook_event_name':name,'session_id':'test',**kwargs})

    def test_start_baseline_excludes_old_worksheets(self):
        self.path.write_text('Old number 999')
        self.assertEqual(self.event('SessionStart'), {})
        self.assertEqual(self.event('Stop'), {})

    def test_after_write_block_and_stop_still_blocks_on_continuation(self):
        self.event('SessionStart')
        self.path.write_text('Bad claim 999')
        for event in ('PostToolUse','Stop','Stop'):
            result = self.event(event, stop_hook_active=True)
            self.assertEqual(result['decision'], 'block')
            self.assertIn('Bad claim 999',result['reason'])

    def test_existing_worksheet_edit_is_checked(self):
        self.path.write_text('No numbers')
        self.event('SessionStart')
        self.path.write_text('Bad claim 999')
        self.assertEqual(self.event('PostToolUse')['decision'],'block')

    def test_correction_is_rechecked_and_releases_stop(self):
        self.event('SessionStart')
        self.path.write_text('Bad claim 999')
        self.event('PostToolUse')
        self.path.write_text('Missing amount: not known')
        self.assertEqual(self.event('Stop'),{})

    def test_evidence_change_is_checked_without_worksheet_change(self):
        self.event('SessionStart')
        (self.run/'filing.txt').write_text('20')
        self.path.write_text('20 [filing path=filing.txt line=1]')
        self.assertEqual(self.event('PostToolUse'),{})
        (self.run/'filing.txt').write_text('21')
        self.assertEqual(self.event('Stop')['decision'],'block')

    def test_missing_session_start_checks_existing_files(self):
        self.path.write_text('Bad claim 999')
        self.assertEqual(self.event('Stop')['decision'],'block')

    def test_deleted_pending_output_fails(self):
        self.event('SessionStart')
        self.path.write_text('Bad claim 999')
        self.event('PostToolUse')
        self.path.unlink()
        self.assertEqual(self.event('Stop')['decision'],'block')

    def test_state_stores_no_numerical_evidence(self):
        self.event('SessionStart')
        self.path.write_text('Bad claim 999')
        self.event('PostToolUse')
        for path in (self.root/'.state').glob('*.json'):
            state = json.loads(path.read_text())
            self.assertEqual(set(state),{'observed','pending'})
            self.assertNotIn('Bad claim',path.read_text())

    def test_hook_exception_returns_explicit_block_json(self):
        result = subprocess.run([sys.executable,str(HOOKS/'worksheet_gate.py')],input='not json',capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout)['decision'],'block')


if __name__ == '__main__': unittest.main()
