"""Conservative factor observations. No HTTP, prices, estimates, or issuer lists."""
import re
from datetime import datetime
from bs4 import BeautifulSoup

DATE = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}'


def iso_date(text):
    for fmt in ('%B %d, %Y','%B %d %Y','%Y-%m-%d'):
        try:return datetime.strptime(text,fmt).date().isoformat()
        except ValueError:pass
    return None


def number(text):
    text=text.strip()
    if not re.fullmatch(r'\$?\s*[\d,]+(?:\.\d+)?\s*%?',text):return None
    return float(text.replace('$','').replace(',','').replace('%','').strip())


def proof(d,section,quote,value,**extra):
    return {'value':value,'filing':d.url,'accession':d.filing.accession,'form':d.filing.form,
            'filed':d.filing.filed,'section':section,'quote':quote,**extra}


def unique_latest(items):
    if not items:return None
    day=max(x['filed'] for x in items)
    latest=[x for x in items if x['filed']==day]
    return latest[-1] if len({x['value'] for x in latest})==1 else None


def extract(docs):
    """Extract only unambiguous group percentages, pro-forma totals, dated shares."""
    observations={'insider_ownership_pct':[],'debt_to_assets':[],'shares_outstanding':[]}
    for d in docs:
        soup=BeautifulSoup(getattr(d,'raw','') or '', 'html.parser')
        registration=d.filing.form in {'10','10/A','10-12B','10-12B/A','10-12G','10-12G/A'}
        # Index preceding headings once; repeated backwards DOM scans are
        # expensive in long filings that have hundreds of tables and no h-tags.
        sections={};current_section='Filing table'
        for element in soup.find_all(['h1','h2','h3','h4','caption','table']):
            if element.name=='table':sections[id(element)]=current_section
            else:current_section=' '.join(element.get_text(' ',strip=True).split())
        for table in soup.find_all('table'):
            section=sections[id(table)]
            rows=[]
            for tr in table.find_all('tr'):
                cells=tr.find_all(['td','th'],recursive=False)
                if cells:rows.append([' '.join(cell.get_text(' ',strip=True).split()) for cell in cells])
            if not rows:continue
            # A multi-row/spanning header is deliberately not guessed.
            header=rows[0]
            pct_cols=[i for i,text in enumerate(header) if re.search(r'percent|%',text,re.I)]
            # Some filing tables separate the number and percent sign and use
            # spacer/spanning header rows. Require one percentage heading and
            # exactly one explicit, terminal percentage in the group row.
            percentage_headers=[row for row in rows if any(re.search(r'percent|%',cell,re.I) for cell in row)
                                and not any(number(cell) is not None for cell in row)]
            for row in rows[1:]:
                if not row:continue
                if registration and re.search(r'all (?:directors and (?:executive )?officers|(?:executive )?officers and directors).*as a group',row[0],re.I):
                    val=number(row[pct_cols[0]]) if len(pct_cols)==1 and len(row)==len(header) else None
                    compact=[cell for cell in row[1:] if cell]
                    if val is None and percentage_headers and all(sum(bool(re.search(r'percent|%',cell,re.I)) for cell in h)==1 for h in percentage_headers):
                        if len(compact)>=2 and compact[-1]=='%' and sum('%' in cell for cell in compact)==1:
                            val=number(compact[-2])
                    if val is not None and 0<=val<=100:
                        observations['insider_ownership_pct'].append(proof(d,section,' | '.join(row),val))
            pro_cols=[i for i,text in enumerate(header) if re.search(r'pro[ -]?forma',text,re.I)]
            if registration and re.search(r'pro[ -]?forma',section+' '+' '.join(header),re.I) and len(pro_cols)==1:
                col=pro_cols[0]; figures={}
                for row in rows[1:]:
                    if len(row)!=len(header):continue
                    label=row[0].strip().lower().rstrip(':')
                    if label in ('total debt','total assets'):
                        val=number(row[col])
                        if val is not None:figures.setdefault(label,[]).append((val,' | '.join(row)))
                if all(len(figures.get(k,[]))==1 for k in ('total debt','total assets')):
                    debt,dq=figures['total debt'][0];assets,aq=figures['total assets'][0]
                    if assets>0:
                        observations['debt_to_assets'].append(proof(d,section,dq+'; '+aq,debt/assets,
                            source=f'computed: total debt {debt:g} / total assets {assets:g}; {d.url}; section {section}; pro forma column',
                            inputs={'debt':debt,'assets':assets}))
            dates={iso_date(x) for x in re.findall(DATE,section)}-{None}
            for row in rows:
                if len(row)!=2 or not re.fullmatch(r'(?:total )?common shares outstanding',row[0],re.I):continue
                val=number(row[1])
                if val is None or len(dates)!=1:continue
                scale=1000 if re.search(r'shares in thousands',section,re.I) else 1000000 if re.search(r'shares in millions',section,re.I) else 1
                observations['shares_outstanding'].append(proof(d,section,' | '.join(row),val*scale,as_of=next(iter(dates)),scale=scale))
    return {'insider_ownership_pct':unique_latest(observations['insider_ownership_pct']),
            'debt_to_assets':unique_latest(observations['debt_to_assets']),
            'shares_outstanding':observations['shares_outstanding']}


def shares_on(facts,day):
    eligible=[item for item in facts.get('shares_outstanding',[]) if item.get('as_of','9999')<=day and item.get('filed','9999')<=day]
    if not eligible:return None
    latest=max(item['as_of'] for item in eligible)
    return unique_latest([item for item in eligible if item['as_of']==latest])


def price_source(row):
    return f"{row['close']:g} on {row['date']} ({row.get('source','closes reader')})"


def cap_metrics(child,parent,first,parent_close):
    if not first:return {}
    own=shares_on(child,first['date'])
    if not own:return {}
    cap=own['value']*first['close']
    result={'absolute_market_cap':{'value':cap,
        'source':f"computed: {own['value']:g} shares as of {own['as_of']}, reported {own['filed']} ({own['filing']}, {own['section']}, quote {own['quote']}) * {price_source(first)}",'shares':own}}
    if not parent_close or parent_close['date']!=first['date']:return result
    if first.get('currency') and parent_close.get('currency') and first['currency']!=parent_close['currency']:return result
    parent_shares=shares_on(parent,first['date'])
    if not parent_shares:return result
    parent_cap=parent_shares['value']*parent_close['close']
    if parent_cap<=0:return result
    result['size_relative_to_parent']={'value':cap/parent_cap,
        'source':f"computed: child cap ({result['absolute_market_cap']['source']}) / parent cap ({parent_shares['value']:g} shares as of {parent_shares['as_of']}, reported {parent_shares['filed']} from {parent_shares['filing']}, {parent_shares['section']}, quote {parent_shares['quote']} * {price_source(parent_close)}); no FX conversion",'parent_shares':parent_shares}
    return result


def ticker(docs):
    found=[]
    for d in docs:
        soup=BeautifulSoup(getattr(d,'raw','') or '', 'html.parser')
        for element in soup.find_all():
            if str(element.get('name','')).lower()=='dei:tradingsymbol':
                symbol=element.get_text('',strip=True)
                if re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,15}',symbol):found.append((d.filing.filed,symbol))
    if not found:return None
    latest=max(x[0] for x in found);symbols={x[1] for x in found if x[0]==latest}
    return next(iter(symbols)) if len(symbols)==1 else None


def insider_purchases(docs,cik,distribution,asof,complete):
    """Count disclosed code-P transactions, never assume missing=0."""
    if not complete:return None
    transactions={}
    for d in docs:
        if d.filing.form=='4/A':return None  # amendment matching needs review
        soup=BeautifulSoup(getattr(d,'raw','') or '', 'html.parser')
        issuer=soup.find(lambda tag:tag.name.lower()=='issuercik')
        if not issuer or not issuer.get_text(strip=True).isdigit() or int(issuer.get_text(strip=True))!=int(cik):return None
        for i,transaction in enumerate(soup.find_all(lambda tag:tag.name.lower() in {'nonderivativetransaction','derivativetransaction'})):
            code=transaction.find(lambda tag:tag.name.lower()=='transactioncode')
            day=transaction.find(lambda tag:tag.name.lower()=='transactiondate')
            if code is None or day is None:return None
            value=day.find(lambda tag:tag.name.lower()=='value')
            if value is None or not iso_date(value.get_text(strip=True)):return None
            day=value.get_text(strip=True)
            if code.get_text(strip=True)=='P' and distribution<=day<=asof:
                transactions[(d.filing.accession,i)]=proof(d,'Form 4 — reported transactions',str(transaction),1,transaction_date=day,code='P')
    return {'value':len(transactions),'transactions':list(transactions.values()),
            'source':f"computed count of disclosed Form 4 code P transactions from {distribution} through {asof}; complete scanned issuer filing list https://data.sec.gov/submissions/CIK{int(cik):010d}.json; "+'; '.join(f"{x['filing']} transaction date {x['transaction_date']} quote {x['quote']}" for x in transactions.values()),
            'coverage':'Observed filings only; late disclosures can change the count. Code P includes open-market or private purchases.'}
