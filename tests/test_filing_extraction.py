import ast
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any


def helpers():
    source = Path(__file__).resolve().parents[1] / 'equity_research_agent_team.py'
    tree = ast.parse(source.read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('numbered_section', 'missing_fact_filing_lines')]
    scope = {'Path': Path, 'Any': Any, 're': re}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])), str(source), 'exec'), scope)
    return scope


class FilingExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / '10-K.txt'
        self.functions = helpers()

    def test_attached_dashes_and_original_line_numbers(self):
        for dash in ('—', '–', '-', '.'):
            self.path.write_text(f'Item\u00a01{dash}Business\nBusiness text.\nItem 2. Properties\nItem 7{dash}MD&A\nDiscussion text.\nItem 8. Statements')
            business = self.functions['numbered_section'](self.path, 1, 2)
            mda = self.functions['numbered_section'](self.path, 7, 8)
            self.assertIn('10-K.txt:L2: Business text.', business)
            self.assertNotIn('Item 2', business)
            self.assertIn('10-K.txt:L5: Discussion text.', mda)

    def test_body_selected_over_contents_and_7a_kept(self):
        self.path.write_text('Item 7. MD&A\n24\nItem 8. Statements\nItem 7—MD&A\nFull discussion with substantial detail.\nItem 7A—Market risk\nRisk detail.\nItem 8—Statements')
        result = self.functions['numbered_section'](self.path, 7, 8)
        self.assertIn('10-K.txt:L4:', result)
        self.assertIn('Risk detail.', result)
        self.assertNotIn('L2:', result)

    def test_null_xbrl_gets_scoped_filing_evidence(self):
        self.path.write_text('Bank Credit Facilities\nThere were no short-term borrowings outstanding under bank credit facilities at year end.\nOther information.')
        result = self.functions['missing_fact_filing_lines'](self.path, {'short_term_borrowings': {'value': None}})
        self.assertIn('short_term_borrowings', result['missing_structured_metrics'])
        self.assertIn('10-K.txt:L2:', result['filing_lines'])
        self.assertIn('bank credit facilities', result['filing_lines'])
        self.assertNotIn('value', result)


if __name__ == '__main__':
    unittest.main()
