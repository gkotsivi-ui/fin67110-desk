import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('insight_layout', Path(__file__).resolve().parents[1] / 'insight_layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class InsightLayoutTests(unittest.TestCase):
    def sections(self):
        sections = {part: 'Sourced report content.' for part in layout.PART_OWNERS}
        for part in layout.INSIGHT_PARTS.values():
            sections[part] += '\nInsight: Supported claim [10-K.txt:L1]'
        return sections

    def test_three_insights_across_five_parts_pass(self):
        self.assertEqual(layout.insight_failures(self.sections()), [])

    def test_old_five_insight_layout_fails_research_only(self):
        sections = self.sections()
        for part in ('Overview', 'Market Positioning and Growth Outlook'):
            sections[part] += '\nInsight: Extra claim'
        failures = layout.insight_failures(sections)
        self.assertEqual([f['role'] for f in failures], ['Research Analyst'])

    def test_missing_financial_insight_fails(self):
        sections = self.sections()
        sections['Valuation Insights'] = 'No insight.'
        self.assertEqual(layout.insight_failures(sections)[0]['role'], 'Financial Analyst')

    def test_misplaced_research_insight_fails(self):
        sections = self.sections()
        sections['Overview'], sections['Future Developments and Strategic Recommendations'] = sections['Future Developments and Strategic Recommendations'], sections['Overview']
        self.assertEqual(layout.insight_failures(sections)[0]['role'], 'Research Analyst')
