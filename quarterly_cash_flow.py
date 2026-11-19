"""Derive one quarter of capital spending from sourced cumulative XBRL facts."""
from datetime import date,timedelta
import math


def quarterly_capital_spending(company_facts, accession, tags):
    result={'value':None,'unit':'USD','formula':None,'inputs':[],'sources':[],
            'reason':'Comparable cumulative capital-spending facts are not available.'}
    ranges={'Q1':(65,110),'Q2':(145,210),'Q3':(225,300),'FY':(350,380)}
    previous={'Q2':'Q1','Q3':'Q2','FY':'Q3'}
    def valid(row):
        try:
            days=(date.fromisoformat(row['end'])-date.fromisoformat(row['start'])).days
            date.fromisoformat(row['filed'])
            return (row.get('form') in {'10-Q','10-Q/A','10-K','10-K/A'} and row.get('accn')
                and not row.get('dimensions') and not row.get('segment')
                and isinstance(row.get('val'),(int,float)) and not isinstance(row['val'],bool)
                and math.isfinite(row['val']) and row.get('fp') in ranges
                and ranges[row['fp']][0]<=days<=ranges[row['fp']][1])
        except (KeyError,TypeError,ValueError):return False
    def unique(rows):
        if not rows:return None
        latest=max(row['filed'] for row in rows)
        rows=[row for row in rows if row['filed']==latest]
        return rows[0] if len({row['val'] for row in rows})==1 else None
    def source(row,tag):
        item={'value':row['val'],'tag':tag,'unit':'USD','period_start':row['start'],
              'period_end':row['end'],'filing':row['accn'],'filed':row['filed']}
        citation=f"XBRL tag {tag}, period start {row['start']}, period end {row['end']}, filing {row['accn']}, filed {row['filed']}, unit USD"
        return item,citation
    gaap=company_facts.get('facts',{}).get('us-gaap',{})
    for tag in tags:
        rows=[row for row in gaap.get(tag,{}).get('units',{}).get('USD',[]) if valid(row)]
        current_rows=[row for row in rows if row['accn']==accession]
        if not current_rows:continue
        end=max(row['end'] for row in current_rows)
        current=unique([row for row in current_rows if row['end']==end])
        if not current:
            result['reason']='Conflicting current cumulative facts.';return result
        item,citation=source(current,tag)
        result.update(inputs=[item],sources=[citation],period_end=end,tag=tag)
        if current['fp']=='Q1':
            result.update(value=current['val'],formula=str(current['val']),period_start=current['start'],reason=None,
                          method='Q1 cumulative amount is the first quarter amount')
            return result
        prior=unique([row for row in rows if row['fp']==previous[current['fp']]
            and row['accn']!=accession and row['start']==current['start']
            and row['filed']<=current['filed']
            and 65<=(date.fromisoformat(end)-date.fromisoformat(row['end'])).days<=110])
        if not prior:
            result['reason']='The preceding quarter cumulative amount is missing, conflicting, or incompatible; no zero substitute is used.'
            return result
        prior_item,prior_citation=source(prior,tag)
        result.update(value=current['val']-prior['val'],formula=f"{current['val']} - {prior['val']}",
                      inputs=[item,prior_item],sources=[citation,prior_citation],reason=None,
                      period_start=(date.fromisoformat(prior['end'])+timedelta(days=1)).isoformat(),
                      method='computed: current fiscal-year-to-date amount minus preceding fiscal-year-to-date amount from a different filing')
        return result
    return result
