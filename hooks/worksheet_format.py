"""Read the worksheet's existing presentation, not its computed JSON claims.

Every accepted span has been checked against a saved filing, authored rule,
saved raw reader observation, or arithmetic using the printed worksheet rows.
"""
from __future__ import annotations

import ast
from datetime import datetime, time
from decimal import Decimal, localcontext
import json
from pathlib import Path
import re
from statistics import median
from zoneinfo import ZoneInfo

from worksheet_numbers import NUMBER, NUM, amount, rounded_equal, within

N = '('+NUMBER+')'
DATE = r'\d{4}-\d{2}-\d{2}'
HEADER = re.compile(r'^(?:(?:PRO FORMA|UNAUDITED|CONDENSED)\s+)*(?:CONSOLIDATED|COMBINED)\s+STATEMENTS?\s+OF\s+(?:INCOME|OPERATIONS|CASH FLOWS)\s*$', re.I)
MONTH_DATE = re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b', re.I)
SOURCE = re.compile(r'\[(?P<file>[^\]\n]+\.txt):L(?P<line>\d+)\] section (?P<section>[^;\n]+); year ended (?P<period>'+DATE+r'); units (?P<scale>'+NUMBER+r'); (?P<label>[^;=\n]+?) = (?P<reported>'+NUMBER+r')')
SPENDING = re.compile(r'; spending = -\((?P<input>'+NUMBER+r')\) = (?P<result>'+NUMBER+r')')
SHARES = re.compile(r'\[(?P<file>[^\]\n]+\.txt):L(?P<line>\d+)\] section Cover page; as of (?P<period>'+DATE+r'); quote: (?P<label>The number of shares outstanding[^;\n]*?was)\s+(?P<value>'+NUMBER+r')', re.I)
EQUATION = re.compile(r'computed:\s*(?P<expr>[\d,.eE+*/()\s−-]+?)\s*=\s*(?P<result>'+NUMBER+r')')
METRICS = {'after_tax_earnings':'after_tax_earnings','depreciation_and_amortization':'depreciation_and_amortization','depreciation':'depreciation','capital_spending':'capital_spending',
           'after-tax earnings':'after_tax_earnings','depreciation and amortization':'depreciation_and_amortization','capital spending':'capital_spending'}


def arithmetic(expression):
    """Decimal arithmetic on literal worksheet inputs; no eval or calls."""
    expression = expression.replace(',', '').replace('−','-')
    tree = ast.parse(expression.strip(), mode='eval')
    def visit(node):
        if isinstance(node, ast.Expression): return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value,(int,float)) and not isinstance(node.value,bool):
            return Decimal(ast.get_source_segment(expression.strip(),node))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            return (-1 if isinstance(node.op,ast.USub) else 1)*visit(node.operand)
        if isinstance(node, ast.BinOp):
            a,b=visit(node.left),visit(node.right)
            if isinstance(node.op,ast.Add):return a+b
            if isinstance(node.op,ast.Sub):return a-b
            if isinstance(node.op,ast.Mult):return a*b
            if isinstance(node.op,ast.Div):return a/b
        raise ValueError('Unsupported printed arithmetic')
    with localcontext() as ctx:
        ctx.prec=60
        return visit(tree)


def number_row(lines, start):
    """A row ends at the next label; signs and currency occupy separate lines."""
    result=[]; negative=False
    for line in lines[start:]:
        s=line.strip()
        if s in ('','$',')'):
            if s==')': negative=False
            continue
        if s=='(':negative=True;continue
        if not re.fullmatch(r'\(?[−-]?\d[\d,]*(?:\.\d+)?\)?',s):break
        value=amount(s.strip('()'))
        result.append(-abs(value) if negative or s.startswith('(') else value)
    return result


class WorksheetFormat:
    def __init__(self,run,workspace,worksheet,text):
        self.run=run;self.workspace=workspace;self.worksheet=worksheet
        self.lines=text.splitlines();self.spans={};self.errors={};self.sources={};self.rows={};self.facts={}
        self.approved=set();self.ocf=None;self.low=None;self.mid=None;self.shares=None;self.price=None
        self.daily={};self.median=None
        self.enabled=bool(self.lines and self.lines[0].startswith('Spinoff worksheet |'))
        if not self.enabled:return
        self.settings=self.rules()
        for i,line in enumerate(self.lines,1):self.read_sources(i,line)
        for i,line in enumerate(self.lines,1):self.read_table(i,line)
        for i,line in enumerate(self.lines,1):self.read_daily(i,line)
        if self.settings.get('observations')==len(self.daily):
            self.median=median([close*volume for close,volume in self.daily.values()])
        self.compute_inputs()
        # Price precedes score checking; read all value and price lines first.
        for i,line in enumerate(self.lines,1):self.read_values(i,line)
        for i,line in enumerate(self.lines,1):self.read_equations(i,line)
        for i,line in enumerate(self.lines,1):self.read_price(i,line)
        for i,line in enumerate(self.lines,1):self.read_remaining(i,line)

    def mask(self,i,start,end):self.spans.setdefault(i,[]).append((start,end))
    def fail(self,i,message):self.errors.setdefault(i,[]).append(message)
    def check(self,i,match,group,expected,label,exact=False):
        self.mask(i,*match.span(group))
        raw=match[group]
        if expected is None or not (amount(raw)==expected if exact else rounded_equal(raw,expected)):
            self.fail(i,label+' does not match its source or printed inputs')
            return False
        return True

    def rules(self):
        path=self.workspace/'spinoff-rules.md'
        try:
            text=path.read_text()
            def get(pattern):
                m=re.search(pattern,text,re.I)
                if not m:raise ValueError('Authored rule missing')
                return amount(m[1])
            return {'low':get(r'Low case:\s*owner cash flow\s*÷\s*([\d.]+%)'),
                    'mid':get(r'Mid case:\s*owner cash flow\s*÷\s*([\d.]+%)'),
                    'years':get(r'average of the last\s+(\d+)\s+fiscal years'),
                    'portfolio':get(r'Client portfolio:\s*\$([\d,]+(?:\.\d+)?)'),
                    'positions':get(r'Purchase size:[^\n]*?÷\s*(\d+)\s+positions'),
                    'observations':get(r'median daily dollar volume over the last\s*(\d+)\s*trading days'),
                    'participation':get(r'purchase size\s*≤\s*([\d.]+%)'),
                    'days':get(r'completed within\s*(\d+)\s*trading days')}
        except (OSError,ValueError):return {}

    def filing_value(self,m):
        lines=within(self.run,m['file']).read_text().splitlines()
        idx=int(m['line'])-1
        if not 0<=idx<len(lines) or lines[idx].strip()!=m['label'].strip():
            raise ValueError('Cited filing row label does not match saved text')
        headings=[j for j in range(idx) if HEADER.fullmatch(lines[j].strip())]
        if not headings:raise ValueError('Statement header not established for cited row')
        h=headings[-1]
        if lines[h].strip()!=m['section'].strip():raise ValueError('Cited statement section does not match')
        next_header=next((j for j in range(h+1,len(lines)) if HEADER.fullmatch(lines[j].strip())),len(lines))
        statement='\n'.join(lines[h:next_header])
        if re.search(r'\b(?:CAD|AUD|HKD|EUR|GBP)\b|C\$|A\$|HK\$|€|£',statement,re.I):
            raise ValueError('Filing statement currency is incompatible with the printed USD inputs')
        if '$' not in statement and not re.search(r'USD|U[.]S[.] dollars',statement,re.I):
            raise ValueError('USD statement currency is not established')
        intro=' '.join(lines[h+1:idx])
        if not re.search(r'(?:years?|weeks?)\s+ended',intro,re.I):raise ValueError('Annual column header is missing')
        # Only the header before the first data label supplies periods/units.
        period_matches=list(MONTH_DATE.finditer(intro))
        dates=[]
        for x in period_matches:
            raw=re.sub(r'\s+',' ',x[0]);raw=re.sub(r'(\d),? (\d{4})$',r'\1, \2',raw)
            day=datetime.strptime(raw,'%B %d, %Y').date().isoformat()
            if day not in dates:dates.append(day)
        if m['period'] not in dates:raise ValueError('Claimed period is absent from filing columns')
        scale=Decimal(1000000) if re.search(r'amounts? in millions',intro,re.I) else Decimal(1000) if re.search(r'amounts? in thousands',intro,re.I) else Decimal(1)
        if amount(m['scale'])!=scale:raise ValueError('Claimed unit scale differs from filing header')
        values=number_row(lines,idx+1)
        if len(values)!=len(dates):raise ValueError('Filing row cannot be assigned unambiguously to period columns')
        return values[dates.index(m['period'])]*scale

    def read_sources(self,i,line):
        for m in SOURCE.finditer(line):
            for group in ('scale','reported'):self.mask(i,*m.span(group))
            value=None
            try:
                value=self.filing_value(m)
                if not rounded_equal(m['reported'],value):raise ValueError('Printed filing amount differs from the cited period column')
                self.sources[(i,m.start())]={'value':value,'period':m['period'],'label':m['label'].strip(),'kind':'statement'}
                self.approved.add(value)
            except (OSError,ValueError,ArithmeticError) as error:self.fail(i,str(error))
            spend=SPENDING.match(line,m.end())
            if spend:
                for group in ('input','result'):self.mask(i,*spend.span(group))
                if value is None or not rounded_equal(spend['input'],value) or not rounded_equal(spend['result'],-value):
                    self.fail(i,'Spending sign conversion does not match the filing row')
                else:self.approved.add(-value)
        for m in SHARES.finditer(line):
            self.mask(i,*m.span('value'))
            try:
                lines=within(self.run,m['file']).read_text().splitlines();idx=int(m['line'])-1
                label=' '.join(lines[idx].split()) if 0<=idx<len(lines) else ''
                if label!=' '.join(m['label'].split()):raise ValueError('Cover-page shares citation does not match saved label')
                dates=MONTH_DATE.findall(label)
                if len(dates)!=1:raise ValueError('Cover-page share-count date is not established')
                day=datetime.strptime(re.sub(r'\s+',' ',dates[0]),'%B %d, %Y').date().isoformat()
                values=number_row(lines,idx+1)
                if day!=m['period'] or len(values)!=1 or values[0]!=amount(m['value']):raise ValueError('Share count or date differs from the cited cover-page text')
                self.sources[(i,m.start())]={'value':values[0],'period':day,'kind':'shares'}
                self.approved.add(values[0])
            except (OSError,ValueError,ArithmeticError) as error:self.fail(i,str(error))

    def read_table(self,i,line):
        m=re.match(r'(?P<label>[^|]+)\|\s*(?P<value>'+NUMBER+r')\s*(?:USD|shares)?\s*\|\s*(?P<basis>[^|]+)\|\s*(?P<source>.*)$',line)
        if not m:
            cells=[x.strip() for x in line.split('|')]
            if len(cells)==4 and cells[0] not in ('Fact','---'):
                self.facts[cells[0]]={'value':cells[1],'source':cells[3]}
            return
        label=m['label'].strip();metric=METRICS.get(label.lower().split(', Fiscal year')[0])
        if not metric:metric=METRICS.get(re.split(r',\s*Fiscal year',label,flags=re.I)[0].lower())
        metric=metric or ('shares_outstanding' if label=='shares_outstanding' else None)
        if not metric:
            self.facts[label]={'value':amount(m['value']),'source':m['source']}
            return
        self.mask(i,*m.span('value'))
        sources=[v for (j,start),v in self.sources.items() if j==i and start>=m.start('source')]
        if len(sources)!=1:
            self.fail(i,'Table amount has no verified filing row');return
        src=sources[0];expected=abs(src['value']) if metric=='capital_spending' else src['value']
        basis=m['basis'].strip()
        expected_basis='pro forma' if re.search(r'section PRO FORMA',m['source'],re.I) else 'historical'
        if basis!=expected_basis:
            self.fail(i,'Table statement basis differs from its cited filing header');return
        period=re.search(DATE,label)
        if period and period[0]!=src['period']:
            self.fail(i,'Table period differs from its filing citation');return
        if amount(m['value'])!=expected:
            self.fail(i,'Table amount differs from its cited filing period/units');return
        key=(metric,src['period'])
        if key in self.rows and self.rows[key]!=expected:
            self.fail(i,'Conflicting printed inputs for the same metric and period');return
        self.rows[key]=expected
        self.facts[label]={'value':expected,'source':m['source']}
        if metric=='shares_outstanding':self.shares=expected

    def compute_inputs(self):
        periods=sorted({p for key,p in self.rows if key=='after_tax_earnings'},reverse=True)
        years=self.settings.get('years')
        if years is None or years!=len(periods):return
        if any(int(periods[k][:4])-int(periods[k+1][:4])!=1 for k in range(len(periods)-1)):return
        totals=[]
        for period in periods:
            keys=[('after_tax_earnings',period),('depreciation_and_amortization',period),('capital_spending',period)]
            if not all(k in self.rows for k in keys):return
            a,b,c=[self.rows[k] for k in keys];totals.append(a+b-c)
        self.approved.update(totals)
        with localcontext() as ctx:
            ctx.prec=60
            self.ocf=sum(totals)/years
            self.approved.add(self.ocf)
            if self.shares and self.ocf>=0:
                self.low=self.ocf/self.settings['low']/self.shares
                self.mid=self.ocf/self.settings['mid']/self.shares
                self.approved.update((self.low,self.mid))

    def read_values(self,i,line):
        m=re.match(r'Owner cash flow:\s*(?P<value>'+NUMBER+r')',line)
        if m:self.check(i,m,'value',self.ocf,'Owner cash flow')
        m=re.match(r'(?P<case>Low|Mid) value:\s*(?P<value>'+NUMBER+r'); formula:\s*(?P<expr>[^;]+); rates:\s*(?P<rates>\{[^}]*\})',line)
        if m:
            case=m['case'].lower();expected=self.low if case=='low' else self.mid
            self.check(i,m,'value',expected,case.title()+' value')
            for n in NUM.finditer(line,m.start('expr'),m.end('expr')):self.mask(i,*n.span())
            for n in NUM.finditer(line,m.start('rates'),m.end('rates')):self.mask(i,*n.span())
            try:
                rates=json.loads(m['rates'],parse_float=Decimal)
                if rates!={'discount_rate':self.settings.get(case)}:raise ValueError('Discount rate differs from authored '+case+' rule')
                expr,eq,result=m['expr'].partition('=')
                if not eq or expected is None:raise ValueError('Valuation inputs are not established')
                literals=[n[0] for n in NUM.finditer(expr)]
                inputs=[self.ocf,self.settings[case],self.shares]
                if len(literals)!=3 or not all(rounded_equal(s,v) for s,v in zip(literals,inputs)):
                    raise ValueError('Valuation operands differ from printed cash flow, authored rate or printed shares')
                tree=ast.parse(expr.strip(),mode='eval').body
                if not isinstance(tree,ast.BinOp) or not isinstance(tree.op,ast.Div) or not isinstance(tree.left,ast.BinOp) or not isinstance(tree.left.op,ast.Div):
                    raise ValueError('Valuation formula differs from the authored division method')
                calculated=arithmetic(expr)
                if not rounded_equal(result.strip(),calculated) or not rounded_equal(result.strip(),expected):raise ValueError('Printed valuation equation is incorrect')
            except (ValueError,TypeError,ArithmeticError,SyntaxError) as error:self.fail(i,str(error))
        m=re.match(r'Deciding number:\s*(?P<value>'+NUMBER+r')',line)
        if m:self.check(i,m,'value',self.low,'Deciding low-case value')

    def read_equations(self,i,line):
        for m in EQUATION.finditer(line):
            for n in NUM.finditer(line,m.start('expr'),m.end('result')):self.mask(i,*n.span())
            try:
                operands=[x[0] for x in NUM.finditer(m['expr'])]
                allowed=self.approved|({self.settings['years']} if 'years' in self.settings else set())
                if not all(any(rounded_equal(s,value) for value in allowed) for s in operands):
                    raise ValueError('Printed equation uses an input not established by filing rows or authored averaging rule')
                result=arithmetic(m['expr'])
                if not rounded_equal(m['result'],result):raise ValueError('Printed equation result is incorrect')
            except (ValueError,ArithmeticError,SyntaxError) as error:self.fail(i,str(error))

    def reader_rows(self):
        # These are original saved reader observations, not computed worksheet
        # facts, model data, or a hook-specific claim manifest.
        companion=self.worksheet.with_suffix('.json')
        data=json.loads(companion.read_text(),parse_float=Decimal)
        identity=json.loads((self.run/'facts.json').read_text())
        ticker=self.lines[0].split('|')[1].strip()
        if data.get('ticker')!=ticker or identity.get('ticker')!=ticker:raise ValueError('Saved reader data has a conflicting issuer')
        rows=data.get('liquidity',{}).get('inputs')
        if not isinstance(rows,list) or not rows:raise ValueError('No saved raw reader observations')
        return rows

    def read_daily(self,i,line):
        m=re.fullmatch(r'Liquidity day\s*\|\s*(?P<date>'+DATE+r')\s*\|\s*(?P<close>'+NUMBER+r')\s*\|\s*(?P<volume>'+NUMBER+r')\s*\|\s*(?P<currency>[A-Z]+)\s*\|\s*(?P<source>[^|]+?)(?:\s*\|\s*(?P<volume_source>[^|]+))?',line)
        if not m:return
        for name in ('close','volume'):self.mask(i,*m.span(name))
        try:
            matches=[r for r in self.reader_rows() if r.get('date')==m['date']]
            if len(matches)!=1:raise ValueError('Printed daily input has no unique saved reader observation')
            row=matches[0];close=amount(m['close']);volume=amount(m['volume'])
            day=datetime.fromisoformat(m['date']).date()
            cutoff=datetime.fromisoformat(self.lines[0].split('|')[2].strip())
            if day.weekday()>=5 or datetime.combine(day,time(16),ZoneInfo('America/New_York'))>=cutoff:
                raise ValueError('Printed daily input is not a completed trading observation')
            if m['date'] in self.daily:raise ValueError('Duplicate printed daily date')
            if close<=0 or volume<0 or m['currency']!='USD' or row.get('currency')!='USD' or row.get('source')!=m['source'] or amount(row.get('close'))!=close or amount(row.get('volume'))!=volume:
                raise ValueError('Printed daily close/volume/currency/source differs from saved reader output')
            if m['volume_source'] is not None and m['volume_source']!=(row.get('volume_source') or 'not known'):
                raise ValueError('Printed daily volume source differs from saved reader output')
            self.daily[m['date']]=(close,volume)
        except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as error:self.fail(i,str(error))

    def read_price(self,i,line):
        m=re.match(r'Price against low:\s*(?P<price>'+NUMBER+r') on (?P<date>'+DATE+r') \((?P<source>.+)\); low (?P<low>'+NUMBER+r'); \(price - low\) / low \* (?P<scale>'+NUMBER+r') = (?P<percent>'+NUMBER+r')',line)
        if not m:return
        for name in ('price','low','scale','percent'):self.mask(i,*m.span(name))
        try:
            rows=self.reader_rows();cutoff=datetime.fromisoformat(self.lines[0].split('|')[2].strip())
            eligible=[]
            for row in rows:
                day=datetime.fromisoformat(row['date']).date()
                close_time=datetime.combine(day,time(16),ZoneInfo('America/New_York'))
                if day.weekday()<5 and close_time<cutoff:eligible.append(row)
            if not eligible:raise ValueError('Saved reader observations contain no completed close')
            last=max(r['date'] for r in eligible);matches=[r for r in eligible if r['date']==last]
            if len(matches)!=1:raise ValueError('Saved reader close is ambiguous')
            row=matches[0]
            if m['date']!=last or row.get('source')!=m['source'] or row.get('currency')!='USD' or amount(row['close'])!=amount(m['price']):
                raise ValueError('Price/date/source/currency differs from the last saved completed reader close')
            self.price=amount(m['price'])
            if self.low is None or not rounded_equal(m['low'],self.low):raise ValueError('Price comparison uses an unverified low value')
            if amount(m['scale'])!=100:raise ValueError('Percentage conversion must use one hundred')
            # Keep full precision from the printed filing inputs/rate/shares.
            # The displayed low was checked above; rounding it again here can
            # create a false error in the last displayed percentage digit.
            expected=(self.price-self.low)/self.low
            if not rounded_equal(m['percent'],expected):raise ValueError('Price-versus-low percentage is incorrect')
        except (OSError,ValueError,KeyError,TypeError,ArithmeticError) as error:self.fail(i,str(error))

    def read_remaining(self,i,line):
        m=re.match(r'Criterion (?P<id>\d+) — (?P<name>[^:]+): (?P<score>'+NUMBER+r') \(computed in code\);',line)
        if m:
            self.mask(i,*m.span('score'))
            try:
                persona=(self.workspace/'persona-why-cheap.md').read_text()
                if not all(re.search(r'\b'+str(n)+r'\s*=\s*'+word,persona,re.I) for n,word in [(0,'absent'),(1,'partial'),(2,'present')]):
                    raise ValueError('Persona score policy is unavailable')
                index=int(m['id']);expected=None
                names={1:'Forced seller',2:'Indifferent seller',3:'Price against value',4:'Load pushed in',5:'Insiders buying',6:'Parent motive'}
                if names.get(index)!=m['name']:raise ValueError('Criterion identifier and name do not match the persona method')
                keys={1:['forced_seller','index_exclusion','index','relative_size'],2:['indifferent_seller','relative_size','dividend_mismatch'],4:['debt_raised','retained_liabilities','restrictions'],5:['insider_purchases'],6:['cash_to_parent','parent_motive','parent']}
                def absent(key):return key not in self.facts or self.facts[key]['value'] in ('not known','not applicable')
                if index==3:
                    # With no price (LSEG closed) or no low value, the comparison's evidence is absent, and absent
                    # evidence scores 0, as for the other five criteria and in evidence_scores.py. A 2 still needs
                    # both, verified above. On 2026-11-20 this case had no rule, and it stopped a whole run.
                    expected=Decimal(2 if self.price<=self.low else 0) if self.price is not None and self.low is not None else Decimal(0)
                elif index in keys and all(absent(k) for k in keys[index]):expected=Decimal(0)
                if expected is None:raise ValueError('Score needs evidence that cannot be established from printed fact rows')
                if amount(m['score'])!=expected:raise ValueError('Score differs from printed evidence and persona policy')
            except (OSError,ValueError) as error:self.fail(i,str(error))
        m=re.search(r'median\(daily close \* daily volume\) = (?P<median>'+NUMBER+r') USD; client purchase (?P<purchase>'+NUMBER+r') USD; purchase/median (?P<fraction>'+NUMBER+r'); (?P<count>'+NUMBER+r') observations',line)
        if m:
            for name in ('median','purchase','fraction','count'):self.mask(i,*m.span(name))
            purchase=self.settings.get('portfolio',Decimal(0))/self.settings.get('positions',Decimal(1))
            self.check(i,m,'purchase',purchase if self.settings else None,'Client purchase size')
            self.check(i,m,'count',self.settings.get('observations'),'Liquidity observation count',exact=True)
            days=re.findall(DATE,line)
            if len(days)!=len(set(days)) or len(days)!=amount(m['count']):self.fail(i,'Printed liquidity dates do not match its observation count')
            if self.median is None:
                self.fail(i,'Liquidity median and purchase fraction cannot be recomputed: required daily closes and volumes are not printed and verified in the worksheet')
            else:
                if sorted(days)!=sorted(self.daily):self.fail(i,'Liquidity summary dates differ from the printed daily inputs')
                self.check(i,m,'median',self.median,'Liquidity median')
                self.check(i,m,'fraction',purchase/self.median if self.median else None,'Purchase fraction')
        m=re.match(r'Can you buy it: (?P<buyable>yes|no); (?P<rate>'+NUMBER+r') \* median = (?P<capacity>'+NUMBER+r') USD/day; required (?P<days>'+NUMBER+r') trading days; limit (?P<limit>'+NUMBER+r')',line)
        if m:
            for name in ('rate','capacity','days','limit'):self.mask(i,*m.span(name))
            self.check(i,m,'rate',self.settings.get('participation'),'Daily participation rate',exact=True)
            self.check(i,m,'limit',self.settings.get('days'),'Trading-day limit',exact=True)
            if self.median is None:
                self.fail(i,'Trading capacity and required days depend on a median without printed daily inputs')
            else:
                capacity=self.median*self.settings['participation']
                purchase=self.settings['portfolio']/self.settings['positions']
                from decimal import ROUND_CEILING
                days=(purchase/capacity).to_integral_value(rounding=ROUND_CEILING) if capacity else None
                self.check(i,m,'capacity',capacity,'Daily trading capacity')
                self.check(i,m,'days',days,'Required trading days',exact=True)
                expected=days is not None and days<=self.settings['days']
                if (m['buyable']=='yes')!=expected:self.fail(i,'Buyable status differs from the printed inputs and authored limit')

    def result(self,i):
        return self.spans.get(i,[]),self.errors.get(i,[])
