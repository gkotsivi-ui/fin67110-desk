"""One run's saved HTTP/reader evidence and filing inventory. No model routing."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import sys
import time
from urllib.parse import urlparse, parse_qs, urljoin
from unittest.mock import patch

import requests

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT
SEC_SPACING=.23    # seconds between two requests to SEC EDGAR: about four a second, well under its limit of ten
SEC_WAITS=(2,8)    # seconds before a page SEC EDGAR did not give is asked for a second and a third time
LICENSED='sources/licensed'  # in a run folder: raw rows of a licensed price source, never committed


def kept_out_of_the_record(relative):
    """True for a file of a run folder that is not part of the run's public record: licensed rows, the agent
    framework's own storage, and the closes reader's error log. .gitignore keeps the same files out of a commit, so
    a copy of a live run from the repository replays without them."""
    parts=Path(relative).parts
    return parts[:2]==('sources','licensed') or parts[0]=='framework' or parts[-1].startswith('closes_errors_')


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def skill(name):
    scripts=ROOT/'skills'/name/'scripts'
    entry='seeker.py' if name=='us-spinoff-seeker' else 'worksheet.py'
    return load_module('joined_'+name.replace('-','_'),scripts/entry)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    temp=Path(str(path)+'.tmp')
    temp.write_text(json.dumps(data,indent=2,default=str)+'\n',encoding='utf-8');temp.replace(path)


def inside(run,path):
    result=(Path(run)/path).resolve()
    if not result.is_relative_to(Path(run).resolve()):raise ValueError('File leaves the run folder')
    return result


def canonical_url(url):
    parsed=urlparse(url)
    if parsed.path.startswith('/ix') and 'doc' in parse_qs(parsed.query):
        url=urljoin('https://www.sec.gov',parse_qs(parsed.query)['doc'][0]);parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in {'www.sec.gov','data.sec.gov'}:
        raise ValueError('Only HTTPS SEC URLs are accepted by the filing store')
    return parsed._replace(fragment='',query='').geturl()


class Sources:
    def __init__(self,run,user_agent,transport=None):
        self.run=Path(run).resolve();self.user_agent=user_agent
        self.transport=transport or requests.Session().get
        self.phase='setup';self.previous_request=0
        self.path=self.run/'sources.json'
        self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'responses':{},'filings':{}}
        (self.run/'sources/http').mkdir(parents=True,exist_ok=True)

    def save(self):write_json(self.path,self.data)

    def import_cache(self,path):
        target=self.run/'sources/imported';target.mkdir(parents=True,exist_ok=True)
        for source in Path(path).glob('*.txt'):
            dest=target/source.name
            if not dest.exists():shutil.copy2(source,dest)

    def inventory(self,url,form=None,path=None):
        import re
        match=re.search(r'/Archives/edgar/data/(\d+)/(\d{18})/([^/?]+)',url)
        if not match:return
        number=match[2];accession=number[:10]+'-'+number[10:12]+'-'+number[12:]
        item=self.data['filings'].setdefault(accession,{'accession':accession,'cik':match[1],'form':form,'documents':[],'parts':[]})
        if form:item['form']=form
        if url not in item['documents']:item['documents'].append(url)
        if self.phase not in item['parts']:item['parts'].append(self.phase)
        if path:
            local=Path(path).resolve().relative_to(self.run).as_posix();item.setdefault('saved_texts',[])
            if local not in item['saved_texts']:item['saved_texts'].append(local)
            saved=item.setdefault('saved_text_hashes',{})
            current=digest(path)
            if local in saved and saved[local]!=current:raise ValueError('A saved filing text changed: '+local)
            saved[local]=current

    def fetch(self,url,headers,timeout):
        """One SEC page, asked for at most three times. SEC EDGAR answers 429 or 503 when it is busy and asks a
        program to wait and ask again; a connection can also drop. Until 2026-11-22 one such answer among the forty
        to a hundred requests of a run ended the run. Every request, the first or a later one, keeps the spacing."""
        for wait in (*SEC_WAITS,None):
            time.sleep(max(0,self.previous_request+SEC_SPACING-time.monotonic()))
            self.previous_request=time.monotonic()
            try:
                response=self.transport(url,headers=headers,timeout=timeout,allow_redirects=False)
            except (requests.ConnectionError,requests.Timeout,ConnectionError,TimeoutError) as error:
                if wait is None:raise
                problem=type(error).__name__
            else:
                if response.status_code not in (429,500,502,503,504) or wait is None:return response
                problem='status '+str(response.status_code)
                asked=str((getattr(response,'headers',None) or {}).get('Retry-After',''))
                if asked.isdigit():wait=min(60,max(wait,int(asked)))
            print(f'SEC EDGAR did not answer ({problem}); asking again in {wait} seconds.',flush=True)
            time.sleep(wait)

    def response(self,url,**kwargs):
        url=canonical_url(url);key=hashlib.sha256(url.encode()).hexdigest()
        record=self.data['responses'].get(url)
        path=self.run/'sources/http'/(key+'.bin')
        if record:
            path=inside(self.run,record['path'])
            if digest(path)!=record['sha256']:raise ValueError('Cached source changed: '+record['path'])
            content=path.read_bytes()
        else:
            imported=self.run/'sources/imported'/(key+'.txt')
            if imported.exists():content=imported.read_bytes()
            else:
                if not self.user_agent:raise ValueError('SEC_USER_AGENT is missing: write your own name and email in .env')
                headers={**kwargs.pop('headers',{}),'User-Agent':self.user_agent}
                response=self.fetch(url,headers,kwargs.pop('timeout',45))
                if response.status_code in (301,302,303,307,308):
                    raise ValueError('SEC redirect requires an explicit canonical document URL: '+url)
                if response.status_code==403:
                    raise requests.HTTPError('SEC EDGAR refused the request (403). SEC_USER_AGENT in .env must hold your own name and email. '+url,response=response)
                response.raise_for_status();content=response.content
            path.write_bytes(content)
            record={'path':path.relative_to(self.run).as_posix(),'sha256':digest(path),'parts':[]}
            self.data['responses'][url]=record
        if self.phase not in record['parts']:record['parts'].append(self.phase)
        self.inventory(url);self.save()
        result=requests.Response();result.status_code=200;result._content=content
        result.url=url;result.encoding='utf-8'
        return result

    def text(self,url):return self.response(url).text

    def reader(self,method,ticker,*args):
        from desk_timing import elapsed
        with elapsed(self.run,'reader '+method):
            return self._reader(method,ticker,*args)

    def _reader(self,method,ticker,*args):
        from importlib import import_module
        key=hashlib.sha256(json.dumps([method,ticker,*args],default=str).encode()).hexdigest()
        for folder in ('sources/prices',LICENSED):
            path=self.run/folder/(key+'.json')
            if path.exists():return json.loads(path.read_text(encoding='utf-8'))['output']
        reader=import_module('closes_reader')
        output=getattr(reader,method)(ticker,*args)
        # One close is printed in the report with its source, so its answer is part of the run's record. A list of
        # closes is a raw pull of a licensed source: it is saved under sources/licensed, which git ignores and the
        # run's list of files leaves out. Until 2026-11-22 both were saved in sources/prices, and a live run commits
        # that folder.
        path=self.run/(LICENSED if isinstance(output,list) else 'sources/prices')/(key+'.json')
        write_json(path,{'method':method,'ticker':ticker,'args':args,'output':output})
        return output

    def verify(self):
        for item in self.data['responses'].values():
            if digest(inside(self.run,item['path']))!=item['sha256']:
                raise ValueError('Saved SEC source changed: '+item['path'])
        for filing in self.data['filings'].values():
            for path,expected in filing.get('saved_text_hashes',{}).items():
                if digest(inside(self.run,path))!=expected:raise ValueError('Saved filing text changed: '+path)


@contextmanager
def no_fetch():
    def denied(*args,**kwargs):raise RuntimeError('Replay cannot fetch or open a network connection')
    with patch.object(socket.socket,'connect',denied),patch.object(requests.Session,'request',denied):
        yield
