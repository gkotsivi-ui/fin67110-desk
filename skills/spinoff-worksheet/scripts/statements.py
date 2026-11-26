"""Conservative automatic parsing of annual statement rows in saved filing text."""
import json
import re
from datetime import date, datetime
from pathlib import Path


def exact(number):
    """A number as the worksheet prints it in a source or an equation: with every digit it has.

    Six significant digits when they state the number in full ("6.654e+09", as before 2026-11-25), all its digits
    when they do not ("1285647000"). The hook adds up the numbers an equation prints. Rounded to six digits, the
    amounts of a company that reports in thousands gave another sum than the printed one, and the worksheet part
    stopped after the agent team had finished; a resume met the same numbers."""
    short=f'{number:g}'
    return short if float(short)==number else f'{number:.15g}'

HEADER=re.compile(r'^(?:(?:PRO FORMA|UNAUDITED|CONDENSED)\s+)*(?:CONSOLIDATED|COMBINED)(?:\s+AND\s+(?:CONSOLIDATED|COMBINED))?\s+STATEMENTS?\s+OF\s+(INCOME|OPERATIONS|EARNINGS|CASH FLOWS)\s*$',re.I)
DATE=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'
# 2026-11-23, from real 10-Ks: Workday labels its earnings "Net income" but Dollar Tree "Net income (loss)"; Cisco's
# spending row is "Acquisition of property and equipment", Dell's "Capital expenditures and capitalized software
# development costs", NVIDIA's "Purchases related to property and equipment and intangible assets" (each company's own
# capital-spending line, the line its XBRL tags as payments for property or productive assets, checked year by year).
# HPE's "Investment in property, plant and equipment and software assets" also matches its XBRL, but the hook reads HPE's
# cash flow statement on to the next statement heading, through notes that print a pound sign, and refuses it as a
# foreign-currency statement; that row waits until the hook ends a statement where this parser does. Rows that add other items to depreciation
# ("Depreciation, amortization, and other", Cisco) are not read as depreciation and amortization.
LABELS={'after_tax_earnings':r'(?:CONSOLIDATED\s+)?(?:NET INCOME|NET EARNINGS)(?: \(LOSS\))?(?: ATTRIBUTABLE TO (?!NONCONTROLLING)[^\n]+)?',
 'depreciation_and_amortization':r'Depreciation and amortization',
 'depreciation':r'Depreciation(?: expense)?',
 'capital_spending':r'(?:(?:Additions to|Purchases of|Payments (?:for|to acquire)|Acquisitions? of) property(?:,| and)? (?:plant(?:,| and)? )?(?:and )?equipment'
                    r'|Capital expenditures(?: and capitalized software development costs)?|Purchases related to property and equipment and intangible assets)'}
MONTHS=['january','february','march','april','may','june','july','august','september','october','november','december']
# A column date's month as statements print it: in full, or abbreviated ("Jan 25, 2026", NVIDIA, 2026-11-23).
MONTH=r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?'
# Amounts in millions or thousands: "(In millions)", "(Amounts in millions)", and Analog Devices' bare "(thousands)".
MILLIONS=r'\bin millions\b|\(\s*millions\b'
THOUSANDS=r'\bin thousands\b|\(\s*thousands\b'
# 2026-11-20: Lowe's names its statement "of Earnings", pairs each amount with a "% Sales" figure and labels its
# spending "Capital expenditures"; Walmart prints "Fiscal Years Ended January 31," above columns of years and labels its
# earnings "Consolidated net income attributable to Walmart". hooks/worksheet_format.py reads statements the same way.

def month_day(month,day,year):
    return datetime(int(year),MONTHS.index(next(m for m in MONTHS if m.startswith(month.lower().rstrip('.')[:3])))+1,int(day)).date().isoformat()

def period_dates(intro):
    """The statement's column dates: one month and day followed by its columns of years ("Year Ended January 31, 2026
    2025 2024": Workday and Autodesk, 2026-11-23; or "December 31, 2025, 2024 and 2023"), full dates (months in full or
    abbreviated), or one month and day printed above columns of years (Walmart). hooks/worksheet_format.column_dates
    reads them the same way."""
    run=re.search(r'\b('+MONTH+r')\s+(\d{1,2}),?\s+(20\d{2}(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s+)20\d{2})+)(?![\d,.])',intro,re.I)
    if run:return list(dict.fromkeys(month_day(run[1],run[2],year) for year in re.findall(r'20\d{2}',run[3])))
    dates=[]
    for match in re.finditer(r'\b('+MONTH+r')\s+(\d{1,2}),?\s+(\d{4})\b',intro,re.I):
        day=month_day(match[1],match[2],match[3])
        if day not in dates:dates.append(day)
    if dates:return dates
    part=re.search(r'\b('+MONTH+r')\s+(\d{1,2}),?(?!\s*\d{4})',intro,re.I)
    if not part:return []
    for year in re.findall(r'(?<![\d,.$])(20\d{2})(?![\d,.])',intro[part.end():]):
        day=month_day(part[1],part[2],year)
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
        scale=1000000 if re.search(MILLIONS,intro,re.I) else 1000 if re.search(THOUSANDS,intro,re.I) else 1
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
                source=f'[{path.relative_to(run)}:L{h+i+2}] section {lines[h]}; year ended {day}; units {scale:g}; {block[i]} = {exact(reported)}'
                if key=='capital_spending' and reported<0:source+=f'; spending = -({exact(reported)}) = {exact(value)}'
                found.append((key,{'value':value,'unit':unit,'period':'Fiscal year ended '+day,'period_end':day,'kind':basis,'source':source,'reason':None}))
    return found

def saved_company_facts(run):
    """The company's XBRL facts, from SEC's company-facts answer as the run saved it. None when the folder holds none."""
    try:
        saved=json.loads((Path(run)/'sources.json').read_text(encoding='utf-8'))['responses']
        path=next(item['path'] for url,item in saved.items() if '/api/xbrl/companyfacts/' in url)
        return json.loads((Path(run)/path).read_bytes())['facts']
    except (OSError,ValueError,KeyError,TypeError,StopIteration):return None


def in_the_facts(facts,key,item):
    """Whether the company's XBRL facts hold this amount for a fiscal year that ends on the row's date.

    The reader finds a row by its label and reads the unit and the years from the lines above it; the hook reads the
    same lines the same way, so it cannot see a unit or a year that both misread. The company's own XBRL facts can:
    earnings must equal its net income (NetIncomeLoss or ProfitLoss) of that year, sign and all; depreciation and
    capital spending must equal some annual fact of that year, whatever its tag (companies tag these rows in several
    ways). A row in a custom tag, which SEC's answer leaves out, is not confirmed and is left out."""
    for tag,entry in facts.get('us-gaap',{}).items():
        if key=='after_tax_earnings' and tag not in ('NetIncomeLoss','ProfitLoss'):continue
        for row in entry.get('units',{}).get('USD',[]):
            try:
                if row['end']!=item['period_end'] or not 350<=(date.fromisoformat(row['end'])-date.fromisoformat(row['start'])).days<=380:continue
            except (KeyError,ValueError,TypeError):continue
            if row.get('val')==item['value'] or (key!='after_tax_earnings' and abs(row.get('val',0))==abs(item['value'])):return True
    return False


def collect(run,years,include_amortization):
    run=Path(run);observations={};missing=[];pro_forma_income_present=False
    facts=saved_company_facts(run);unconfirmed=False
    for path in [*run.glob('10-K*.txt'),*run.glob('Form10/*.txt')]:
        try:
            if path.parent.name=='Form10' and re.search(r'pro forma[^.\n]{0,100}(?:statements?|income|earnings)',path.read_text(encoding='utf-8'),re.I):pro_forma_income_present=True
            for key,item in parse(path,run):
                # Since 2026-11-25: a 10-K's row is used only when the company's saved XBRL facts hold it (in_the_facts).
                if facts is not None and path.parent.name!='Form10' and item['kind']=='historical' and not in_the_facts(facts,key,item):unconfirmed=True;continue
                observations.setdefault((key,item['period_end']),[]).append(item)
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
                     'inputs':triplet,'source':f'computed: {exact(a)} + {exact(b)} - {exact(c)} = {exact(a+b-c)}; '+'; '.join(x['kind']+': '+x['source'] for x in triplet)})
    # The reason is printed in the worksheet, where the hook refuses any digit it cannot trace to a source
    # (2026-11-20: "3 comparable fiscal years" stopped a run). The count is written as a word.
    count={1:'one',2:'two',3:'three',4:'four',5:'five',6:'six',7:'seven',8:'eight',9:'nine',10:'ten'}.get(years,'the required number of')
    if len(rows)!=years:
        reason=f'{count} comparable fiscal years of earnings, depreciation/amortization and spending were not established'
        if unconfirmed:reason+='; a statement row was read that the company XBRL facts do not hold for its year, and it was left out'
        return {},{'value':None,'kind':'not known','reason':reason,'source':'not known','annual_inputs':rows}
    gaps=[(datetime.fromisoformat(days[i])-datetime.fromisoformat(days[i+1])).days for i in range(len(days)-1)]
    if any(not 350<=gap<=380 for gap in gaps):return {},{'value':None,'kind':'not known','reason':'Fiscal years are not consecutive','source':'not known','annual_inputs':rows}
    latest={key:selected[(key,days[0])] for key in ['after_tax_earnings',dep,'capital_spending']}
    value=sum(x['value'] for x in rows)/years
    basis='mixed historical/pro forma, disclosed by year' if len({x['kind'] for x in rows})>1 else rows[0]['kind']
    ocf={'value':value,'unit':'USD','kind':basis,'period':f'{years}-fiscal-year average','annual_inputs':rows,'reason':None,
         'source':f"computed: ({' + '.join(str(x['value']) for x in rows)}) / {years} = {value:g}; "+'; '.join(x['source'] for x in rows)}
    return latest,ocf


COUNT=r'\d{1,3}(?:,\d{3})+'

def cover_count(lines,n,label,several):
    """Two more cover-page layouts (2026-11-23), each read from real filings. (a) The count alone on the line after a
    dated line that names it: "The number of shares of HP Inc. common stock outstanding as of December 1, 2025 was"
    (HP Inc., HPE, NVIDIA), "Number of shares of the registrant's common stock outstanding as of August 27, 2026:"
    (Cisco), "Number of Ordinary Shares outstanding on June 12, 2026:" (Medtronic), or "As of August 25, 2026, there
    were" / "the registrant had" with "shares of ... common stock ... outstanding" on the line after the count (Dollar
    Tree, Agilent, Autodesk). (b) The registrant's total on the dated line itself: "As of March 9, 2026, there were
    645,748,451 shares of the registrant's common stock outstanding, consisting of" (Dell, which then lists its classes).
    A cover page that names a second class of common stock gives a count only through (b): one class's count is not the
    company's shares, and Zoom and Workday state no total. Returns (day, count) or (None, None).
    hooks/worksheet_format.py checks both layouts against the saved text."""
    dates=re.findall(DATE,label,re.I)
    if len(dates)!=1 or ';' in label or re.search(r'aggregate market value|approximately|non-?affiliates',label,re.I):return None,None
    raw=re.sub(r'(\d),? (\d{4})$',r'\1, \2',' '.join(dates[0].split()));day=datetime.strptime(raw,'%B %d, %Y').date().isoformat()
    total=re.match(r"As of "+DATE+r",? there were ("+COUNT+r") shares of the registrant[’']s common stock outstanding\b",label,re.I)
    if total:return day,total[1]
    if several or not re.search(r"(?:\boutstanding\b.*(?:\bwas|:)|\bthere were|\bregistrant had(?: outstanding)?)$",label,re.I):return None,None
    after=next((k for k in range(n+1,min(n+3,len(lines))) if lines[k].strip()),None)
    if after is None or not re.fullmatch(COUNT,lines[after].strip()):return None,None
    if not re.search(r'\boutstanding\b',label,re.I):
        named=' '.join(lines[after+1].split()) if after+1<len(lines) else ''
        if not all(re.search(p,named,re.I) for p in (r'\bshares\b',r'common stock|ordinary shares',r'\boutstanding\b')):return None,None
    return day,lines[after].strip()

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
        several=re.search(r'Class [BC] (?:common|ordinary)','\n'.join(lines[:400]),re.I)
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
            if not day and n<400:day,count=cover_count(lines,n,label,several)
            if day and count and day<=asof:
                observations.append({'value':float(count.replace(',','')),'unit':'shares','kind':'historical','as_of':day,'period':'As of '+day,
                  'source':f"[{path.relative_to(run)}:L{n+1}] section Cover page; as of {day}; quote: {label}; shares: {count}",'reason':None})
    if not observations:return {'value':None,'source':'not known','kind':'not known','reason':'An eligible actual shares-outstanding count was not established'}
    latest=max(x['as_of'] for x in observations);latest=[x for x in observations if x['as_of']==latest]
    if len({x['value'] for x in latest})!=1:return {'value':None,'source':'not known','kind':'not known','reason':'Conflicting shares-outstanding counts'}
    if replaced_by_a_later_cover(saved_company_facts(run),latest[-1]):
        return {'value':None,'source':'not known','kind':'not known','reason':'A cover-page share count was read, but the company XBRL cover facts hold a later and different count, so the count read is out of date'}
    return latest[-1]


def replaced_by_a_later_cover(facts,count):
    """Whether the company's XBRL cover facts hold, for the count's own day or a later one, another count.

    Every 10-K and 10-Q cover's count is in the facts with its date (dei:EntityCommonStockSharesOutstanding). When
    the reader cannot read the newest cover, it falls back to an older filing's: on 2026-11-25, for one company of
    25, that was a count from before a four-for-one split. On the count's own day any other number is a conflict.
    On a later day only a number more than five percent away is: shares move slowly, and a count one quarter old is
    still the company's. With no facts, or only older ones, the count stands as read."""
    try:rows=facts['dei']['EntityCommonStockSharesOutstanding']['units']['shares']
    except (KeyError,TypeError):return False
    rows=[row for row in rows if isinstance(row,dict) and isinstance(row.get('val'),(int,float)) and str(row.get('end',''))>=count['as_of']]
    if not rows:return False
    newest=max(str(row['end']) for row in rows);values=[row['val'] for row in rows if str(row['end'])==newest]
    if count['value'] in values:return False
    return newest==count['as_of'] or all(abs(value-count['value'])>0.05*abs(value) for value in values)

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
                    'source':f"computed: {exact(cash)} - {exact(debt)}; [{path.relative_to(run)}:L{h+found['cash'][1]+2}] Cash and cash equivalents; [{path.relative_to(run)}:L{h+found['debt'][1]+2}] Total debt; {dates[0][0]}",'reason':None}
    return {'value':None,'kind':'not known','source':'not known','reason':'Matching cash and explicit total-debt balance-sheet lines were not established'}
