"""All desk roles select saved evidence; code renders values and report text."""
import json
from pathlib import Path
import re
from desk_claims import Result,check,load_sources,PLACEHOLDER,format_fact
from desk_sources import inside
from insight_layout import PART_OWNERS,insight_failures

AUTHORS=('Research Analyst','Financial Analyst','Investment Advisor')
PREFIX={role:role.replace(' ','_') for role in (*AUTHORS,'Strategy Manager','Verifier')}


def manager_contract(run):
    sections={}
    for part,owner in PART_OWNERS.items():
        try:path,_=latest(run,owner);name=path.with_name('draft.md').relative_to(Path(run)).as_posix()
        except ValueError:name=f'nodes/{PREFIX[owner]}_1/draft.md'
        sections[part]={'file':name,'start':1,'end':1}
    example={'claims':[],'failures':[],'sections':sections}
    return ('Return exactly one JSON object. claims and failures are arrays. sections is an OBJECT keyed by the five exact section names, never a list. '
            'Every section value is an object with file, start and end. Do not return draft or a part field inside a sections list. '
            'Required shape (replace example start/end with actual inclusive body line ranges from the assigned files):\n'+json.dumps(example,indent=2))


def latest(run,role):
    run=Path(run)
    for number in (2,1):
        path=run/'nodes'/f'{PREFIX[role]}_{number}'/'output.json'
        if path.is_file():return path,json.loads(path.read_text(encoding='utf-8'))
    raise ValueError('No saved checked output for '+role)


def origins_for(run,role):
    permitted=AUTHORS[:2] if role=='Investment Advisor' else AUTHORS if role in ('Strategy Manager','Verifier') else ()
    origins={}
    for author in permitted:
        for number in (1,2):
            path=Path(run)/'nodes'/f'{PREFIX[author]}_{number}'/'output.json'
            if not path.exists():continue
            data=json.loads(path.read_text(encoding='utf-8'));texts,facts=load_sources(run)
            result=check({'claims':data.get('claims'),'draft':data.get('template')},texts,facts,
                         origins_for(run,author),author=='Investment Advisor')
            if not result.ok or result.rendered!=data.get('draft'):
                raise ValueError('Saved '+author+' ledger or draft failed: '+'; '.join(result.errors or ['rendering differs']))
            md=path.with_name('draft.md')
            if md.exists() and md.read_text(encoding='utf-8')!=data['draft']:raise ValueError('Saved role Markdown differs from its checked output: '+str(md))
            origins[author]=result.values
            origins[path.relative_to(Path(run)).as_posix()]=result.values
        if author not in origins and role=='Investment Advisor':raise ValueError('No saved checked output for '+author)
    return origins


def values_for(run,role,data):
    texts,facts=load_sources(run)
    claims=data.get('claims',[])
    if isinstance(claims,list):
        claims=[dict(c) if isinstance(c,dict) else c for c in claims]
        for c in claims:
            if isinstance(c,dict) and c.get('from') in AUTHORS and 'from_file' not in c:
                path,_=latest(run,c['from']);c['from_file']=path.relative_to(Path(run)).as_posix()
    result=check({'claims':claims,'draft':data.get('draft','')},texts,facts,
                 origins_for(run,role),role in ('Investment Advisor','Strategy Manager'))
    result.normalized_claims=claims
    return result


def substitute(text,values):
    return PLACEHOLDER.sub(lambda m:values[m[1]],text)


def validate(run,role,raw):
    """One validator for model attempts and saved outputs. No model calls."""
    result=Result()
    if not isinstance(raw,dict):
        result.errors.append('Return a JSON object.');return result
    if role in AUTHORS:
        # A reply with no draft is an error the role can repair. Until 2026-11-22 it raised KeyError out of this
        # check, which no repair catches, and the run stopped.
        if not isinstance(raw.get('draft'),str) or not raw['draft'].strip():
            result.errors.append('draft must be the text of your part, as a string; received '+type(raw.get('draft')).__name__+'.');return result
        try:result=values_for(run,role,raw)
        except (ValueError,OSError,TypeError) as error:result.errors.append(str(error));return result
        if result.ok:
            result.output={'contract':'claims','role':role,'claims':result.normalized_claims,'template':raw['draft'],'draft':result.rendered}
        return result
    if role=='Strategy Manager':
        failures=raw.get('failures');refs=raw.get('sections')
        if not isinstance(raw.get('claims'),list):result.errors.append('claims must be an array; received '+type(raw.get('claims')).__name__+'.')
        if not isinstance(failures,list):result.errors.append('failures must be an array; received '+type(failures).__name__+'.')
        if not isinstance(refs,dict):result.errors.append('sections must be an object keyed by the five exact section names; received '+type(refs).__name__+'.')
        if result.errors:
            result.errors.append(manager_contract(run));return result
        prose=[]
        for item in failures:
            # A part that is a list or an object cannot be looked up: it is the same error, not a TypeError.
            if not isinstance(item,dict) or not isinstance(item.get('part'),str) or item.get('part') not in PART_OWNERS or item.get('role')!=PART_OWNERS.get(item.get('part')) or not isinstance(item.get('feedback'),str):
                result.errors.append('Each failure must name a required part, its owner, and feedback.');continue
            prose.append(item['feedback'])
        try:
            checked=values_for(run,role,{'claims':raw.get('claims',[]),'draft':'\n'.join(prose)})
            result.errors.extend(checked.errors)
            sections={};used=[]
            for part,owner in PART_OWNERS.items():
                ref=refs.get(part)
                if ref is None and any(f.get('part')==part for f in failures if isinstance(f,dict)):
                    sections[part]='';continue
                if not isinstance(ref,dict):raise ValueError('Select a saved text range for '+part)
                source,data=latest(run,owner)
                md=source.with_name('draft.md')
                expected=md.relative_to(Path(run)).as_posix()
                if ref.get('file')!=expected:raise ValueError(part+' must select the latest saved draft of '+owner)
                lines=md.read_text(encoding='utf-8').splitlines();start=ref.get('start');end=ref.get('end')
                if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(lines):raise ValueError('Invalid saved line range for '+part)
                if md.read_text(encoding='utf-8')!=data['draft']:raise ValueError('Saved author file differs from its checked draft')
                sections[part]='\n'.join(lines[start-1:end])
                template=data['template'].splitlines()
                for cid in PLACEHOLDER.findall('\n'.join(template[start-1:end])):
                    target={'role':owner,'claim':cid}
                    if target not in used:used.append(target)
            unknown=set(refs)-set(PART_OWNERS)
            if unknown:raise ValueError('Unexpected report sections: '+', '.join(unknown))
            if result.ok:
                result.output={'contract':'selection','role':role,'claims':checked.normalized_claims,
                    'section_refs':refs,'sections':sections,'template_failures':failures,
                    'failures':[{**f,'feedback':substitute(f['feedback'],checked.values)} for f in failures],
                    'used_claims':used}
        except (ValueError,OSError,TypeError,KeyError) as error:result.errors.append(str(error))
        return result
    if role=='Verifier':
        checks=raw.get('checks')
        if not isinstance(checks,list):result.errors.append('Return claims and checks array.');return result
        try:
            _,manager=latest(run,'Strategy Manager')
            required={(t['role'],t['claim']) for t in manager['used_claims']}
            origins=origins_for(run,role);seen=set();prose=[]
            for item in checks:
                if not isinstance(item,dict):raise ValueError('Each verification check must be an object')
                target=item.get('target',{})
                if not isinstance(target,dict) or not isinstance(target.get('role'),str) or not isinstance(target.get('claim'),str):raise ValueError('Verifier target must contain role and claim identifiers')
                key=(target.get('role'),target.get('claim'))
                if key not in required or key in seen:raise ValueError('Verifier target must name one unchecked published claim')
                seen.add(key)
                if item.get('status') not in ('correct','wrong','unsupported'):raise ValueError('Invalid verification status')
                if not all(isinstance(item.get(k,''),str) for k in ('reason','correction')):raise ValueError('Reason and correction must be templates')
                # One line each. Until 2026-11-22 a reason with line breaks left the marks table and was published
                # under it as free text, with a heading of its own. The audit's first cure refused such a reply; no
                # mend covers a refusal here, so a Verifier that repeated it stopped the run at its last stage. The
                # reason is put on one line instead, and the table writes it into one cell (verified_text).
                for k in ('reason','correction'):
                    if k in item:item[k]=' '.join(item[k].split())
                prose.extend([item.get('reason',''),item.get('correction','')])
            if seen!=required:raise ValueError('Verifier must check every published claim exactly once')
            checked=values_for(run,role,{'claims':raw.get('claims',[]),'draft':'\n'.join(prose)})
            result.errors.extend(checked.errors)
            if result.ok:
                rendered=[]
                for item in checks:
                    target=item['target'];value=origins[target['role']][target['claim']]
                    rendered.append({'claim':value,'status':item['status'],
                        'reason':substitute(item.get('reason',''),checked.values),
                        'correction':substitute(item.get('correction',''),checked.values),'source':value,'target':target})
                result.output={'contract':'verification','role':role,'claims':checked.normalized_claims,
                    'template_checks':checks,'checks':rendered}
        except (ValueError,OSError,TypeError,KeyError) as error:result.errors.append(str(error))
        return result
    result.errors.append('Unsupported role contract: '+role)
    return result


def verify_output(run,data):
    role=data.get('role');contract=data.get('contract')
    if contract=='claims':raw={'claims':data.get('claims'),'draft':data.get('template')}
    elif contract=='selection':raw={'claims':data.get('claims',[]),'sections':data.get('section_refs'),'failures':data.get('template_failures')}
    elif contract=='verification':raw={'claims':data.get('claims',[]),'checks':data.get('template_checks')}
    else:return ['Unknown saved role contract']
    result=validate(run,role,raw)
    if result.ok:
        expected={k:v for k,v in data.items() if k!='claim_attempts'}
        if expected!=result.output:return ['Saved role output differs from its checked rendering']
    return result.errors


def report_text(run,sections=None):
    """The compiled report. sections, when given, replaces the Manager's selected text part by part
    (published_sections leaves out the lines the Verifier flagged)."""
    run=Path(run)
    manifest=json.loads((run/'team_report.json').read_text(encoding='utf-8'))
    _,manager=latest(run,'Strategy Manager')
    errors=verify_output(run,manager)
    if errors:raise ValueError('; '.join(errors))
    if manager['failures']:raise ValueError('Manager has unresolved failures')
    if insight_failures(manager['sections']):raise ValueError('Compiled report violates one Insight per role')
    if sections is None:sections=manager['sections']
    content=[manifest['filings_line'],'Run time: '+manifest['run_time'],'']
    core=core_claims_table(run)
    for part in PART_OWNERS:
        content.extend(['## '+part,sections[part]])
        if part=='Overview' and core:content.extend(['',core])
        content.append('')
    return '\n'.join(content)


def core_claims_table(run):
    """The course's 11 core claims, printed by code from the run's saved facts, so that every report states them and
    any two reports compare (the base desk printed them the same way). On 2026-11-20 a report left out revenue growth,
    which the desk had computed: the roles chose which numbers to state. '' for a run without saved facts."""
    run=Path(run)
    try:
        payload=json.loads((run/'facts.json').read_text(encoding='utf-8'));facts=payload.get('facts',{})
        saved=json.loads((run/'calculated_facts.json').read_text(encoding='utf-8'))
    except (OSError,ValueError,AttributeError):return ''
    metrics=saved.get('metrics') or {};quarter=saved.get('quarter_results') or {}
    missing='not established by code'
    # Why no annual fact is stated, when the company facts are not those of the 10-K the desk read (compile_facts).
    annual_problem=payload.get('annual_problem') or ''
    def cell(text):return str(text).replace('|','/').replace('\n',' ')
    def fact(key):
        item=facts.get(key) or {}
        if item.get('value') is None or not item.get('tag') or not item.get('filing'):return missing,annual_problem or 'no saved fact'
        return format_fact(key,item,'value'),f"XBRL tag {item['tag']}, period end {item['period_end']}, filing {item['filing']}"
    def metric(key):
        item=metrics.get(key) or {};value=item.get('value')
        if value is None:return missing,(annual_problem if key!='quarter_revenue_growth' and annual_problem else 'no saved calculation')
        unit=item.get('unit')
        shown=f'{float(value):.2f}%' if unit=='%' else f'{float(value):.3f}' if unit=='ratio' else format_fact(key,item,'value')
        return shown,'computed in code: '+str(item.get('formula',''))
    def release(value_key,source_key,eps=False):
        value=quarter.get(value_key);source=str(quarter.get(source_key) or '').split('; quote:')[0]
        if value is None or not source or source=='source unavailable':return missing,'the release reader found no table row'
        # A loss per share is printed as a loss. The quarter's revenue is printed as the release table prints it, with
        # that table's unit: on 2026-11-22 a table in billions ("18.5") was printed as "18".
        if eps:return ('-' if float(value)<0 else '')+f'${abs(float(value)):,.2f}',source
        unit=quarter.get('revenue_unit')
        return (quarter.get('total_revenue_printed') or f'{float(value):,.0f}')+(f' ({unit})' if unit else '')+', as the release table prints it',source
    period=(facts.get('revenue') or {}).get('period_end') or 'not established'
    rows=[('1',f'Total revenue, fiscal year ended {period}',*fact('revenue')),
          ('2','Revenue growth versus the prior year',*metric('revenue_growth')),
          ('3','Operating income',*fact('operating_income')),
          ('3','Operating margin (operating income / total revenue)',*metric('operating_margin')),
          ('4','Net income attributable to the company',*fact('net_income_attributable_to_parent')),
          ('5','Diluted EPS, GAAP',*fact('diluted_eps')),
          ('6','Return on average equity',*metric('return_on_average_equity')),
          ('7','Debt to equity (long-term debt with its current portion)',*metric('debt_to_equity')),
          ('8','Free cash flow (cash from operations - additions to property and equipment)',*metric('free_cash_flow')),
          ('9',"Latest quarter's revenue",*release('total_revenue','revenue_source')),
          ('10','Quarter growth versus the same quarter last year',*metric('quarter_revenue_growth')),
          ('11',"Latest quarter's diluted EPS, GAAP",*release('diluted_eps','diluted_eps_source',eps=True))]
    lines=['### The 11 core claims, read and computed in code','','| # | Claim | Value | Source |','|---|---|---|---|']
    lines+=[f'| {n} | {cell(claim)} | {cell(value)} | {cell(source)} |' for n,claim,value,source in rows]
    return '\n'.join(lines)


# The body of a part whose every line held a claim the Verifier did not mark correct.
LEFT_OUT_PART='_Left out: every line of this part held a claim the Verifier did not mark correct._'


def published_sections(run,checks):
    """The Manager's sections with every line left out that holds a claim the Verifier did not mark correct.

    A missing claim costs nothing in the audit; a wrong one fails it; and a run that stops publishes no report
    at all. So a flagged claim's line is left out and the rest is published. The lines are cut from the owner's
    saved, checked draft by the range the Manager chose, so the published text is rebuilt from saved files only.
    Returns the sections and, per part, the claims left out with their marks."""
    flagged={(c['target']['role'],c['target']['claim']):c['status'] for c in checks if c.get('status')!='correct'}
    # A claim that repeats another role's claim (from, claim) shares its fate. Until 2026-11-22 a number the Verifier
    # marked wrong was left out of its own part and printed two parts later through the Advisor's reference to it;
    # and a reference could still point at a draft that the Manager had sent back and its author had replaced.
    values=origins_for(run,'Verifier')  # each saved draft's rendered claims, and each author's latest
    changed=True
    while changed:
        changed=False
        for owner in dict.fromkeys(PART_OWNERS.values()):
            try:_,data=latest(run,owner)
            except ValueError:continue
            for claim in data.get('claims') or []:
                if not isinstance(claim,dict) or 'from' not in claim or (owner,claim.get('id')) in flagged:continue
                source=(claim.get('from'),claim.get('claim'))
                then=values.get(claim.get('from_file') or claim.get('from'),{}).get(claim.get('claim'))
                now=values.get(claim.get('from'),{}).get(claim.get('claim'))
                if source in flagged:flagged[(owner,claim['id'])]='repeats a claim marked '+flagged[source].removeprefix('repeats a claim marked ');changed=True
                elif then!=now:flagged[(owner,claim['id'])]='repeats a claim its author has since replaced';changed=True
    _,manager=latest(run,'Strategy Manager')
    sections=dict(manager['sections']);left_out={}
    for part,owner in PART_OWNERS.items():
        ref=manager['section_refs'].get(part);mine={claim:s for (role,claim),s in flagged.items() if role==owner}
        if not isinstance(ref,dict) or not mine:continue
        _,data=latest(run,owner)
        draft=data['draft'].splitlines();template=data['template'].splitlines()
        if len(draft)!=len(template):raise ValueError('The draft of '+owner+' and its template differ in lines')
        keep=[]
        for i in range(ref['start']-1,ref['end']):
            bad=[c for c in dict.fromkeys(PLACEHOLDER.findall(template[i])) if c in mine]
            if bad:left_out.setdefault((part,owner),{}).update((c,mine[c]) for c in bad)
            else:keep.append(draft[i])
        sections[part]='\n'.join(keep) if keep else LEFT_OUT_PART
    return sections,left_out


def published_verified_text(run,code_checks,model_checks):
    """The verified report as published: the marks, a line naming what was left out, and the report without
    those lines. With nothing flagged it is the verified report as before."""
    sections,left_out=published_sections(run,model_checks)
    note=''
    if left_out:
        note=('Left out of the text below, because the Verifier did not mark them correct: '
              +'; '.join(part+', '+owner+' '+', '.join(f'{c} ({s})' for c,s in claims.items()) for (part,owner),claims in left_out.items())+'.')
    return verified_text(report_text(run,sections),code_checks,model_checks,note)


def report_catalog(run):
    _,manager=latest(run,'Strategy Manager')
    if verify_output(run,manager):raise ValueError('Saved manager output failed validation')
    origins=origins_for(run,'Verifier')
    return [{'target':t,'value':origins[t['role']][t['claim']]} for t in manager['used_claims']]


def code_marks(run):
    return [{'claim':c['value'],'status':'correct','reason':'Saved claim, source and rendering match; meaning requires verifier review.',
             'correction':'','source':c['value']} for c in report_catalog(run)]


def verified_text(report,code_checks,model_checks,note=''):
    marks=['| Claim | Mark | Reason | Correction and filing source |','|---|---|---|---|']
    for mark in code_checks+model_checks:
        esc=lambda s:' '.join(str(s).replace('|','\\|').split())  # one line in one cell, whatever the text held
        marks.append('| '+esc(mark['claim'])+' | '+mark['status']+' | '+esc(mark.get('reason',''))+' | '+esc(mark.get('correction','')+' '+mark.get('source',''))+' |')
    if not code_checks and not model_checks:marks.append('| No non-thesis numeric claims found. | correct | No numeric claims to check. | |')
    lines=report.splitlines()
    return lines[0]+'\n\n'+'\n'.join(marks)+('\n\n'+note if note else '')+'\n\n'+'\n'.join(lines[1:])+'\n'


def verify_team_file(run,path):
    """Rebuild the saved report/marks from the actual checked role files."""
    run=Path(run);path=Path(path)
    expected=report_text(run)
    if path.name=='verified_report.md':
        _,verifier=latest(run,'Verifier')
        errors=verify_output(run,verifier)
        if errors:raise ValueError('; '.join(errors))
        aggregate=json.loads((run/'nodes/Verifier/output.json').read_text(encoding='utf-8'))
        marks=code_marks(run)
        if aggregate.get('model_checks')!=verifier or aggregate.get('code_checks')!=marks:raise ValueError('Saved verification summary differs from checked role outputs')
        # A flagged claim does not stop the run: its line must be absent from the published text, which is
        # rebuilt here from the saved files and compared byte for byte below.
        expected=published_verified_text(run,marks,verifier['checks'])
    if path.read_text(encoding='utf-8')!=expected:raise ValueError('Saved report differs from checked role files')
