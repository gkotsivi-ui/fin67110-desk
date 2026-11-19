"""Seeded boundary failures. No reader or model calls."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from desk_files import AssignedFiles
from desk_hook import Hook,HookFailure,report_errors
from desk_sources import Sources
from desk_timing import timed_role


class BoundaryTests(unittest.TestCase):
    def test_real_crewai_file_tool_with_seeded_llm(self):
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('desk_tool_smoke.py'))],
                              text=True,capture_output=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout[-4000:]+result.stderr[-4000:])
        self.assertIn('SEEDED real file-tool smoke check passed',result.stdout)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name).resolve()

    def store(self):
        source=self.run/'skill.md';source.write_text('Computed amount: $100\n')
        return AssignedFiles(self.run,[source],self.run/'reads.json')

    def test_file_manifest_has_paths_and_permissions_without_contents(self):
        store=self.store();manifest=store.manifest()
        self.assertEqual(manifest[0]['file'],'skill.md')
        self.assertIn('never recompute',manifest[0]['permission'])
        self.assertNotIn('$100',json.dumps(manifest))
        self.assertIn('skill.md:L1: Computed amount: $100',store.read('skill.md'))
        store.verify()

    def test_unread_file_blocks_role_completion(self):
        with self.assertRaisesRegex(ValueError,'did not read'):self.store().verify()

    def test_parallel_native_tool_reads_keep_one_complete_access_log(self):
        store=self.store()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(store.read,['skill.md']*32))
        self.assertEqual(len(results),32)
        self.assertEqual(len(json.loads((self.run/'reads.json').read_text())['reads']),32)
        store.verify()

    def test_unassigned_file_and_path_escape_are_rejected(self):
        for name in ['secret.env','../outside.md']:
            with self.subTest(name=name):
                store=self.store()
                with self.assertRaises(ValueError):store.read(name)
                with self.assertRaises(ValueError):store.verify()

    def test_changed_assigned_file_is_rejected_before_and_after_read(self):
        store=self.store();store.read('skill.md')
        (self.run/'skill.md').write_text('Computed amount: $101\n')
        with self.assertRaisesRegex(ValueError,'changed'):store.verify()
        with self.assertRaisesRegex(ValueError,'changed'):store.read('skill.md')

    def test_missing_output_is_failed_and_recorded(self):
        with self.assertRaisesRegex(HookFailure,'missing'):
            Hook(self.run,Sources(self.run,'')).check('seeded missing file',[self.run/'never-written.md'])
        record=json.loads(next((self.run/'hook').glob('*.json')).read_text())
        self.assertEqual(record['status'],'FAIL')
        self.assertEqual(record['requested_outputs'],['never-written.md'])

    def test_empty_output_list_is_failed(self):
        with self.assertRaisesRegex(HookFailure,'no saved output'):
            Hook(self.run,Sources(self.run,'')).check('seeded empty outputs',[])

    def test_hook_reads_actual_report_even_when_decoy_claims_are_correct(self):
        (self.run/'filing.txt').write_text('Income $100.')
        (self.run/'hook-only.json').write_text('{"income":100}')
        report=self.run/'report.md';report.write_text('Income $101 [filing.txt:L1].')
        with self.assertRaisesRegex(HookFailure,r'Income \$101'):
            Hook(self.run,Sources(self.run,'')).check('seeded actual output',[report])

    def test_line_and_note_identifiers_skipped_but_wrong_amount_rejected(self):
        (self.run/'filing.txt').write_text('Income $100.')
        text='Income $100 [filing.txt:L1]. See L1010-L1012 and Note 11.'
        self.assertEqual(report_errors(self.run,self.run/'report.md',text),[])
        self.assertTrue(report_errors(self.run,self.run/'report.md',text.replace('$100','$101')))

    def test_written_basis_points_and_scaled_money_match_exact_sources(self):
        cases=[
            ('Gross margin decreased three basis points.','Gross margin fell three basis points.','Gross margin fell four basis points.'),
            ('Expenses rose one basis point.','Expenses rose 1 basis point.','Expenses rose one percent.'),
            ('Margin fell 3 basis points.','Margin fell 0.03 percentage points.','Margin fell 3 percentage points.'),
            ('Revenue was $93.9 billion.','Revenue was $93.9 billion.','Revenue was $93.9 million.'),
            ('Revenue was $93.9 billion.','Revenue was $93,900 million.','Revenue was $93.8 billion.'),
            ('Revenue was $93.9 billion.','Revenue was $93,900,000,000.','Revenue was EUR 93.9 billion.'),
            ('Revenue was $93.9 BILLION.','Revenue was $93.9 billion.','Revenue was $94.9 billion.'),
            ('Income was three million dollars.','Income was $3,000,000.','Income was four million dollars.'),
            ('Margin rose twenty-five basis points.','Margin rose 25 bps.','Margin rose twenty-six basis points.'),
            ('Revenue grew 11.2 percent.','Revenue grew 11.2%.','Revenue grew 12.2%.'),
        ]
        for source,correct,incorrect in cases:
            with self.subTest(source=source,correct=correct):
                (self.run/'filing.txt').write_text(source)
                self.assertEqual(report_errors(self.run,self.run/'report.md',correct+' [filing.txt:L1].'),[])
                self.assertTrue(report_errors(self.run,self.run/'report.md',incorrect+' [filing.txt:L1].'))

    def test_written_amount_requires_the_exact_cited_line(self):
        (self.run/'filing.txt').write_text('Margin fell three basis points.\nUnrelated text.')
        text='Margin fell three basis points. [filing.txt:L2].'
        self.assertTrue(report_errors(self.run,self.run/'report.md',text))

    def test_written_amount_without_citation_fails(self):
        self.assertTrue(report_errors(self.run,self.run/'report.md','Margin fell three basis points.'))
        self.assertTrue(report_errors(self.run,self.run/'report.md','Up twenty-five bps.'))

    def test_formula_result_ignores_citation_identifiers_and_requires_correct_arithmetic(self):
        (self.run/'filing.txt').write_text('Cash $100; debt $20.')
        correct='Net cash $80 [filing.txt:L1] [computed using formula 100 - 20 based on filing].'
        self.assertEqual(report_errors(self.run,self.run/'report.md',correct),[])
        self.assertTrue(report_errors(self.run,self.run/'report.md',correct.replace('$80','$81')))

    def test_section_units_scale_money_but_not_per_share_or_percent(self):
        (self.run/'filing.txt').write_text('Item 7—Management discussion\n(amounts in millions, except per share data)\nNet income was $100, or $2 per diluted share; growth was 5%.\n')
        valid='Income was $100 million and EPS was $2 per diluted share; growth was 5%. [filing.txt:L3].'
        self.assertEqual(report_errors(self.run,self.run/'report.md',valid),[])
        for wrong in [valid.replace('$100 million','$101 million'),valid.replace('$100 million','$100 billion'),valid.replace('$2 per diluted share','$2 million per diluted share')]:
            self.assertTrue(report_errors(self.run,self.run/'report.md',wrong))

    def test_section_units_do_not_leak_into_next_section(self):
        (self.run/'filing.txt').write_text('Item 7—Discussion\n(amounts in millions)\nRevenue $100.\nItem 8—Other section\nRevenue $100.\n')
        self.assertTrue(report_errors(self.run,self.run/'report.md','Revenue $100 million [filing.txt:L5].'))
        self.assertEqual(report_errors(self.run,self.run/'report.md','Revenue $100 [filing.txt:L5].'),[])

    def test_table_specific_sentence_does_not_set_section_units(self):
        (self.run/'filing.txt').write_text('The following table shows repurchases (dollars in millions).\nIncome $100.\n')
        self.assertTrue(report_errors(self.run,self.run/'report.md','Income $100 million [filing.txt:L2].'))

    def test_literal_quote_can_retain_filing_units_without_allowing_wrong_unquoted_scale(self):
        (self.run/'filing.txt').write_text('Item 7—Discussion\n(amounts in millions)\nNet income was $100.\n')
        valid='Income was $100 million. [filing.txt:L3] "Net income was $100."'
        self.assertEqual(report_errors(self.run,self.run/'report.md',valid),[])
        self.assertTrue(report_errors(self.run,self.run/'report.md',valid.replace('Income was $100 million.','Income was $100 billion.')))
        self.assertTrue(report_errors(self.run,self.run/'report.md',valid.replace('"Net income was $100."','"Net income was $101."')))

    def test_inline_list_labels_are_identifiers_but_amounts_still_require_sources(self):
        text='Recommendations: (1) Track demand. (2) Review costs. (3) Watch margins.'
        self.assertEqual(report_errors(self.run,self.run/'report.md',text),[])
        self.assertTrue(report_errors(self.run,self.run/'report.md',text.replace('Review costs.','Review costs of $999.')))
        self.assertTrue(report_errors(self.run,self.run/'report.md','Losses: (1) million dollars and (2) million dollars.'))

    def test_one_to_watch_is_prose_but_one_basis_point_is_a_claim(self):
        self.assertEqual(report_errors(self.run,self.run/'report.md','The worldwide renewal rate is the one to watch.'),[])
        self.assertTrue(report_errors(self.run,self.run/'report.md','The worldwide renewal rate rose one basis point.'))

    def test_role_elapsed_line_and_saved_seconds_exist_on_failure(self):
        class Role:
            output_dir=self.run
            @timed_role
            def call(inner,name):raise ValueError('seeded role failure')
        output=io.StringIO()
        with redirect_stdout(output),self.assertRaisesRegex(ValueError,'seeded'):
            Role().call('Seeded role')
        self.assertRegex(output.getvalue().splitlines()[-1],r'^Part role Seeded role: \d+\.\d{3} seconds$')
        self.assertGreaterEqual(json.loads(next((self.run/'timings').glob('*.json')).read_text())['seconds'],0)


if __name__=='__main__':unittest.main()
