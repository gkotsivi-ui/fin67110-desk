"""Exercise the real adapter boundaries and role packet builder without models."""
import ast
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
from contextlib import redirect_stdout

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desk import parser,snapshot_inputs
from desk_parts import Parts
from desk_sources import Sources,write_json
from desk_files import AssignedFiles, reply_with_required_reads
from desk_timing import timed_role
from desk_claims import parse_response
import re


class AdapterTests(unittest.TestCase):
    def test_registry_with_unresolved_ticker_is_not_applicable(self):
        self.parts.registry={'candidates':{'12345':{'facts':{'ticker':None}}}}
        with redirect_stdout(io.StringIO()):self.parts.spinoff_status('ZZZZ')
        self.assertEqual(json.loads((self.run/'spinoff_status.json').read_text(encoding='utf-8'))['spinoff'],'not applicable')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name).resolve();self.options=parser().parse_args(['ZZZZ'])
        snapshot_inputs(self.run,self.options)
        self.sources=Sources(self.run,'invented test identity')
        self.parts=Parts(self.run,self.sources,self.options)
        self.started=datetime.fromisoformat('2026-11-17T09:00:00-05:00')

    def test_a_ticker_run_with_no_registry_goes_on_with_its_spinoff_parts_not_applicable(self):
        # On a fresh clone `desk.py TICKER` stopped with "No seeker registry was supplied". A name the seeker never
        # saw must run, with its spinoff parts "not applicable" (the project page; Lab 08).
        import desk_parts
        missing=self.run/'no_registry_here.json'
        self.assertEqual(parser().parse_args(['ZZZZ']).registry,desk_parts.DEFAULT_REGISTRY)  # the default the command uses
        with patch.object(desk_parts,'DEFAULT_REGISTRY',missing):
            self.options.registry=missing
            with redirect_stdout(io.StringIO()):self.assertIsNone(self.parts.seeker_part())
            self.assertEqual(json.loads((self.run/'registry.json').read_text(encoding='utf-8'))['candidates'],{})
            self.assertEqual(json.loads((self.run/'seeker_status.json').read_text(encoding='utf-8'))['mode'],'not requested')
            with redirect_stdout(io.StringIO()):self.parts.spinoff_status('ZZZZ')
            self.assertEqual(json.loads((self.run/'spinoff_status.json').read_text(encoding='utf-8'))['spinoff'],'not applicable')
            # A registry path that someone gave on purpose and that does not exist still stops the run.
            self.options.registry=self.run/'a_typo.json'
            with self.assertRaisesRegex(ValueError,'Registry does not exist'):self.parts.seeker_part()

    def test_team_uses_provided_folder_and_does_not_refetch_saved_filing(self):
        from equity_research_desk import Filing
        url='https://www.sec.gov/Archives/edgar/data/12345/000001234526000001/a.htm'
        self.sources.transport=Mock(side_effect=AssertionError('filing fetched twice'))
        (self.run/'10-K.txt').write_text('Saved text remains unchanged.',encoding='utf-8')
        captured={}
        class FakeFlow:
            def __init__(self,*args,**kwargs):captured.update(kwargs)
            def kickoff(self):
                desk=captured['desk']
                desk.filings={'10-K':Filing('10-K','0000012345-26-000001','2026-11-01','a.htm',document_url=url)}
                desk.step3()
                path=desk.output_dir/'verified_report.md';path.write_text('No numerical claims.',encoding='utf-8')
                return str(path)
        fake=SimpleNamespace(EquityResearchFlow=FakeFlow)
        with patch.dict(sys.modules,{'equity_research_agent_team':fake}),patch.dict('os.environ',{'SEC_USER_AGENT':'invented test identity'}):
            result=self.parts.team('ZZZZ',self.started,lambda *a,**k:None)
        self.assertEqual(result,self.run/'verified_report.md')
        self.assertEqual(captured['desk'].output_dir,self.run)
        self.assertEqual(captured['desk'].run_timestamp,self.started.isoformat())
        self.assertEqual((self.run/'10-K.txt').read_text(encoding='utf-8'),'Saved text remains unchanged.')
        self.assertTrue(all(p.is_relative_to(self.run) for p in captured['skill_files']))
        self.sources.transport.assert_not_called()

    def test_worksheet_model_reads_the_saved_input_file(self):
        self.parts.registry={'candidates':{}}
        write_json(self.run/'facts.json',{'ticker':'ZZZZ','cik':'12345'})
        w=self.parts.worksheet_module;captured={}
        def build(run,config,persona,registry,reader,model_call,now):
            stem=f'Spinoff worksheet, ZZZZ, {now:%Y-%m-%d}, {now:%H-%M-%S.%f}'
            path=run/(stem+', model input.json')
            write_json(path,{'persona':'Saved persona','input':{'filing_facts':{'from_file':True},'value_range':{},'price_vs_low':{}}})
            model_call('wrong in-memory persona',{'wrong_payload':True})
            target=run/(stem+'.md');target.write_text('Saved worksheet',encoding='utf-8')
            return {'model_error_type':None,'files':{'markdown':target}}
        def judge(persona,payload,record_response):
            captured.update(persona=persona,payload=payload)
            record_response({'content':[]})
            return {'judgment':'Known only from file','next_filing_trigger':'Next filing'}
        with patch.object(w,'build',build),patch.object(w,'judge_once',judge):
            path=self.parts.worksheet(self.started,lambda *a,**k:None)
        self.assertEqual(captured['persona'],'Saved persona')
        self.assertTrue(captured['payload']['filing_facts']['from_file'])
        self.assertNotIn('wrong_payload',captured['payload'])
        self.assertTrue(path.is_relative_to(self.run))

    def test_registration_fetch_failure_stops_before_model(self):
        self.parts.registry={'candidates':{'12345':{'cik':'12345','facts':{'ticker':{'value':'ZZZZ'}}}}}
        write_json(self.run/'facts.json',{'ticker':'ZZZZ','cik':'12345'})
        w=self.parts.worksheet_module
        with patch.object(w,'fetch_registration',side_effect=ValueError('saved registration unavailable')),patch.object(w,'judge_once') as judge:
            with self.assertRaisesRegex(ValueError,'registration unavailable'):
                self.parts.worksheet(self.started,lambda *a,**k:None)
            judge.assert_not_called()

    def test_authored_rules_are_validated_before_any_fetch(self):
        (self.run/'inputs/spinoff-rules.md').write_text('FILL',encoding='utf-8')
        with patch.object(self.sources,'response') as get:
            with self.assertRaises(ValueError):self.parts.validate_setup()
            get.assert_not_called()

    def test_role_packet_passes_files_and_requires_tool_reads_without_recomputation(self):
        source=Path(__file__).resolve().parents[1]/'equity_research_agent_team.py'
        tree=ast.parse(source.read_text(encoding='utf-8'));runtime=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Runtime')
        method=next(n for n in runtime.body if isinstance(n,ast.FunctionDef) and n.name=='role_call')
        numbered=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='numbered_lines')
        captured={}
        class FakeCrew:
            def __init__(self,**kwargs):pass
            def kickoff(self,inputs):
                captured.update(json.loads(inputs['payload']))
                captured['read_text']=captured['store'].read('pick.json')
                return SimpleNamespace(raw='{"draft":"No figures."}')
        def tool(store):captured['store']=store;return store
        import model_calls  # the role call's retry rule and time limit (2026-11-22)
        scope={'Any':Any,'Path':Path,'json':json,'re':re,'AssignedFiles':AssignedFiles,'reply_with_required_reads':reply_with_required_reads,'file_tool':tool,'timed_role':timed_role,'CLAIMS_ROLES':{'research_analyst.md'},'ROLE_CONTRACTS':{},
               'within_time_limit':model_calls.within_time_limit,'retry_reason':model_calls.retry_reason,'CALL_TIME_LIMIT_SECONDS':model_calls.CALL_TIME_LIMIT_SECONDS,
               'RETRY_WAIT_SECONDS':0,'RATE_LIMIT_WAIT_SECONDS':0,
               'Agent':lambda **k:None,'Task':lambda **k:None,
               'Crew':FakeCrew,'Process':SimpleNamespace(sequential='sequential'),'parse_response':parse_response}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[numbered,method],type_ignores=[])),str(source),'exec'),scope)
        path=self.run/'pick.json';path.write_text('{"ticker":"ZZZZ"}\n',encoding='utf-8')
        self_stub=SimpleNamespace(output_dir=self.run,skill_files=[path],role_call_counts={},llm=object(),instructions=lambda name:'Role instructions',save_node=Mock())
        envelope={'task':'Quote the assigned file','context':{},'expected_output':'JSON draft'}
        with redirect_stdout(io.StringIO()):scope['role_call'](self_stub,'Financial Analyst','financial_analyst.md',envelope)
        self.assertIn('Never recompute',captured['task'])
        self.assertIn('Do not combine facts from different source lines',captured['task'])
        self.assertIn('Keep this separation when revising or assembling the report',captured['task'])
        self.assertIn('One factual claim per output line',captured['expected_output'])
        assigned=captured['context']['skill_output_files'][0]
        self.assertEqual(assigned['file'],'pick.json')
        self.assertNotIn('lines',assigned)
        self.assertIn('pick.json:L1: {"ticker":"ZZZZ"}',captured['read_text'])
        self.assertTrue((self.run/'nodes/Financial_Analyst_1/files_read.json').is_file())

    def test_financial_context_uses_saved_values_without_inline_copies(self):
        source=Path(__file__).resolve().parents[1]/'equity_research_agent_team.py'
        runtime=next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef) and n.name=='Runtime')
        method=next(n for n in runtime.body if isinstance(n,ast.FunctionDef) and n.name=='financial_context')
        scope={'Any':Any,'missing_fact_filing_lines':lambda *a:'filing evidence',
               'relevant_release_lines':lambda *a:'release evidence','calculator_inputs':lambda *a:{'income':100}}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(source),'exec'),scope)
        facts={'income':{'value':100}}
        stub=SimpleNamespace(output_dir=self.run,skill_files=[self.run/'facts.json'],
            desk=SimpleNamespace(ticker='ZZZZ',report_period='2026-08-30',facts=facts,
                                 computed_metrics={'margin':.1},quarter_results={},peer_results={}))
        context=scope['financial_context'](stub)
        self.assertNotIn('facts',context)
        self.assertNotIn('computed_metrics',context)
        self.assertNotIn('calculation_inputs',context)
        self.assertEqual(context['saved_values']['facts'],'facts.json')
        stub.skill_files=[]
        self.assertIs(scope['financial_context'](stub)['facts'],facts)


if __name__=='__main__':unittest.main()
