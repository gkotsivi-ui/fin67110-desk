"""Conservative automatic parsing of annual statement rows in saved filing text."""
import re
from datetime import datetime
from pathlib import Path

HEADER=re.compile(r'^(?:(?:PRO FORMA|UNAUDITED|CONDENSED)\s+)*(?:CONSOLIDATED|COMBINED)(?:\s+AND\s+(?:CONSOLIDATED|COMBINED))?\s+STATEMENTS?\s+OF\s+(INCOME|OPERATIONS|EARNINGS|CASH FLOWS)\s*$',re.I)
DATE=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'
LABELS={'after_tax_earnings':r'(?:CONSOLIDATED\s+)?(?:NET INCOME|NET EARNINGS)(?: ATTRIBUTABLE TO (?!NONCONTROLLING)[^\n]+)?',
 'depreciation_and_amortization':r'Depreciation and amortization',
 'depreciation':r'Depreciation(?: expense)?',
 'capital_spending':r'(?:(?:Additions to|Purchases of|Payments (?:for|to acquire)) property(?:,| and)? (?:plant(?:,| and)? )?(?:and )?equipment|Capital expenditures)'}
MONTHS=['january','february','march','april','may','june','july','august','september','october','november','december']
# 2026-11-20: Lowe's names its statement "of Earnings", pairs each amount with a "% Sales" figure and labels its
# spending "Capital expenditures"; Walmart prints "Fiscal Years Ended January 31," above columns of years and labels its
# earnings "Consolidated net income attributable to Walmart". hooks/worksheet_format.py reads statements the same way.

def period_dates(intro):
    """The statement's column dates: full dates, or one month and day printed above columns of years."""
    dates=[]
    for match in re.finditer(DATE,intro,re.I):
        raw=re.sub(r'\s+',' ',match[0]);raw=re.sub(r'(\d),? (\d{4})$',r'\1, \2',raw)
        day=datetime.strptime(raw,'%B %d, %Y').date().isoformat()
        if day not in dates:dates.append(day)
    if dates:return dates
    part=re.search(r'\b('+'|'.join(MONTHS)+r')\s+(\d{1,2}),?(?!\s*\d{4})',intro,re.I)
    if not part:return []
    for year in re.findall(r'(?<![\d,.$])(20\d{2})(?![\d,.])',intro[part.end():]):
        day=datetime(int(year),MONTHS.index(part[1].lower())+1,int(part[2])).date().isoformat()
        if day not in dates:dates.append(day)
    return dates

def amounts(lines,start):
    values=[];negative=False
    for text in lines[start:]:
        text=text.strip()
        if text in {'$','',')'}:
            if text==')':negative=False
            continue
        if text=='(':negative=True;continue
        if text in {'%','%)',')%'}:
            if values:values.pop()  # the number before it was a percentage of sales
            continue
        if not re.fullmatch(r'\(?-?\d[\d,]*(?:\.\d+)?\)?',text):break
        v=float(text.replace(',','').replace('(','-').replace(')',''))
        values.append(-abs(v) if negative else v)
    return values

def parse(path,run):
    text=path.read_text(encoding='utf-8');lines=text.splitlines();found=[]
    headers=[i for i,line in enumerate(lines) if HEADER.fullmatch(line.strip())]
    for h in headers:
        end=next((i for i in range(h+1,len(lines)) if re.match(r'^(?:CONSOLIDATED|COMBINED)\s+(?:STATEMENTS|BALANCE SHEETS)|^NOTES TO (?:CONSOLIDATED|COMBINED)',lines[i],re.I)),len(lines))
        block=lines[h+1:end]
        metric_positions=[i for i,line in enumerate(block) if any(re.fullmatch(pattern,line.strip(),re.I) for pattern in LABELS.values())]
        if not metric_positions:continue
        intro=' '.join(block[:min(metric_positions)])
        if not re.search(r'(?:years?|(?:52|53)\s*weeks?)\s+ended',intro,re.I):continue
        dates=period_dates(intro)
        if not dates:continue
        scale=1000000 if re.search(r'in millions',intro,re.I) else 1000 if re.search(r'in thousands',intro,re.I) else 1
        # Dollar-bearing US team statements are USD; explicit foreign units
        # cannot enter a dollar valuation without a sourced conversion.
        foreign=re.search(r'\b(?:CAD|AUD|HKD|EUR|GBP)\b|C\$|A\$|HK\$|€|£',' '.join(block[:200]))
        unit='USD' if not foreign and ('$' in '\n'.join(block) or re.search('U.S. dollars|USD',intro,re.I)) else 'not known'
        basis='pro forma' if re.search('pro forma',lines[h],re.I) else 'historical'
        for key,pattern in LABELS.items():
            cash=HEADER.fullmatch(lines[h].strip())[1].upper()=='CASH FLOWS'
            if (key=='after_tax_earnings' and cash) or (key!='after_tax_earnings' and not cash):continue
            positions=[i for i,line in enumerate(block) if re.fullmatch(pattern,line.strip(),re.I)]
            if key=='after_tax_earnings':
                parent=[i for i in positions if 'attributable to' in block[i].lower()]
                if parent:positions=parent
            if len(positions)!=1:continue
            i=positions[0];values=amounts(block,i+1)
            if len(values)==2*len(dates) and re.search(r'%\s*(?:of\s+)?(?:net\s+)?sales',intro,re.I):values=values[::2]  # amount, % sales
            if len(values)!=len(dates):continue
            for day,val in zip(dates,values):
                reported=val*scale;value=abs(reported) if key=='capital_spending' else reported
                source=f'[{path.relative_to(run)}:L{h+i+2}] section {lines[h]}; year ended {day}; units {scale:g}; {block[i]} = {reported:g}'
                if key=='capital_spending' and reported<0:source+=f'; spending = -({reported:g}) = {value:g}'
                found.append((key,{'value':value,'unit':unit,'period':'Fiscal year ended '+day,'period_end':day,'kind':basis,'source':source,'reason':None}))
    return found

def collect(run,years,include_amortization):
    run=Path(run);observations={};missing=[];pro_forma_income_present=False
    for path in [*run.glob('10-K*.txt'),*run.glob('Form10/*.txt')]:
        try:
            if path.parent.name=='Form10' and re.search(r'pro forma[^.\n]{0,100}(?:statements?|income|earnings)',path.read_text(encoding='utf-8'),re.I):pro_forma_income_present=True
            for key,item in parse(path,run):observations.setdefault((key,item['period_end']),[]).append(item)
        except (ValueError,OSError):continue
    selected={}
    for key,items in observations.items():
        pro=[x for x in items if x['kind']=='pro forma'];items=pro or items
        if len({(x['value'],x['unit']) for x in items})==1:selected[key]=items[-1]
    if pro_forma_income_present and not any(key=='after_tax_earnings' and ob['kind']=='pro forma' for (key,_),ob in selected.items()):
        return {},{'value':None,'kind':'not known','reason':'Registration contains pro-forma income statements, but their columns were not established; historical figures were not silently substituted','source':'not known','annual_inputs':[]}
    dep='depreciation_and_amortization' if include_amortization else 'depreciation'
    days=sorted({day for key,day in selected if key=='after_tax_earnings'},reverse=True)[:years]
    rows=[]
    for day in days:
        triplet=[selected.get((key,day)) for key in ['after_tax_earnings',dep,'capital_spending']]
        if any(x is None for x in triplet) or any(x['unit']!='USD' for x in triplet):continue
        a,b,c=[x['value'] for x in triplet]
        rows.append({'value':a+b-c,'unit':'USD','period':'Fiscal year ended '+day,'kind':triplet[0]['kind'] if len({x['kind'] for x in triplet})==1 else 'mixed basis, explicitly disclosed by input',
                     'inputs':triplet,'source':f'computed: {a:g} + {b:g} - {c:g} = {a+b-c:g}; '+'; '.join(x['kind']+': '+x['source'] for x in triplet)})
    # The reason is printed in the worksheet, where the hook refuses any digit it cannot trace to a source
    # (2026-11-20: "3 comparable fiscal years" stopped a run). The count is written as a word.
    count={1:'one',2:'two',3:'three',4:'four',5:'five',6:'six',7:'seven',8:'eight',9:'nine',10:'ten'}.get(years,'the required number of')
    if len(rows)!=years:return {},{'value':None,'kind':'not known','reason':f'{count} comparable fiscal years of earnings, depreciation/amortization and spending were not established','source':'not known','annual_inputs':rows}
    gaps=[(datetime.fromisoformat(days[i])-datetime.fromisoformat(days[i+1])).days for i in range(len(days)-1)]
    if any(not 350<=gap<=380 for gap in gaps):return {},{'value':None,'kind':'not known','reason':'Fiscal years are not consecutive','source':'not known','annual_inputs':rows}
    latest={key:selected[(key,days[0])] for key in ['after_tax_earnings',dep,'capital_spending']}
    value=sum(x['value'] for x in rows)/years
    basis='mixed historical/pro forma, disclosed by year' if len({x['kind'] for x in rows})>1 else rows[0]['kind']
    ocf={'value':value,'unit':'USD','kind':basis,'period':f'{years}-fiscal-year average','annual_inputs':rows,'reason':None,
         'source':f"computed: ({' + '.join(str(x['value']) for x in rows)}) / {years} = {value:g}; "+'; '.join(x['source'] for x in rows)}
    return latest,ocf


def shares_outstanding(run,asof):
    observations=[]
    pattern=re.compile(r"(?:The )?number of shares outstanding of the registrant[’']s common stock[^\n]{0,60}?as of ("+DATE+r"),?\s*was\s*([\d,]+)",re.I)
    for path in [*Path(run).glob('10-K*.txt'),*Path(run).glob('10-Q*.txt')]:
        text=path.read_text(encoding='utf-8')
        for match in pattern.finditer(text):
            raw=' '.join(match[1].split());raw=re.sub(r'(\d),? (\d{4})$',r'\1, \2',raw)
            day=datetime.strptime(raw,'%B %d, %Y').date().isoformat()
            if day>asof:continue
            value=float(match[2].replace(',',''))
            observations.append({'value':value,'unit':'shares','kind':'historical','as_of':day,'period':'As of '+day,
              'source':f"[{path.relative_to(run)}:L{text[:match.start()].count(chr(10))+1}] section Cover page; as of {day}; quote: "+' '.join(match[0].split()),'reason':None})
        # Two more cover-page layouts (2026-11-20): Walmart's "The registrant had / N / shares of common stock outstanding
        # as of March 11, 2026." and Lowe's "OUTSTANDING AT 3/19/2026 / Common Stock, $0.50 par value / N". The source
        # quotes the dated line and names the count; hooks/worksheet_format.py checks both against the saved text.
        lines=text.splitlines()
        for n,line in enumerate(lines):
            label=' '.join(line.split());day=None;count=None
            dated=re.match(r"shares of (?:the registrant[’']s )?(?:Class A )?common stock[^\n]{0,60}?outstanding (?:as of|at) ("+DATE+r")\.?$",label,re.I)
            if dated and n>0 and re.fullmatch(r'\d{1,3}(?:,\d{3})+',lines[n-1].strip()):
                raw=re.sub(r'(\d),? (\d{4})$',r'\1, \2',' '.join(dated[1].split()))
                day=datetime.strptime(raw,'%B %d, %Y').date().isoformat();count=lines[n-1].strip()
            heading=re.fullmatch(r'OUTSTANDING AT (\d{1,2})/(\d{1,2})/(\d{4})',label,re.I)
            if heading:
                found=next((lines[k].strip() for k in range(n+1,min(n+4,len(lines))) if re.fullmatch(r'\d{1,3}(?:,\d{3})+',lines[k].strip())),None)
                if found:day=datetime(int(heading[3]),int(heading[1]),int(heading[2])).date().isoformat();count=found
            if day and count and day<=asof:
                observations.append({'value':float(count.replace(',','')),'unit':'shares','kind':'historical','as_of':day,'period':'As of '+day,
                  'source':f"[{path.relative_to(run)}:L{n+1}] section Cover page; as of {day}; quote: {label}; shares: {count}",'reason':None})
    if not observations:return {'value':None,'source':'not known','kind':'not known','reason':'An eligible actual shares-outstanding count was not established'}
    latest=max(x['as_of'] for x in observations);latest=[x for x in observations if x['as_of']==latest]
    if len({x['value'] for x in latest})!=1:return {'value':None,'source':'not known','kind':'not known','reason':'Conflicting shares-outstanding counts'}
    return latest[-1]

def net_cash(run):
    """Only explicit total debt, never an assumed zero or long-term-only proxy."""
    for path in [*Path(run).glob('10-Q*.txt'),*Path(run).glob('10-K*.txt')]:
        lines=path.read_text(encoding='utf-8').splitlines()
        headers=[i for i,line in enumerate(lines) if re.fullmatch(r'(?:CONDENSED )?(?:CONSOLIDATED|COMBINED) BALANCE SHEETS',line.strip(),re.I)]
        for h in headers:
            end=next((i for i in range(h+1,len(lines)) if HEADER.fullmatch(lines[i].strip())),len(lines))
            block=lines[h+1:end];found={}
            for key,label in [('cash',r'Cash and cash equivalents'),('debt',r'Total debt')]:
                positions=[i for i,x in enumerate(block) if re.fullmatch(label,x.strip(),re.I)]
                if len(positions)==1:
                    i=positions[0];vals=amounts(block,i+1)
                    if vals:found[key]=(vals[0],i)
            if set(found)!={'cash','debt'}:continue
            intro=' '.join(block[:min(v[1] for v in found.values())])
            dates=list(re.finditer(DATE,intro,re.I))
            if not dates:continue
            scale=1000000 if 'in millions' in intro.lower() else 1000 if 'in thousands' in intro.lower() else 1
            if not ('$' in '\n'.join(block) or 'USD' in intro):continue
            cash,debt=found['cash'][0]*scale,found['debt'][0]*scale
            return {'value':cash-debt,'unit':'USD','kind':'historical','period':'Balance sheet '+dates[0][0],
                    'source':f"computed: {cash:g} - {debt:g}; [{path.relative_to(run)}:L{h+found['cash'][1]+2}] Cash and cash equivalents; [{path.relative_to(run)}:L{h+found['debt'][1]+2}] Total debt; {dates[0][0]}",'reason':None}
    return {'value':None,'kind':'not known','source':'not known','reason':'Matching cash and explicit total-debt balance-sheet lines were not established'}
