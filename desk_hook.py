"""The desk's blocking, offline output gate. It reads actual saved outputs."""
from __future__ import annotations

import ast
from decimal import Decimal
import json
from pathlib import Path
import re
import sys

from desk_sources import WORKSPACE,inside,digest,write_json

HOOK_DIR=WORKSPACE/'hooks'
if str(HOOK_DIR) not in sys.path:sys.path.insert(0,str(HOOK_DIR))
from worksheet_numbers import (Auditor,NUM,DATE,ACCESSION,TEXT_DATE,FORM_ID,PERIOD_ID,
                              LABEL_ID,amount,rounded_equal,financial_word_numbers)
from worksheet_format import arithmetic
from desk_quantities import quantities,matches,source_quantities,enumeration_spans,heading_spans
from desk_claims import verify_saved
from desk_role_contracts import verify_output,verify_team_file,PREFIX

XBRL=re.compile(r'\[XBRL\s+tag\s+([^,\]]+),\s*period end\s+(\d{4}-\d{2}-\d{2}),\s*filing\s+([^\]]+)\]',re.I)
REF=re.compile(r'([\w./-]+\.(?:txt|json|md)):L(\d+)')
FORMULA=re.compile(r'\[computed using formula\s+(.*?)\s+based on\s+([^\]]+)\]',re.I)


class HookFailure(ValueError):pass


def fact_values(facts,tag,period,accession):
    values=[]
    groups=[facts.get('facts',{})]+[x.get('facts',{}) for x in facts.get('peers',{}).values()]
    for group in groups:
        for fact in group.values():
            if fact.get('tag')!=tag:continue
            for prefix in ('','prior_'):
                if fact.get(prefix+'period_end')==period and str(fact.get(prefix+'filing'))==accession:
                    value=fact.get(prefix+'value')
                    if value is not None:values.append(Decimal(str(value)))
    if len(set(values))>1:raise ValueError('Conflicting tag/period/accession evidence')
    return values


def report_errors(run,path,text=None):
    """Each financial token must be linked to a local citation or arithmetic."""
    run=Path(run);path=Path(path)
    lines=(path.read_text() if text is None else text).splitlines()
    facts=json.loads((run/'facts.json').read_text()) if (run/'facts.json').exists() else {}
    errors=[]
    for i,line in enumerate(lines,1):
        if i<=2 and (line.startswith('Filings read:') or line.startswith('Run time:')):continue
        covered=[False]*len(line);values=set();fact_numbers=set();evidence=[];cited_text=[]
        def mask(a,b):covered[a:b]=[True]*(b-a)
        for pattern in (DATE,ACCESSION,TEXT_DATE,FORM_ID,PERIOD_ID,LABEL_ID):
            for m in pattern.finditer(line):mask(*m.span())
        for m in re.finditer(r'\b10-[KQ]\b',line):mask(*m.span())
        for start,end in heading_spans(line):mask(start,end)
        for m in re.finditer(r'\bL\d+(?:\s*[-–]\s*L?\d+)?\b|\b(?:Note|Item|Section)\s+\d+(?:\.\d+)*\b',line,re.I):mask(*m.span())
        for m in re.finditer(r'\b(?:FY|fiscal(?:\s+year)?)\s*20\d{2}\b|\b(?:in|during|for)\s+20\d{2}\b|\b\d+[- ](?:weeks?|months?|years?)\b',line,re.I):mask(*m.span())
        for start,end in enumeration_spans(line):mask(start,end)
        for m in re.finditer(r'\bthe\s+(one)\s+to\s+watch\b',line,re.I):mask(*m.span(1))
        for m in XBRL.finditer(line):
            mask(*m.span())
            try:
                found=fact_values(facts,*[s.strip() for s in m.groups()])
                if not found:raise ValueError('Exact XBRL tag/period/accession not found in facts.json')
                values.update(found)
                fact_numbers.update(found)
            except ValueError as error:errors.append((i,str(error),line))
        for m in REF.finditer(line):
            # A source filename starts at its citation delimiter, not arbitrary
            # prose preceding it (the regex intentionally permits nested paths).
            name=re.split(r'[\[;|]',m[1])[-1].strip()
            mask(m.end(1)-len(name),m.end())
            try:
                source=inside(run,name).read_text().splitlines();number=int(m[2])-1
                if not 0<=number<len(source):raise ValueError('Cited filing line does not exist')
                values.update(amount(n[0]) for n in NUM.finditer(source[number]))
                evidence.extend(source_quantities(source,number,NUM,financial_word_numbers(source[number])))
                cited_text.append(source[number])
            except (OSError,ValueError) as error:errors.append((i,str(error),line))
        # Literal quotations retain the filing's printed units. Normalized
        # evidence above checks amounts outside quotations in base units.
        quotes=[m.span(1) for m in re.finditer(r'["“]([^"”]+)["”]',line)
                if any(m[1] in source for source in cited_text)]
        for m in FORMULA.finditer(line):
            mask(*m.span())
            try:
                expr=m[1].replace('$','').replace(',','').strip()
                constants=[amount(n[0]) for n in NUM.finditer(expr)]
                # One hundred converts a fraction to percent; every financial
                # operand still needs a filing/tag citation on this same line.
                if not constants or any(v not in values and abs(v) not in values and abs(v) not in {Decimal(1),Decimal(100)} for v in constants):
                    raise ValueError('Formula contains an operand without cited evidence')
                result=arithmetic(expr)
                prefix=[n for n in NUM.finditer(line[:m.start()]) if not all(covered[n.start():n.end()])]
                if not prefix:raise ValueError('Formula has no printed result')
                printed=prefix[-1]
                percent=line[printed.end():].lstrip().startswith('%')
                expected=result*100 if percent and not re.search(r'\*\s*100\b',expr) else result
                if not rounded_equal(printed[0],expected):raise ValueError('Printed arithmetic result is incorrect')
                mask(*printed.span())
            except (ValueError,ArithmeticError,SyntaxError) as error:errors.append((i,str(error),line))
        for q in quantities(line,NUM,financial_word_numbers(line)):
            if all(covered[q.start:q.end]):continue
            if any(start<=q.start and q.end<=end for start,end in quotes):continue
            # Formula results are checked above; their unit suffix is not a
            # second claim. Identifier masks cover their number tokens too.
            numeric=list(NUM.finditer(line[q.start:q.end]))
            if numeric and all(all(covered[q.start+n.start():q.start+n.end()]) for n in numeric):continue
            if not any(matches(q,source) for source in evidence) and q.value not in fact_numbers:
                errors.append((i,'Financial number has no matching cited value or calculation: '+q.printed,line))
    return errors


def check_facts(run,sources):
    path=run/'facts.json'
    if not path.exists():return
    saved=json.loads(path.read_text())
    company=[]
    for url,item in sources.data['responses'].items():
        if '/api/xbrl/companyfacts/' in url:
            company.append(json.loads(inside(run,item['path']).read_text()))
    for group in [saved.get('facts',{})]+[p.get('facts',{}) for p in saved.get('peers',{}).values()]:
        for name,fact in group.items():
            for prefix in ('','prior_'):
                value=fact.get(prefix+'value')
                if value is None:continue
                valid=False
                for data in company:
                    for taxonomy in data.get('facts',{}).values():
                        concept=taxonomy.get(fact.get('tag'),{})
                        for observations in concept.get('units',{}).values():
                            valid |= any(x.get('end')==fact.get(prefix+'period_end') and x.get('accn')==fact.get(prefix+'filing') and x.get('val')==value for x in observations)
                if not valid:raise HookFailure(f'{path}: {name}.{prefix}value does not match saved SEC XBRL evidence')


def check_screen(run,path,markdown=None):
    from datetime import date,datetime
    from desk_sources import skill
    from desk_parts import validate_screen
    module=skill('us-spinoff-seeker');data=json.loads(path.read_text())
    validate_screen(module,data)
    configured=module.load_factors(str(run/'inputs/spinoff_factors.json'))
    saved=data.get('factors') or data['registry'].get('factors')
    if configured!=saved:raise ValueError('Screen factors differ from the authored factor file; refresh the screen')
    if markdown:
        registry=data['registry'];asof=date.fromisoformat(registry['as_of'])
        pending=set(registry.get('pending_ciks',[]))
        candidates=[c for c in registry['candidates'].values() if c.get('eligibility')!='before start' and c['cik'] not in pending]
        from copy import deepcopy
        ranked,unranked=module.rank(deepcopy([c for c in candidates if not c.get('drop') and c.get('eligibility')=='included']),saved)
        expected=module.report(candidates,ranked,unranked,asof,registry.get('index_date'),data.get('limitations',[]),
                               run_day=datetime.fromisoformat(data['run_time']).date(),factors=saved)
        if NUM.findall(markdown.read_text())!=NUM.findall(expected):
            raise ValueError('Seeker report numbers differ from saved facts and recomputed factor ranks')


def check_calculations(run,path):
    data=json.loads(path.read_text())
    for name,metric in data.get('metrics',{}).items():
        if metric.get('value') is None:continue
        expression=metric.get('formula')
        if not expression:raise ValueError('Calculated fact has no printed formula: '+name)
        expected=arithmetic(expression)
        if metric.get('unit')=='%' and not re.search(r'\*\s*100\b',expression):expected*=100
        # The desk saves the value as a float; the formula is redone here exactly. A float carries about sixteen
        # significant digits, so its last printed digit can differ from the exact result's, and a correct value
        # was refused (2026-11-19). A wrong input or formula moves the value far more than one part in 10**12.
        saved=Decimal(repr(float(metric['value'])))
        if abs(saved-expected)>max(abs(expected),Decimal(1))*Decimal('1e-12'):
            raise ValueError('Calculated fact differs from its input arithmetic: '+name)


class Hook:
    def __init__(self,run,sources):
        self.run=Path(run).resolve();self.sources=sources
        self.sequence=max([int(p.stem) for p in (self.run/'hook').glob('*.json') if p.stem.isdigit()] or [0])

    def check(self,phase,paths,worksheet=None,verified=None):
        self.sequence+=1;errors=[]
        requested=[Path(p).resolve() for p in paths]
        paths=[]
        if not requested:errors.append(('<outputs>',1,'Part supplied no saved output files',''))
        for path in requested:
            if not path.is_relative_to(self.run):raise HookFailure('Output is outside the shared run: '+str(path))
            if not path.is_file():errors.append((path.relative_to(self.run).as_posix(),1,'Requested saved output is missing',''))
            else:paths.append(path)
        try:
            self.sources.verify()
            if (self.run/'facts.json').exists():check_facts(self.run,self.sources)
        except (OSError,ValueError,TypeError) as error:errors.append(('sources.json',1,str(error),''))
        for path in paths:
            if not path.resolve().is_relative_to(self.run.resolve()):raise HookFailure('Output is outside the shared run: '+str(path))
            relative=path.relative_to(self.run).as_posix()
            try:
                if path.suffix=='.json':
                    data=json.loads(path.read_text())
                    if path.name=='pick.json':
                        state=json.loads((self.run/'desk_run.json').read_text())
                        if state['selector']=='screen':
                            from desk_parts import validate_screen
                            from desk_sources import skill
                            expected,candidate=validate_screen(skill('us-spinoff-seeker'),json.loads((self.run/'screen.json').read_text()))
                            if data.get('ticker')!=expected or data.get('candidate')!=candidate:raise ValueError('Pick differs from the saved screen top entry')
                        elif data.get('ticker')!=state['selector'].upper():raise ValueError('Pick differs from the requested ticker')
                    if path.name=='spinoff_status.json':
                        registry=json.loads((self.run/'registry.json').read_text())
                        matches=[c for c in registry.get('candidates',{}).values() if str((c.get('facts',{}).get('ticker') or {}).get('value','')).upper()==data['ticker']]
                        if data.get('spinoff')!=('applicable' if matches else 'not applicable'):raise ValueError('Spinoff applicability differs from registry evidence')
                    if path.name.startswith('Spinoff worksheet') and ', model ' not in path.name:
                        from desk_sources import skill
                        rendered=skill('spinoff-worksheet').render(data)
                        if not path.with_suffix('.md').is_file() or rendered!=path.with_suffix('.md').read_text():
                            raise ValueError('Worksheet JSON does not match the actual saved worksheet')
                    if path.name=='calculated_facts.json':check_calculations(self.run,path)
                    if isinstance(data,dict) and isinstance(data.get('registry'),dict) and data.get('run_time'):
                        check_screen(self.run,path)
                    ledger=(self.run/'team_report.json').exists()
                    if 'nodes/' in relative and path.name=='output.json' and isinstance(data,dict) and path.parent.name.startswith('Verifier_') and path.parent.name!='Verifier_Code':
                        if ledger:
                            # A claims-ledger run leaves a flagged claim's line out of the published text
                            # (published_sections), so a flag does not stop it. The file must be a checked verification.
                            if data.get('contract')!='verification':raise ValueError('Verifier output is not a checked verification')
                        else:
                            for check in data.get('checks',[]):
                                if check.get('status')!='correct':raise ValueError('Verifier rejected a claim: '+str(check.get('claim','unknown')))
                    if isinstance(data,dict) and 'model_checks' in data and not ledger:
                        if any(c.get('status')!='correct' for c in data['model_checks'].get('checks',[])):
                            raise ValueError('Team verifier has wrong or unsupported claims')
                    if path.name=='view.json':
                        from view_record import validate_view
                        validate_view(data)
                        if not isinstance(data,dict) or not data.get('view_time') or not data.get('direction'):raise ValueError('View has no direction/time')
                        worksheets=[p for p in self.run.glob('Spinoff worksheet*.json') if ', model ' not in p.name]
                        if len(worksheets)!=1:raise ValueError('View has no unique saved worksheet')
                        evidence=json.loads(worksheets[0].read_text())
                        if data['direction']!=evidence.get('view',{}).get('direction'):raise ValueError('View direction differs from the saved worksheet')
                        when=evidence.get('view_time') or evidence.get('view',{}).get('time')
                        if when and when!=data['view_time']:raise ValueError('View time differs from the saved worksheet')
                    if 'nodes/' in relative and path.name=='output.json':
                        if isinstance(data,dict) and 'contract' in data:
                            role=data.get('role')
                            if role not in PREFIX or not re.fullmatch(re.escape(PREFIX[role])+r'_[12]',path.parent.name):raise ValueError('Role contract does not match its saved node')
                            errors.extend((relative,1,e,'') for e in verify_output(self.run,data))
                            if data['contract']=='claims' and path.with_name('draft.md').read_text()!=data['draft']:raise ValueError('Saved role Markdown differs from its checked draft')
                        elif isinstance(data,dict) and 'claims' in data:
                            # Claims-ledger output: every number was rendered by code from
                            # a checked quote, so recheck the claims, not the prose.
                            errors.extend((relative,1,e,'') for e in verify_saved(self.run,data))
                        elif isinstance(data,dict) and 'draft' in data:
                            errors.extend((relative,*e) for e in report_errors(self.run,path,data['draft']))
                        if isinstance(data,dict) and 'sections' in data and 'contract' not in data:
                            for section,body in data['sections'].items():errors.extend((relative,*e) for e in report_errors(self.run,path,str(body)))
                elif path.suffix=='.md':
                    if path.name=='draft.md' and path.parent.parent.name=='nodes':
                        data=json.loads(path.with_name('output.json').read_text())
                        if verify_output(self.run,data) or path.read_text()!=data.get('draft'):raise ValueError('Role Markdown differs from checked source claims')
                    elif path.name=='screen.md' or path.name.startswith('Spinoffs,'):
                        snapshot=path.with_suffix('.json') if path.with_suffix('.json').exists() else self.run/'screen.json'
                        check_screen(self.run,snapshot,path)
                    elif path.name.startswith('Spinoff worksheet'):
                        for error in Auditor(self.run,self.run/'inputs').check(path):errors.append((relative,error.line,error.reason,error.text))
                    elif path.name in {'report.md','verified_report.md','final_report.md'}:
                        text=path.read_text()
                        if path.name=='final_report.md':
                            if not worksheet or not verified:raise ValueError('Final report has no source report and worksheet')
                            expected=self.compose(Path(verified),Path(worksheet))
                            if text!=expected:raise ValueError('Final report differs from the saved report/worksheet composition')
                            # Both actual source files are independently rechecked;
                            # the byte comparison above includes every final line.
                            if (self.run/'team_report.json').exists():verify_team_file(self.run,verified)
                            else:errors.extend((relative,*e) for e in report_errors(self.run,verified))
                            for error in Auditor(self.run,self.run/'inputs').check(worksheet):errors.append((relative,error.line,error.reason,error.text))
                        elif (self.run/'team_report.json').exists():verify_team_file(self.run,path)
                        else:errors.extend((relative,*e) for e in report_errors(self.run,path))
            except (ValueError,TypeError,OSError) as error:errors.append((relative,1,str(error),''))
        record={'part':phase,'requested_outputs':[p.relative_to(self.run).as_posix() for p in requested],
                'outputs':[{'path':p.relative_to(self.run).as_posix(),'sha256':digest(p)} for p in paths],
                'status':'FAIL' if errors else 'PASS','errors':errors}
        write_json(self.run/'hook'/f'{self.sequence:05d}.json',record)
        if errors:
            raise HookFailure('\n'.join(f'{p}:{line}: {why}\n{text}' for p,line,why,text in errors))
        return record

    def compose(self,verified,worksheet):
        report=verified.read_text().splitlines()
        body='\n'.join(report[1:]) if report and report[0].startswith('Filings read:') else '\n'.join(report)
        return self.sources.filing_line()+'\n'+body.rstrip()+'\n\n## Worksheet view and evidence\n\n'+worksheet.read_text().rstrip()+'\n'
