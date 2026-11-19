import importlib.util,sys,unittest,tempfile
from datetime import datetime
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'scripts/worksheet.py'
spec=importlib.util.spec_from_file_location('worksheet_rules_tested',P);w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)
class MarkdownRulesTests(unittest.TestCase):
    def test_first_view_is_frozen_without_overwriting_its_time(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)
            filed='2026-11-10T17:00:00-05:00'
            (run/'filing_time.json').write_text(json.dumps({'effective_filed_eastern':filed,'edgar_accepted':filed}))
            first=datetime.fromisoformat('2026-11-11T09:00:00-05:00')
            w.freeze_view(run,'ZZZ','more than the price',clock=lambda:first)
            path=run/'view.json';before=(path.read_bytes(),path.stat().st_mtime_ns)
            w.freeze_view(run,'ZZZ','less than the price',clock=lambda:datetime.fromisoformat('2026-11-11T17:00:00-05:00'))
            self.assertEqual((path.read_bytes(),path.stat().st_mtime_ns),before)
            data=json.loads(path.read_text());self.assertEqual(data['view_time'],first.isoformat());self.assertEqual(data['filing_time'],filed)

    def test_older_worksheet_is_not_shadowed_by_a_new_canonical_view(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)
            (run/'Spinoff worksheet, earlier.json').write_text(json.dumps({'worksheet_time':'2026-11-11T09:00:00-05:00','view':{'direction':'not computed'}}))
            w.freeze_view(run,'ZZZ','more than the price',clock=lambda:datetime.fromisoformat('2026-11-11T17:00:00-05:00'))
            self.assertFalse((run/'view.json').exists())
    def test_author_rules_are_read_without_overwriting_choices(self):
        path=w.ANALYST/'spinoff-rules.md'
        cfg=w.load_worksheet(path,datetime.fromisoformat('2027-02-02T12:00:00-05:00'))
        self.assertEqual(cfg['owner_cash_flow_years'],3)
        self.assertTrue(cfg['include_amortization'])
        self.assertEqual(cfg['valuation']['low']['rates']['discount_rate'],.1)
        self.assertEqual(cfg['valuation']['mid']['rates']['discount_rate'],.07)
        self.assertEqual(cfg['liquidity']['purchase_size'],125000)
        self.assertEqual(cfg['liquidity']['observations'],60)
        self.assertEqual(cfg['liquidity']['participation_rate'],.1)
        self.assertEqual(cfg['liquidity']['max_trading_days'],3)
    def test_annual_average_uses_three_statement_years_and_combined_da(self):
        module=w.load_module('test_statement_parser',P.with_name('statements.py'))
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)
            run.joinpath('10-K.txt').write_text('CONSOLIDATED STATEMENTS OF INCOME\nAmounts in USD\nYears ended\nDecember 31, 2026\nDecember 31, 2025\nDecember 31, 2024\nNET INCOME\n100\n80\n60\nCONSOLIDATED STATEMENTS OF CASH FLOWS\nAmounts in USD\nYears ended\nDecember 31, 2026\nDecember 31, 2025\nDecember 31, 2024\nDepreciation and amortization\n20\n15\n10\nAdditions to property and equipment\n(30)\n(25)\n(20)\nNOTES TO CONSOLIDATED STATEMENTS\n')
            facts,average=module.collect(run,3,True)
        self.assertEqual(average['value'],70)
        self.assertEqual([x['value'] for x in average['annual_inputs']],[90,70,50])
        self.assertTrue(all(x['source'] for x in average['annual_inputs']))
    def test_sixty_sessions_required_and_daily_capacity_sets_buyability(self):
        cfg={'start':'2026-01-01','end':'2026-12-31','purchase_size':250,'currency':'USD','observations':3,'participation_rate':.1,'max_trading_days':3}
        rows=[{'date':f'2026-01-0{i}','close':10,'volume':100,'currency':'USD'} for i in [1,2,3]]
        result=w.liquidity(rows,cfg)
        self.assertTrue(result['buyable']);self.assertEqual(result['minimum_trading_days'],3)
        self.assertTrue(w.liquidity(rows[:2],cfg)['reason'])
    def test_negative_owner_cash_flow_uses_net_cash_only(self):
        result=w.value_range({'negative_cash_flow_method':'net_cash'}, {'net_cash':{'value':100,'source':'filing line','kind':'historical'},'shares_outstanding':{'value':10,'source':'filing line','kind':'historical'}},{'value':-10,'source':'filing line'})
        self.assertEqual(result['low']['value'],10)
        self.assertIsNone(result['mid']['value'])
    def test_only_latest_requested_sessions_need_volume(self):
        cfg={'start':'2026-01-01','end':'2026-12-31','purchase_size':100,'currency':'USD','observations':2}
        rows=[{'date':'2026-01-01','close':10,'volume':None,'currency':'USD'},{'date':'2026-01-02','close':10,'volume':10,'currency':'USD'},{'date':'2026-01-05','close':20,'volume':10,'currency':'USD'}]
        self.assertEqual(w.liquidity(rows,cfg)['median_daily_dollar_volume'],150)
    def test_full_markdown_run_uses_author_persona_and_average(self):
        from unittest.mock import Mock
        from datetime import timedelta
        import json
        now=datetime.fromisoformat('2027-02-02T12:00:00-05:00')
        config=w.load_worksheet(w.ANALYST/'spinoff-rules.md',now)
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)
            run.joinpath('facts.json').write_text(json.dumps({'ticker':'ZZZ','cik':'101'}))
            run.joinpath('10-K.txt').write_text('The number of shares outstanding of the registrant’s common stock as of January 15, 2027, was 10\nCONSOLIDATED STATEMENTS OF INCOME\nAmounts in USD\nYears ended\nDecember 31, 2026\nDecember 31, 2025\nDecember 31, 2024\nNET INCOME\n100\n80\n60\nCONSOLIDATED STATEMENTS OF CASH FLOWS\nAmounts in USD\nYears ended\nDecember 31, 2026\nDecember 31, 2025\nDecember 31, 2024\nDepreciation and amortization\n20\n15\n10\nAdditions to property and equipment\n(30)\n(25)\n(20)\nNOTES TO CONSOLIDATED STATEMENTS\n')
            rows=[];day=now.date()-timedelta(days=1)
            while len(rows)<60:
                if day.weekday()<5:rows.append({'date':day.isoformat(),'close':10,'volume':100000,'currency':'USD'})
                day-=timedelta(days=1)
            reader=Mock();reader.daily_closes_and_volumes.return_value=rows;reader.last_close_before.return_value={'date':'2027-02-01','close':50,'currency':'USD','source':'invented close'}
            model=Mock(return_value={'judgment':'Not the forced seller story here; the earnings are established [fact:after_tax_earnings].','next_filing_trigger':'Check earnings in the next quarterly statement.','insight':'Reported depreciation contributes to owner cash flow [fact:depreciation_and_amortization].'})
            result=w.build(run,config,(w.ANALYST/'persona-why-cheap.md').read_text(),{'candidates':{}},reader,model,now)
            self.assertEqual(result['owner_cash_flow']['value'],70)
            self.assertEqual(result['value_range']['low']['value'],70)
            self.assertAlmostEqual(result['price_vs_low']['percent_price_minus_low'],-28.57142857)
            self.assertEqual(result['conviction'],'low')
            self.assertEqual(len(result['criteria_scores']),6)
            self.assertEqual(model.call_count,1)
            self.assertIn('10-K.txt:L',result['judgment']['judgment'])
            text=result['files']['markdown'].read_text();self.assertIn('Insight:',text);self.assertIn('Can you buy it: yes',text)
    def test_conviction_high_low_and_no_conviction_follow_rules(self):
        module=w.load_module('test_evidence_scores',P.with_name('evidence_scores.py'))
        facts={'shares_outstanding':{'value':10,'source':'filing section, dated'}}
        ocf={'value':70,'source':'filing arithmetic'};values={'low':{'value':70}}
        comparison={'price':50,'price_source':'dated reader close'}
        conditions={k:True for k in ['seller_identified','insider_interest','at_or_below_low','parent_load_quantified_and_covered']}
        self.assertEqual(module.conviction(conditions,{'buyable':True},facts,ocf,values,comparison)[0],'high')
        conditions['seller_identified']=False
        self.assertEqual(module.conviction(conditions,{'buyable':True},facts,ocf,values,comparison)[0],'low')
        self.assertEqual(module.conviction(conditions,{'buyable':False},facts,ocf,values,comparison)[0],'no conviction')
        facts['shares_outstanding']['source']='not known'
        self.assertEqual(module.conviction(conditions,{'buyable':True},facts,ocf,values,comparison)[0],'no conviction')
    def test_fill_marker_stops_before_any_model_or_reader(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'rules.md';path.write_text((w.ANALYST/'spinoff-rules.md').read_text()+'\nDiscount rate: FILL\n')
            with self.assertRaisesRegex(ValueError,'FILL'):w.load_worksheet(path)
    def test_truncated_model_response_is_recorded_without_a_second_call(self):
        from unittest.mock import Mock,patch
        response=Mock();raw={'stop_reason':'max_tokens','content':[{'type':'text','text':'partial'}]};response.json.return_value=raw
        record=Mock()
        with patch.dict('os.environ',{'MODEL':'claude-test','API_KEY':'invented-test-key'}),patch('requests.post',return_value=response) as post:
            with self.assertRaisesRegex(ValueError,'truncated'):w.judge_once('persona',{},record_response=record)
        self.assertEqual(post.call_count,1);record.assert_called_once_with(raw)
