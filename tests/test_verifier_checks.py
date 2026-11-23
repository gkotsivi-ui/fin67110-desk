"""Offline regression checks for source validation, without provider calls."""
import ast
import re
import unittest
from pathlib import Path
from typing import Any


def load_checks():
    source = Path(__file__).resolve().parents[1] / 'equity_research_agent_team.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'code_checks')
    scope = {'ast': ast, 're': re, 'Any': Any}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), 'exec'), scope)
    return scope['code_checks']


class VerifierChecks(unittest.TestCase):
    def test_section_labels_are_identifiers_in_legacy_checks(self):
        self.assertEqual(load_checks()(None,'Filings\nRuntime\n== 1. CASH GENERATION ==\n## 2. PROFITABILITY\n3. FUNDING\n(1) Review earnings.\nRecommendations: (1) Review earnings. (2) Review debt.',{},{}),[])
        self.assertTrue(load_checks()(None,'Filings\nRuntime\n== 1. CASH GENERATION ==\nIncome $999.',{},{}))
    def check_quote(self, amount):
        return load_checks()(None, f'Filings read\nRun time\nEPS "Annual diluted EPS was ${amount}." [release.txt:L1]', {}, {'release.txt': 'Annual diluted EPS was $20.76.'})

    def test_tampered_quote_fails(self):
        checks = self.check_quote('21.76')
        self.assertEqual(checks[0]['status'], 'wrong')
        self.assertIn('20.76', checks[0]['correction'])

    def test_clean_quote_requires_semantic_review(self):
        self.assertEqual(self.check_quote('20.76')[0]['status'], 'unsupported')

    def test_line_existence_is_not_support(self):
        checks = load_checks()(None, 'Filings\nRuntime\nEPS was $21.76 [release.txt:L1]', {}, {'release.txt': 'Annual diluted EPS was $20.76.'})
        self.assertEqual(checks[0]['status'], 'unsupported')

    def test_annual_eps_correction_uses_10k(self):
        report = 'Filings\nRuntime\n"Net income for the fiscal year was $9 billion, $21.76 per diluted share." [release.txt:L1]'
        facts = {'facts': {'diluted_eps': {'value': 20.76, 'period_end': '2026-08-30', 'filing': 'example-accession'}}}
        texts = {'release.txt': 'Net income for the fiscal year was $9 billion, $20.76 per diluted share.', '10-K.txt': 'Diluted\n$\n20.76'}
        checks = load_checks()(None, report, facts, texts)
        self.assertEqual(checks[0]['status'], 'wrong')
        self.assertIn('10-K.txt:L3', checks[0]['source'])
        self.assertIn('example-accession', checks[0]['source'])

    def test_valid_pe_arithmetic(self):
        checks = load_checks()(None, 'Filings\nRuntime\nP/E 47.79046242774566 [computed using formula 992.13 / 20.76 based on user-supplied price and XBRL tag EarningsPerShareDiluted]', {}, {})
        self.assertTrue(any(c['status'] == 'correct' and c['claim'].startswith('Arithmetic:') for c in checks))


if __name__ == '__main__':
    unittest.main()
