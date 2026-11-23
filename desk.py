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

import os

from dotenv import dotenv_values

from desk_sources import ROOT,Sources,digest,inside,kept_out_of_the_record,no_fetch,write_json
from desk_rules import course_footer
from desk_hook import Hook
from desk_timing import elapsed

EASTERN=ZoneInfo('America/New_York')


def tree(run):
    return {p.relative_to(run).as_posix():digest(p) for p in run.rglob('*')
            if p.is_file() and not any(x.startswith('.') for x in p.relative_to(run).parts)
            and p.relative_to(run).parts[0] not in {'hook','replay_audits'} and p.name!='artifacts.json' and p.suffix!='.tmp'
            and not kept_out_of_the_record(p.relative_to(run))}


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
    if (run/'facts.json').exists():walk(json.loads((run/'facts.json').read_text(encoding='utf-8')))
    sources.save()


def setting(name,default=''):
    """One setting as the agent team reads it: the environment's value, or else .env's."""
    try:saved=dotenv_values(ROOT/'.env')
    except UnicodeDecodeError:
        # The same words as the setup check's (check_pipeline.read_settings): until 2026-11-22 the command printed
        # "'utf-8' codec can't decode byte 0xff" here, which names neither .env nor the cure.
        from check_pipeline import NOT_UTF8
        raise ValueError(NOT_UTF8) from None
    return (os.environ.get(name) or saved.get(name) or default).strip()


class DeskRun:
    def __init__(self,options,parts_factory=None,clock=None,hook_factory=Hook,resume=None):
        self.options=options
        # Read before a run folder is made: a .env that cannot be read then leaves no empty folder behind.
        agent=setting('SEC_USER_AGENT')
        if resume:
            # A saved run is finished in its own folder, under its own start time (resume, below).
            self.run=Path(resume).resolve()
            self.state=json.loads((self.run/'desk_run.json').read_text(encoding='utf-8'))
            self.started=datetime.fromisoformat(self.state['started_at'])
        else:
            self.started=clock or datetime.now(EASTERN)
            stamp=self.started.strftime('%Y-%m-%d_%H-%M-%S.%f')
            root=Path(options.runs_root) if options.runs_root else ROOT/'runs'/('live' if options.live else 'practice')
            root=root.resolve()
            root.mkdir(parents=True,exist_ok=True)
            self.run=root/((options.selector.upper() if options.selector!='screen' else 'SCREEN')+'_'+stamp)
            self.run.mkdir()
        # The value the agent team reads: the environment's, or else .env's. Until 2026-11-22 this read .env alone, so
        # a name and email set in the terminal passed the team's check and then failed at the first request.
        self.sources=Sources(self.run,agent)
        self.hook=hook_factory(self.run,self.sources)
        if not resume:
            # The course's three lines, saved at the start so that a replay on another computer writes the same final
            # report. Until 2026-11-22 the group desk's final report had no footer at all (a practice report of
            # 2026-11-20 shows it); anything public ends with these lines (AGENTS.md).
            tools=setting('AI_TOOLS','Claude Code and OpenAI Codex');model=setting('MODEL','a model the run did not record')
            self.state={'schema_version':1,'started_at':self.started.isoformat(),'selector':options.selector,
                        'ticker':None,'status':'running','parts':[],'tools':tools,'model':model,
                        'footer':course_footer(f"{tools} (the desk's code); {model} (the roles and the worksheet's judgment)")}
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
        # The part in progress is saved before it runs, so a run that is killed still says where it was.
        self.state['current_part']=name;self.save()
        began=time.perf_counter();before=tree(self.run)
        try:
            result=action()
            changed=[self.run/p for p,h in tree(self.run).items() if before.get(p)!=h and p!='desk_run.json']
            self.audit(name,changed,**audit_args)
            self.state['parts'].append({'name':name,'seconds':time.perf_counter()-began,'status':'PASS',
                'outputs':[{'path':p.relative_to(self.run).as_posix(),'sha256':digest(p)} for p in changed]})
            self.state.pop('current_part',None)
            self.save();return result
        except BaseException as error:
            # Ctrl+C is not an error of the desk, but the run did stop in this part: until 2026-11-22 it left
            # desk_run.json at "running" for good, with no part named, and --replay refused the folder.
            stopped=isinstance(error,KeyboardInterrupt)
            if not stopped and not isinstance(error,Exception):error_text=f'{type(error).__name__}: {error}'  # a program exit inside a part
            else:error_text=str(error)
            # A final report that did not pass its check does not keep the name of a final report.
            if name=='final report' and (self.run/'final_report.md').exists():
                (self.run/'final_report.md').replace(self.run/'final_report.rejected.md')
            # Audit partial outputs too. Keep the original part failure as the
            # primary error; an output check must never turn it into success.
            changed=[self.run/p for p,h in tree(self.run).items() if before.get(p)!=h and p!='desk_run.json']
            if not stopped:
                try:self.audit(name+' failed outputs',changed,**audit_args)
                except Exception as hook_error:self.state['failed_output_check']=str(hook_error)
            self.state.update(status='stopped' if stopped else 'failed',failed_part=name,
                              error='The run was stopped by hand.' if stopped else error_text)
            self.state.pop('current_part',None)
            self.state['parts'].append({'name':name,'seconds':time.perf_counter()-began,'status':'STOPPED' if stopped else 'FAIL',
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
            print(f'Stopped in part {name}.' if stopped else f'Error: Part {name} failed: {error}',flush=True)
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
        return self.finish(verified)

    def finish(self,verified):
        """The parts after the team: the worksheet and the final report. A resumed run starts here."""
        worksheet=getattr(self,'kept_worksheet',None)
        if worksheet is None:
            worksheet=self.part('worksheet',lambda:self.parts.worksheet(self.started,self.audit))
            # Saved as soon as the worksheet is finished and checked, so that a stop in the final report can keep it.
            self.state['worksheet']=Path(worksheet).relative_to(self.run).as_posix();self.save()
        final=self.run/'final_report.md'
        def compose():
            final.write_text(self.hook.compose(verified,worksheet),encoding='utf-8')
            return final
        self.part('final report',compose,verified=verified,worksheet=worksheet)
        self.state.update(status='complete',verified_report=Path(verified).relative_to(self.run).as_posix(),
                          worksheet=Path(worksheet).relative_to(self.run).as_posix(),final_report=final.name)
        for name in ('failed_part','error','failed_output_check','view_save_error'):self.state.pop(name,None)
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
                records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((run/'hook').glob('*.json'))]
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
            state=json.loads((run/'desk_run.json').read_text(encoding='utf-8'))
            if state.get('status') not in {'complete','failed','stopped'}:
                where=state.get('current_part')
                raise ValueError('Saved run is still active or has no recorded status'+(f': it was last in the part "{where}", and was killed there if no desk is running' if where else ''))
            if (run/'artifacts.json').is_file():saved=json.loads((run/'artifacts.json').read_text(encoding='utf-8'))['files']
            elif state['status']!='complete':
                saved={}
                for path in sorted((run/'hook').glob('*.json')):
                    for item in json.loads(path.read_text(encoding='utf-8')).get('outputs',[]):saved[item['path']]=item['sha256']
                if not saved:raise ValueError('Failed run has no saved output identities')
            else:raise ValueError('Completed run has no artifact manifest')
            for relative,expected in saved.items():
                source=inside(run,relative)
                if not source.is_file() or digest(source)!=expected:raise ValueError('Replay source/output changed: '+relative)
        except Exception as error:
            print(f'Error: Replay part saved evidence failed: {error}',flush=True);raise
        finally:print(f'Part replay saved evidence: {time.perf_counter()-began:.3f} seconds',flush=True)
        sources=Sources(run,'');hook=hook_factory(run,sources)
        if state['status']!='complete':return replay_failed(run,state,hook)
        worksheet=inside(run,state['worksheet']);verified=inside(run,state['verified_report']);final=inside(run,state['final_report'])
        for name in ('seeker','pick','team','worksheet','final report'):
            began=time.perf_counter();print('Part starting: replay '+name,flush=True)
            try:
                if name=='seeker' and (run/'screen.json').exists():
                    from desk_parts import validate_screen
                    from desk_sources import skill
                    # As in the run: only a run that picked from the screen needed a ranked name.
                    picked=(run/'pick.json').exists() and json.loads((run/'pick.json').read_text(encoding='utf-8')).get('selection')=='top ranked entry in saved screen'
                    validate_screen(skill('us-spinoff-seeker'),json.loads((run/'screen.json').read_text(encoding='utf-8')),need_ticker=picked)
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


def resume(path,parts_factory=None,hook_factory=Hook):
    """Finish a run that stopped in its worksheet or its final report, in its own folder, without the team again.

    The worksheet's model call is the last one of a run. Until 2026-11-22 a failure there (a dropped connection, a
    rate limit, an empty credit balance) left a finished and checked team report with no way to a final report but
    the whole run again: new requests, every role paid for again, a new folder and a new start time. A run that
    stopped earlier is run again from the start.

    The files the run saved must be as it left them. The view is not made again: it keeps the time it was first
    saved, or stays "not computed" as the stop left it, because a view is never made later and dated earlier.
    """
    run=Path(path).resolve()
    state=json.loads((run/'desk_run.json').read_text(encoding='utf-8'))
    if state.get('status')=='complete':raise ValueError('This run is complete: there is nothing to resume')
    where=state.get('failed_part') or state.get('current_part')
    if where not in ('worksheet','final report'):
        raise ValueError('Only a run that stopped in its worksheet or its final report can be resumed. This one stopped in '
                         +(f'"{where}"' if where else 'a part it did not record')+'. Run the desk again.')
    verified=run/'verified_report.md'
    if not any(p['name']=='team' and p['status']=='PASS' for p in state['parts']) or not verified.is_file():
        raise ValueError('This run holds no checked team report to resume from')
    # A stop seals every file of the folder in artifacts.json, the view and the run's state among them. A run
    # that was killed sealed nothing: then the files its finished parts recorded are checked. Until 2026-11-22
    # only the parts' records were read, which hold no view.json: an edited view was published and sealed.
    sealed=run/'artifacts.json'
    if state.get('failed_part') and sealed.is_file():saved=json.loads(sealed.read_text(encoding='utf-8'))['files']
    else:
        saved={}
        for part in state['parts']:
            for item in part.get('outputs',[]):saved[item['path']]=item['sha256']  # the last hash the run saved for each file
    for relative,expected in saved.items():
        source=inside(run,relative)
        if not source.is_file() or digest(source)!=expected:raise ValueError('A file of this run changed after it stopped: '+relative)
    # The parts and the settings are made ready before anything in the folder changes: a resume that cannot
    # start leaves the run as the stop left it. Until 2026-11-22 it left the status "running" and the files moved.
    options=parser().parse_args([state['selector']]);validate_local_options(options)
    runner=DeskRun(options,parts_factory=parts_factory,hook_factory=hook_factory,resume=run)
    runner.parts=runner.parts_factory(runner.run,runner.sources,options)
    runner.parts.registry=json.loads((run/'registry.json').read_text(encoding='utf-8')) if (run/'registry.json').is_file() else {'candidates':{}}
    if hasattr(runner.parts,'validate_setup'):runner.parts.validate_setup()
    # A stop in the final report keeps the finished worksheet: its model is not called a second time.
    kept=run/state['worksheet'] if where=='final report' and state.get('worksheet') else None
    runner.kept_worksheet=kept if kept and kept.is_file() else None
    # What the stopped part left behind is kept, out of the way of the new attempt.
    aside=run/'earlier_attempt'
    for old in [*([] if runner.kept_worksheet else run.glob('Spinoff worksheet*')),run/'final_report.md',run/'final_report.rejected.md']:
        if old.is_file():
            aside.mkdir(exist_ok=True);target=aside/old.name;number=1
            while target.exists():number+=1;target=aside/f'{old.stem} ({number}){old.suffix}'
            old.replace(target)
    # The footer names the tools actually used. A run that stopped because one provider refused is often resumed
    # on another: the worksheet's judgment is then the second model's. Until 2026-11-22 the footer saved at the
    # start still named the first for it. The roles' model stays the one that wrote them.
    model=setting('MODEL');first=runner.state.get('model')
    if not runner.kept_worksheet and model and first and model!=first:
        tools=runner.state.get('tools') or setting('AI_TOOLS','Claude Code and OpenAI Codex')
        runner.state['footer']=course_footer(f"{tools} (the desk's code); {first} (the roles); {model} (the worksheet's judgment)")
    runner.state.update(status='running')
    runner.state.setdefault('resumed',[]).append({'time':datetime.now(EASTERN).isoformat(),'from_part':where,'model':model or first})
    runner.save()
    # The folder as this attempt starts is sealed again, so that a second resume finds what the first set aside
    # where the first put it. Until 2026-11-22 the second was refused for the files the first had moved.
    write_json(run/'artifacts.json',{'files':tree(run)})
    return runner


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('selector',nargs='?',help='Ticker, or screen for the top name in the latest seeker report')
    result.add_argument('--replay',type=Path,help='Check a completed or failed run using saved files only; no external calls')
    result.add_argument('--resume',type=Path,help='Finish a run that stopped in its worksheet or its final report, without running the team again')
    result.add_argument('--peers',nargs='*',default=[])
    # Checked when the command is read, as the lab desk does. Until 2026-11-22 a time that does not exist was
    # refused only in the team part, after the seeker and the pick had run and a run folder was saved.
    def filed_time(value):
        from closes_reader import filing_time
        filing_time(value);return value
    result.add_argument('--filed',type=filed_time,help='Explicit Eastern Accepted-time override: YYYY-MM-DDTHH:MM:SS')
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
    for name in ('registry','screen_folder','screen_report','factors','worksheet_rules','persona','runs_root','replay','resume'):
        value=getattr(options,name,None)
        if value is None:continue
        path=Path(value).expanduser()
        path=(ROOT/path).resolve()
        if path!=ROOT.resolve() and ROOT.resolve() not in path.parents:
            raise ValueError('--'+name.replace('_','-')+' must stay inside this repository')
        setattr(options,name,path)


def resume_line(run):
    """The command that finishes this run, as a member types it in the repository's folder.

    Until 2026-11-22 the line said "python", which on a member's computer is often not the desk's environment, and
    the run folder's whole path. It names the Python that ran the desk when that Python is inside this folder.
    """
    def here(path):
        for root in (ROOT,ROOT.resolve()):
            try:return str(Path(path).relative_to(root))
            except ValueError:pass
        return None
    # The Python's path is not resolved: on a Mac the environment's python is a link to one outside this folder.
    python=here(os.path.abspath(sys.executable)) if sys.executable else None
    run=Path(run).resolve()
    return (python or 'python')+' desk.py --resume "'+(here(run) or str(run))+'"'


def say_how_to_resume(runner):
    if runner.state.get('failed_part') in ('worksheet','final report'):
        print('The team report is finished and checked. To finish this run without running the team again: '+resume_line(runner.run),flush=True)


def main(argv=None):
    args=parser().parse_args(argv);runner=None
    try:
        validate_local_options(args)
        if args.replay:
            if args.selector or args.refresh_screen:raise ValueError('--replay cannot fetch, select a new ticker, or refresh the seeker')
            replay(args.replay);return 0
        if args.resume:
            if args.selector or args.refresh_screen:raise ValueError('--resume finishes a saved run: give it the run folder and nothing else')
            runner=resume(args.resume);runner.finish(runner.run/'verified_report.md');return 0
        if not args.selector:raise ValueError('Supply a ticker, screen, --replay or --resume')
        args.selector='screen' if args.selector.lower()=='screen' else args.selector.upper()
        if args.selector!='screen' and not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,15}',args.selector):raise ValueError('Invalid ticker')
        runner=DeskRun(args);runner.execute();return 0
    except KeyboardInterrupt:
        if runner:
            print('Saved run: '+str(runner.run.resolve()),flush=True)
            say_how_to_resume(runner)
        print('Stopped.',file=sys.stderr);return 130
    except Exception as error:
        if runner:
            print('Saved run: '+str(runner.run.resolve()),flush=True)
            say_how_to_resume(runner)
        print('Error: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':
    import utf8_mode;utf8_mode.ensure()
    raise SystemExit(main())
