import hashlib,importlib.util,json,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from datetime import datetime
P=Path(__file__).resolve().parents[1]/'scripts/worksheet.py'
spec=importlib.util.spec_from_file_location('worksheet_tested',P)
w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)

class WorksheetTests(unittest.TestCase):
    def test_prediction_is_saved_before_model_and_report_uses_that_record(self):
        saved_at=datetime.fromisoformat('2027-02-02T12:05:00-05:00')
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return saved_at
        def judgment(persona,payload):
            record=json.loads((self.run/'view.json').read_text(encoding='utf-8'))
            self.assertEqual(record['direction'],'up')
            self.assertEqual(record['time'],saved_at.isoformat())
            return {'judgment':'The supplied evidence supports the valuation.',
                    'next_filing_trigger':'A decline in earnings would weaken the view.'}
        with patch.object(w,'datetime',Clock):
            result=self.execute(model=judgment)
        saved=json.loads((self.run/'view.json').read_text(encoding='utf-8'))
        text=result['files']['markdown'].read_text(encoding='utf-8')
        self.assertEqual(result['view']['direction'],saved['direction'])
        self.assertEqual(result['view']['time'],saved['time'])
        self.assertIn('View on the release: up',text)
        self.assertIn('View timestamp: '+saved['time'],text)
        self.assertIn('Filing acceptance: '+saved['filing_time'],text)
        self.assertIn(saved['reaction_window']['first_close_after_filing_time'],text)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name)
        (self.run/'filing_time.json').write_text(json.dumps({'edgar_accepted':'2027-02-01 16:30:00'}),encoding='utf-8')
        (self.run/'facts.json').write_text(json.dumps({'ticker':'ZZZ','company':'Issuer','cik':'101','report_period':'2026-12-31','facts':{}}),encoding='utf-8')
        (self.run/'10-K.txt').write_text('CONSOLIDATED STATEMENTS\nYear ended December 31, 2026\nNet income $100\nDepreciation $20\nCapital spending $30\nShares outstanding 10\n', encoding='utf-8')
        (self.run/'persona.md').write_text('Test supplied filing facts and explain the deciding evidence.',encoding='utf-8')
        self.cfg={'price_filed':'2027-02-01T16:30:00','liquidity':{'start':'2027-01-01','end':'2027-02-01','purchase_size':100,'currency':'USD'},'facts':{key:{'file':'10-K.txt','section':'CONSOLIDATED STATEMENTS','pattern':pattern,'kind':'historical','period':'Year ended December 31, 2026','unit':unit} for key,pattern,unit in [('after_tax_earnings',r'Net income \$(?P<amount>\d+)','USD'),('depreciation',r'Depreciation \$(?P<amount>\d+)','USD'),('capital_spending',r'Capital spending \$(?P<amount>\d+)','USD'),('shares_outstanding',r'Shares outstanding (?P<amount>\d+)','shares')]},'valuation':{'low':{'formula':'owner_cash_flow / discount_rate / shares_outstanding','rates':{'discount_rate':.1}},'mid':{'formula':'owner_cash_flow / discount_rate / shares_outstanding','rates':{'discount_rate':.08}}},'conviction':{'high_if':'price < low_value * margin','parameters':{'margin':.8}}}
        self.reader=Mock();self.reader.last_close_before.return_value={'close':50,'date':'2027-02-01','source':'test','currency':'USD'}
        self.reader.daily_closes_and_volumes.return_value=[{'date':'2027-01-04','close':10,'volume':10,'currency':'USD'},{'date':'2027-01-05','close':20,'volume':20,'currency':'USD'},{'date':'2027-01-06','close':30,'volume':30,'currency':'USD'}]
    def execute(self,registry=None,model=None):
        self.model=model or Mock(return_value={'judgment':'The supplied earnings support the low case.','next_filing_trigger':'A decline in reported earnings would weaken the view.'})
        return w.build(self.run,self.cfg,(self.run/'persona.md').read_text(encoding='utf-8'),registry or {'candidates':{}},self.reader,self.model,now=datetime.fromisoformat('2027-02-02T12:00:00+00:00'))
    def test_an_insight_the_model_labels_itself_is_printed_with_one_label(self):
        # In the Workday live run (2026-11-25) the model began its insight with "Insight:", and the final report printed
        # "Insight: Insight:". The saved model output keeps the model's own words.
        model=Mock(return_value={'judgment':'The supplied earnings support the low case.',
                                 'next_filing_trigger':'A decline in reported earnings would weaken the view.',
                                 'insight':'Insight: reported earnings [fact:after_tax_earnings] carry the owner cash flow.'})
        result=self.execute(model=model)
        lines=[line for line in result['files']['markdown'].read_text(encoding='utf-8').splitlines() if line.startswith('Insight:')]
        self.assertEqual(len(lines),1)
        self.assertTrue(lines[0].startswith('Insight: reported earnings'),lines[0])
        saved=next(self.run.glob('Spinoff worksheet*, model output.json'))
        self.assertTrue(json.loads(saved.read_text(encoding='utf-8'))['insight'].startswith('Insight: reported'))
    def test_complete_non_spinoff_one_call_liquidity_not_in_model(self):
        result=self.execute();self.assertEqual(self.model.call_count,1)
        payload=self.model.call_args.args[1]
        self.assertEqual(set(payload),{'filing_facts','value_range','price_vs_low'})
        self.assertNotIn('volume',json.dumps(payload));self.assertNotIn('purchase_size',json.dumps(payload))
        self.assertEqual(result['owner_cash_flow']['value'],90)
        self.assertEqual(result['value_range']['low']['value'],90)
        self.assertEqual(result['liquidity']['median_daily_dollar_volume'],400)
        self.assertEqual(result['liquidity']['purchase_fraction'],.25)
        self.assertEqual(result['view']['direction'],'up')
        self.assertEqual(result['conviction'],'high')
        self.assertEqual(result['facts']['parent']['value'],'not applicable')
        self.assertTrue(result['files']['markdown'].exists())
        text=result['files']['markdown'].read_text(encoding='utf-8');self.assertLess(text.index('Judgment:'),text.index('Liquidity:'))
        self.assertEqual(result['files']['markdown'].stem,result['files']['json'].stem)
    def test_no_close_keeps_other_sections_but_no_price_or_view(self):
        self.reader.last_close_before.return_value='not available'
        result=self.execute();self.assertEqual(result['view']['direction'],'not computed')
        self.assertIsNone(result['price_vs_low']['price']);self.assertEqual(result['owner_cash_flow']['value'],90)
        self.assertEqual(self.model.call_count,1)
    def test_the_daily_rows_are_saved_beside_the_run_and_never_printed(self):
        # 2026-11-22: the worksheet printed its daily closes and volumes and saved them in its JSON, and a live run
        # commits both. The rows are a raw pull of a licensed source: they now go to a file git ignores.
        self.reader.daily_closes_and_volumes.return_value[0].update(close=10.123456789012345,source='saved close source',volume_source='saved volume source',currency='USD')
        result=self.execute();text=result['files']['markdown'].read_text(encoding='utf-8')
        self.assertFalse([line for line in text.splitlines() if line.startswith('Liquidity day |')])
        saved=json.loads(result['files']['json'].read_text(encoding='utf-8'))['liquidity']
        self.assertNotIn('inputs',saved)
        self.assertTrue(saved['inputs_file'].startswith('sources/licensed/'))
        rows_file=self.run/saved['inputs_file']
        rows=json.loads(rows_file.read_text(encoding='utf-8'))
        self.assertEqual(len(rows),saved['observations'])
        self.assertEqual((rows[0]['close'],rows[0]['source'],rows[0]['volume_source']),(10.123456789012345,'saved close source','saved volume source'))
        self.assertEqual(hashlib.sha256(rows_file.read_bytes()).hexdigest(),saved['inputs_sha256'])
        self.assertIn(f"{saved['observations']} observations, {saved['first_date']} to {saved['last_date']};",text)
        self.assertIn('are licensed data: they are saved beside the run and are not printed',text)
        self.assertNotIn(str(rows[0]['volume']),text.split('Liquidity:')[1].split('\n')[0].split('sources:')[0].split('observations')[1])
    def test_period_mismatch_missing_inputs_and_unsafe_formula_not_computed(self):
        self.cfg['facts']['depreciation']['period']='Year ended December 31, 2025'
        result=self.execute();self.assertIsNone(result['owner_cash_flow']['value'])
        self.assertIsNone(result['value_range']['low']['value'])
        with self.assertRaises(ValueError):w.calculate('__import__("os").system("false")',{})
        # A value that is not known applied no rate: the rates are not printed as numbers with no source. On
        # 2026-11-19 the hook refused that line, and the run stopped at the worksheet.
        lines=[l for l in w.render(result).splitlines() if l.startswith(('Low value:','Mid value:'))]
        self.assertEqual(len(lines),2)
        for line in lines:
            self.assertIn('rates: not applied;',line)
            self.assertNotRegex(line.split('formula:')[0]+line.split('rates:')[1],r'\d')
    def test_model_cannot_add_number_or_receive_liquidity(self):
        result=self.execute(model=Mock(return_value={'judgment':'Worth 999 dollars.','next_filing_trigger':'Next earnings.'}))
        self.assertEqual(result['judgment']['judgment'],'not known')
        self.assertIn('model judgment rejected',result['not_known'])
    def test_scaled_figure_requires_filing_units(self):
        self.cfg['facts']['after_tax_earnings']['scale']=1000000
        self.assertIsNone(self.execute()['owner_cash_flow']['value'])
    def test_registry_accession_used_and_original_information_statement_retained(self):
        candidate={'cik':'101','facts':{'ticker':{'value':'ZZZ'}},'history':[], 'read_filings':['https://www.sec.gov/Archives/edgar/data/101/0000000101-26-000001.txt']}
        registry={'candidates':{'101':candidate}}
        fetch=Mock(return_value=[{'file':'Form10/statement.txt','accession':'0000000101-26-000001','form':'10-12B'}])
        from unittest.mock import patch
        with patch.object(w,'fetch_registration',fetch):
            d=self.run/'Form10';d.mkdir();(d/'statement.txt').write_text('Information Statement\nParent: Parent issuer;\nDistribution ratio: one share for every two shares;\nRecord date: January 20, 2026\nDistribution date: February 2, 2026\nPro forma financing\nDebt raised: $500\nCash paid to parent: $400\nRetained liabilities: $100\nTax restriction: 2 years\n', encoding='utf-8')
            result=self.execute(registry)
        fetch.assert_called_once();self.assertEqual(result['facts']['parent']['value'],'Parent issuer')
        self.assertEqual(result['facts']['debt_raised']['value'],500)
        self.assertIn('statement.txt',result['facts']['debt_raised']['source'])
    def test_quarter_capex_uses_two_filing_lines(self):
        (self.run/'prior.txt').write_text('Cash flow\nSix months ended June 30, 2026\nCapital spending $50\n', encoding='utf-8')
        (self.run/'current.txt').write_text('Cash flow\nNine months ended September 30, 2026\nCapital spending $90\n', encoding='utf-8')
        spec={'file':'current.txt','section':'Cash flow','pattern':r'Capital spending \$(?P<amount>\d+)','period':'Nine months ended September 30, 2026','kind':'historical','unit':'USD','cumulative':True,'fiscal_start':'2026-01-01','period_end':'2026-09-30','quarter_period':'Quarter ended September 30, 2026','prior':{'file':'prior.txt','section':'Cash flow','pattern':r'Capital spending \$(?P<amount>\d+)','period':'Six months ended June 30, 2026','kind':'historical','unit':'USD','fiscal_start':'2026-01-01','period_end':'2026-06-30'}}
        result=w.measurement(self.run,spec)
        self.assertEqual(result['value'],40);self.assertIn('prior.txt',result['source']);self.assertIn('90 - 50',result['source'])
    def test_form4_only_code_p_issuer_and_aggregate_consideration(self):
        d=self.run/'Form4';d.mkdir()
        (d/'one.xml').write_text('<ownershipDocument><issuer><issuerCik>101</issuerCik></issuer><nonDerivativeTransaction><transactionDate><value>2027-01-04</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>5</value></transactionShares><transactionPricePerShare><value>4</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction><nonDerivativeTransaction><transactionDate><value>2027-01-05</value></transactionDate><transactionCoding><transactionCode>S</transactionCode></transactionCoding></nonDerivativeTransaction></ownershipDocument>',encoding='utf-8')
        ob=w.form4_purchases(self.run,'101','2027-01-01','2027-02-01')
        self.assertEqual(ob['value'],20);self.assertEqual(ob['transactions'],1)

class AdditionalContracts(unittest.TestCase):
    setUp=WorksheetTests.setUp
    execute=WorksheetTests.execute
    def test_saved_effective_timestamp_is_used_in_eastern(self):
        self.cfg.pop('price_filed')
        (self.run/'filing_time.json').write_text(json.dumps({'effective_filed_eastern':'2027-02-01T16:30:00-05:00'}),encoding='utf-8')
        self.execute();self.reader.last_close_before.assert_called_once_with('ZZZ','2027-02-01T16:30:00')
    def test_liquidity_refuses_missing_volume_or_currency(self):
        self.reader.daily_closes_and_volumes.return_value=[{'date':'2027-01-04','close':10,'volume':None,'currency':'USD'}]
        self.assertTrue(self.execute()['liquidity']['reason'])
        self.reader.daily_closes_and_volumes.return_value=[{'date':'2027-01-04','close':10,'volume':100,'currency':'CAD'}]
        self.assertTrue(self.execute()['liquidity']['reason'])
    def test_a_model_of_another_provider_goes_through_the_teams_llm(self):
        # Another team runs the desk with its own key. A Claude model keeps its one HTTP call to Anthropic below;
        # any other model goes through CrewAI's LLM, as the agent team's does.
        calls=[]
        class FakeLLM:
            def __init__(self,**kwargs):calls.append(kwargs)
            def call(self,messages):
                calls.append(messages)
                return '```json\n'+json.dumps({'judgment':'Supported.','next_filing_trigger':'Watch earnings.'})+'\n```'
        payload={'filing_facts':{'facts':{'earnings':{'value':10,'source':'invented filing'}}}}
        for model,key in (('gemini/gemini-test','AIza-invented-test-key'),('openai/gpt-test','sk-invented-test-key')):
            calls.clear();record=Mock()
            with patch.dict('os.environ',{'MODEL':model,'API_KEY':key,'ANTHROPIC_API_KEY':''}),patch('crewai.LLM',FakeLLM),patch('requests.post') as post:
                self.assertEqual(w.judge_once('Test persona',payload,record_response=record)['judgment'],'Supported.')
            post.assert_not_called()
            self.assertEqual((calls[0]['model'],calls[0]['api_key']),(model,key))
            system,user=calls[1]
            self.assertTrue(system['content'].startswith('Test persona'))
            self.assertIn('Citation contract:',system['content'])
            self.assertEqual(json.loads(user['content']),payload)
            self.assertEqual(record.call_args.args[0]['model'],model)
    def test_a_sentence_after_the_fenced_judgment_is_not_used(self):
        # The shape of a real reply on 2026-11-19: a thinking block, the fenced JSON, then one more sentence.
        judgment={'judgment':'Supported {not a fact}.','next_filing_trigger':'Watch earnings.'}
        text='```json\n'+json.dumps(judgment,indent=2)+'\n```\n\nNo Insight is offered. The contract {allows} none.'
        response=Mock();response.json.return_value={'stop_reason':'end_turn','content':[{'type':'thinking','thinking':''},{'type':'text','text':text}]}
        with patch.dict('os.environ',{'MODEL':'anthropic/claude-test','API_KEY':'invented-test-key'}),patch('requests.post',return_value=response):
            self.assertEqual(w.judge_once('Test persona',{}),judgment)
        self.assertEqual(w.judgment_object('Here it is: '+json.dumps(judgment)),judgment)
        with self.assertRaisesRegex(ValueError,'holds no JSON object'):w.judgment_object('No judgment {today}.')
    def test_a_dropped_connection_is_tried_once_more_and_no_more(self):
        import requests
        response=Mock();response.json.return_value={'content':[{'type':'text','text':json.dumps({'judgment':'Supported.','next_filing_trigger':'Watch earnings.'})}]}
        env={'MODEL':'anthropic/claude-test','API_KEY':'invented-test-key'}
        with patch.dict('os.environ',env),patch.object(w,'RETRY_WAIT_SECONDS',0),patch('requests.post',side_effect=[requests.exceptions.ConnectionError('dropped'),response]) as post:
            self.assertEqual(w.judge_once('Test persona',{})['judgment'],'Supported.')
        self.assertEqual(post.call_count,2)
        with patch.dict('os.environ',env),patch.object(w,'RETRY_WAIT_SECONDS',0),patch('requests.post',side_effect=requests.exceptions.ConnectionError('dropped')) as post:
            with self.assertRaises(requests.exceptions.ConnectionError):w.judge_once('Test persona',{})
        self.assertEqual(post.call_count,2)
    def test_printed_reasons_hold_no_digit_the_hook_cannot_trace(self):
        # 2026-11-20: "3 comparable fiscal years ... were not established" stopped a whole run at the hook.
        spec=importlib.util.spec_from_file_location('statements_tested',P.with_name('statements.py'))
        s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
        _,ocf=s.collect(tempfile.mkdtemp(),3,True)
        self.assertTrue(ocf['reason'].startswith('three comparable fiscal years'),ocf['reason'])
        settings={'start':'2027-01-01','end':'2027-01-31','observations':20,'currency':'USD'}
        rows=[{'date':'2027-01-04','close':10,'volume':100,'currency':'USD'}]
        thin=w.liquidity(rows,settings)
        self.assertEqual((thin['required'],thin['supplied']),(20,1))
        for reason in (ocf['reason'],thin['reason']):self.assertNotRegex(reason,r'\d')
    def test_lowes_and_walmart_statements_and_covers_are_read(self):
        # 2026-11-20: the parser read no owner cash flow and no share count for Lowe's or Walmart. Amounts are the 10-Ks'.
        spec=importlib.util.spec_from_file_location('statements_layouts',P.with_name('statements.py'))
        s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
        run=Path(tempfile.mkdtemp())
        dates=['Fiscal Years Ended','January 30, 2026','January 31, 2025','February 2, 2024']
        lines=['Consolidated Statements of Earnings','(In millions, except per share and percentage data)',*dates,'Amount','% Sales',
               'Net earnings','$','6,654','7.71','$','6,957','8.31','$','7,726','8.94',
               'Consolidated Statements of Cash Flows','(In millions)',*dates,'Net earnings','$','6,654','$','6,957','$','7,726',
               'Depreciation and amortization','2,194','1,972','1,923','Capital expenditures','(2,213)','(1,927)','(1,964)',
               'Consolidated Balance Sheets','CLASS','OUTSTANDING AT 3/19/2026','Common Stock, $0.50 par value','560,063,429']
        (run/'10-K.txt').write_text('\n'.join(lines),encoding='utf-8')
        _,ocf=s.collect(run,3,True)
        self.assertEqual([r['value'] for r in ocf['annual_inputs']],[6635e6,7002e6,7685e6])
        self.assertAlmostEqual(ocf['value'],21322e6/3)
        shares=s.shares_outstanding(run,'2026-11-20')
        self.assertEqual((shares['value'],shares['as_of']),(560063429.0,'2026-03-19'))
        self.assertTrue(shares['source'].endswith('quote: OUTSTANDING AT 3/19/2026; shares: 560,063,429'))
        (run/'10-Q.txt').write_text('The registrant had\n7,933,746,241\nshares of common stock outstanding as of August 26, 2026.',encoding='utf-8')
        self.assertEqual(s.shares_outstanding(run,'2026-11-20')['value'],7933746241.0)
        self.assertEqual(s.period_dates('Fiscal Years Ended January 31, (Amounts in millions) 2026 2025 2024'),['2026-01-31','2025-01-31','2024-01-31'])
    def statements_module(self):
        spec=importlib.util.spec_from_file_location('statements_more_layouts',P.with_name('statements.py'))
        s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
        return s
    def test_column_dates_as_more_10ks_print_them(self):
        # 2026-11-23: Workday's and Autodesk's "Year Ended January 31, 2026 2025 2024" read as one date; NVIDIA's "Jan 25,
        # 2026" as none. The view was "not computed" for want of the three years.
        s=self.statements_module()
        three=['2026-01-31','2025-01-31','2024-01-31']
        self.assertEqual(s.period_dates('(in millions) Year Ended January 31, 2026 2025 2024 Cash flows from operating activities:'),three)
        self.assertEqual(s.period_dates('(In millions) Year Ended Jan 25, 2026 Jan 26, 2025 Jan 28, 2024'),['2026-01-25','2025-01-26','2024-01-28'])
        self.assertEqual(s.period_dates('Years Ended December 31, 2025, 2024 and 2023'),['2025-12-31','2024-12-31','2023-12-31'])
        self.assertEqual(s.period_dates('Years ended November 1, 2025, November 2, 2024 and October 28, 2023 (thousands)'),['2025-11-01','2024-11-02','2023-10-28'])
    def test_workdays_statements_give_three_years_of_owner_cash_flow(self):
        # Workday's 10-K for fiscal 2026; the amounts are its own and match its XBRL facts (read 2026-11-23).
        s=self.statements_module();run=Path(tempfile.mkdtemp())
        head=['Year Ended January 31,','2026','2025','2024']
        lines=['CONSOLIDATED STATEMENTS OF OPERATIONS','(in millions, except number of shares which are reflected in thousands and per share data)',*head,
               'Net income','$','693','$','526','$','1,381','Net income per share, basic','$','2.61','$','1.98','$','5.21',
               'CONSOLIDATED STATEMENTS OF CASH FLOWS','(in millions)',*head,'Cash flows from operating activities:','Net income','$','693','$','526','$','1,381',
               'Depreciation and amortization','347','326','282','Capital expenditures','(162)','(269)','(232)']
        (run/'10-K.txt').write_text('\n'.join(lines),encoding='utf-8')
        _,ocf=s.collect(run,3,True)
        self.assertEqual([r['value'] for r in ocf['annual_inputs']],[878e6,583e6,1431e6])
        self.assertAlmostEqual(ocf['value'],2892e6/3)
    def test_amounts_of_seven_digits_are_printed_with_all_of_them(self):
        # A company that reports in thousands prints 1,285,647 for $1.3 billion: seven digits. Until 2026-11-25 the
        # worksheet printed its equations with six ("-1.28565e+09 + 1.18296e+09 - ..."). The hook adds up what is
        # printed, got another sum, and stopped the worksheet part after the agent team had been paid for; a resume
        # met the same numbers and could not pass. Found on made-up statements: the companies the desk had run on
        # report in millions. Every amount here is made up.
        s=self.statements_module();run=Path(tempfile.mkdtemp())
        head=['Year Ended January 31,','2026','2025','2024']
        lines=['CONSOLIDATED STATEMENTS OF OPERATIONS','(in thousands, except per share data)',*head,
               'Net income','$','1,285,647','$','836,097','$','796,705',
               'CONSOLIDATED STATEMENTS OF CASH FLOWS','(in thousands)',*head,'Cash flows from operating activities:','Net income','$','1,285,647','$','836,097','$','796,705',
               'Depreciation and amortization','1,182,963','1,119,903','1,063,115','Capital expenditures','(1,046,227)','(1,035,079)','(1,025,168)']
        (run/'10-K.txt').write_text('\n'.join(lines),encoding='utf-8')
        _,ocf=s.collect(run,3,True)
        first=ocf['annual_inputs'][0]
        self.assertEqual(first['value'],1285647e3+1182963e3-1046227e3)
        self.assertIn('computed: 1285647000 + 1182963000 - 1046227000 = 1422383000;',first['source'])
        self.assertIn('Net income = 1285647000',first['source']);self.assertIn('spending = -(-1046227000) = 1046227000',first['source'])
        # Every equation the worksheet prints must hold on its own printed numbers, as the hook checks it.
        sys.path.insert(0,str(P.parents[3]/'hooks'))
        from worksheet_format import EQUATION,arithmetic,rounded_equal
        found=list(EQUATION.finditer(ocf['source']))
        self.assertGreaterEqual(len(found),4)
        for m in found:self.assertTrue(rounded_equal(m['result'],arithmetic(m['expr'])),m[0])
        # A number that six digits state in full is printed as it always was.
        self.assertEqual((s.exact(6654e6),s.exact(-2213e6),s.exact(1285647e3),s.exact(0.1)),('6.654e+09','-2.213e+09','1285647000','0.1'))
    def facts_run(self,unit,head,facts,income='Net income'):
        """A made-up run folder: a 10-K's two statements, and SEC's company-facts answer as a run saves it."""
        run=Path(tempfile.mkdtemp())
        lines=['CONSOLIDATED STATEMENTS OF OPERATIONS',unit,*head,income,'$','300','$','200','$','100',
               'CONSOLIDATED STATEMENTS OF CASH FLOWS',unit,*head,'Cash flows from operating activities:',income,'$','300','$','200','$','100',
               'Depreciation and amortization','30','20','10','Capital expenditures','(3)','(2)','(1)']
        (run/'10-K.txt').write_text('\n'.join(lines),encoding='utf-8')
        if facts is not None:
            years=[('2025-01-01','2025-12-31'),('2024-01-01','2024-12-31'),('2023-01-01','2023-12-31')]
            rows=lambda values:{'units':{'USD':[{'start':a,'end':b,'val':v} for (a,b),v in zip(years,values)]}}
            (run/'sources/http').mkdir(parents=True);(run/'sources/http/facts.bin').write_text(json.dumps({'facts':{'us-gaap':{k:rows(v) for k,v in facts.items()}}}),encoding='utf-8')
            (run/'sources.json').write_text(json.dumps({'responses':{'https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json':{'path':'sources/http/facts.bin'}}}),encoding='utf-8')
        return run
    def test_a_statement_row_is_used_only_when_the_companys_xbrl_facts_hold_it(self):
        # On 2026-11-25 made-up statements showed the reader giving a wrong amount that the hook then passed, because
        # the hook reads the same text the same way: a unit line it does not know ("($ millions)") read as dollars,
        # so the low value was near zero; the years of a title read onto the wrong columns; a noncontrolling
        # interest's row read as the company's earnings. On the real 10-Ks of the day (Lowe's, Walmart, Dell,
        # Workday) every row read equals an XBRL fact of its year. That comparison is now made in every run: a row
        # that the company's own facts do not hold for that year is left out, and the reason says so.
        s=self.statements_module();head=['Year Ended December 31,','2025','2024','2023']
        right={'NetIncomeLoss':[300e6,200e6,100e6],'DepreciationDepletionAndAmortization':[30e6,20e6,10e6],'PaymentsToAcquirePropertyPlantAndEquipment':[3e6,2e6,1e6]}
        _,ocf=s.collect(self.facts_run('(in millions)',head,right),3,True)
        self.assertEqual([r['value'] for r in ocf['annual_inputs']],[327e6,218e6,109e6])
        # A unit the reader does not know: 300 dollars is not the company's 300 million.
        _,ocf=s.collect(self.facts_run('($ millions)',head,right),3,True)
        self.assertIsNone(ocf['value']);self.assertEqual(ocf['annual_inputs'],[])
        self.assertIn('XBRL facts do not hold',ocf['reason']);self.assertFalse(re.search(r'\d',ocf['reason']))
        # The right amounts under the wrong years.
        _,ocf=s.collect(self.facts_run('(in millions)',['Year Ended December 31,','2024','2023','2022'],right),3,True)
        self.assertIsNone(ocf['value'])
        # Another company's worth of earnings: the facts' net income is not this row.
        other={**right,'NetIncomeLoss':[900e6,800e6,700e6],'NetIncomeLossAttributableToNoncontrollingInterest':[300e6,200e6,100e6]}
        _,ocf=s.collect(self.facts_run('(in millions)',head,other),3,True)
        self.assertIsNone(ocf['value'])
        # A loss is not a profit of the same size.
        loss={**right,'NetIncomeLoss':[-300e6,-200e6,-100e6]}
        _,ocf=s.collect(self.facts_run('(in millions)',head,loss),3,True)
        self.assertIsNone(ocf['value'])
        # A folder with no saved facts (a made-up folder, a registration statement) is read as before.
        _,ocf=s.collect(self.facts_run('(in millions)',head,None),3,True)
        self.assertEqual([r['value'] for r in ocf['annual_inputs']],[327e6,218e6,109e6])
    def test_dell_nvidia_and_dollar_tree_rows_and_dells_total_share_count(self):
        # Dell's spending row and its cover's total across three classes; NVIDIA's abbreviated dates and spending row;
        # Dollar Tree's "Net income (loss)". The rows the reader uses carry the 10-Ks' own amounts, which match their XBRL
        # facts (read 2026-11-23); Dell's consolidated row before fiscal 2026 and its split by class are made up.
        s=self.statements_module();run=Path(tempfile.mkdtemp())
        dell=['January 30, 2026','January 31, 2025','February 2, 2024']
        lines=['CONSOLIDATED STATEMENTS OF INCOME','(in millions, except per share amounts',')','Fiscal Year Ended',*dell,
               'Net income','5,936','4,576','3,211','Net income attributable to Dell Technologies Inc.','$','5,936','$','4,592','$','3,388',
               'CONSOLIDATED STATEMENTS OF CASH FLOWS','(in millions',')','Fiscal Year Ended',*dell,'Net income','$','5,936','$','4,576','$','3,211',
               'Depreciation and amortization','3,029','3,123','3,303','Capital expenditures and capitalized software development costs','(2,633)','(2,652)','(2,756)']
        (run/'10-K.txt').write_text('\n'.join(lines),encoding='utf-8')
        _,ocf=s.collect(run,3,True)
        self.assertEqual([r['value'] for r in ocf['annual_inputs']],[6332e6,5063e6,3935e6])
        (run/'10-Q.txt').write_text('As of September 1, 2026, there were 635,812,750 shares of the registrant’s common stock outstanding, consisting of\n'
                                   '354,000,000\noutstanding shares of Class C Common Stock,\n200,000,000\noutstanding shares of Class A Common Stock, and\n'
                                   '81,812,750\noutstanding shares of Class B Common Stock.',encoding='utf-8')
        shares=s.shares_outstanding(run,'2026-11-23')
        self.assertEqual((shares['value'],shares['as_of']),(635812750.0,'2026-09-01'))
        nvidia=Path(tempfile.mkdtemp())
        (nvidia/'10-K.txt').write_text('\n'.join(['Consolidated Statements of Cash Flows','(In millions)','Year Ended','Jan 25, 2026','Jan 26, 2025','Jan 28, 2024',
            'Net income','$','120,067','$','72,880','$','29,760','Depreciation and amortization','2,843','1,864','1,508',
            'Purchases related to property and equipment and intangible assets','(6,042)','(3,236)','(1,069)',
            'Consolidated Statements of Income','(In millions, except per share data)','Year Ended','Jan 25, 2026','Jan 26, 2025','Jan 28, 2024',
            'Net income','$','120,067','$','72,880','$','29,760']),encoding='utf-8')
        _,ocf=s.collect(nvidia,3,True)
        self.assertEqual([r['value'] for r in ocf['annual_inputs']],[116868e6,71508e6,30199e6])
        tree=['CONSOLIDATED STATEMENTS OF OPERATIONS','(in millions)','Year Ended','January 31, 2026','February 1, 2025','February 3, 2024',
              'Net income (loss)','$','1,282.5','$','(3,030.0',')','$','(998.4',')']
        self.assertEqual([(k,v['value']) for k,v in self.parsed(s,tree)],[('after_tax_earnings',1282.5e6),('after_tax_earnings',-3030e6),('after_tax_earnings',-998.4e6)])
    def parsed(self,s,lines):
        run=Path(tempfile.mkdtemp());(run/'10-K.txt').write_text('\n'.join(lines),encoding='utf-8')
        return s.parse(run/'10-K.txt',run)
    def test_rows_that_are_not_the_measure_and_amounts_in_bare_thousands(self):
        s=self.statements_module()
        head=['CONSOLIDATED STATEMENTS OF CASH FLOWS','(in millions)','Years Ended','July 25, 2026','July 26, 2025','July 27, 2024']
        # Cisco: its spending row is read; its "Depreciation, amortization, and other" adds other items, so it is not.
        rows=self.parsed(s,[*head,'Depreciation, amortization, and other','2,000','1,900','1,800','Acquisition of property and equipment','(905)','(670)','(849)'])
        self.assertEqual([k for k,_ in rows],['capital_spending']*3)
        # A noncontrolling interest's earnings are never the company's.
        income=['CONSOLIDATED STATEMENTS OF OPERATIONS','(in millions)','Years Ended','July 25, 2026','July 26, 2025','July 27, 2024']
        self.assertEqual(self.parsed(s,[*income,'Net income (loss) attributable to noncontrolling interests','1','2','3']),[])
        # Analog Devices prints "(thousands)", without "in": the amounts are thousands, not dollars.
        adi=['CONSOLIDATED STATEMENTS OF CASH FLOWS','Years ended November 1, 2025, November 2, 2024 and October 28, 2023','(thousands)','2025','2024','2023',
             'Depreciation and amortization','$','800,000','$','700,000','$','600,000']
        self.assertEqual([v['value'] for _,v in self.parsed(s,adi)],[800e6,700e6,600e6])
    def test_a_share_count_that_a_later_cover_has_replaced_is_not_used(self):
        # On 2026-11-25 the reader was run on 25 real filings. For one company it could not read the newest 10-Q's
        # cover (two classes are named near it) and took the 10-K's count from before a four-for-one split:
        # value per share would have been four times too high. The company's XBRL cover facts hold every cover's
        # count with its date. A count read is used only if no later cover fact differs from it by more than
        # five percent (shares move slowly: two other companies were a quarter behind, by under one percent).
        s=self.statements_module()
        def count(facts):
            run=Path(tempfile.mkdtemp())
            (run/'10-K.txt').write_text('As of March 1, 2026, there were\n100,000,000\nshares of the registrant’s common stock outstanding.',encoding='utf-8')
            if facts is not None:
                rows=[{'end':day,'val':value} for day,value in facts]
                (run/'sources/http').mkdir(parents=True)
                (run/'sources/http/facts.bin').write_text(json.dumps({'facts':{'dei':{'EntityCommonStockSharesOutstanding':{'units':{'shares':rows}}}}}),encoding='utf-8')
                (run/'sources.json').write_text(json.dumps({'responses':{'https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json':{'path':'sources/http/facts.bin'}}}),encoding='utf-8')
            return s.shares_outstanding(run,'2026-11-25')
        split=count([('2026-03-01',100000000),('2026-11-19',400000000)])
        self.assertIsNone(split['value']);self.assertIn('later',split['reason']);self.assertFalse(re.search(r'\d',split['reason']))
        self.assertIsNone(count([('2026-03-01',123456789)])['value'])                                      # the same day, another count
        self.assertEqual(count([('2026-03-01',100000000),('2026-08-25',100600000)])['value'],100000000.0)  # a quarter behind, under one percent
        self.assertEqual(count([('2026-03-01',100000000)])['value'],100000000.0)
        self.assertEqual(count([('2018-11-30',220000000)])['value'],100000000.0)                           # an old fact says nothing of today
        self.assertEqual(count([])['value'],100000000.0);self.assertEqual(count(None)['value'],100000000.0)
    def test_more_cover_page_share_counts_and_the_ones_not_taken(self):
        s=self.statements_module()
        def count(text):
            run=Path(tempfile.mkdtemp());(run/'10-Q.txt').write_text(text,encoding='utf-8')
            return s.shares_outstanding(run,'2026-11-23')
        # Dollar Tree, HP Inc. and Cisco: the count alone on the line after the dated line (their 10-Qs, 2026).
        self.assertEqual(count('As of August 25, 2026, there were\n187,630,299\nshares of the registrant’s common stock outstanding.')['value'],187630299.0)
        self.assertEqual(count('The number of shares of HP Inc. common stock outstanding as of August 19, 2026 was\n901,790,969')['value'],901790969.0)
        self.assertEqual(count('Number of shares of the registrant’s common stock outstanding as of November 12, 2026:\n3,942,448,184')['as_of'],'2026-11-12')
        # NVIDIA's rounded "24.1 billion", Workday's "approximately 196 million" by class, and Zoom's two classes with no
        # total are not an actual count of the company's shares.
        for text in ('The number of shares of common stock, $0.001 par value, outstanding as of August 21, 2026, was\n24.1\nbillion.',
                     'As of August 25, 2026, there were approximately\n196\nmillion shares of the registrant’s Class A common stock and\n45\nmillion shares of the registrant’s Class B common stock outstanding.',
                     'As of August 14, 2026, the number of shares of the registrant’s Class A common stock outstanding was\n263,233,141\n'
                     'and the number of shares of the registrant’s Class B common stock outstanding was\n28,550,570\n.'):
            self.assertIsNone(count(text)['value'],text[:60])
    def test_with_no_price_the_price_criterion_says_so_in_words(self):
        spec=importlib.util.spec_from_file_location('scores_tested',P.with_name('evidence_scores.py'))
        e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
        rows=e.score({},{'price':None,'low_value':None,'price_source':None},{'value':None})
        third=next(r for r in (rows[0] if isinstance(rows,tuple) else rows) if r['criterion']==3)
        self.assertEqual((third['score'],third['source']),(0,'Code price/low comparison; not computed, no price or no low value'))
    def test_a_refused_request_is_not_sent_again(self):
        import requests
        refused=Mock();refused.raise_for_status.side_effect=requests.exceptions.HTTPError('400 Client Error',response=Mock(status_code=400))
        with patch.dict('os.environ',{'MODEL':'anthropic/claude-test','API_KEY':'invented-test-key'}),patch.object(w,'RETRY_WAIT_SECONDS',0),patch('requests.post',return_value=refused) as post:
            with self.assertRaises(requests.exceptions.HTTPError):w.judge_once('Test persona',{})
        self.assertEqual(post.call_count,1)
    def test_a_missing_model_or_key_says_what_to_set(self):
        for env in ({'MODEL':'','API_KEY':'invented-test-key'},{'MODEL':'gemini/gemini-test','API_KEY':'','ANTHROPIC_API_KEY':''}):
            with patch.dict('os.environ',env),patch('requests.post') as post,patch('crewai.LLM') as llm:
                with self.assertRaisesRegex(ValueError,'Configure MODEL'):w.judge_once('persona',{})
            post.assert_not_called();llm.assert_not_called()
    def test_the_model_is_told_to_write_no_number_words(self):
        # The Workday live run's worksheet wrote that a criterion "would move off zero", and the hook refused the word as
        # it should (2026-11-25): the instruction now names number words as well as digits.
        response=Mock();response.json.return_value={'content':[{'type':'text','text':json.dumps({'judgment':'Supported.','next_filing_trigger':'Watch earnings.'})}]}
        with patch.dict('os.environ',{'MODEL':'claude-test','API_KEY':'invented-test-key'}),patch('requests.post',return_value=response) as post:
            w.judge_once('Test persona',{})
        self.assertIn('Write no number words either, such as zero, one or two',post.call_args.kwargs['json']['system'])
    def test_one_http_call_and_numeric_free_response(self):
        from unittest.mock import patch
        response=Mock();response.json.return_value={'content':[{'type':'text','text':json.dumps({'judgment':'Supported.','next_filing_trigger':'Watch earnings.'})}]}
        with patch.dict('os.environ',{'MODEL':'claude-test','API_KEY':'invented-test-key'}),patch('requests.post',return_value=response) as post:
            payload={'filing_facts':{'facts':{'earnings':{'value':10,'source':'invented filing'},'parent':{'value':'not applicable','source':'registry'},'net_cash':{'value':None,'source':'not known'}}},'value_range':{},'price_vs_low':{}}
            self.assertEqual(w.judge_once('Test persona',payload)['judgment'],'Supported.')
        self.assertEqual(post.call_count,1)
        body=post.call_args.kwargs['json']
        self.assertEqual(json.loads(body['messages'][0]['content']),payload)
        self.assertNotIn('tools',body)
        contract=body['system'].split('Citation contract:')[1]
        self.assertIn('[fact:earnings]',contract)
        self.assertNotIn('[fact:parent]',contract)
        self.assertNotIn('[fact:net_cash]',contract)
        self.assertIn('Registry absence does not establish',contract)
    def test_form4_amendment_does_not_count_as_an_extra_purchase(self):
        d=self.run/'Form4';d.mkdir()
        (d/'amend.xml').write_text('<ownershipDocument><documentType>4/A</documentType><issuer><issuerCik>101</issuerCik></issuer></ownershipDocument>',encoding='utf-8')
        self.assertIsNone(w.form4_purchases(self.run,'101','2027-01-01','2027-02-01')['value'])
    def test_fetch_registration_reads_only_registry_accessions(self):
        from types import SimpleNamespace as N
        from unittest.mock import patch
        row=N(cik='101',accession='0000000101-26-000001',form='10-12B',filed='2026-01-01')
        other=N(cik='101',accession='0000000101-26-000099',form='10-12B',filed='2026-02-01')
        document=N(url='https://www.sec.gov/Archives/edgar/data/101/a/info.htm',raw='<p>Information statement</p>',text='Information statement',blocks=[('Information statement','Parent: Parent issuer;')])
        client=Mock();client.errors=[];client.submissions.return_value=({},[row,other])
        seeker=N(Edgar=Mock(return_value=client),is_registration=lambda form:form=='10-12B',read_folder=Mock(return_value=([document],True)))
        with patch.object(w,'load_module',return_value=seeker):
            docs=w.fetch_registration(self.run,{'cik':'101','registration_accession':row.accession})
        seeker.read_folder.assert_called_once_with(client,row)
        self.assertTrue((self.run/docs[0]['raw_file']).exists());self.assertTrue((self.run/docs[0]['file']).exists())
        self.assertEqual(docs[0]['accession'],row.accession)
    def test_registry_ticker_cannot_override_saved_issuer_identity(self):
        with self.assertRaises(ValueError):w.registry_match({'candidates':{'202':{'cik':'202','facts':{'ticker':{'value':'ZZZ'}}}}},'ZZZ','101')
    def test_million_scale_cannot_use_a_thousands_heading(self):
        p=self.run/'10-K.txt';p.write_text(p.read_text(encoding='utf-8')+'Amounts in thousands\n',encoding='utf-8')
        spec=self.cfg['facts']['after_tax_earnings'];spec.update(scale=1000000,units_pattern='in thousands')
        self.assertIsNone(w.measurement(self.run,spec)['value'])
    def test_report_is_not_a_filing_source(self):
        p=self.run/'report.md';p.write_text((self.run/'10-K.txt').read_text(encoding='utf-8'),encoding='utf-8')
        spec={**self.cfg['facts']['after_tax_earnings'],'file':'report.md'}
        self.assertIsNone(w.measurement(self.run,spec)['value'])

    def test_unclassified_statement_figure_stays_unknown(self):
        folder=self.run/'Form10';folder.mkdir()
        (folder/'info.txt').write_text('Information Statement\nDebt raised: $500 million\n',encoding='utf-8')
        result=w.spin_facts(self.run,[{'file':'Form10/info.txt'}])
        self.assertIsNone(result['debt_raised']['value'])
        self.assertIn('classification',result['debt_raised']['reason'])
