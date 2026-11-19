"""Invented cumulative cash-flow facts; no network or model calls."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from quarterly_cash_flow import quarterly_capital_spending

TAG='PaymentsToAcquirePropertyPlantAndEquipment'
def row(value,end,fp,accession,start='2026-01-01',filed='2026-11-01',**extra):
    return dict(val=value,start=start,end=end,fp=fp,accn=accession,filed=filed,form='10-K' if fp=='FY' else '10-Q',**extra)
def facts(rows,tag=TAG):return {'facts':{'us-gaap':{tag:{'units':{'USD':rows}}}}}

class QuarterlyCashFlowTests(unittest.TestCase):
    def test_q3_is_nine_months_minus_six_months_from_two_filings(self):
        data=facts([row(90,'2026-09-30','Q3','current'),row(55,'2026-06-30','Q2','prior',filed='2026-08-01'),row(90,'2026-09-30','Q3','current',start='2026-07-01')])
        result=quarterly_capital_spending(data,'current',[TAG])
        self.assertEqual(result['value'],35)
        self.assertEqual(result['period_start'],'2026-07-01')
        self.assertEqual(result['period_end'],'2026-09-30')
        self.assertEqual([x['filing'] for x in result['inputs']],['current','prior'])
        self.assertEqual(result['formula'],'90 - 55')
        self.assertTrue(all(TAG in source for source in result['sources']))

    def test_q1_is_reported_ytd_and_q2_is_difference(self):
        data=facts([row(20,'2026-03-31','Q1','first',filed='2026-05-01'),row(55,'2026-06-30','Q2','second')])
        self.assertEqual(quarterly_capital_spending(data,'first',[TAG])['value'],20)
        self.assertEqual(quarterly_capital_spending(data,'second',[TAG])['value'],35)

    def test_fourth_quarter_is_full_year_minus_nine_months(self):
        data=facts([row(130,'2026-12-31','FY','annual',filed='2027-02-01'),row(90,'2026-09-30','Q3','third')])
        self.assertEqual(quarterly_capital_spending(data,'annual',[TAG])['value'],40)

    def test_missing_or_incompatible_prior_is_not_treated_as_zero(self):
        current=row(90,'2026-09-30','Q3','current')
        for prior in [[],[row(55,'2026-06-30','Q2','prior',start='2025-12-31')],[row(20,'2026-03-31','Q1','prior')],[row(55,'2026-06-30','Q2','current')],[row(55,'2026-06-30','Q2','prior',filed='2027-01-01')]]:
            result=quarterly_capital_spending(facts([current]+prior),'current',[TAG])
            self.assertIsNone(result['value']);self.assertTrue(result['reason'])

    def test_conflicting_or_dimensional_facts_remain_unavailable(self):
        current=row(90,'2026-09-30','Q3','current');prior=row(55,'2026-06-30','Q2','prior')
        self.assertIsNone(quarterly_capital_spending(facts([current,prior,row(60,'2026-06-30','Q2','prior')]),'current',[TAG])['value'])
        prior['dimensions']={'segment':'one'}
        self.assertIsNone(quarterly_capital_spending(facts([current,prior]),'current',[TAG])['value'])

    def test_different_tags_are_not_subtracted(self):
        data=facts([row(90,'2026-09-30','Q3','current')]);data['facts']['us-gaap']['OtherTag']={'units':{'USD':[row(55,'2026-06-30','Q2','prior')]}}
        self.assertIsNone(quarterly_capital_spending(data,'current',[TAG,'OtherTag'])['value'])

class QuarterlyCashFlowIntegrationTests(unittest.TestCase):
    def test_desk_uses_selected_filing_and_cached_facts(self):
        from equity_research_desk import Desk,Filing
        desk=Desk.__new__(Desk)
        desk.filings={'10-Q':Filing('10-Q','current','2026-11-01','filing.htm')}
        desk.company_facts=facts([row(90,'2026-09-30','Q3','current'),row(55,'2026-06-30','Q2','prior')])
        result=desk.quarterly_capex()
        self.assertEqual(result['value'],35)
        self.assertEqual(len(result['sources']),2)

if __name__=='__main__':unittest.main()
