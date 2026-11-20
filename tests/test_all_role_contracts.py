"""Seeded all-role contracts. No provider calls or downloaded fixtures."""
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import os
import sys
from desk_claims import check,load_sources,with_repairs
from desk_sources import write_json,Sources
from desk_role_contracts import validate,verify_output,report_text,verify_team_file,report_catalog,code_marks,verified_text,manager_contract
from desk_hook import Hook,HookFailure,report_errors
from insight_layout import PART_OWNERS


class AllRoleContracts(unittest.TestCase):
    def test_real_crewai_all_role_chain_with_seeded_model(self):
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('desk_all_roles_smoke.py'))],text=True,encoding="utf-8",env={**os.environ,"PYTHONIOENCODING":"utf-8"},capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout[-4500:]+result.stderr[-4500:])
        self.assertIn('SEEDED all-role CrewAI chain passed',result.stdout)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name).resolve()
        (self.run/'10-K.txt').write_text('Income was $100.\nDebt was $20.\n')
        write_json(self.run/'calculated_facts.json',{'metrics':{'free_cash_flow':{'value':80,'formula':'100 - 20','unit':'USD','sources':['10-K.txt:L1','10-K.txt:L2']},
            'pe':{'value':None,'formula':'None / 2','unit':'ratio','sources':['not available']}},'quarter_results':{}})

    def save(self,role,raw,number=1):
        result=validate(self.run,role,raw)
        self.assertTrue(result.ok,result.errors)
        path=self.run/'nodes'/f'{role.replace(" ","_")}_{number}'/'output.json'
        write_json(path,result.output)
        if 'draft' in result.output:path.with_name('draft.md').write_text(result.output['draft'])
        return result.output,path

    def authors(self):
        research={'claims':[{'id':'c1','file':'10-K.txt','line':1,'quote':'Income was $100.','value':'$100'}],
                  'draft':'== 1. OVERVIEW ==\nIncome was {c1}.\nGrowth is supported by {c1}.\nInsight: Income supports the business at {c1}.'}
        financial={'claims':[{'id':'c1','computed':'free_cash_flow'}],
                   'draft':'== 2. CASH GENERATION ==\nCash generation was {c1}.\nInsight: Cash remains after spending at {c1}.'}
        advisor={'claims':[{'id':'c1','from':'Financial Analyst','claim':'c1'}],
                 'draft':'== 3. RECOMMENDATION ==\nHold. Cash generation of {c1} supports caution.\nInsight: Cash protection remains at {c1}.'}
        for role,raw in zip(('Research Analyst','Financial Analyst','Investment Advisor'),(research,financial,advisor)):self.save(role,raw)

    def manager(self):
        self.authors()
        research='nodes/Research_Analyst_1/draft.md'
        refs={'Overview':{'file':research,'start':2,'end':2},
              'Market Positioning and Growth Outlook':{'file':research,'start':3,'end':3},
              'Future Developments and Strategic Recommendations':{'file':research,'start':4,'end':4},
              'Valuation Insights':{'file':'nodes/Financial_Analyst_1/draft.md','start':2,'end':3},
              'Investment Recommendation':{'file':'nodes/Investment_Advisor_1/draft.md','start':2,'end':3}}
        raw={'claims':[],'failures':[],'sections':refs}
        output,path=self.save('Strategy Manager',raw)
        return raw,output,path

    def test_financial_uses_saved_computation_and_rechecks_it(self):
        result=validate(self.run,'Financial Analyst',{'claims':[{'id':'c1','computed':'free_cash_flow'}],'draft':'== 1. CASH ==\nCash {c1}.'})
        self.assertTrue(result.ok,result.errors)
        self.assertIn('$80',result.rendered)
        self.assertIn('formula 100 - 20',result.rendered)
        data=json.loads((self.run/'calculated_facts.json').read_text());data['metrics']['free_cash_flow']['value']=81
        write_json(self.run/'calculated_facts.json',data)
        self.assertFalse(validate(self.run,'Financial Analyst',{'claims':[{'id':'c1','computed':'free_cash_flow'}],'draft':'Cash {c1}.'}).ok)

    def test_unavailable_calculation_cannot_become_a_claim(self):
        self.assertFalse(validate(self.run,'Financial Analyst',{'claims':[{'id':'c1','computed':'pe'}],'draft':'P/E {c1}.'}).ok)
        self.assertTrue(validate(self.run,'Financial Analyst',{'claims':[],'draft':'P/E is unavailable.'}).ok)

    def test_advisor_can_only_reuse_checked_author_claims(self):
        self.authors()
        self.assertFalse(validate(self.run,'Investment Advisor',{'claims':[{'id':'c1','file':'10-K.txt','line':1,'quote':'Income was $100.','value':'$100'}],'draft':'Hold {c1}.'}).ok)
        self.assertFalse(validate(self.run,'Investment Advisor',{'claims':[{'id':'c1','from':'Financial Analyst','claim':'c99'}],'draft':'Hold {c1}.'}).ok)

    def test_manager_copies_saved_ranges_verbatim_and_cannot_retype(self):
        raw,out,_=self.manager()
        self.assertEqual(out['sections']['Overview'],'Income was $100 [10-K.txt:L1].')
        self.assertEqual(verify_output(self.run,out),[])
        raw['sections']['Overview']='Income $999'
        self.assertFalse(validate(self.run,'Strategy Manager',raw).ok)

    def test_manager_list_error_names_required_type_and_shows_complete_shape(self):
        raw,_,_=self.manager()
        raw['sections']=[{'part':part,**ref} for part,ref in raw['sections'].items()]
        result=validate(self.run,'Strategy Manager',raw)
        self.assertFalse(result.ok)
        self.assertIn('sections must be an object keyed by the five exact section names; received list.',result.errors)
        shape=json.loads(result.errors[-1].split('):\n',1)[1])
        self.assertEqual(set(shape['sections']),set(PART_OWNERS))
        self.assertIsInstance(shape['claims'],list)
        self.assertIsInstance(shape['failures'],list)
        self.assertTrue(all(set(ref)=={'file','start','end'} for ref in shape['sections'].values()))

    def test_manager_prompt_example_uses_latest_saved_author_filename(self):
        self.authors()
        self.save('Financial Analyst',{'claims':[{'id':'c1','computed':'free_cash_flow'}],'draft':'Cash {c1}.\nInsight: Cash matters at {c1}.'},number=2)
        shape=json.loads(manager_contract(self.run).split('):\n',1)[1])
        self.assertEqual(shape['sections']['Valuation Insights']['file'],'nodes/Financial_Analyst_2/draft.md')

    def test_manager_cannot_change_owner_or_choose_arbitrary_file(self):
        raw,_,_=self.manager()
        raw['sections']['Overview']['file']='nodes/Financial_Analyst_1/draft.md'
        self.assertFalse(validate(self.run,'Strategy Manager',raw).ok)
        raw['sections']['Overview']['file']='../outside.md'
        self.assertFalse(validate(self.run,'Strategy Manager',raw).ok)

    def test_manager_feedback_uses_checked_placeholders(self):
        raw,_,_=self.manager()
        raw['failures']=[{'role':'Financial Analyst','part':'Valuation Insights','feedback':'Explain {c1}.'}]
        raw['claims']=[{'id':'c1','from':'Financial Analyst','claim':'c1'}]
        result=validate(self.run,'Strategy Manager',raw)
        self.assertTrue(result.ok,result.errors)
        self.assertIn('$80',result.output['failures'][0]['feedback'])
        raw['failures'][0]['feedback']='Explain $81.'
        self.assertFalse(validate(self.run,'Strategy Manager',raw).ok)

    def test_verifier_targets_every_published_claim_without_retyping(self):
        self.manager()
        checks=[{'target':c['target'],'status':'correct','reason':'Source and period agree.','correction':''} for c in report_catalog(self.run)]
        raw={'claims':[],'checks':checks}
        out,path=self.save('Verifier',raw)
        self.assertEqual(verify_output(self.run,out),[])
        self.assertTrue(all('source' in c for c in out['checks']))
        raw['checks']=checks[:-1]
        self.assertFalse(validate(self.run,'Verifier',raw).ok)
        raw['checks']=checks
        raw['checks'][0]['reason']='The amount is $999.'
        self.assertFalse(validate(self.run,'Verifier',raw).ok)

    def test_verifier_accepts_only_actual_saved_field_names(self):
        data=json.loads((self.run/'calculated_facts.json').read_text())
        data['quarter_results']['latest_10q_capital_spending']={'value':80,'formula':'100 - 20','unit':'USD','sources':['10-K.txt:L1','10-K.txt:L2']}
        write_json(self.run/'calculated_facts.json',data)
        self.manager()
        raw={'claims':[],'checks':[{'target':c['target'],'status':'correct',
             'reason':'calculated_facts.json latest_10q_capital_spending is the saved quarterly calculation.','correction':''} for c in report_catalog(self.run)]}
        self.assertTrue(validate(self.run,'Verifier',raw).ok)
        raw['checks'][0]['reason']+=' Its value was $999.'
        self.assertFalse(validate(self.run,'Verifier',raw).ok)
        raw['checks'][0]['reason']=raw['checks'][1]['reason']
        del data['quarter_results']['latest_10q_capital_spending']
        write_json(self.run/'calculated_facts.json',data)
        self.assertFalse(validate(self.run,'Verifier',raw).ok)

    def test_reports_and_hook_rebuild_from_actual_saved_role_files(self):
        self.manager()
        write_json(self.run/'team_report.json',{'filings_line':'Filings read: seeded filing','run_time':'2026-11-17T12:00:00-05:00'})
        report=self.run/'report.md';report.write_text(report_text(self.run))
        checks=[{'target':c['target'],'status':'correct','reason':'Source and period agree.','correction':''} for c in report_catalog(self.run)]
        verifier,_=self.save('Verifier',{'claims':[],'checks':checks})
        marks=code_marks(self.run)
        write_json(self.run/'nodes/Verifier/output.json',{'code_checks':marks,'model_checks':verifier})
        verified=self.run/'verified_report.md';verified.write_text(verified_text(report.read_text(),marks,verifier['checks']))
        self.assertEqual(Hook(self.run,Sources(self.run,'')).check('seeded report',[report,verified])['status'],'PASS')
        verified.write_text(verified.read_text().replace('$80','$81'))
        with self.assertRaisesRegex(HookFailure,'differs'):Hook(self.run,Sources(self.run,'')).check('seeded changed report',[verified])

    def test_tampered_author_file_and_ledger_fail_downstream(self):
        _,out,_=self.manager()
        p=self.run/'nodes/Research_Analyst_1/draft.md';p.write_text(p.read_text().replace('$100','$999'))
        self.assertTrue(verify_output(self.run,out))

    def test_advisor_references_are_pinned_when_an_author_is_corrected(self):
        self.authors()
        _,advisor=__import__('desk_role_contracts').latest(self.run,'Investment Advisor')
        self.assertEqual(advisor['claims'][0]['from_file'],'nodes/Financial_Analyst_1/output.json')
        self.save('Financial Analyst',{'claims':[{'id':'c1','file':'10-K.txt','line':2,'quote':'Debt was $20.','value':'$20'}],
                  'draft':'Debt {c1}.\nInsight: Debt needs monitoring at {c1}.'},number=2)
        self.assertEqual(verify_output(self.run,advisor),[])
        self.assertIn('$80',advisor['draft'])

    def test_periods_dates_and_claim_ids_are_identifiers(self):
        text='== 4. LATEST QUARTER (Q4, quarter ended 2026-08-30) ==\nAs of August 30, 2026. See Section 3 and claim c1.'
        result=validate(self.run,'Financial Analyst',{'claims':[],'draft':text})
        self.assertTrue(result.ok,result.errors)
        self.assertFalse(validate(self.run,'Financial Analyst',{'claims':[],'draft':text+'\nIncome $999.'}).ok)
        for financial in ['Income was 2026.','There were 2026 warehouses.','Revenue USD 2026.','Income three trillion.']:
            self.assertFalse(validate(self.run,'Financial Analyst',{'claims':[],'draft':financial}).ok)

    def test_each_remaining_role_gets_bounded_targeted_claim_repairs(self):
        manager,_,_=self.manager()
        verifier={'claims':[],'checks':[{'target':c['target'],'status':'correct','reason':'The period agrees.','correction':''} for c in report_catalog(self.run)]}
        bad_manager=json.loads(json.dumps(manager));bad_manager['sections']['Overview']='Income $999.'
        bad_verifier=json.loads(json.dumps(verifier));bad_verifier['checks'][0]['reason']='The amount is $999.'
        cases=[
            ('Financial Analyst',{'claims':[],'draft':'Cash $999.'},{'claims':[{'id':'c1','computed':'free_cash_flow'}],'draft':'Cash {c1}.'}),
            ('Investment Advisor',{'claims':[],'draft':'Hold with $999.'},{'claims':[{'id':'c1','from':'Financial Analyst','claim':'c1'}],'draft':'Hold with {c1}.'}),
            ('Strategy Manager',bad_manager,manager),('Verifier',bad_verifier,verifier)]
        for role,bad,good in cases:
            with self.subTest(role=role):
                responses=iter([bad,good]);feedback=[]
                def ask(message):feedback.append(message);return next(responses)
                output,attempts=with_repairs(ask,{}, {},validator=lambda raw:validate(self.run,role,raw))
                self.assertEqual(output['role'],role)
                self.assertEqual(len(attempts),2)
                self.assertTrue(feedback[1])
                self.assertTrue(attempts[0]['errors'])
                saved=[]
                with self.assertRaisesRegex(ValueError,'after repairs'):
                    with_repairs(lambda message:bad,{}, {},validator=lambda raw:validate(self.run,role,raw),on_attempt=lambda a:saved.append(len(a)))
                self.assertEqual(saved,[1,2,3])

    def test_all_heading_labels_pass_but_real_numbers_do_not(self):
        for label in ['== 1. CASH ==','## 2. PROFITABILITY','3. FUNDING','(1) Review income.','## 4 CASH','== 5 CASH ==']:
            self.assertEqual(report_errors(self.run,self.run/'report.md',label),[])
            result=validate(self.run,'Financial Analyst',{'claims':[],'draft':label})
            self.assertTrue(result.ok,result.errors)
        self.assertTrue(report_errors(self.run,self.run/'report.md','== 1. CASH ==\nIncome $999.'))
        self.assertFalse(validate(self.run,'Financial Analyst',{'claims':[],'draft':'== 1. CASH ==\nIncome $999.'}).ok)
        for amount in ['## 100 million of income','== 100 shares ==']:
            self.assertTrue(report_errors(self.run,self.run/'report.md',amount))
            self.assertFalse(validate(self.run,'Financial Analyst',{'claims':[],'draft':amount}).ok)


if __name__=='__main__':unittest.main()
