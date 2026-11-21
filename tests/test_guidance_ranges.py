"""Synthetic guidance endpoints must be one range in saved evidence."""
import unittest
from desk_claims import check, with_repairs


class GuidanceRangeTests(unittest.TestCase):
    texts = {'10-K.txt': 'We project capital expenditures of $18 billion to $22 billion.',
             'earnings_release_Ex99-1.txt': 'Nine-month capital expenditures increased by $3 billion.'}

    def output(self, wrong=False):
        high_file = 'earnings_release_Ex99-1.txt' if wrong else '10-K.txt'
        return {'claims': [
            {'id':'c1','file':'10-K.txt','line':1,'quote':self.texts['10-K.txt'],'value':'$18 billion'},
            {'id':'c2','file':high_file,'line':1,'quote':self.texts[high_file],
             'value':'$3 billion' if wrong else '$22 billion'}],
            'draft':'Capital expenditure guidance is {c1} to {c2}.'}

    def test_mixed_metric_endpoints_are_rejected_even_with_exact_quotes(self):
        result=check(self.output(True),self.texts)
        self.assertFalse(result.ok)
        self.assertTrue(any('guidance range' in e.lower() for e in result.errors))

    def test_actual_guidance_pair_is_accepted(self):
        self.assertTrue(check(self.output(),self.texts).ok)

    def test_same_line_does_not_license_unrelated_endpoint(self):
        text=self.texts['10-K.txt']+' Prior spending increased by $3 billion.'
        out=self.output();out['claims'][1]['value']='$3 billion'
        for c in out['claims']:c['quote']=text
        self.assertFalse(check(out,{'10-K.txt':text}).ok)

    def test_reversed_endpoints_are_rejected(self):
        out=self.output();out['draft']='The projected range is {c2} to {c1}.'
        self.assertFalse(check(out,self.texts).ok)

    def test_actual_changes_are_not_treated_as_guidance_ranges(self):
        out=self.output(True);out['draft']='Spending changed from {c1} to {c2}.'
        self.assertTrue(check(out,self.texts).ok)

    def test_supported_between_and_dash_ranges_are_accepted(self):
        for source, draft in [
            ('Our outlook is between $18 billion and $22 billion.', 'Guidance is between {c1} and {c2}.'),
            ('We forecast $18 billion–$22 billion.', 'The projected range is {c1}–{c2}.')]:
            out=self.output();out['draft']=draft
            for claim in out['claims']:claim['quote']=source
            result=check(out,{'10-K.txt':source})
            self.assertTrue(result.ok,result.errors)

    def test_an_unrelated_guidance_sentence_does_not_change_actual_comparisons(self):
        out=self.output(True)
        out['draft']='Guidance is unavailable. Actual spending changed from {c1} to {c2}.'
        self.assertTrue(check(out,self.texts).ok)

    def test_inherited_claims_cannot_reassemble_an_unsupported_range(self):
        out={'claims':[{'id':'c1','from':'Research Analyst','claim':'c1'},
                       {'id':'c2','from':'Research Analyst','claim':'c2'}],
             'draft':'Guidance is {c1} to {c2}.'}
        origins={'Research Analyst':{'c1':'$18 billion [10-K.txt:L1]',
                                    'c2':'$3 billion [earnings_release_Ex99-1.txt:L1]'}}
        self.assertFalse(check(out,self.texts,origins=origins,reference_only=True).ok)

    def test_bad_range_enters_existing_repair_loop(self):
        calls=[]
        def ask(feedback):
            calls.append(feedback)
            return self.output(wrong=len(calls)==1)
        result,attempts=with_repairs(ask,self.texts,{})
        self.assertEqual(len(attempts),2)
        self.assertIn('guidance range',calls[1].lower())
        self.assertIn('$22 billion',result['draft'])
