"""Validate one Insight line per analyst across the five report parts."""
INSIGHT_PARTS = {
    'Research Analyst': 'Future Developments and Strategic Recommendations',
    'Financial Analyst': 'Valuation Insights',
    'Investment Advisor': 'Investment Recommendation',
}
PART_OWNERS = {
    'Overview': 'Research Analyst',
    'Market Positioning and Growth Outlook': 'Research Analyst',
    'Valuation Insights': 'Financial Analyst',
    'Future Developments and Strategic Recommendations': 'Research Analyst',
    'Investment Recommendation': 'Investment Advisor',
}


def insight_failures(sections):
    failures = []
    for role, final_part in INSIGHT_PARTS.items():
        parts = [part for part, owner in PART_OWNERS.items() if owner == role]
        insights = [(part, line) for part in parts
                    for line in str(sections.get(part, '')).splitlines()
                    if line.strip().startswith('Insight:')]
        final_lines = str(sections.get(final_part, '')).strip().splitlines()
        if len(insights) != 1 or insights[0][0] != final_part or not final_lines or not final_lines[-1].startswith('Insight:'):
            failures.append({'role': role, 'part': final_part, 'feedback':
                f'Provide exactly one Insight: line across all parts owned by {role}. '
                f'Place it as the last line of {final_part}; remove Insight lines from other owned parts. '
                f'Found {len(insights)} Insight lines.'})
    return failures
