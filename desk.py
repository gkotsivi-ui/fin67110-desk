#!/usr/bin/env python3
"""One fixed-order desk: seeker -> pick -> team -> worksheet -> final, gated by hook."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys
import time
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

from desk_sources import ROOT,Sources,digest,inside,no_fetch,write_json
from desk_hook import Hook
from desk_timing import elapsed

EASTERN=ZoneInfo('America/New_York')


def tree(run):
    return {p.relative_to(run).as_posix():digest(p) for p in run.rglob('*')
            if p.is_file() and not any(x.startswith('.') for x in p.relative_to(run).parts)
            and p.relative_to(run).parts[0] not in {'hook','replay_audits'} and p.name!='artifacts.json' and p.suffix!='.tmp'}


def snapshot_inputs(run,options):
    for source,relative in [(options.worksheet_rules,'inputs/spinoff-rules.md'),
                           (options.persona,'inputs/persona-why-cheap.md'),
                           (options.factors,'inputs/spinoff_factors.json')]:
        source=Path(source)
        if not source.is_file():raise ValueError('Authored input is missing: '+str(source))
        target=run/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    shutil.copytree(ROOT/'pipeline_roles',run/'inputs/roles')


def collect_fact_filings(run,sources):
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('filing','prior_filing') and isinstance(item,str) and re.fullmatch(r'\d{10}-\d{2}-\d{6}',item):
                    sources.data['filings'].setdefault(item,{'accession':item,'form':None,'documents':[],
                        'parts':['saved XBRL facts'],'cik':None})
                else:walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    if (run/'facts.json').exists():walk(json.loads((run/'facts.json').read_text()))
    sources.save()


class DeskRun:
    def __init__(self,options,parts_factory=None,clock=None,hook_factory=Hook):
        self.options=options;self.started=clock or datetime.now(EASTERN)
        stamp=self.started.strftime('%Y-%m-%d_%H-%M-%S.%f')
        root=Path(options.runs_root) if options.runs_root else ROOT/'runs'/('live' if options.live else 'practice')
        root=root.resolve()
        root.mkdir(parents=True,exist_ok=True)
        self.run=root/((options.selector.upper() if options.selector!='screen' else 'SCREEN')+'_'+stamp)
        self.run.mkdir()
        self.sources=Sources(self.run,dotenv_values(ROOT/'.env').get('SEC_USER_AGENT',''))
        self.hook=hook_factory(self.run,self.sources)
        self.state={'schema_version':1,'started_at':self.started.isoformat(),'selector':options.selector,
                    'ticker':None,'status':'running','parts':[]}
        self.save()
        if parts_factory is None:
            from desk_parts import Parts
            parts_factory=Parts
        self.parts_factory=parts_factory
        self.parts=None

    def save(self):write_json(self.run/'desk_run.json',self.state)

    def audit(self,name,paths,**kwargs):
        with elapsed(self.run,'hook ('+name+')'):
            return self.hook.check(name,paths,**kwargs)

    def part(self,name,action,**audit_args):
        print('Part starting: '+name,flush=True);self.sources.phase=name
        began=time.perf_counter();before=tree(self.run)
        try:
            result=action()
            changed=[self.run/p for p,h in tree(self.run).items() if before.get(p)!=h and p!='desk_run.json']
            self.audit(name,changed,**audit_args)
            self.state['parts'].append({'name':name,'seconds':time.perf_counter()-began,'status':'PASS',
                'outputs':[{'path':p.relative_to(self.run).as_posix(),'sha256':digest(p)} for p in changed]})
            self.save();return result
        except Exception as error:
            # Audit partial outputs too. Keep the original part failure as the
            # primary error; an output check must never turn it into success.
            changed=[self.run/p for p,h in tree(self.run).items() if before.get(p)!=h and p!='desk_run.json']
            try:self.audit(name+' failed outputs',changed,**audit_args)
            except Exception as hook_error:self.state['failed_output_check']=str(hook_error)
            self.state.update(status='failed',failed_part=name,error=str(error))
            self.state['parts'].append({'name':name,'seconds':time.perf_counter()-began,'status':'FAIL',
                'outputs':[{'path':p.relative_to(self.run).as_posix(),'sha256':digest(p)} for p in changed]})
            # A stopped run must not fabricate a successful prediction or backdate one.
            ticker=self.state.get('ticker') or (self.options.selector if self.options.selector!='screen' else None)
            if ticker:
                try:
                    from view_record import freeze_view
                    freeze_view(self.run,ticker,'not computed')
                except Exception as view_error:
                    self.state['view_save_error']=str(view_error)
            self.save()
            write_json(self.run/'artifacts.json',{'files':tree(self.run)})
            print(f'Error: Part {name} failed: {error}',flush=True)
            raise
        finally:print(f'Part {name}: {time.perf_counter()-began:.3f} seconds',flush=True)

    def execute(self):
        def prepare():
            snapshot_inputs(self.run,self.options)
            self.parts=self.parts_factory(self.run,self.sources,self.options)
            if hasattr(self.parts,'validate_setup'):self.parts.validate_setup()
        self.part('inputs',prepare)
        self.part('seeker',self.parts.seeker_part)
        def choose():
            ticker=self.parts.pick()
            if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,15}',ticker):raise ValueError('Selected ticker is invalid')
            if self.options.selector=='screen':
                destination=self.run.with_name(ticker+'_'+self.started.strftime('%Y-%m-%d_%H-%M-%S.%f'))
                self.run.rename(destination);self.run=destination
                self.parts.relocate(destination);self.hook.run=destination
            self.state['ticker']=ticker;self.save()
            self.parts.spinoff_status(ticker)
            return ticker
        ticker=self.part('pick',choose)
        def team():
            report=self.parts.team(ticker,self.started,self.audit)
            collect_fact_filings(self.run,self.sources)
            return report
        verified=self.part('team',team)
        worksheet=self.part('worksheet',lambda:self.parts.worksheet(self.started,self.audit))
        final=self.run/'final_report.md'
        def finish():
            final.write_text(self.hook.compose(verified,worksheet))
            return final
        self.part('final report',finish,verified=verified,worksheet=worksheet)
        self.state.update(status='complete',verified_report=Path(verified).relative_to(self.run).as_posix(),
                          worksheet=Path(worksheet).relative_to(self.run).as_posix(),final_report=final.name)
        self.save()
        # Seal source and output identities for offline replay. The audit log
        # and this checksum manifest are evidence, not alternative numeric claims.
        write_json(self.run/'artifacts.json',{'files':tree(self.run)})
        print('Final report: '+str(final.resolve()),flush=True)
        return final


def replay_failed(run,state,hook):
    """Check completed stages and partial outputs, then retain the saved failure."""
    for part in state['parts']:
        name=part['name'];began=time.perf_counter()
        print('Part starting: replay '+name,flush=True)
        try:
            outputs=part.get('outputs')
            if outputs is None: # Older failed runs retained hashes in hook records.
                records=[json.loads(p.read_text()) for p in sorted((run/'hook').glob('*.json'))]
                records=[r for r in records if r.get('part') in (name,name+' failed outputs')]
                outputs=records[-1]['outputs'] if records else []
            paths=[inside(run,r['path']) for r in outputs]
            if part['status']=='PASS':
                hook.check('replay '+name,paths)
            else:
                required={'inputs':[], 'seeker':['registry.json'],'pick':['pick.json','spinoff_status.json'],
                          'team':['report.md','verified_report.md'],'worksheet':[],
                          'final report':['final_report.md']}.get(name,[])
                if name=='worksheet' and not list(run.glob('Spinoff worksheet*.md')):
                    print('Missing output: worksheet Markdown and JSON',flush=True)
                for relative in required:
                    source=inside(run,relative)
                    if not source.is_file():print('Missing output: '+relative,flush=True)
                    if source not in paths:paths.append(source)
                try:hook.check('replay failed '+name,paths)
                except Exception as error:print('Saved output check: '+str(error),flush=True)
                raise ValueError('Saved part '+name+' failed: '+state.get('error','error unavailable'))
        except Exception as error:
            print('Error: Replay part '+name+' failed: '+str(error),flush=True);raise
        finally:print(f'Part replay {name}: {time.perf_counter()-began:.3f} seconds',flush=True)
    raise ValueError('Saved failed run has no recorded failed part')


def replay(path,hook_factory=Hook):
    run=Path(path).resolve()
    with no_fetch():
        began=time.perf_counter();print('Part starting: replay saved evidence',flush=True)
        try:
            state=json.loads((run/'desk_run.json').read_text())
            if state.get('status') not in {'complete','failed'}:raise ValueError('Saved run is still active or has no recorded status')
            if (run/'artifacts.json').is_file():saved=json.loads((run/'artifacts.json').read_text())['files']
            elif state['status']=='failed':
                saved={}
                for path in sorted((run/'hook').glob('*.json')):
                    for item in json.loads(path.read_text()).get('outputs',[]):saved[item['path']]=item['sha256']
                if not saved:raise ValueError('Failed run has no saved output identities')
            else:raise ValueError('Completed run has no artifact manifest')
            for relative,expected in saved.items():
                source=inside(run,relative)
                if not source.is_file() or digest(source)!=expected:raise ValueError('Replay source/output changed: '+relative)
        except Exception as error:
            print(f'Error: Replay part saved evidence failed: {error}',flush=True);raise
        finally:print(f'Part replay saved evidence: {time.perf_counter()-began:.3f} seconds',flush=True)
        sources=Sources(run,'');hook=hook_factory(run,sources)
        if state['status']=='failed':return replay_failed(run,state,hook)
        worksheet=inside(run,state['worksheet']);verified=inside(run,state['verified_report']);final=inside(run,state['final_report'])
        for name in ('seeker','pick','team','worksheet','final report'):
            began=time.perf_counter();print('Part starting: replay '+name,flush=True)
            try:
                if name=='seeker' and (run/'screen.json').exists():
                    from desk_parts import validate_screen
                    from desk_sources import skill
                    # As in the run: only a run that picked from the screen needed a ranked name.
                    picked=(run/'pick.json').exists() and json.loads((run/'pick.json').read_text()).get('selection')=='top ranked entry in saved screen'
                    validate_screen(skill('us-spinoff-seeker'),json.loads((run/'screen.json').read_text()),need_ticker=picked)
                paths={'seeker':[run/'registry.json'],'pick':[run/'pick.json'],
                       'team':[run/'facts.json',run/'report.md',verified],
                       'worksheet':[worksheet,worksheet.with_suffix('.json')],
                       'final report':[final]}[name]
                hook.check('replay '+name,paths,worksheet=worksheet,verified=verified)
            except Exception as error:
                print(f'Error: Replay part {name} failed: {error}',flush=True);raise
            finally:print(f'Part replay {name}: {time.perf_counter()-began:.3f} seconds',flush=True)
        print('Final report: '+str(final),flush=True)
        return final


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('selector',nargs='?',help='Ticker, or screen for the top name in the latest seeker report')
    result.add_argument('--replay',type=Path,help='Check a completed or failed run using saved files only; no external calls')
    result.add_argument('--peers',nargs='*',default=[])
    result.add_argument('--filed',help='Explicit Eastern Accepted-time override: YYYY-MM-DDTHH:MM:SS')
    result.add_argument('--live',action='store_true',help='Save new run under this repository runs/live; default is practice')
    result.add_argument('--runs-root',type=Path,help='Explicit run parent folder')
    result.add_argument('--registry',type=Path,default=ROOT/'spinoff_output/registry.json')
    result.add_argument('--screen-folder',type=Path,default=ROOT/'spinoff_output')
    result.add_argument('--screen-report',type=Path,help='Explicit saved seeker JSON snapshot')
    result.add_argument('--refresh-screen',metavar='YYYY-MM-DD',help='Run the seeker first, using this distribution start')
    result.add_argument('--index-start',default='1994-07-01')
    result.add_argument('--as-of')
    result.add_argument('--max-candidates',type=int)
    result.add_argument('--factors',type=Path,default=ROOT/'spinoff_factors.json')
    result.add_argument('--worksheet-rules',type=Path,default=ROOT/'spinoff-rules.md')
    result.add_argument('--persona',type=Path,default=ROOT/'persona-why-cheap.md')
    return result


def validate_local_options(options):
    """Keep command inputs, run storage, and replay inside this group checkout."""
    for name in ('registry','screen_folder','screen_report','factors','worksheet_rules','persona','runs_root','replay'):
        value=getattr(options,name,None)
        if value is None:continue
        path=Path(value).expanduser()
        path=(ROOT/path).resolve()
        if path!=ROOT.resolve() and ROOT.resolve() not in path.parents:
            raise ValueError('--'+name.replace('_','-')+' must stay inside this repository')
        setattr(options,name,path)


def main(argv=None):
    args=parser().parse_args(argv);runner=None
    try:
        validate_local_options(args)
        if args.replay:
            if args.selector or args.refresh_screen:raise ValueError('--replay cannot fetch, select a new ticker, or refresh the seeker')
            replay(args.replay);return 0
        if not args.selector:raise ValueError('Supply a ticker, screen, or --replay')
        args.selector='screen' if args.selector.lower()=='screen' else args.selector.upper()
        if args.selector!='screen' and not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,15}',args.selector):raise ValueError('Invalid ticker')
        runner=DeskRun(args);runner.execute();return 0
    except Exception as error:
        if runner:print('Saved run: '+str(runner.run.resolve()),flush=True)
        print('Error: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':
    import utf8_mode;utf8_mode.ensure()
    raise SystemExit(main())
