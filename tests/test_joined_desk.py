"""Fixed-order desk tests with invented filings and injected parts; no paid calls."""
import ast
from contextlib import redirect_stdout
from datetime import datetime,timedelta
import io
import json
from pathlib import Path
import socket
from portable import local_sockets_only
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desk
from desk_sources import Sources,canonical_url,digest,no_fetch,write_json,skill
from desk_hook import Hook,HookFailure,report_errors
from desk_parts import latest_screen,validate_screen

ACC='0000012345-26-000001'
FILE_URL='https://www.sec.gov/Archives/edgar/data/12345/000001234526000001/annual.htm'


class FakeParts:
    calls=[]
    failure=None
    def __init__(self,run,sources,options):self.run=run;self.sources=sources;self.options=options
    def relocate(self,run):self.run=run;self.sources.run=run;self.sources.path=run/'sources.json'
    def seeker_part(self):
        self.calls.append('seeker')
        if self.failure=='seeker':raise ValueError('invented seeker failure')
        registry={'candidates':{}}
        if self.options.selector=='screen':
            module=skill('us-spinoff-seeker');factors=module.load_factors(str(self.run/'inputs/spinoff_factors.json'))
            candidate=module.new_candidate('12345','Invented test issuer')
            candidate['facts']['ticker']={'value':'ZZZZ'};candidate['facts']['distribution_date']={'value':'2026-11-01'}
            candidate['eligibility']='included';candidate['drop']=False
            candidate['stage']='in its window'
            module.rank([candidate],factors)
            registry.update(candidates={'12345':candidate},complete=True,pending_ciks=[],factors=factors,as_of='2026-11-17',index_date='2026-11-16')
            started=json.loads((self.run/'desk_run.json').read_text())['started_at']
            data={'registry':registry,'factors':factors,'run_time':started,'limitations':[]}
            write_json(self.run/'screen.json',data)
        write_json(self.run/'registry.json',registry)
    def pick(self):
        self.calls.append('pick');data={'ticker':'ZZZZ'}
        if self.options.selector=='screen':
            ticker,candidate=validate_screen(skill('us-spinoff-seeker'),json.loads((self.run/'screen.json').read_text()))
            data.update(ticker=ticker,candidate=candidate,source='screen.json')
        write_json(self.run/'pick.json',data);return data['ticker']
    def spinoff_status(self,ticker):
        write_json(self.run/'spinoff_status.json',{'ticker':ticker,'spinoff':'applicable' if self.options.selector=='screen' else 'not applicable'})
    def team(self,ticker,started,output_hook):
        self.calls.append('team')
        if self.failure=='team':raise ValueError('invented team failure')
        company={'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[{'val':100,'end':'2026-08-30','accn':ACC}]}}}}}
        def get(url,**kwargs):
            response=__import__('requests').Response();response.status_code=200
            response._content=(json.dumps(company) if 'companyfacts' in url else 'Net income was $100.').encode()
            return response
        self.sources.transport=get
        self.sources.text('https://data.sec.gov/api/xbrl/companyfacts/CIK0000012345.json')
        text=self.sources.text(FILE_URL)
        (self.run/'10-K.txt').write_text(text);self.sources.inventory(FILE_URL,'10-K',self.run/'10-K.txt');self.sources.save()
        write_json(self.run/'facts.json',{'ticker':ticker,'cik':'0000012345','facts':{'net_income':{'tag':'NetIncomeLoss','period_end':'2026-08-30','filing':ACC,'value':100}}})
        value=101 if self.failure=='number' else 100
        body=f'Filings read: 10-K {ACC}\nRun time: {started.isoformat()}\n\nIncome is ${value} [XBRL tag NetIncomeLoss, period end 2026-08-30, filing {ACC}].\n'
        (self.run/'report.md').write_text(body)
        (self.run/'verified_report.md').write_text(body)
        return self.run/'verified_report.md'
    def worksheet(self,started,output_hook):
        self.calls.append('worksheet')
        if self.failure=='worksheet':raise ValueError('invented worksheet failure')
        path=self.run/'Spinoff worksheet, ZZZZ.md'
        payload={'ticker':'ZZZZ','worksheet_time':started.isoformat(),
                 'facts':{'parent':{'value':'not applicable','kind':'not applicable','source':'registry'}},
                 'owner_cash_flow':{'value':None,'source':'not known'},
                 'value_range':{'low':{'value':None},'mid':{'value':None}},
                 'price_vs_low':{'comparison':'not computed'},'judgment':{'judgment':'not known','next_filing_trigger':'not known'},
                 'liquidity':{'reason':'not known'},'view':{'direction':'not computed','deciding_number':None,'source':'not known'},
                 'conviction':'not known','not_known':[]}
        path.write_text(skill('spinoff-worksheet').render(payload))
        write_json(path.with_suffix('.json'),payload)
        write_json(self.run/'view.json',{'ticker':'ZZZZ','view_time':started.isoformat(),'direction':'not computed'})
        return path


class JoinedDeskTests(unittest.TestCase):
    def setUp(self):
        identity = patch.object(desk, 'dotenv_values', return_value={'SEC_USER_AGENT': 'Synthetic offline test identity'})
        identity.start(); self.addCleanup(identity.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);FakeParts.calls=[];FakeParts.failure=None
        self.options=desk.parser().parse_args(['ZZZZ','--runs-root',str(self.root)])
        self.started=datetime.fromisoformat('2026-11-17T09:12:13.123456-05:00')

    def runner(self):return desk.DeskRun(self.options,parts_factory=FakeParts,clock=self.started)
    def execute(self):
        runner=self.runner()
        with redirect_stdout(io.StringIO()),local_sockets_only():
            result=runner.execute()
        return runner,result

    def test_fixed_order_one_folder_and_start_time(self):
        runner,result=self.execute()
        self.assertEqual(FakeParts.calls,['seeker','pick','team','worksheet'])
        self.assertEqual(runner.run.name,'ZZZZ_2026-11-17_09-12-13.123456')
        self.assertEqual(result.parent,runner.run)
        state=json.loads((runner.run/'desk_run.json').read_text())
        self.assertEqual([p['name'] for p in state['parts']],['inputs','seeker','pick','team','worksheet','final report'])
        self.assertEqual(state['started_at'],self.started.isoformat())
        self.assertTrue(all(p['seconds']>=0 for p in state['parts']))

    def test_final_contains_verified_team_and_worksheet_and_filing_inventory(self):
        runner,result=self.execute();text=result.read_text()
        self.assertEqual(text.splitlines()[0],f'Filings read: 10-K {ACC}')
        self.assertIn('Income is $100',text);self.assertIn('## Worksheet view and evidence',text)
        self.assertIn('View on the release: not computed',text)
        self.assertTrue(all(json.loads(p.read_text())['status']=='PASS' for p in (runner.run/'hook').glob('*.json')))

    def test_not_applicable_does_not_skip_team_or_worksheet(self):
        runner,_=self.execute()
        self.assertEqual(json.loads((runner.run/'spinoff_status.json').read_text())['spinoff'],'not applicable')
        self.assertIn('worksheet',FakeParts.calls)

    def test_each_failure_stops_later_parts_and_keeps_folder(self):
        for phase in ('seeker','team','worksheet'):
            with self.subTest(phase=phase):
                FakeParts.calls=[];FakeParts.failure=phase
                runner=self.runner()
                with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'invented'):
                    runner.execute()
                state=json.loads((runner.run/'desk_run.json').read_text())
                self.assertEqual(state['status'],'failed');self.assertEqual(state['failed_part'],phase)
                self.assertFalse((runner.run/'final_report.md').exists())
                if phase in ('seeker','team'):self.assertNotIn('worksheet',FakeParts.calls)
                # Same test timestamp: use a new root for the next failure case.
                self.options.runs_root=self.root/phase

    def test_hook_rejects_a_seeded_team_amount_and_stops_before_worksheet(self):
        FakeParts.failure='number';runner=self.runner();output=io.StringIO()
        with redirect_stdout(output),self.assertRaises(HookFailure):runner.execute()
        self.assertNotIn('worksheet',FakeParts.calls)
        self.assertIn('$101',output.getvalue())
        self.assertEqual(json.loads((runner.run/'desk_run.json').read_text())['failed_part'],'team')

    def test_offline_replay_preserves_view_and_makes_no_fetches(self):
        runner,result=self.execute();view=runner.run/'view.json'
        before=(view.read_bytes(),view.stat().st_mtime_ns)
        with redirect_stdout(io.StringIO()),patch('requests.Session.request',side_effect=AssertionError('HTTP attempted')),local_sockets_only():
            self.assertEqual(desk.replay(runner.run),result)
        self.assertEqual(before,(view.read_bytes(),view.stat().st_mtime_ns))
        self.assertEqual(FakeParts.calls,['seeker','pick','team','worksheet'])

    def test_replay_rejects_changed_source_and_changed_final(self):
        runner,result=self.execute();original=result.read_text();result.write_text(original.replace('$100','$101'))
        with self.assertRaisesRegex(ValueError,'changed'):desk.replay(runner.run)
        result.write_text(original);(runner.run/'10-K.txt').write_text('Income is $101')
        with self.assertRaisesRegex(ValueError,'changed'):desk.replay(runner.run)

    def test_replay_does_not_overwrite_original_audit_logs(self):
        runner,_=self.execute();old={p.name:p.read_bytes() for p in (runner.run/'hook').glob('*.json')}
        with redirect_stdout(io.StringIO()):desk.replay(runner.run)
        for name,data in old.items():self.assertEqual((runner.run/'hook'/name).read_bytes(),data)

    def test_failed_run_replays_saved_stages_and_retains_original_failure(self):
        FakeParts.failure='team';runner=self.runner()
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'invented team failure'):runner.execute()
        original=(runner.run/'desk_run.json').read_bytes();calls=list(FakeParts.calls)
        output=io.StringIO()
        with redirect_stdout(output),local_sockets_only(),self.assertRaisesRegex(ValueError,'Saved part team failed: invented team failure'):
            desk.replay(runner.run)
        self.assertIn('Part replay pick:',output.getvalue())
        self.assertIn('Missing output: verified_report.md',output.getvalue())
        self.assertNotIn('Part starting: replay worksheet',output.getvalue())
        self.assertEqual(original,(runner.run/'desk_run.json').read_bytes())
        self.assertEqual(calls,FakeParts.calls)

    def test_failed_run_replay_rejects_changed_saved_output(self):
        FakeParts.failure='number';runner=self.runner()
        with redirect_stdout(io.StringIO()),self.assertRaises(HookFailure):runner.execute()
        (runner.run/'report.md').write_text('Changed report')
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'changed'):desk.replay(runner.run)

    def test_final_report_itself_is_checked_not_just_source_fragments(self):
        runner,result=self.execute();result.write_text(result.read_text().replace('$100','$101'))
        with self.assertRaises(HookFailure):
            runner.hook.check('final',[result],verified=runner.run/'verified_report.md',worksheet=runner.run/'Spinoff worksheet, ZZZZ.md')

    def test_screen_run_is_renamed_to_picked_ticker_with_original_start(self):
        self.options.selector='screen';runner,result=self.execute()
        self.assertEqual(runner.run.name,'ZZZZ_2026-11-17_09-12-13.123456')
        self.assertFalse(any(p.name.startswith('SCREEN_') for p in self.root.iterdir()))
        self.assertIn('ZZZZ_',str(result))

    def test_real_worksheet_and_final_hook_with_sourced_financial_values(self):
        runner=self.real_worksheet_runner()
        with redirect_stdout(io.StringIO()),local_sockets_only():
            result=runner.execute()
        self.assertEqual(json.loads((runner.run/'desk_run.json').read_text())['status'],'complete')
        self.assertIn('Low value: 90;',result.read_text())
        self.assertEqual(sum(line.startswith('Liquidity day |') for line in result.read_text().splitlines()),60)
        with redirect_stdout(io.StringIO()):self.assertEqual(desk.replay(runner.run),result)

    def test_real_worksheet_price_failure_stops_before_model(self):
        runner=self.real_worksheet_runner('price')
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'reader last_close_before failed: seeded'):
            runner.execute()
        self.assertEqual(self.seeded_calls,{'model':0,'liquidity':0})
        self.assertFalse((runner.run/'final_report.md').exists())
        self.assertEqual(json.loads((runner.run/'desk_run.json').read_text())['failed_part'],'worksheet')

    def test_real_worksheet_liquidity_failure_stops_final_report(self):
        runner=self.real_worksheet_runner('liquidity')
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'reader daily_closes_and_volumes failed: seeded'):
            runner.execute()
        self.assertEqual(self.seeded_calls,{'model':1,'liquidity':1})
        self.assertFalse((runner.run/'final_report.md').exists())

    def test_real_worksheet_model_failure_does_not_fetch_liquidity(self):
        runner=self.real_worksheet_runner('model')
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'worksheet judgment failed: seeded'):
            runner.execute()
        self.assertEqual(self.seeded_calls,{'model':1,'liquidity':0})

    def real_worksheet_runner(self,failure=None):
        from desk_parts import Parts
        class KnownParts(FakeParts):
            def team(inner,ticker,started,output_hook):
                self=inner;self.calls.append('team')
                dates='Years ended\nAugust 30, 2026\nAugust 31, 2025\nSeptember 1, 2024\n'
                filing=('The number of shares outstanding of the registrant’s common stock as of September 29, 2026, was\n10,000,000\n.\n'
                         'CONSOLIDATED STATEMENTS OF INCOME\n(amounts in millions)\n'+dates+'NET INCOME\n$\n100\n90\n80\n'
                         'CONSOLIDATED STATEMENTS OF CASH FLOWS\n(amounts in millions)\n'+dates+'Net income\n$\n100\n90\n80\nDepreciation and amortization\n20\n25\n30\nAdditions to property and equipment\n(30)\n(25)\n(20)\n')
                company={'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[{'val':100000000,'end':'2026-08-30','accn':ACC}]}}}}}
                def get(url,**kwargs):
                    response=__import__('requests').Response();response.status_code=200
                    response._content=(json.dumps(company) if 'companyfacts' in url else filing).encode();return response
                self.sources.transport=get
                self.sources.text('https://data.sec.gov/api/xbrl/companyfacts/CIK0000012345.json')
                (self.run/'10-K.txt').write_text(self.sources.text(FILE_URL));self.sources.inventory(FILE_URL,'10-K',self.run/'10-K.txt');self.sources.save()
                write_json(self.run/'facts.json',{'ticker':ticker,'cik':'12345','facts':{'net_income':{'tag':'NetIncomeLoss','period_end':'2026-08-30','filing':ACC,'value':100000000}}})
                write_json(self.run/'filing_time.json',{'effective_filed_eastern':'2026-11-16T17:00:00-05:00'})
                report=f'Filings read: 10-K {ACC}\nRun time: {started.isoformat()}\nIncome is $100000000 [XBRL tag NetIncomeLoss, period end 2026-08-30, filing {ACC}].\n'
                (self.run/'report.md').write_text(report);(self.run/'verified_report.md').write_text(report)
                return self.run/'verified_report.md'
            def worksheet(inner,started,output_hook):
                inner.calls.append('worksheet');adapter=Parts(inner.run,inner.sources,inner.options);adapter.registry={'candidates':{}}
                rows=[];day=(started-timedelta(days=1)).date()
                while len(rows)<60:
                    if day.weekday()<5:rows.append({'date':day.isoformat(),'close':50.0,'volume':100000.0,'currency':'USD','source':'LSEG TR.PriceClose (ZZZZ.O)','volume_source':'LSEG TR.Volume (ZZZZ.O)'})
                    day-=timedelta(days=1)
                rows.sort(key=lambda r:r['date']);price=dict(rows[-1],ticker='ZZZZ')
                class Clock(datetime):
                    @classmethod
                    def now(cls,tz=None):return started
                judged={'judgment':'The supplied earnings support the cash flow measure.','next_filing_trigger':'Read the next cash flow statement.','insight':'Capital spending uses cash [fact:capital_spending].'}
                with patch('closes_reader.last_close_before',return_value=price,side_effect=RuntimeError('seeded price failure') if failure=='price' else None),patch('closes_reader.daily_closes_and_volumes',return_value=rows,side_effect=RuntimeError('seeded liquidity failure') if failure=='liquidity' else None) as daily,patch.object(adapter.worksheet_module,'judge_once',return_value=judged,side_effect=RuntimeError('seeded model failure') if failure=='model' else None) as judge,patch.object(adapter.worksheet_module,'datetime',Clock):
                    try:return adapter.worksheet(started,output_hook)
                    finally:self.seeded_calls={'model':judge.call_count,'liquidity':daily.call_count}
        return desk.DeskRun(self.options,parts_factory=KnownParts,clock=self.started)


class SourceReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.run=Path(self.tmp.name)
        response=__import__('requests').Response();response.status_code=200;response._content=b'saved filing text'
        self.transport=Mock(return_value=response);self.sources=Sources(self.run,'invented test identity',self.transport)

    def test_two_parts_read_one_filing_with_one_fetch(self):
        self.sources.phase='seeker';self.sources.text(FILE_URL)
        self.sources.phase='team';self.sources.text(FILE_URL)
        self.sources.phase='worksheet';self.sources.text(FILE_URL)
        self.assertEqual(self.transport.call_count,1)
        self.assertEqual(len(self.sources.data['filings']),1)
        self.assertEqual(self.sources.data['filings'][ACC]['parts'],['seeker','team','worksheet'])

    def test_reuse_imported_seeker_cache_without_fetch(self):
        import hashlib
        path=self.run/'sources/imported'/(hashlib.sha256(FILE_URL.encode()).hexdigest()+'.txt')
        path.parent.mkdir(parents=True);path.write_text('already saved')
        self.assertEqual(self.sources.text(FILE_URL),'already saved');self.transport.assert_not_called()

    def test_corrupted_cached_source_is_rejected(self):
        self.sources.text(FILE_URL)
        record=self.sources.data['responses'][FILE_URL];(self.run/record['path']).write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.sources.text(FILE_URL)

    def test_changed_plain_text_filing_is_rejected(self):
        path=self.run/'10-K.txt';path.write_text('Original statement')
        self.sources.inventory(FILE_URL,'10-K',path);path.write_text('Changed statement')
        with self.assertRaisesRegex(ValueError,'filing text changed'):self.sources.verify()

    def test_only_sec_hosts_and_safe_paths(self):
        with self.assertRaises(ValueError):self.sources.text('https://example.com/filing')
        self.assertIn('/Archives/',canonical_url('https://www.sec.gov/ix?doc=/Archives/edgar/data/12345/a.htm'))

    def test_replay_guard_blocks_network(self):
        with no_fetch(),self.assertRaisesRegex(RuntimeError,'Replay'):__import__('requests').get('https://www.sec.gov')


class ScreenAndReportTests(unittest.TestCase):
    def test_latest_snapshot_uses_saved_run_time_not_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,time in [('a','2026-11-16T12:00:00-05:00'),('b','2026-11-17T12:00:00-05:00')]:
                write_json(root/('Spinoffs, '+name+'.json'),{'run_time':time,'registry':{}})
            (root/'Spinoffs, a.json').touch()
            self.assertEqual(latest_screen(root).name,'Spinoffs, b.json')

    def test_rank_is_recomputed_and_pending_names_not_picked(self):
        def rank(pool,factors):
            pool.sort(key=lambda c:c['cik'])
            for c in pool:c.update(rank=1,points={'a':1},total_points=1)
            return pool,[]
        module=type('Module',(),{'rank':staticmethod(rank)})
        c={'cik':'12345','eligibility':'included','rank':1,'points':{'a':1},'total_points':1,'facts':{'ticker':{'value':'ZZZZ'}}}
        data={'factors':{'a':1},'registry':{'complete':False,'pending_ciks':['00001'],'candidates':{'12345':c,'00001':dict(c,cik='00001')}}}
        self.assertEqual(validate_screen(module,data)[0],'ZZZZ')
        c['total_points']=2
        with self.assertRaisesRegex(ValueError,'total_points'):validate_screen(module,data)
        # A requested ticker still gets the rank check, but needs no ranked name.
        with self.assertRaisesRegex(ValueError,'total_points'):validate_screen(module,data,need_ticker=False)

    def test_a_screen_that_ranks_nobody_stops_only_a_screen_pick(self):
        # On 2026-11-19 a bounded scan found ten registrants and could date none, so it ranked none. A run on a
        # requested ticker stopped there, though the ticker needed no screen.
        module=type('Module',(),{'rank':staticmethod(lambda pool,factors:([],[]))})
        c={'cik':'12345','eligibility':'missing dates','facts':{}}
        data={'factors':{'a':1},'registry':{'complete':False,'pending_ciks':[],'candidates':{'12345':c}}}
        with self.assertRaisesRegex(ValueError,'no ranked ticker'):validate_screen(module,data)
        self.assertEqual(validate_screen(module,data,need_ticker=False),(None,None))

    def test_report_numeric_citation_is_exact_and_stray_amount_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);(run/'release.txt').write_text('Net income was $100.')
            p=run/'report.md'
            self.assertEqual(report_errors(run,p,'Income was $100 [release.txt:L1].'),[])
            self.assertTrue(report_errors(run,p,'Income was $101 [release.txt:L1].'))
            self.assertTrue(report_errors(run,p,'Income was $100, and debt was $999 [release.txt:L1].'))

    def test_verifier_wrong_mark_blocks_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);path=run/'nodes/Verifier_1/output.json'
            write_json(path,{'checks':[{'claim':'invented mismatch','status':'wrong'}]})
            with self.assertRaises(HookFailure):Hook(run,Sources(run,'')).check('verifier',[path])


if __name__=='__main__':unittest.main()
