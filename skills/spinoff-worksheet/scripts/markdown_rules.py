"""Read the author's Markdown worksheet choices; no assumed financial rates."""
import re
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

def load(text,now=None):
    for line in text.splitlines():
        if re.fullmatch(r'\s*(?:[-*]\s*)?(?:[^:\n]+:\s*)?(?:FILL|\[FILL\])\s*',line,re.I):
            raise ValueError('Worksheet has an unfilled FILL field: '+line.strip())
    def get(pattern):
        m=re.search(pattern,text,re.I|re.M)
        if not m:raise ValueError('Worksheet choice not found: '+pattern)
        return float(m[1].replace(',',''))
    low=get(r'Low case:\s*owner cash flow\s*÷\s*([\d.]+)%')/100
    mid=get(r'Mid case:\s*owner cash flow\s*÷\s*([\d.]+)%')/100
    years=int(get(r'average of the last\s+(\d+)\s+fiscal years'))
    portfolio=get(r'Client portfolio:\s*\$([\d,]+(?:\.\d+)?)')
    positions=get(r'Purchase size:[^\n]*?÷\s*(\d+)\s+positions')
    stated=get(r'Purchase size:[^\n]*?=\s*\$([\d,]+(?:\.\d+)?)')
    observations=int(get(r'median daily dollar volume over the last\s*(\d+)\s*trading days'))
    participation=get(r'purchase size\s*≤\s*([\d.]+)%')/100
    days=int(get(r'completed within\s*(\d+)\s*trading days'))
    if positions<=0 or abs(portfolio/positions-stated)>.005:raise ValueError('Purchase-size arithmetic disagrees with the worksheet')
    if not 0<low<1 or not 0<mid<1 or years<1 or observations<1 or not 0<participation<=1 or days<1:raise ValueError('Worksheet rates or counts are invalid')
    required=['depreciation and amortization','Negative owner cash flow','Low case = net cash','Price at or below the low case','No conviction:']
    if any(phrase.lower() not in text.lower() for phrase in required):raise ValueError('Unsupported Markdown worksheet method; supply explicit JSON for a different method')
    now=now or datetime.now(ZoneInfo('America/New_York'))
    end=now.date().isoformat();start=(now.date()-timedelta(days=365)).isoformat()
    return {'rules_format':'author_markdown','rules_text':text,'owner_cash_flow_years':years,'include_amortization':True,
      'price_mode':'worksheet_date','price_currency':'USD','auto_statement_facts':True,
      'liquidity':{'start':start,'end':end,'purchase_size':portfolio/positions,'currency':'USD','observations':observations,
                   'participation_rate':participation,'max_trading_days':days},'facts':{},
      'valuation':{case:{'formula':'owner_cash_flow / discount_rate / shares_outstanding','rates':{'discount_rate':rate}} for case,rate in [('low',low),('mid',mid)]},
      'conviction':{'mode':'worksheet_evidence'},'negative_cash_flow_method':'net_cash',
      'assumption_sources':{'rates':'Value range','average':'Owner cash flow input','purchase':'Client purchase size','conviction':'Conviction rule'}}
