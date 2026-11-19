"""Invented saved filings and existing worksheet formatting, with mutations."""
import json
from datetime import date,timedelta
from decimal import Decimal,ROUND_CEILING
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worksheet_numbers import Auditor


class ExistingFormatTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.run=self.root/'run';self.run.mkdir()
        rules=self.root/'spinoff-rules.md';rules.parent.mkdir(parents=True,exist_ok=True)
        rules.write_text('Low case: owner cash flow ÷ 10%\nMid case: owner cash flow ÷ 7%\nOwner cash flow: average of the last 3 fiscal years\nClient portfolio: $1,000,000\nPurchase size: $1,000,000 ÷ 8 positions = $125,000\nmedian daily dollar volume over the last 60 trading days\npurchase size ≤ 10%\ncompleted within 3 trading days\n')
        (rules.parent/'persona-why-cheap.md').write_text('Scores: 0 = absent, 1 = partial, 2 = present and cited')
        (self.run/'facts.json').write_text(json.dumps({'ticker':'TEST','facts':{}}))
        self.filing=self.run/'10-K.txt'
        lines=['The number of shares outstanding of the registrant’s common stock as of September 29, 2026, was','10,000,000','.']
        header=['(amounts in millions)','(U.S. dollars)','52 Weeks Ended','August 30,','2026','August 31,','2025','September 1,','2024']
        lines+=['CONSOLIDATED STATEMENTS OF INCOME']+header+['NET INCOME','$','100','$','90','$','80']
        lines+=['CONSOLIDATED STATEMENTS OF CASH FLOWS']+header+['Depreciation and amortization','20','25','30','Additions to property and equipment','(','30',')','(','25',')','(','20',')','Next row label','123']
        self.filing.write_text('\n'.join(lines))
        self.positions={label:lines.index(label)+1 for label in ['NET INCOME','Depreciation and amortization','Additions to property and equipment']}
        self.path=self.run/'Spinoff worksheet, TEST.md'
        data={'ticker':'TEST','value_range':{'low':{'value':999999}},'liquidity':{'median_daily_dollar_volume':999999,'inputs':[
            {'date':'2026-11-11','close':50,'volume':200,'currency':'USD','source':'LSEG TR.PriceClose (TEST.O)','volume_source':'LSEG TR.Volume (TEST.O)'}]}}
        self.path.with_suffix('.json').write_text(json.dumps(data))
        self.periods=['2026-08-30','2025-08-31','2024-09-01']
        self.amounts=[[100000000,20000000,30000000],[90000000,25000000,25000000],[80000000,30000000,20000000]]
        self.share_source='[10-K.txt:L1] section Cover page; as of 2026-09-29; quote: The number of shares outstanding of the registrant’s common stock as of September 29, 2026, was 10,000,000'
        self.text=self.make_text()

    def source(self,metric,period,value):
        label=['NET INCOME','Depreciation and amortization','Additions to property and equipment'][metric]
        section='CONSOLIDATED STATEMENTS OF INCOME' if metric==0 else 'CONSOLIDATED STATEMENTS OF CASH FLOWS'
        reported=-value if metric==2 else value
        s=f'[10-K.txt:L{self.positions[label]}] section {section}; year ended {period}; units 1e+06; {label} = {reported:g}'
        if metric==2:s+=f'; spending = -({reported:g}) = {value:g}'
        return s

    def make_text(self):
        lines=['Spinoff worksheet | TEST | 2026-11-12T09:22:40.444799-05:00','','Fact | Amount or value | Statement basis | Filing and section','---|---|---|---']
        for name in ['parent','distribution_ratio','record_date','distribution_date','debt_raised','cash_to_parent','retained_liabilities','restrictions']:
            lines.append(name+' | not applicable | not applicable | Ticker is not in the supplied seeker registry')
        names=['after_tax_earnings','depreciation_and_amortization','capital_spending']
        for metric,name in enumerate(names):lines.append(f'{name} | {self.amounts[0][metric]} USD | historical | '+self.source(metric,self.periods[0],self.amounts[0][metric]))
        lines.append('shares_outstanding | 10000000 shares | historical | '+self.share_source)
        lines.append('insider_purchases | not known | not known | not known')
        for period,values in zip(self.periods,self.amounts):
            for metric,name in enumerate(['After-tax earnings','Depreciation and amortization','Capital spending']):
                lines.append(f'{name}, Fiscal year ended {period} | {values[metric]} USD | historical | '+self.source(metric,period,values[metric]))
        equations='computed: (90000000.0 + 90000000.0 + 90000000.0) / 3 = 9e+07'
        for a,b,c in self.amounts:equations+=f'; computed: {a:g} + {b:g} - {c:g} = 9e+07'
        lines+=['Owner cash flow: 90000000; '+equations,
                'Low value: 90; formula: (90000000) / (0.1) / (10000000) = 90; rates: {"discount_rate": 0.1}; sources: '+self.share_source+'; '+equations,
                'Mid value: 128.571428571429; formula: (90000000) / (0.07) / (10000000) = 128.571428571429; rates: {"discount_rate": 0.07}; sources: '+self.share_source,
                'Price against low: 50 on 2026-11-11 (LSEG TR.PriceClose (TEST.O)); low 90; (price - low) / low * 100 = -44.4444444444444%',
                'Judgment: The supplied earnings '+self.source(0,self.periods[0],100000000)+' support the calculation.',
                'Insight: Spending '+self.source(2,self.periods[0],30000000)+' is above depreciation '+self.source(1,self.periods[0],20000000)]
        names=['Forced seller','Indifferent seller','Price against value','Load pushed in','Insiders buying','Parent motive']
        for index,name in enumerate(names,1):lines.append(f'Criterion {index} — {name}: {2 if index==3 else 0} (computed in code); not known')
        lines+=['Deciding number: 90 USD/share (computed low value); '+self.share_source+'; '+equations,
                'Conviction rule: At least one of seller, insider interest, low-case price or quantified/covered parent load is missing',
                '- insider_purchases: No saved Form 4 XML; coverage is not established']
        return '\n'.join(lines)

    def check(self,text=None):
        self.path.write_text(self.text if text is None else text)
        return Auditor(self.run,self.root).check(self.path)

    def test_existing_format_passes_without_new_annotations(self):
        self.assertEqual(self.check(),[])

    def test_changed_table_amount_fails(self):
        f=self.check(self.text.replace('after_tax_earnings | 100000000','after_tax_earnings | 100000001'))
        self.assertTrue(any('Table amount differs' in x.reason for x in f))

    def test_wrong_period_column_fails(self):
        f=self.check(self.text.replace('year ended 2026-08-30','year ended 2025-08-31',1))
        self.assertTrue(f)

    def test_wrong_table_period_fails(self):
        self.assertTrue(self.check(self.text.replace('After-tax earnings, Fiscal year ended 2025-08-31','After-tax earnings, Fiscal year ended 2026-08-30')))

    def test_wrong_units_fails(self):
        self.assertTrue(self.check(self.text.replace('units 1e+06','units 1e+03',1)))

    def test_wrong_filing_row_or_label_fails(self):
        for old,new in [('NET INCOME =','Fake income ='),(f'L{self.positions["NET INCOME"]}]',f'L{self.positions["NET INCOME"]+1}]')]:
            with self.subTest(new=new):self.assertTrue(self.check(self.text.replace(old,new,1)))

    def test_changed_filing_amount_fails_unchanged_worksheet(self):
        self.filing.write_text(self.filing.read_text().replace('\n100\n','\n101\n'))
        self.assertTrue(self.check())

    def test_changed_cover_share_count_fails(self):
        self.filing.write_text(self.filing.read_text().replace('10,000,000','11,000,000'))
        self.assertTrue(self.check())

    def test_changed_cover_share_date_fails(self):
        self.assertTrue(self.check(self.text.replace('as of 2026-09-29','as of 2026-09-28')))

    def test_wrong_spending_sign_fails(self):
        self.assertTrue(self.check(self.text.replace('spending = -(-3e+07) = 3e+07','spending = -(-3e+07) = -3e+07',1)))

    def test_printed_equation_result_is_recomputed(self):
        self.assertTrue(self.check(self.text.replace('/ 3 = 9e+07','/ 3 = 8e+07',1)))

    def test_printed_equation_cannot_introduce_unsupported_input(self):
        self.assertTrue(self.check(self.text.replace('computed: 1e+08 +','computed: 9.99999e+08 +',1)))

    def test_changed_owner_cash_flow_fails(self):
        self.assertTrue(self.check(self.text.replace('Owner cash flow: 90000000','Owner cash flow: 90000001')))

    def test_changed_low_mid_or_deciding_number_fails(self):
        for old,new in [('Low value: 90','Low value: 91'),('Mid value: 128.571428571429','Mid value: 130'),('Deciding number: 90','Deciding number: 91')]:
            with self.subTest(new=new):self.assertTrue(self.check(self.text.replace(old,new)))

    def test_changed_authored_discount_rate_fails(self):
        p=self.root/'spinoff-rules.md'
        p.write_text(p.read_text().replace('÷ 10%','÷ 11%'))
        self.assertTrue(self.check())

    def test_changed_printed_rate_or_valuation_operand_fails(self):
        for old,new in [('"discount_rate": 0.1','"discount_rate": 0.11'),('(90000000) / (0.1)','(90000001) / (0.1)'),('(90000000) / (0.1)','(90000000) * (0.1)')]:
            with self.subTest(new=new):self.assertTrue(self.check(self.text.replace(old,new)))

    def test_changed_price_date_source_or_percentage_fails(self):
        for old,new in [('Price against low: 50','Price against low: 51'),('on 2026-11-11','on 2026-11-10'),('LSEG TR.PriceClose (TEST.O)); low','other reader); low'),('-44.4444444444444%','-43%')]:
            with self.subTest(new=new):self.assertTrue(self.check(self.text.replace(old,new)))

    def test_price_checks_only_original_reader_observations(self):
        data=json.loads(self.path.with_suffix('.json').read_text())
        data['value_range']={'low':{'value':90}} # Irrelevant computed sidecar claims.
        data['price_vs_low']={'price':50}
        data['liquidity']['inputs'][0]['close']=51
        self.path.with_suffix('.json').write_text(json.dumps(data))
        self.assertTrue(self.check())

    def test_price_rejects_duplicate_dates_and_foreign_currency(self):
        path=self.path.with_suffix('.json');original=json.loads(path.read_text())
        data=json.loads(path.read_text());data['liquidity']['inputs']*=2
        path.write_text(json.dumps(data));self.assertTrue(self.check())
        original['liquidity']['inputs'][0]['currency']='EUR'
        path.write_text(json.dumps(original));self.assertTrue(self.check())

    def test_changed_score_fails(self):
        self.assertTrue(self.check(self.text.replace('Price against value: 2','Price against value: 0')))
        self.assertTrue(self.check(self.text.replace('Forced seller: 0','Forced seller: 2')))

    def test_present_qualitative_evidence_is_not_treated_as_absent(self):
        self.assertTrue(self.check(self.text+'\nforced_seller | The holders have a mandate mismatch | historical | [10-K.txt:L1]'))
        self.assertTrue(self.check(self.text.replace('Criterion 3 — Price against value','Criterion 3 — Load pushed in')))

    def test_unrelated_number_in_prose_still_fails(self):
        self.assertTrue(self.check(self.text+'\nDebt is $999.'))

    def test_basis_and_currency_cannot_be_changed(self):
        self.assertTrue(self.check(self.text.replace('| historical |','| pro forma |',1)))
        self.filing.write_text(self.filing.read_text().replace('(U.S. dollars)','(CAD)'))
        self.assertTrue(self.check())

    def with_printed_daily_inputs(self):
        days=[];day=date(2026,11,11)
        while len(days)<60:
            if day.weekday()<5:days.append(day.isoformat())
            day-=timedelta(days=1)
        days.sort()
        data=json.loads(self.path.with_suffix('.json').read_text())
        data['liquidity']['inputs']=[{'date':day,'close':50,'volume':1000+j,'currency':'USD','source':'LSEG TR.PriceClose (TEST.O)','volume_source':'LSEG TR.Volume (TEST.O)'} for j,day in enumerate(days)]
        self.path.with_suffix('.json').write_text(json.dumps(data))
        lines=[f'Liquidity day | {day} | 50 | {1000+j} | USD | LSEG TR.PriceClose (TEST.O)' for j,day in enumerate(days)]
        med=Decimal('51475');purchase=Decimal(125000);capacity=med/10
        required=(purchase/capacity).to_integral_value(rounding=ROUND_CEILING)
        lines+=['Liquidity: historical; median(daily close * daily volume) = 51475 USD; client purchase 125000 USD; purchase/median '+format(purchase/med,'.15g')+'; 60 observations; '+', '.join(days)+'; sources: LSEG TR.PriceClose (TEST.O); daily inputs saved in companion JSON',
                f'Can you buy it: no; 10% * median = {capacity} USD/day; required {required} trading days; limit 3']
        return self.text+'\n'+'\n'.join(lines)

    def test_liquidity_recomputes_from_printed_inputs(self):
        self.assertEqual(self.check(self.with_printed_daily_inputs()),[])

    def test_printed_volume_sources_are_verified(self):
        text=self.with_printed_daily_inputs()
        text='\n'.join(line+' | LSEG TR.Volume (TEST.O)' if line.startswith('Liquidity day |') else line for line in text.splitlines())
        self.assertEqual(self.check(text),[])
        self.assertTrue(self.check(text.replace('| LSEG TR.Volume (TEST.O)','| wrong volume source',1)))

    def test_wrong_liquidity_summary_or_capacity_fails(self):
        text=self.with_printed_daily_inputs()
        for old,new in [('= 51475 USD','= 51476 USD'),('purchase 125000','purchase 125001'),('= 5147.5 USD/day','= 5148.5 USD/day'),('required 25 trading','required 24 trading'),('limit 3','limit 4'),('Can you buy it: no','Can you buy it: yes'),('60 observations','59 observations')]:
            with self.subTest(new=new):self.assertTrue(self.check(text.replace(old,new)))

    def test_daily_close_volume_or_date_change_fails(self):
        text=self.with_printed_daily_inputs()
        for old,new in [('| 50 | 1000 |','| 51 | 1000 |'),('| 50 | 1000 |','| 50 | 999 |'),('Liquidity day | 2026-','Liquidity day | 2025-')]:
            with self.subTest(new=new):self.assertTrue(self.check(text.replace(old,new,1)))

    def test_missing_or_duplicate_printed_day_fails(self):
        text=self.with_printed_daily_inputs();lines=text.splitlines()
        day=next(line for line in lines if line.startswith('Liquidity day |'))
        self.assertTrue(self.check(text.replace(day+'\n','',1)))
        self.assertTrue(self.check(text+'\n'+day))

    def test_missing_daily_inputs_is_an_evidence_gap_not_a_format_error(self):
        text=self.text+'\nLiquidity: historical; median(daily close * daily volume) = 10000 USD; client purchase 125000 USD; purchase/median 12.5; 60 observations; daily inputs saved in companion JSON\nCan you buy it: no; 10% * median = 1000 USD/day; required 125 trading days; limit 3'
        f=self.check(text)
        self.assertTrue(any('daily closes and volumes are not printed' in x.reason for x in f))
        self.assertTrue(any('without printed daily inputs' in x.reason for x in f))


if __name__=='__main__':unittest.main()
