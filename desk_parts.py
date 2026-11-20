"""Adapters for the existing team and skills. All mutable outputs stay in run."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import gzip
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import patch

from dotenv import dotenv_values

from desk_sources import ROOT,WORKSPACE,skill,inside,write_json,digest

# Where desk.py looks for a seeker registry when --registry is not given (its parser default). A fresh clone has none.
DEFAULT_REGISTRY=ROOT/'spinoff_output'/'registry.json'


def json_path(path):
    path=Path(path)
    compressed=path.with_name(path.name+'.gz')
    return compressed if not path.is_file() and compressed.is_file() else path


def read_saved_json(path):
    path=json_path(path)
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8') as source:return json.load(source)


def copy_saved_json(source,target):
    source=json_path(source)
    if source.suffix=='.gz':
        with gzip.open(source,'rb') as src,Path(target).open('wb') as dst:shutil.copyfileobj(src,dst)
    else:shutil.copy2(source,target)


def latest_screen(folder):
    choices=[]
    for path in sorted(set(Path(folder).glob('Spinoffs, *.json')) | set(Path(folder).glob('Spinoffs, *.json.gz'))):
        data=read_saved_json(path)
        if 'registry' not in data or not data.get('run_time'):continue
        when=datetime.fromisoformat(data['run_time'])
        if when.tzinfo is None:raise ValueError('Screen snapshot has no timezone: '+str(path))
        choices.append((when,path.name,path))
    if not choices:raise ValueError('No dated seeker report snapshot exists; use --refresh-screen YYYY-MM-DD')
    return max(choices)[2]


def validate_screen(module,data,need_ticker=True):
    """Recompute the saved ranks. need_ticker: the run picks the top name, so the screen must have one.
    A run on a requested ticker checks the ranks the same way but does not need a ranked name: a screen that
    ranks nobody is a valid screen, and the requested ticker's spinoff parts are then 'not applicable'."""
    registry=data.get('registry',{});factors=data.get('factors') or registry.get('factors')
    if not factors:raise ValueError('Screen has no saved factor specification')
    pending=set(registry.get('pending_ciks',[]))
    pool=[deepcopy(c) for c in registry.get('candidates',{}).values() if not c.get('drop') and c.get('eligibility')=='included' and c['cik'] not in pending]
    ranked,_=module.rank(pool,factors)
    for row in ranked:
        original=registry['candidates'][row['cik']]
        for key in ('rank','points','total_points'):
            if original.get(key)!=row.get(key):raise ValueError('Saved screen '+key+' differs from the factor calculation')
    if not ranked:
        if need_ticker:raise ValueError('The latest seeker report has no ranked ticker')
        return None,None
    chosen=ranked[0];ticker=(chosen.get('facts',{}).get('ticker') or {}).get('value')
    if not ticker:
        if need_ticker:raise ValueError('Top screen entry has no filing-established regular ticker')
        return None,chosen
    return str(ticker).upper(),chosen


class Parts:
    def __init__(self,run,sources,options):
        self.run=Path(run).resolve();self.sources=sources;self.options=options
        self.seeker=skill('us-spinoff-seeker');self.worksheet_module=skill('spinoff-worksheet')
        self.registry=None;self.snapshot=None;self.picked=None

    def validate_setup(self):
        self.worksheet_module.load_worksheet(self.run/'inputs/spinoff-rules.md')
        if not (self.run/'inputs/persona-why-cheap.md').read_text().strip():
            raise ValueError('Worksheet persona is empty')
        self.seeker.load_factors(str(self.run/'inputs/spinoff_factors.json'))

    def relocate(self,run):self.run=Path(run);self.sources.run=self.run;self.sources.path=self.run/'sources.json'

    @contextmanager
    def shared_seeker(self):
        module=self.seeker;sources=self.sources;original=module.Edgar
        class SavedEdgar(original):
            def __init__(self,user_agent,cache,session=None):
                super().__init__(user_agent,sources.run/'sources/seeker-cache',session)
            def get(self,url,fresh=False,_redirects=0):return sources.text(url)
            def pause(self):pass # Sources serializes and spaces the actual network requests.
        reader=lambda ticker,start,end:sources.reader('daily_closes',ticker,start,end)
        with patch.object(module,'Edgar',SavedEdgar),patch.object(module,'ANALYST',self.run),\
             patch.object(module,'dotenv_values',lambda _:dotenv_values(ROOT/'.env')),\
             patch.object(module,'load_reader',lambda:reader):
            yield module

    def seeker_part(self):
        options=self.options
        if options.registry:
            source=json_path(options.registry)
            if source.is_file():copy_saved_json(source,self.run/'registry.json')
            elif options.selector!='screen' and not options.refresh_screen:
                if Path(options.registry).resolve()!=DEFAULT_REGISTRY.resolve():raise ValueError('Registry does not exist: '+str(source))
                # A run on a ticker needs no seeker (Lab 08: "the seeker when asked"). With no registry the ticker is in
                # none, so its spinoff parts are "not applicable" and the rest runs. A fresh clone has no registry.
                write_json(self.run/'registry.json',{'candidates':{},'complete':False,'pending_ciks':[],
                           'note':'No seeker registry was supplied; this run did not establish whether the ticker is a spinoff.'})
        if options.refresh_screen:
            args=SimpleNamespace(start=options.refresh_screen,factors=str(self.run/'inputs/spinoff_factors.json'),
                 output=str(self.run),index_start=options.index_start,as_of=options.as_of,
                 resume=False,max_candidates=options.max_candidates,no_prices=False)
            with self.shared_seeker() as seeker:path=seeker.run(args)
            self.snapshot=self.run/'screen.json'
            shutil.copy2(Path(path).with_suffix('.json'),self.snapshot)
            shutil.copy2(path,self.run/'screen.md')
        elif options.selector=='screen':
            path=json_path(options.screen_report) if options.screen_report else latest_screen(options.screen_folder)
            if not path.is_file():raise ValueError('Seeker snapshot does not exist')
            self.snapshot=self.run/'screen.json';copy_saved_json(path,self.snapshot)
            report=path.with_suffix('') if path.suffix=='.gz' else path
            if report.with_suffix('.md').is_file():shutil.copy2(report.with_suffix('.md'),self.run/'screen.md')
            self.sources.import_cache(path.parent/'cache')
            write_json(self.run/'registry.json',json.loads(self.snapshot.read_text())['registry'])
        elif not (self.run/'registry.json').exists():
            raise ValueError('No seeker registry was supplied')
        self.registry=json.loads((self.run/'registry.json').read_text())
        write_json(self.run/'seeker_status.json',{'mode':'refreshed' if options.refresh_screen else 'saved snapshot' if options.selector=='screen' else 'not requested',
                  'snapshot':self.snapshot.name if self.snapshot else None})
        if self.snapshot:
            # Only a run that picks from the screen needs a ranked name; a requested ticker does not.
            data=json.loads(self.snapshot.read_text());validate_screen(self.seeker,data,need_ticker=options.selector=='screen')
        return self.snapshot

    def pick(self):
        if self.options.selector=='screen':
            ticker,self.picked=validate_screen(self.seeker,json.loads(self.snapshot.read_text()))
        else:ticker=self.options.selector.upper()
        data={'ticker':ticker,'selection':'top ranked entry in saved screen' if self.picked else 'requested ticker',
              'source':self.snapshot.name if self.snapshot else None,'candidate':self.picked,
              'coverage':'complete' if self.registry.get('complete') else 'partial or not established'}
        write_json(self.run/'pick.json',data)
        return ticker

    def team(self,ticker,started,output_hook):
        with patch.dict(os.environ,{'CREWAI_STORAGE_DIR':str(self.run/'framework')}):
            return self._team(ticker,started,output_hook)

    def _team(self,ticker,started,output_hook):
        from equity_research_desk import Desk
        from equity_research_agent_team import EquityResearchFlow
        sources=self.sources;run=self.run
        class SavedDesk(Desk):
            def create_output_dir(self,company=None):self.output_dir=run;return run
            def get(self,url):return sources.response(url)
            def save_facts(self):
                super().save_facts()
                write_json(run/'calculated_facts.json',{'metrics':self.computed_metrics,'quarter_results':self.quarter_results})
                output_hook('team calculated facts',[run/'facts.json',run/'calculated_facts.json'])
            def step2(self):
                super().step2()
                write_json(run/'filings.json',{name:vars(row) for name,row in self.filings.items()})
            def step3(self):
                names={'10-K':'10-K.txt','10-Q':'10-Q.txt','8-K':'earnings_release_Ex99-1.txt'}
                for form,row in self.filings.items():
                    url=row.release_url if form=='8-K' else row.document_url
                    path=run/names[form]
                    if not path.exists():path.write_text(self.html_to_text(self.get(url).content))
                    sources.inventory(url,form,path);sources.save()
        desk=SavedDesk(ticker,self.options.peers,filed=self.options.filed)
        desk.output_dir=run;desk.run_started_at=started;desk.run_timestamp=started.isoformat()
        # The data-step module imported this function directly, so replace that
        # binding only for this call; all reader evidence is saved in the run.
        with patch('equity_research_desk.last_close_before',lambda symbol,cutoff:sources.reader('last_close_before',symbol,cutoff)):
            flow=EquityResearchFlow(ticker,self.options.peers,filed=self.options.filed,desk=desk,
                                    skill_files=[run/'pick.json',run/'spinoff_status.json',run/'facts.json',run/'calculated_facts.json'],output_hook=output_hook)
            result=flow.kickoff()
        path=Path(str(result))
        if path.resolve()!=run/'verified_report.md' or not path.is_file():raise ValueError('Team did not save its verified report in this run')
        return path

    def spinoff_status(self,ticker):
        matches=[c for c in self.registry.get('candidates',{}).values()
                 if str((c.get('facts',{}).get('ticker') or {}).get('value','')).upper()==ticker]
        if len(matches)>1:raise ValueError('Registry contains conflicting issuer identities for ticker')
        status='applicable' if matches else 'not applicable'
        write_json(self.run/'spinoff_status.json',{'ticker':ticker,'spinoff':status})
        print('Spinoff parts: '+status,flush=True)

    def worksheet(self,started,output_hook):
        w=self.worksheet_module;run=self.run;sources=self.sources
        failures=[]
        def check_failure():
            if failures:
                name,error=failures[0]
                raise RuntimeError(name+' failed: '+str(error)) from error
        def read(method,*args):
            check_failure()
            try:return sources.reader(method,*args)
            except Exception as error:
                failures.append(('reader '+method,error))
                raise
        config=w.load_worksheet(run/'inputs/spinoff-rules.md',now=started)
        persona=(run/'inputs/persona-why-cheap.md').read_text()
        identity=json.loads((run/'facts.json').read_text())
        candidate=w.registry_match(self.registry,identity['ticker'],identity['cik'])
        old_loader=w.load_module
        def shared_loader(name,path):
            if name=='worksheet_edgar':return self.seeker
            return old_loader(name,path)
        # Fetch registration documents before entering build's soft-missing
        # handler. A fetch error must stop the part before a model is called.
        manifest=[]
        with self.shared_seeker(),patch.object(w,'load_module',shared_loader):
            if candidate:
                settings=config.get('liquidity',{})
                manifest=w.fetch_registration(run,candidate,settings.get('start'),settings.get('end'))
                output_hook('worksheet filings',list((run/'Form10').glob('*'))+list((run/'Form4').glob('*')))
            reader=SimpleNamespace(last_close_before=lambda symbol,cutoff:read('last_close_before',symbol,cutoff),
                daily_closes_and_volumes=lambda symbol,start,end:read('daily_closes_and_volumes',symbol,start,end))
            stem=f'Spinoff worksheet, {identity["ticker"]}, {started:%Y-%m-%d}, {started:%H-%M-%S.%f}'
            def judge(_persona,_payload):
                check_failure()
                try:
                    # Read the exact saved skill input file, not a rewritten summary.
                    packet=json.loads((run/(stem+', model input.json')).read_text())
                    output_hook('worksheet model input',[run/(stem+', model input.json')])
                    return w.judge_once(packet['persona'],packet['input'],record_response=lambda value:write_json(run/(stem+', model raw response.json'),value))
                except Exception as error:
                    failures.append(('worksheet judgment',error))
                    raise
            with patch.object(w,'fetch_registration',lambda *a,**k:manifest):
                result=w.build(run,config,persona,self.registry,reader,model_call=judge,now=started)
        check_failure()
        if result.get('model_error_type'):raise ValueError('Worksheet judgment failed: '+str(result.get('model_error_message') or result['model_error_type']))
        return result['files']['markdown']
