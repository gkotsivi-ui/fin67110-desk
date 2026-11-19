"""Conservative automatic parsing of annual statement rows in saved filing text."""
import re
from datetime import datetime
from pathlib import Path

HEADER=re.compile(r'^(?:(?:PRO FORMA|UNAUDITED|CONDENSED)\s+)*(?:CONSOLIDATED|COMBINED)(?:\s+AND\s+(?:CONSOLIDATED|COMBINED))?\s+STATEMENTS?\s+OF\s+(INCOME|OPERATIONS|CASH FLOWS)\s*$',re.I)
DATE=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'
LABELS={'after_tax_earnings':r'(?:NET INCOME|NET EARNINGS)(?: ATTRIBUTABLE TO (?!NONCONTROLLING)[^\n]+)?',
 'depreciation_and_amortization':r'Depreciation and amortization',
 'depreciation':r'Depreciation(?: expense)?',
 'capital_spending':r'(?:Additions to|Purchases of|Payments (?:for|to acquire)) property(?:,| and)? (?:plant(?:,| and)? )?(?:and )?equipment'}

def amounts(lines,start):
    values=[];negative=False
    for text in lines[start:]:
        text=text.strip()
        if text in {'$','',')'}:
            if text==')':negative=False
            continue
        if text=='(':negative=True;continue
        if not re.fullmatch(r'\(?-?\d[\d,]*(?:\.\d+)?\)?',text):break
        v=float(text.replace(',','').replace('(','-').replace(')',''))
        values.append(-abs(v) if negative else v)
    return values

def parse(path,run):
    text=path.read_text();lines=text.splitlines();found=[]
    headers=[i for i,line in enumerate(lines) if HEADER.fullmatch(line.strip())]
    for h in headers:
        end=next((i for i in range(h+1,len(lines)) if re.match(r'^(?:CONSOLIDATED|COMBINED)\s+(?:STATEMENTS|BALANCE SHEETS)|^NOTES TO (?:CONSOLIDATED|COMBINED)',lines[i],re.I)),len(lines))
        block=lines[h+1:end]
        metric_positions=[i for i,line in enumerate(block) if any(re.fullmatch(pattern,line.strip(),re.I) for pattern in LABELS.values())]
        if not metric_positions:continue
        intro=' '.join(block[:min(metric_positions)])
        if not re.search(r'(?:years?|(?:52|53)\s*weeks?)\s+ended',intro,re.I):continue
        dates=[]
        for match in re.finditer(DATE,intro,re.I):
            raw=re.sub(r'\s+',' ',match[0]);raw=re.sub(r'(\d),? (\d{4})$',r'\1, \2',raw)
            day=datetime.strptime(raw,'%B %d, %Y').date().isoformat()
            if day not in dates:dates.append(day)
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
            if path.parent.name=='Form10' and re.search(r'pro forma[^.\n]{0,100}(?:statements?|income|earnings)',path.read_text(),re.I):pro_forma_income_present=True
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
    if len(rows)!=years:return {},{'value':None,'kind':'not known','reason':f'{years} comparable fiscal years of earnings, depreciation/amortization and spending were not established','source':'not known','annual_inputs':rows}
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
        text=path.read_text()
        for match in pattern.finditer(text):
            raw=' '.join(match[1].split());raw=re.sub(r'(\d),? (\d{4})$',r'\1, \2',raw)
            day=datetime.strptime(raw,'%B %d, %Y').date().isoformat()
            if day>asof:continue
            value=float(match[2].replace(',',''))
            observations.append({'value':value,'unit':'shares','kind':'historical','as_of':day,'period':'As of '+day,
              'source':f"[{path.relative_to(run)}:L{text[:match.start()].count(chr(10))+1}] section Cover page; as of {day}; quote: "+' '.join(match[0].split()),'reason':None})
    if not observations:return {'value':None,'source':'not known','kind':'not known','reason':'An eligible actual shares-outstanding count was not established'}
    latest=max(x['as_of'] for x in observations);latest=[x for x in observations if x['as_of']==latest]
    if len({x['value'] for x in latest})!=1:return {'value':None,'source':'not known','kind':'not known','reason':'Conflicting shares-outstanding counts'}
    return latest[-1]

def net_cash(run):
    """Only explicit total debt, never an assumed zero or long-term-only proxy."""
    for path in [*Path(run).glob('10-Q*.txt'),*Path(run).glob('10-K*.txt')]:
        lines=path.read_text().splitlines()
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
