"""Factor extraction and valuation use invented filings and closes only."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH=Path(__file__).resolve().parents[1]/'scripts/factor_data.py'
spec=importlib.util.spec_from_file_location('factor_data_tested',PATH)
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def document(raw, form='10-12B', cik='101', accession='0000000101-26-000001', filed='2026-01-20'):
    return SimpleNamespace(raw=raw,url='https://www.sec.gov/Archives/edgar/data/'+cik+'/'+accession+'/doc.htm',
        filing=SimpleNamespace(form=form,cik=cik,accession=accession,filed=filed))


class FactorDataTests(unittest.TestCase):
    def test_ownership_split_percent_cells_and_spanning_headers(self):
        d=document('<h2>Security ownership</h2><table><tr><td></td><td></td></tr>'
            '<tr><td colspan="3">Beneficial ownership</td></tr>'
            '<tr><td>Name</td><td>Number</td><td>Percentage of shares</td></tr>'
            '<tr><td>All directors and executive officers as a group (7 persons)</td><td></td><td>900</td><td></td><td>2.7</td><td>%</td></tr></table>')
        result=f.extract([d])['insider_ownership_pct']
        self.assertEqual(result['value'],2.7)
        self.assertIn('2.7 | %',result['quote'])

    def test_split_ownership_rejects_bounds_and_multiple_class_columns(self):
        for header,value in [('Percentage','&lt;1'),('Percentage Class A</td><td>Percentage Class B','2')]:
            d=document(f'<table><tr><td>Name</td><td>{header}</td></tr><tr><td>All directors and executive officers as a group</td><td>{value}</td><td>%</td></tr></table>')
            self.assertIsNone(f.extract([d])['insider_ownership_pct'])

    def test_ownership_source_section_follows_the_table_heading(self):
        d=document('<h2>Earlier section</h2><table><tr><td>Unrelated</td></tr></table>'
            '<h3>Security ownership</h3><table><tr><th>Name</th><th>Percent</th></tr>'
            '<tr><td>All directors and executive officers as a group</td><td>4%</td></tr></table>')
        self.assertEqual(f.extract([d])['insider_ownership_pct']['section'],'Security ownership')

    def test_officer_group_percentage_not_individual_holdings(self):
        d=document('<h2>Beneficial ownership</h2><table><tr><th>Owner</th><th>Percent of class</th></tr><tr><td>One officer</td><td>4%</td></tr><tr><td>All directors and executive officers as a group</td><td>18.5%</td></tr></table>')
        facts=f.extract([d]);self.assertEqual(facts['insider_ownership_pct']['value'],18.5)
        self.assertIn('18.5%',facts['insider_ownership_pct']['quote'])
        self.assertIn('Beneficial ownership',facts['insider_ownership_pct']['section'])

    def test_less_than_one_percent_is_not_estimated(self):
        d=document('<h2>Beneficial ownership</h2><table><tr><th>Owner</th><th>Percent of class</th></tr><tr><td>All directors and executive officers as a group</td><td>&lt;1%</td></tr></table>')
        self.assertIsNone(f.extract([d])['insider_ownership_pct'])

    def test_debt_ratio_uses_proforma_column(self):
        d=document('<h2>Pro Forma Balance Sheet</h2><table><tr><th>Line</th><th>Historical</th><th>Pro forma</th></tr><tr><td>Total debt</td><td>700</td><td>200</td></tr><tr><td>Total assets</td><td>900</td><td>1000</td></tr></table>')
        facts=f.extract([d]);self.assertEqual(facts['debt_to_assets']['value'],.2)
        self.assertIn('200',facts['debt_to_assets']['source']);self.assertIn('1000',facts['debt_to_assets']['source'])

    def test_ambiguous_proforma_columns_and_zero_assets_are_missing(self):
        for headers,values in [('<th>Pro forma child</th><th>Pro forma parent</th>','<td>2</td><td>3</td>'),('<th>Pro forma</th>','<td>0</td>')]:
            d=document('<h2>Pro Forma Balance Sheet</h2><table><tr><th>Line</th>'+headers+'</tr><tr><td>Total debt</td>'+values+'</tr><tr><td>Total assets</td>'+values+'</tr></table>')
            self.assertIsNone(f.extract([d])['debt_to_assets'])

    def test_missing_total_debt_is_not_replaced_by_long_term_debt(self):
        d=document('<h2>Pro Forma Balance Sheet</h2><table><tr><th>Line</th><th>Pro forma</th></tr><tr><td>Long-term debt</td><td>20</td></tr><tr><td>Total assets</td><td>100</td></tr></table>')
        self.assertIsNone(f.extract([d])['debt_to_assets'])

    def test_latest_reported_shares_on_or_before_price_date(self):
        d=document('<h2>Shares outstanding as of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>1,000</td></tr></table>')
        facts=f.extract([d]);self.assertEqual(f.shares_on(facts,'2026-02-03')['value'],1000)
        self.assertEqual(f.shares_on(facts,'2026-02-04')['value'],1000)
        self.assertIsNone(f.shares_on(facts,'2026-02-02'))

    def test_share_counts_reject_future_filings_and_preserve_both_dates(self):
        def count(n,asof,filed):
            return {'value':n,'as_of':asof,'filed':filed,'filing':'https://www.sec.gov/Archives/test.htm','section':'Shares','quote':str(n)}
        facts={'shares_outstanding':[count(100,'2026-01-10','2026-01-12'),count(200,'2026-01-20','2026-01-22'),count(300,'2026-01-25','2026-02-10')]}
        self.assertEqual(f.shares_on(facts,'2026-02-01')['value'],200)
        child= {'shares_outstanding':[count(100,'2026-01-10','2026-01-12')]}
        metrics=f.cap_metrics(child,facts,{'date':'2026-02-01','close':10},{'date':'2026-02-01','close':20})
        source=metrics['size_relative_to_parent']['source']
        for item in ['2026-01-10','2026-01-12','2026-01-20','2026-01-22','https://www.sec.gov/Archives/test.htm']:self.assertIn(item,source)

    def test_market_caps_both_use_child_first_close_date(self):
        child=f.extract([document('<h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>1000</td></tr></table>')])
        parent=f.extract([document('<h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>10000</td></tr></table>',form='10-K',cik='202')])
        metrics=f.cap_metrics(child,parent,{'date':'2026-02-03','close':10},{'date':'2026-02-03','close':20})
        self.assertEqual(metrics['absolute_market_cap']['value'],10000)
        self.assertEqual(metrics['size_relative_to_parent']['value'],.05)
        self.assertIn('2026-02-03',metrics['size_relative_to_parent']['source'])
        wrong=f.cap_metrics(child,parent,{'date':'2026-02-03','close':10},{'date':'2026-02-04','close':20})
        self.assertNotIn('size_relative_to_parent',wrong)

    def test_caps_missing_shares_or_incompatible_currencies_are_not_estimated(self):
        self.assertEqual(f.cap_metrics(f.extract([]),f.extract([]),{'date':'2026-02-03','close':10},None),{})

    def test_form4_counts_only_issuer_non_derivative_p_transactions_in_range(self):
        xml='<ownershipDocument><issuer><issuerCik>101</issuerCik></issuer><nonDerivativeTable>'
        for day,code in [('2026-02-01','P'),('2026-02-02','P'),('2026-02-03','S'),('2026-02-04','P'),('2026-03-01','P')]:
            xml+=f'<nonDerivativeTransaction><transactionDate><value>{day}</value></transactionDate><transactionCoding><transactionCode>{code}</transactionCode></transactionCoding></nonDerivativeTransaction>'
        xml+='</nonDerivativeTable></ownershipDocument>'
        d=document(xml,form='4',filed='2026-02-05')
        result=f.insider_purchases([d,d],'101','2026-02-02','2026-02-28',complete=True)
        self.assertEqual(result['value'],2);self.assertEqual(len(result['transactions']),2)
        self.assertIsNone(f.insider_purchases([d],'202','2026-02-02','2026-02-28',complete=True))

    def test_zero_purchases_requires_complete_coverage(self):
        self.assertEqual(f.insider_purchases([],'101','2026-02-02','2026-02-28',complete=True)['value'],0)
        self.assertIsNone(f.insider_purchases([],'101','2026-02-02','2026-02-28',complete=False))

    def test_form4_amendment_and_missing_xml_prevent_false_count(self):
        d=document('<ownershipDocument/>',form='4/A')
        self.assertIsNone(f.insider_purchases([d],'101','2026-02-02','2026-02-28',complete=True))
        self.assertIsNone(f.insider_purchases([document('Unreadable XML',form='4')],'101','2026-02-02','2026-02-28',complete=True))

    def test_same_day_conflicting_ownership_is_blank(self):
        def item(pct):return document(f'<h2>Beneficial ownership</h2><table><tr><th>Owner</th><th>Percent of class</th></tr><tr><td>All directors and executive officers as a group</td><td>{pct}%</td></tr></table>')
        self.assertIsNone(f.extract([item(10),item(20)])['insider_ownership_pct'])

    def test_parent_ticker_requires_filing_symbol_not_a_guessed_suffix(self):
        d=document('<ix:nonNumeric name="dei:TradingSymbol">PPP</ix:nonNumeric>',cik='202')
        self.assertEqual(f.ticker([d]),'PPP');self.assertIsNone(f.ticker([]))

    def test_periodic_acquisition_proforma_does_not_replace_form10_spinoff_debt(self):
        def table(debt,form,day):return document(f'<h2>Pro forma balance sheet</h2><table><tr><th>Line</th><th>Pro forma</th></tr><tr><td>Total debt</td><td>{debt}</td></tr><tr><td>Total assets</td><td>100</td></tr></table>',form=form,filed=day)
        result=f.extract([table(20,'10-12B','2026-01-20'),table(90,'10-Q','2026-02-20')])
        self.assertEqual(result['debt_to_assets']['value'],.2)

    def test_code_p_derivative_purchase_is_counted_and_qualified(self):
        xml='<ownershipDocument><issuer><issuerCik>101</issuerCik></issuer><derivativeTransaction><transactionDate><value>2026-02-03</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding></derivativeTransaction></ownershipDocument>'
        result=f.insider_purchases([document(xml,form='4')],'101','2026-02-02','2026-02-28',True)
        self.assertEqual(result['value'],1)
        self.assertIn('private',result['coverage'])

    def test_caps_reject_known_currency_mismatch_for_relative_size(self):
        d=document('<h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>1000</td></tr></table>')
        facts=f.extract([d])
        metrics=f.cap_metrics(facts,facts,{'date':'2026-02-03','close':10,'currency':'USD'},{'date':'2026-02-03','close':20,'currency':'EUR'})
        self.assertNotIn('size_relative_to_parent',metrics)



if __name__=='__main__':unittest.main()
