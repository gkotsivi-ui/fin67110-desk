#!/usr/bin/env python3
"""Evidence-first EDGAR spinoff screen. No network or market reads at import."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import gzip
import json
import math
import os
import re
import sys
import time
from contextlib import contextmanager
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cached_property
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dotenv import dotenv_values

WORKSPACE = Path(__file__).resolve().parents[3]
ANALYST = WORKSPACE
FACT_KEYS = ('parent', 'parent_cik', 'distribution_ratio', 'record_date', 'distribution_date', 'ticker')
DATE_TEXT = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}'
REGISTRATIONS = {'10', '10/A', '10-12B', '10-12B/A', '10-12G', '10-12G/A'}
EASTERN = ZoneInfo('America/New_York')


@dataclass(frozen=True)
class Filing:
    cik: str
    name: str
    form: str
    filed: str
    path: str

    @property
    def accession(self): return Path(self.path).stem

    @property
    def folder(self):
        return f'https://www.sec.gov/Archives/edgar/data/{int(self.cik)}/{self.accession.replace("-", "")}/'

    @property
    def url(self): return 'https://www.sec.gov/Archives/' + self.path


@dataclass
class Document:
    filing: Filing
    url: str
    blocks: list[tuple[str, str]]
    raw: str = ""

    @cached_property
    def text(self): return '\n'.join(section + '\n' + text for section, text in self.blocks)


def is_registration(form): return form.upper() in REGISTRATIONS


def parse_form_index(text, forms=None):
    lines = text.splitlines()
    header = next((line for line in lines if 'Form Type' in line and 'Company Name' in line and 'File Name' in line), '')
    if not header: raise ValueError('Unrecognized EDGAR form index; no column header.')
    result = []
    parsed_any = False
    # SEC data rows can use different offsets from their column heading.
    pattern = re.compile(r'^\s*(\S+)\s+(.+?)\s+(\d{1,10})\s+(\d{4}-\d{2}-\d{2})\s+(edgar/data/\S+[.]txt)\s*$')
    for line in lines:
        match = pattern.match(line)
        if match:
            form, name, cik, filed, path = match.groups()
            parsed_any = True
            if forms is None or form in forms:
                result.append(Filing(str(int(cik)), name.strip(), form, filed, path))
    if not parsed_any and any('edgar/data/' in line for line in lines):
        raise ValueError('Index has filing rows but none could be parsed; coverage is unavailable.')
    return result


def index_urls(asof, first=date(1994, 7, 1)):
    result = []
    year, quarter = first.year, (first.month-1)//3+1
    while (year, quarter) <= (asof.year, (asof.month-1)//3+1):
        result.append(f'https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/form.idx')
        quarter += 1
        if quarter == 5: year, quarter = year+1, 1
    return result


def index_date(text):
    match = re.search(r'Last Data (?:Received|Updated)\s*:?\s*([^\n\r]+)', text, re.I)
    if match:
        for fmt in ('%B %d, %Y', '%b %d, %Y', '%Y-%m-%d'):
            try: return datetime.strptime(match[1].strip(), fmt).date().isoformat()
            except ValueError: pass
    return None


class Edgar:
    """Serial, cross-process rate gate; all redirects and retries use the same gate."""
    def __init__(self, user_agent, cache, session=None):
        if not user_agent or not user_agent.strip(): raise ValueError('SEC_USER_AGENT is required in .env.')
        self.user_agent = user_agent.strip()
        self.cache = Path(cache); self.cache.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.interval = .21  # <5/sec, below SEC's 10/sec maximum
        self.errors = []
        self._submissions = {}

    def pause(self):
        # Shared by concurrent seeker processes in the same workspace.
        path = ANALYST / 'spinoff_output/.sec_rate_gate'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            try: previous = float(stream.read() or 0)
            except ValueError: previous = 0
            time.sleep(max(0, previous + self.interval - time.time()))
            stream.seek(0); stream.truncate(); stream.write(str(time.time())); stream.flush()
            fcntl.flock(stream, fcntl.LOCK_UN)

    def get(self, url, fresh=False, _redirects=0):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'www.sec.gov', 'data.sec.gov'}:
            raise ValueError('Only HTTPS SEC URLs are permitted.')
        cache = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.txt')
        if not fresh and cache.exists() and time.time() - cache.stat().st_mtime < 7*86400:
            return cache.read_text(encoding='utf-8')
        for attempt in range(4):
            self.pause()
            response = self.session.get(url, headers={'User-Agent': self.user_agent, 'Accept-Encoding': 'gzip, deflate'}, timeout=45, allow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                if _redirects >= 5: raise RuntimeError('Too many SEC redirects.')
                return self.get(urljoin(url, response.headers['Location']), fresh=True, _redirects=_redirects+1)
            if response.status_code in (429, 503):
                if attempt == 3: break
                retry = response.headers.get('Retry-After', '')
                time.sleep(min(60, max(2 ** (attempt+1), float(retry) if retry.isdigit() else 0)))
                continue
            if response.status_code != 200:
                raise RuntimeError(f'HTTP {response.status_code}: {url}')
            text = response.content.decode('utf-8', errors='replace')
            cache.write_text(text, encoding='utf-8')
            return text
        raise RuntimeError(f'SEC throttled/unavailable after bounded retries: {url}')

    def submissions(self, cik):
        cik = str(int(cik))
        if cik in self._submissions: return self._submissions[cik]
        data = json.loads(self.get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json', fresh=True))
        blocks = [data.get('filings', {}).get('recent', {})]
        for older in data.get('filings', {}).get('files', []):
            try: blocks.append(json.loads(self.get('https://data.sec.gov/submissions/' + older['name'])))
            except Exception as error: self.errors.append(f'Older filing list unavailable for CIK {cik}: {error}')
        rows = []
        for block in blocks:
            for i, accession in enumerate(block.get('accessionNumber', [])):
                rows.append(Filing(cik, data.get('name', ''), block['form'][i], block['filingDate'][i], f'edgar/data/{int(cik)}/{accession}.txt'))
        self._submissions[cik] = (data, rows)
        return data, rows


def html_blocks(text):
    soup = BeautifulSoup(text, 'html.parser')
    for node in soup(['script', 'style', 'ix:header']): node.decompose()
    result, section = [], 'Filing text'
    for element in soup.find_all(['h1','h2','h3','h4','h5','h6','p','tr','div']):
        if element.name == 'div' and element.find(['div','p','table','h1','h2','h3']): continue
        content = ' '.join(element.get_text(' ', strip=True).split())
        if not content: continue
        if element.name.startswith('h') or (len(content) < 130 and element.find(['b','strong']) and not element.find('table')):
            section = content
        if not result or result[-1] != (section, content): result.append((section, content))
    if not result:
        result = [('Filing text', ' '.join(line.split())) for line in soup.get_text('\n').splitlines() if line.strip()]
    for element in soup.find_all():
        concept = str(element.get('name', '')).lower()
        if concept in {'dei:tradingsymbol', 'dei:securityexchangename'}:
            content = ' '.join(element.get_text(' ', strip=True).split())
            if content: result.append((concept, content))
    return result


def read_folder(client, filing):
    """Read all textual exhibits, not just a registration cover page."""
    docs, complete = [], True
    try:
        items = json.loads(client.get(filing.folder + 'index.json'))['directory']['item']
        if any(item['name'].lower().endswith('.pdf') for item in items):
            complete = False
            client.errors.append(f'PDF exhibit requires manual reading: {filing.folder}')
        names = [item['name'] for item in items if re.search(r'\.(?:htm|html|txt)$', item['name'], re.I)
                 and not re.search(r'(?:-index(?:-headers)?|index|FilingSummary)\.', item['name'], re.I)]
        if filing.form in {'4','4/A'}:
            # Index headers and the combined submission are not ownership XML.
            # Passing them to the factor engine falsely invalidates coverage.
            names = [item['name'] for item in items if item['name'].lower().endswith('.xml') and not item['name'].lower().startswith('filingsummary')]
        # The accession .txt duplicates all submitted exhibits when HTML is present.
        if any(re.search(r'\.html?$', name, re.I) for name in names):
            names = [name for name in names if name != filing.accession + '.txt']
        if not names: complete = False
        for name in names:
            try:
                url = urljoin(filing.folder, name)
                raw = client.get(url)
                docs.append(Document(filing, url, html_blocks(raw), raw))
            except Exception as error:
                complete = False; client.errors.append(f'Unreadable exhibit: {filing.folder}{name}: {error}')
    except Exception as error:
        complete = False; client.errors.append(f'Unreadable filing folder: {filing.folder}: {error}')
    return docs, complete


def new_candidate(cik, name):
    return {'cik': str(int(cik)), 'name': name, 'facts': {key: None for key in FACT_KEYS},
            'history': [], 'conflicts': [], 'drop': None, 'drop_history': [],
            'listing_evidence': None, 'trading_evidence': None, 'distribution_evidence': None, 'us_listing_evidence': None,
            'metrics': {}, 'prices': {'first': None, 'latest': None}, 'limitations': [], 'read_filings': []}


def evidence(doc, section, quote):
    return {'filing': doc.url, 'accession': doc.filing.accession, 'form': doc.filing.form,
            'filed': doc.filing.filed, 'section': section, 'quote': quote}


def put_fact(c, key, value, doc, section, quote):
    if quote not in doc.text: raise ValueError('Fact quotation is not in the read filing.')
    incoming = {'value': value, **evidence(doc, section, quote)}
    prior = c['facts'].get(key)
    conflict = next((v for v in c['conflicts'] if v['field'] == key and v['filed'] == doc.filing.filed), None)
    if conflict: return
    if prior and prior['filed'] > incoming['filed']: return
    if prior and prior['value'] != value:
        c['history'].append({'field': key, **prior})
        if prior['filed'] == incoming['filed']:
            c['conflicts'].append({'field': key, 'filed': incoming['filed'], 'observations': [prior, incoming]})
            c['facts'][key] = None
            return
    c['facts'][key] = incoming
    for old_conflict in c['conflicts']:
        if old_conflict['field'] == key and old_conflict['filed'] < incoming['filed']:
            old_conflict['resolved_by'] = incoming


def parsed_date(value):
    for fmt in ('%B %d, %Y', '%B %d %Y', '%Y-%m-%d'):
        try: return datetime.strptime(value, fmt).date().isoformat()
        except ValueError: pass
    return None


def value(c, key): return (c['facts'].get(key) or {}).get('value')


def label_dates(text, label):
    matches = re.findall(rf'\b{label}\s*(?:is|was|will be|:|\|)?\s*({DATE_TEXT})', text, re.I)
    if label == r'record date':
        matches += re.findall(rf'({DATE_TEXT})\s*,?\s*\(?\s*(?:the\s+)?["“]?record date\b',text,re.I)
    # Explicit alternatives are not a fact, even if the first date matches a pattern.
    if re.search(rf'{label}[^.;]{{0,120}}\b(?:or|between)\b', text, re.I): return []
    return list({parsed_date(item) for item in matches if parsed_date(item)})


def apply_documents(c, docs, complete=True, parent=False):
    registration_docs = [d for d in docs if is_registration(d.filing.form)]
    for d in sorted(docs, key=lambda item: (item.filing.filed, item.filing.accession)):
        if d.filing.url not in c['read_filings']: c['read_filings'].append(d.filing.url)
        form = d.filing.form
        if not parent and form in {'10-Q', '10-K', '4'}:
            c['trading_evidence'] = evidence(d, 'Own registrant filing list', f'{form} filed {d.filing.filed}')
        if not parent and form == 'CERT':
            c['listing_evidence'] = evidence(d, 'Exchange certification', d.text[:500])
        spin_context = bool(re.search(r'\b(?:spin[ -]?off|distribution|information statement|separation)\b', d.text, re.I))
        for section, text in d.blocks:
            # Parent filings can discuss many transactions; require an explicit child reference.
            related = not parent or c['name'].casefold() in text.casefold() or bool(value(c, 'ticker') and re.search(r'\b' + re.escape(value(c,'ticker')) + r'\b', text))
            if not related: continue
            if section == 'dei:tradingsymbol' and re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,15}', text) and not when_issued(text):
                put_fact(c, 'ticker', text, d, section, text)
            if section == 'dei:securityexchangename' and re.search(r'Nasdaq|New York Stock Exchange|NYSE', text, re.I):
                c['us_listing_evidence'] = evidence(d, section, text)
            if re.search(r'\b(?:Nasdaq|New York Stock Exchange|NYSE American|NYSE Arca)\b', text, re.I) and (form == 'CERT' or re.search(r'listing|exchange|trading symbol|registered', text, re.I)):
                c['us_listing_evidence'] = evidence(d, section, text)
            if not spin_context: continue
            actual = re.search(r'\b(?:completed|consummated|effected)\b[^.]{0,200}\bdistribution\b|\bdistributed\b[^.]{0,200}\b(?:stockholders|shareholders)\b', text, re.I)
            if actual and parent:
                target = text[actual.start():]
                identifiers = [c['name']] + ([value(c,'ticker')] if value(c,'ticker') else [])
                if not any(re.search(r'(?<!\w)' + re.escape(identifier) + r'(?!\w)', target, re.I) for identifier in identifiers):
                    continue
            if actual and (parent or re.search(r'\bparent\b', text, re.I)):
                c['distribution_evidence'] = evidence(d, section, text)
                if c['drop'] and d.filing.filed > c['drop']['filed']:
                    c['drop_history'].append(c['drop']); c['drop'] = None
            for key, label in [('record_date', r'record date'), ('distribution_date', r'distribution date')]:
                dates = label_dates(text, label)
                if len(dates) == 1: put_fact(c, key, dates[0], d, section, text)
            # Actual distribution announcements with a single unambiguous date.
            completion_dates={parsed_date(match) for match in re.findall(
                r'\bOn\s+('+DATE_TEXT+r'),?\s+(?:the\s+)?(?:spin[ -]?off|distribution)\s+was\s+(?:completed|consummated|effected)\b',text,re.I)}-{None}
            if len(completion_dates)==1:
                put_fact(c,'distribution_date',completion_dates.pop(),d,section,text)
            if actual and not re.search(r'\brecord date\b|\bincorporated\b|\bformed\b',text,re.I):
                dates = {parsed_date(match) for match in re.findall(DATE_TEXT, text, re.I)} - {None}
                if len(dates) == 1: put_fact(c, 'distribution_date', dates.pop(), d, section, text)
            if actual and form in {'8-K','8-K/A'} and re.search(r'\bcompleted today\b|\beffective as of today\b',text,re.I):
                # "Today" refers to an explicitly dated release, never the
                # filing date or a record date elsewhere in the announcement.
                datelines=list(re.finditer(rf'(?:—|–|--)\s*({DATE_TEXT})\s*(?:—|–|--)',d.text[:5000],re.I))
                dates={parsed_date(m[1]) for m in datelines}-{None}
                if len(dates)==1:
                    start=min(datelines[0].start(),d.text.find(text))
                    end=max(datelines[0].end(),d.text.find(text)+len(text))
                    put_fact(c,'distribution_date',dates.pop(),d,'Release dateline and completion statement',d.text[start:end])
            for pattern in (r'\bdistribution (?:will occur|will be made|is expected to occur|was made|occurred) on\s+(' + DATE_TEXT + r')',):
                dates = {parsed_date(match) for match in re.findall(pattern, text, re.I)} - {None}
                if len(dates) == 1 and not re.search(r'\bor\b|\bbetween\b', text, re.I):
                    put_fact(c, 'distribution_date', dates.pop(), d, section, text)
            parent_name = re.search(r'\bParent(?: company)?\s*:\s*([^;\n]+?)(?=\.(?:\s|$)|;|$)', text, re.I)
            if not parent_name:
                parent_name = re.search(r'\b(?:wholly[ -]owned |majority[ -]owned )?subsidiary of\s+([^;\n]+?)(?=\.(?:\s|$)|;|$)', text)
            if parent_name: put_fact(c, 'parent', parent_name[1].strip().rstrip('.'), d, section, text)
            parent_cik = re.search(r'\bParent(?: company)?\s+CIK\s*:\s*(\d{1,10})\b', text, re.I)
            if parent_cik: put_fact(c, 'parent_cik', str(int(parent_cik[1])), d, section, text)
            ratio = re.search(r'\bdistribution ratio\s*:\s*([^;\n]+?)(?=\.(?:\s|$)|;|$)', text, re.I)
            if not ratio:
                ratio = re.search(r'\b((?:one|two|three|four|five|ten|\d+(?:\.\d+)?)\s+(?:share|shares)[^.]{0,130}?\bfor (?:every|each)\b[^.;]{1,100})', text, re.I)
            if ratio and not re.search(r'\[|\]|to be determined|TBD', ratio[1], re.I):
                put_fact(c, 'distribution_ratio', ratio[1].strip(), d, section, text)
            symbol = re.search(r'\b(?:regular[- ]way trading symbol|trading symbol|ticker symbol)\s*(?:is|will be|:|\|)\s*["“]?((?-i:[A-Z][A-Z0-9.\-]{0,15}))\b', text, re.I)
            if symbol and symbol[1] not in {'TBD','NA','NONE','UNKNOWN'} and not when_issued(symbol[1]): put_fact(c, 'ticker', symbol[1], d, section, text)
    if registration_docs and not c['distribution_evidence']:
        combined = '\n'.join(d.text for d in registration_docs)
        reason = None
        if complete and (not re.search(r'\binformation statement\b', combined, re.I) or re.search(r'\b(?:contains|includes|has) no information statement\b', combined, re.I)): reason = 'Form 10 with no information statement in the readable filing folder'
        fund = re.search(r'\b(?:we are|registrant is|company is)\s+(?:a|an)\s+(?:registered\s+)?(?:closed[- ]end\s+)?(?:investment fund|investment company|fund|business development company)\b', combined, re.I)
        existing = re.search(r'\b(?:we are|registrant is|company is)\s+registering\s+(?:our|its)\s+existing\s+outstanding\s+shares\b', combined, re.I)
        if fund: reason = 'Registrant is a fund'
        if existing: reason = 'Registrant is registering existing shares'
        if reason:
            d = next((d for d in registration_docs if (fund and fund[0] in d.text) or (existing and existing[0] in d.text)), registration_docs[-1])
            c['drop'] = {'reason': reason, **evidence(d, 'Registration review', (fund[0] if fund else existing[0] if existing else 'No information statement found across all readable textual exhibits'))}


def parent_filings(client, c, asof, start=None):
    cik = value(c, 'parent_cik')
    if not cik: return []
    _, rows = client.submissions(cik)
    return sorted((row for row in rows if row.form in {'8-K', '8-K/A'} and row.filed <= asof.isoformat() and (start is None or row.filed >= start.isoformat())), key=lambda r:(r.filed,r.accession))


def stage(c, asof, window):
    if not c['trading_evidence']: return 'listing approved' if c['listing_evidence'] else 'registered'
    distribution = value(c, 'distribution_date')
    if not distribution: return 'trading'
    days = (asof-date.fromisoformat(distribution)).days
    if 1 <= days <= window: return 'in its window'
    if days > window: return 'past it'
    return 'trading'


def when_issued(ticker):
    return bool(re.search(r'(?:_w(?:[.]|$)|[.\-_/ ]WI(?:[.]|$)|[.\-_/ ]W[.\-_/ ]I(?:[.]|$)|[.\-_/ ]WHEN[.\-_/ ]?ISSUED$)', ticker, re.I))


def prices(c, asof, reader, horizon=None):
    c['prices'] = {'first': None, 'latest': None}
    c['metrics'].pop('return_since_first_close', None)
    c['metrics'].pop('early_price_performance', None)
    distribution, ticker = value(c,'distribution_date'), value(c,'ticker')
    if not distribution or not ticker or not c['trading_evidence']:
        c['limitations'].append('Prices unavailable: distribution date, regular ticker or trading evidence missing.'); return
    if when_issued(ticker):
        c['limitations'].append('When-issued symbol rejected.'); return
    first_day = date.fromisoformat(distribution) + timedelta(days=1)
    if first_day > asof: return
    try: rows = reader(ticker, first_day.isoformat(), asof.isoformat())
    except Exception: rows = 'not available'
    if rows == 'not available' or not rows:
        c['limitations'].append('Closes reader: not available.'); return
    clean = []
    for row in rows:
        try:
            day, close = date.fromisoformat(row['date']), float(row['close'])
            vendor = re.search(r'LSEG TR[.]PriceClose \(([^)]+)\)', row.get('source',''))
            is_wi = row.get('when_issued') or when_issued(row.get('ticker', ticker)) or (vendor and when_issued(vendor[1]))
            if first_day <= day <= asof and math.isfinite(close) and close > 0 and not is_wi:
                clean.append({**row, 'date': day.isoformat(), 'close': close})
        except (KeyError, ValueError, TypeError): continue
    if not clean: return
    clean.sort(key=lambda row: row['date'])
    first, latest = clean[0], clean[-1]
    c['prices'] = {'first': first, 'latest': latest}
    c['metrics']['return_since_first_close'] = {'value': round(latest['close']/first['close']-1, 12),
        'source': f'computed: {price_text(latest)} / {price_text(first)} - 1'}
    if horizon is not None:
        if len(clean) > horizon:
            horizon_close = clean[horizon]
            c['prices']['early_horizon'] = horizon_close
            c['metrics']['early_price_performance'] = {'value': round(horizon_close['close']/first['close']-1, 12),
                'source': f"computed, {horizon} trading-day intervals after first close: {price_text(horizon_close)} / {price_text(first)} - 1"}
        else:
            c['limitations'].append(f'Early price performance unavailable: need first close plus {horizon} later trading closes; have {len(clean)} source rows.')


def eligibility(c, start):
    distribution = value(c, 'distribution_date')
    if not distribution: return 'unknown', 'Distribution date missing; start-date eligibility cannot be established.'
    if date.fromisoformat(distribution) < start: return 'before start', 'Distribution date is before the supplied start date.'
    return 'included', ''


PDF_FACTOR_NAMES = {
    'Insider ownership / incentives': 'insider_ownership_pct',
    'Size relative to parent': 'size_relative_to_parent',
    'Insider buying': 'insider_buying',
    'Early price performance': 'early_price_performance',
    'Debt transferred': 'debt_to_assets',
    'Absolute market cap': 'absolute_market_cap',
    'Analyst recommendations': 'analyst_recommendations',
    'Unwanted selling pressure': 'unwanted_selling_pressure',
}


def parse_pdf_factors(rows, text):
    window = re.search(r'Window length:\s*(\d+)\s+days', text, re.I)
    horizon = re.search(r'Early-performance horizon:\s*(\d+)\s+trading days', text, re.I)
    if not window or not horizon:
        raise ValueError('PDF must explicitly state window length and early-performance horizon.')
    factors = []
    for row in rows:
        if not row or len(row) < 4: continue
        label = ' '.join(str(row[0] or '').split())
        if label in {'Factor', 'Total', ''}: continue
        if label not in PDF_FACTOR_NAMES:
            raise ValueError('Unrecognized PDF factor; add its test and measurement rule first: ' + label)
        factors.append({'name': PDF_FACTOR_NAMES[label], 'label': label,
                        'direction': str(row[1]).strip().lower(), 'weight': float(row[2]),
                        'measured_as': ' '.join(str(row[3] or '').split())})
    if {f['label'] for f in factors} != set(PDF_FACTOR_NAMES):
        raise ValueError('PDF factor table is incomplete; no fallback to example weights.')
    if not math.isclose(sum(f['weight'] for f in factors), 1, abs_tol=1e-9):
        raise ValueError('PDF factor weights must total 1.00.')
    return validate_factors({'window_days': int(window[1]),
                             'early_performance_trading_days': int(horizon[1]), 'factors': factors,
                             'insider_buying_measure': 'count',
                             'limitations': ['Analyst recommendations: no EDGAR/closes-reader source; zero weight.',
                                             'Unwanted selling pressure: measured indirectly by relative size; no separate observation; zero weight.']})


def load_pdf_factors(path):
    import pdfplumber
    path = Path(path).expanduser().resolve()
    rows, texts = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or '')
            for table in page.extract_tables(): rows.extend(table)
    result = parse_pdf_factors(rows, '\n'.join(texts))
    result.update(source_pdf=str(path), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def load_factors(path):
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() == '.pdf': return load_pdf_factors(path)
    config = json.loads(path.read_text())
    if 'source_pdf' in config:
        source = Path(config['source_pdf']).expanduser()
        return load_pdf_factors(source if source.is_absolute() else path.parent/source)
    if 'early_return_days' in config:
        horizon = config['early_return_days']
        if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0:
            raise ValueError('early_return_days must be a positive integer of trading-day intervals.')
        config['early_performance_trading_days'] = horizon
    if isinstance(config.get('factors'), dict):
        aliases = {'insider_ownership':'insider_ownership_pct', 'relative_size':'size_relative_to_parent',
                   'early_return':'early_price_performance', 'market_cap':'absolute_market_cap',
                   'analyst_count':'analyst_recommendations', 'unwanted_selling':'unwanted_selling_pressure'}
        config['factors'] = [{'name': aliases.get(name,name), 'configured_name':name, **settings}
                             for name,settings in config['factors'].items()]
    config.setdefault('limitations', [])
    zero_names = {f['name'] for f in config.get('factors', []) if f.get('weight') == 0}
    if 'analyst_recommendations' in zero_names:
        config['limitations'].append('Analyst count: no EDGAR/closes-reader source; zero weight.')
    if 'unwanted_selling_pressure' in zero_names:
        config['limitations'].append('Unwanted selling: represented by relative size; no separate observation; zero weight.')
    return validate_factors(config)


def validate_factors(config):
    if not isinstance(config.get('window_days'), int) or isinstance(config['window_days'], bool) or config['window_days'] <= 0:
        raise ValueError('window_days must be a positive integer, in calendar days after distribution.')
    factors = config.get('factors')
    if not isinstance(factors, list) or not factors: raise ValueError('Supply at least one factor.')
    names = set()
    for factor in factors:
        name, weight, direction = factor.get('name'), factor.get('weight'), factor.get('direction')
        if not isinstance(name, str) or not name or name in names or not isinstance(weight, (int,float)) or isinstance(weight,bool) or not math.isfinite(weight) or weight < 0 or direction not in {'higher','lower'}:
            raise ValueError('Each factor needs a unique name, finite nonnegative weight, and direction higher or lower.')
        names.add(name)
    if not any(f['weight'] > 0 for f in factors): raise ValueError('At least one weight must be positive.')
    return config


def factor_blank_reason(c, key):
    return c.get('factor_missing_reasons',{}).get(key,'no usable sourced value was extracted or established')


def valid_metric(c, key):
    item=c.get('metrics',{}).get(key) or {}
    v=item.get('value')
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and bool(item.get('source'))


def rank(candidates, config):
    ranked, unranked = [], []
    for c in candidates:
        c.pop('unranked_reason',None)
        if not value(c,'distribution_date'):
            c['unranked_reason']='Distribution date missing; eligibility and window cannot be established.'
            unranked.append(c);continue
        if c.get('stage') != 'in its window': continue
        ranked.append(c)
        c['points']={};c['total_points']=0;c['factor_blanks']={}
        c['factor_labels']={f['name']:f.get('configured_name',f['name']) for f in config['factors']}
    for factor in config['factors']:
        key,weight=factor['name'],factor['weight']
        observed=[c for c in ranked if valid_metric(c,key)] if weight else []
        for c in ranked:
            points=0
            if weight and c in observed:
                v=c['metrics'][key]['value']
                others=[x['metrics'][key]['value'] for x in observed if x is not c]
                wins=sum((v>x if factor['direction']=='higher' else v<x) for x in others)
                ties=sum(v==x for x in others)
                points=weight if not others else weight*(wins+ties/2)/len(others)
            elif weight:
                c['factor_blanks'][key]=factor_blank_reason(c,key)
            c['points'][key]=points;c['total_points']+=points
    ranked.sort(key=lambda c:(-c['total_points'],c['cik']))
    for c in ranked:c['rank']=1+sum(other['total_points']>c['total_points'] for other in ranked)
    return ranked,unranked


def md(text): return str(text).replace('|','\\|').replace('\n',' ')


def price_text(row):
    return 'not available (price date: blank)' if not row else f"{row['close']:g} (price date: {row['date']}; {row.get('source','closes reader')})"


def source_text(item):
    if not item: return 'blank — not established by a readable filing'
    return f"{md(item.get('value',''))} — [{md(item['form'])} {item['accession']}]({item['filing']}), section: {md(item['section'])}; quote: {md(item['quote'])}"


def report(candidates, ranked, unranked, asof, index_day, limitations, run_day=None, factors=None):
    price_days = sorted({row['date'] for c in candidates for row in c['prices'].values() if row})
    lines = [f"Run date: {(run_day or asof).isoformat()} | Price date: {', '.join(price_days) or 'blank (not available)'} | Index date: {index_day or 'blank (not available)'}", '', '# U.S. spinoff screen', '', f'As-of date: {asof.isoformat()}', '', '## In their window, by rank', '']
    partial=[limit for limit in limitations if limit.startswith('PARTIAL RUN:')]
    if partial:lines[6:6]=['Coverage: PARTIAL — '+partial[0], '']
    if ranked:
        factor_names = list(ranked[0]['points'])
        lines += ['| Rank | Registrant / CIK | Parent | Distribution date | Window ends | Total points | ' + ' | '.join(md(ranked[0].get('factor_labels',{}).get(n,n))+' points' for n in factor_names) + ' | First close | Latest close |',
                  '|---|---|---|---|---|---|' + '---|'*(len(factor_names)+2)]
        for c in ranked:
            lines.append(f"| {c['rank']} | {md(c['name'])} / {c['cik']} | {md(value(c,'parent') or 'blank')} | {value(c,'distribution_date') or 'blank'} | {c.get('window_end') or 'blank'} | {c['total_points']:.6g} | " + ' | '.join(f"{c['points'][n]:.6g}" + (f" (blank: {md(c['factor_blanks'][n])})" if n in c.get('factor_blanks',{}) else '') for n in factor_names) + f" | {md(price_text(c['prices']['first']))} | {md(price_text(c['prices']['latest']))} |")
        for c in ranked:
            for key in factor_names:
                item = c['metrics'].get(key) if valid_metric(c,key) else None
                detail=(f"blank; 0 points; reason: {md(c['factor_blanks'][key])}" if key in c.get('factor_blanks',{}) else 'not scored (zero weight; no observation required)')
                lines.append(f"\nFactor {md(c.get('factor_labels',{}).get(key,key))} for CIK {c['cik']}: " + (f"{md(item['value'])}; {md(item['source'])}" if item else detail) + '\n')
    else: lines.append('No names can be ranked in the window from the established facts.')
    lines += ['', '## Unranked / missing dates', '']
    combined = {c['cik']:c for c in unranked}
    for c in candidates:
        if not c['drop'] and not value(c,'distribution_date'):
            c['unranked_reason'] = 'Distribution date missing; eligibility and window cannot be established.'; combined[c['cik']] = c
    for c in combined.values(): lines.append(f"- {md(c['name'])} / {c['cik']}: {md(c['unranked_reason'])}")
    if not combined: lines.append('None.')
    lines += ['', '## Watch list — registered names not yet trading', '']
    watch = [c for c in candidates if not c['drop'] and not c['trading_evidence']]
    lines += [f"- {md(c['name'])} / {c['cik']}: {c.get('stage','registered')}; U.S. listing {'established' if c.get('us_listing_evidence') else 'unconfirmed'}" for c in watch] or ['None.']
    lines += ['', '## Other retained stages', '']
    other = [c for c in candidates if not c['drop'] and c['trading_evidence'] and c.get('stage') != 'in its window']
    lines += [f"- {md(c['name'])} / {c['cik']}: {c.get('stage','registered')}" for c in other] or ['None.']
    lines += ['', '## Dropped and why', '']
    dropped = [c for c in candidates if c['drop']]
    for c in dropped: lines.append(f"- {md(c['name'])} / {c['cik']}: {md(c['drop']['reason'])}; {source_text(c['drop'])}")
    if not dropped: lines.append('None.')
    lines += ['', '## Registry facts and evidence', '']
    for c in candidates:
        lines += [f"### {md(c['name'])} / {c['cik']}"]
        for metric,item in c.get('metrics',{}).items():
            lines.append(f"- Observed factor {md(metric)}: {md(item['value'])}; {md(item.get('source','source unavailable'))}")
        for key in FACT_KEYS: lines.append(f'- {key}: {source_text(c["facts"].get(key))}')
        for key in ('listing_evidence','trading_evidence','distribution_evidence','us_listing_evidence'):
            if c.get(key): lines.append(f'- {key}: {source_text(c[key])}')
        for conflict in (v for v in c['conflicts'] if not v.get('resolved_by')): lines.append(f"- Unresolved conflicting {conflict['field']} observations on {conflict['filed']}; field blank pending a later filing.")
        for limit in dict.fromkeys(c['limitations']): lines.append('- Limit: ' + md(limit))
    if factors:
        lines += ['', '## Factor requirements', '']
        for factor in factors['factors']:
            label=factor.get('configured_name',factor['name'])
            requirement='not required for ranking' if factor['weight']==0 else 'blank values receive 0 points'
            lines.append(f"- {md(label)}: weight {factor['weight']:g}; {requirement}.")
    lines += ['', '## What the data cannot show', '']
    if factors:
        lines += [f"- {md(f.get('configured_name',f['name']))}: weight 0; no source required; no observation supplied or scored." for f in factors['factors'] if f['weight']==0]
    lines += ['- ' + md(item) for item in dict.fromkeys(limitations)]
    lines += ['- Blank facts were not established; no dates, ratios or prices were estimated.',
              '- Blank extraction results do not prove that a fact is absent from a filing. Unsupported layouts, incomplete coverage, ambiguous evidence or incompatible dates require filing-level review.',
              '- A filing list is trading evidence under this screen rule; it is not exchange trade-tape verification.',
              '- First close means the first available regular-symbol close after distribution in the configured reader, not an intraday trade or a when-issued price. Gaps in the reader cannot prove an earlier close did not exist.',
              '- Indexes update nightly; recent filings, unreadable exhibits, unsupported wording and incomplete histories can leave candidates undiscovered or unranked.',
              '- Registry evidence and any conflicts require review before acting. Missing factor values receive 0 points without estimated values. Each observed factor is compared only with other observed values in the window; weights are not redistributed.', '', 'screens, not recommendations']
    return '\n'.join(lines) + '\n'


def save_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(tmp, 'wt', encoding='utf-8') as output:
        if path.suffix == '.gz':json.dump(data, output, ensure_ascii=False, separators=(',', ':'))
        else:json.dump(data, output, ensure_ascii=False, indent=2)
        output.write('\n')
    tmp.replace(path)


def report_stem(now, start):
    return f'Spinoffs, {now:%Y-%m-%d}, {now:%H-%M-%S.%f}, start {start:%Y-%m-%d}'


def save_report(root, text, now, start):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    path = root / (report_stem(now,start)+'.md')
    path.write_text(text, encoding='utf-8'); return path


def load_reader():
    # This only loads the local module; the caller controls whether it is invoked.
    path = ANALYST / 'closes_reader.py'
    spec = importlib.util.spec_from_file_location('spinoff_closes_reader', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.daily_closes


def resolve_parent(client, c, indexed, asof):
    """Resolve an exact parent name to one CIK; no fuzzy issuer guessing."""
    if value(c,'parent_cik') or not value(c,'parent'): return
    normalize = lambda text: re.sub(r'\W+', '', text).casefold()
    matches = {row.cik for row in indexed if normalize(row.name) == normalize(value(c,'parent'))}
    if len(matches) != 1:
        c['limitations'].append('Parent CIK not established by an exact unique registrant match.'); return
    cik = matches.pop()
    _, rows = client.submissions(cik)
    latest = sorted((r for r in rows if r.filed <= asof.isoformat()), key=lambda r:(r.filed,r.accession), reverse=True)
    if not latest: return
    row = latest[0]
    index_url = row.folder + row.accession + '-index.html'
    raw = client.get(index_url)
    soup = BeautifulSoup(raw, 'html.parser')
    text = ' '.join(soup.get_text(' ', strip=True).split())
    if not re.search(r'\bCIK\s*[:#]?\s*0*' + re.escape(cik) + r'\b', text, re.I):
        c['limitations'].append('Parent identity not confirmed in the filing index.'); return
    parent_doc = Document(row, index_url, [('Filing index — registrant identity', text)])
    put_fact(c, 'parent_cik', cik, parent_doc, 'Filing index — registrant identity', text)


def factor_engine():
    path=Path(__file__).with_name('factor_data.py')
    spec=importlib.util.spec_from_file_location('spinoff_factor_engine',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def plan_filings(rows,start,asof):
    return [r for r in rows if r.filed<=asof.isoformat() and
            (is_registration(r.form) or r.form=='CERT' or
             (r.form in {'8-K','8-K/A'} and r.filed>=start.isoformat()))]


def rules_digest():
    return hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('factor_data.py').read_bytes()).hexdigest()


def checkpoint_key(start,asof,factors,no_prices):
    payload={'rules':rules_digest(),'start':start.isoformat(),'asof':asof.isoformat(),
             'factors':factors,'no_prices':no_prices}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def populate_factors(c,docs,parent_docs,form4_docs,form4_complete,asof,reader):
    engine=factor_engine()
    own=engine.extract(docs);parent=engine.extract(parent_docs)
    c['factor_facts']=own;c['parent_factor_facts']=parent
    for key in ('insider_ownership_pct','debt_to_assets'):
        observation=own[key]
        if observation:
            c['metrics'][key]={**observation,'source':observation.get('source') or
                f"{observation['filing']}; {observation['section']}; quote {observation['quote']}"}
    distribution=value(c,'distribution_date')
    if distribution:
        purchases=engine.insider_purchases(form4_docs,c['cik'],distribution,asof.isoformat(),complete=form4_complete)
        if purchases:c['metrics']['insider_buying']=purchases
    first=c['prices'].get('first');parent_close=None
    # A parent query is useful only if both dated share counts are known.
    if first and reader and engine.shares_on(own,first['date']) and engine.shares_on(parent,first['date']):
        symbol=engine.ticker(parent_docs)
        if symbol and not when_issued(symbol):
            try:rows=reader(symbol,first['date'],first['date'])
            except Exception:rows='not available'
            if isinstance(rows,list):
                valid=[r for r in rows if r.get('date')==first['date'] and not when_issued(r.get('ticker',symbol)) and not r.get('when_issued') and isinstance(r.get('close'),(int,float)) and math.isfinite(r['close']) and r['close']>0 and not when_issued((re.search(r'LSEG TR[.]PriceClose \(([^)]+)\)',r.get('source','')) or [None,''])[1])]
                if len(valid)==1:parent_close=valid[0];c['prices']['parent_first']=parent_close
    c['metrics'].update(engine.cap_metrics(own,parent,first,parent_close))
    c['factor_missing_reasons']={
        'insider_ownership_pct':'no unambiguous exact group percentage extracted from the registration ownership table',
        'debt_to_assets':'matching total-debt and total-assets inputs were not established in one pro-forma column',
        'insider_buying':'ownership XML coverage is incomplete or amendments/transactions remain unresolved',
        'absolute_market_cap':'first close or eligible shares outstanding reported on or before its date were not established',
        'size_relative_to_parent':'child/parent identity, eligible shares, same-date prices or compatible currencies were not established',
        'early_price_performance':'first close and the required later trading-day close were not established',
    }
    missing=[key for key in ('insider_ownership_pct','debt_to_assets','insider_buying','absolute_market_cap','size_relative_to_parent') if key not in c['metrics']]
    if missing:c['limitations'].append('Missing or ambiguous sourced factor observations: '+', '.join(missing)+'. Share counts use the latest eligible reported observation on or before the price date, with its observation date and filing date disclosed.')
    c['limitations'].append('Insider buying counts disclosed code-P purchases; code P can include private purchases and late filings can change the count. Quote currencies are used as supplied; no FX conversion.')


@contextmanager
def diagnostics_output(path):
    previous=os.environ.get('LSEG_DIAGNOSTICS_FILE')
    path=Path(path)
    path.touch(mode=0o600,exist_ok=True)
    os.environ['LSEG_DIAGNOSTICS_FILE']=str(path)
    try:
        yield path
    finally:
        if previous is None:
            os.environ.pop('LSEG_DIAGNOSTICS_FILE',None)
        else:
            os.environ['LSEG_DIAGNOSTICS_FILE']=previous


def diagnostic_events(path):
    events=[]
    for line in Path(path).read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({'stage':'diagnostic_parse','message':'A diagnostic record could not be decoded.'})
    return events


def run(args):
    now = datetime.now(EASTERN); asof = date.fromisoformat(args.as_of) if args.as_of else now.date()
    start = date.fromisoformat(args.start)
    if start > asof: raise ValueError('Start date must not follow as-of date.')
    factors = load_factors(args.factors)
    root = Path(args.output).resolve(); root.mkdir(parents=True, exist_ok=True)
    registry_path = root / 'registry.json'
    if not registry_path.exists() and (root / 'registry.json.gz').exists():
        registry_path = root / 'registry.json.gz'
    # Prevent two seekers from overwriting each other's registry.
    with (root/'.run.lock').open('a+') as lock, diagnostics_output(root/f'closes_errors_{now:%Y-%m-%d_%H%M%S_%f}.jsonl') as diagnostics:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('A seeker run already owns this registry.')
        config = {**dotenv_values(ANALYST/'.env'), **os.environ}
        client = Edgar(config.get('SEC_USER_AGENT',''), root/'cache')
        indexed, dates, limitations = [], [], list(factors.get('limitations', []))
        if factors.get('source_pdf'):
            limitations.append(f"Factor specification: {factors['source_pdf']}; SHA-256 {factors['source_sha256']}; window {factors['window_days']} days; early horizon {factors['early_performance_trading_days']} trading days.")
        first_index = date.fromisoformat(args.index_start)
        if first_index > date(1994,7,1): limitations.append(f'Index scan deliberately starts {first_index}; earlier registrations can be missed. Registry names are still revisited.')
        urls = index_urls(asof, first_index)
        for i, url in enumerate(urls,1):
            print(f'Index {i}/{len(urls)}: {url}', flush=True)
            try:
                text = client.get(url, fresh='/'+str(asof.year)+'/QTR'+str((asof.month-1)//3+1)+'/' in url)
                indexed.extend(row for row in parse_form_index(text, forms=REGISTRATIONS | {'CERT','8-K','8-K/A'}) if row.filed <= asof.isoformat())
                if index_date(text): dates.append(index_date(text))
                else: limitations.append('Index has no readable Last Data Received header: ' + url)
            except Exception as error: limitations.append(f'Index unavailable: {url}: {error}')
        if registry_path.exists():
            opener = gzip.open if registry_path.suffix == '.gz' else open
            with opener(registry_path, 'rt', encoding='utf-8') as source:registry = json.load(source)
        else:registry = {'version':1,'candidates':{}}
        registrations = defaultdict(list)
        for row in indexed:
            if is_registration(row.form): registrations[row.cik].append(row)
        for cik in list(registry['candidates']): registrations[cik]  # revisit, including prior drops
        reader = None if args.no_prices else load_reader()
        index_by_cik = defaultdict(list)
        for row in indexed: index_by_cik[row.cik].append(row)
        diagnostic_cursor=0
        print(f'Closes diagnostics: {diagnostics}',flush=True)
        checkpoint=checkpoint_key(start,asof,factors,args.no_prices)
        completed=0;skipped=0;total=len(registrations)
        for position,(cik, registration_rows) in enumerate(registrations.items(),1):
            existing=registry['candidates'].get(cik)
            if getattr(args,'resume',False) and existing and existing.get('checkpoint')==checkpoint:
                skipped+=1;continue
            if getattr(args,'max_candidates',None) is not None and completed>=args.max_candidates:
                break
            old = registry['candidates'].get(cik)
            c = old or new_candidate(cik, registration_rows[-1].name)
            c['limitations'] = []; c['metrics'] = {}; c['prices'] = {'first':None,'latest':None}
            # Rebuild dated evidence from readable sources to avoid retaining an old as-of state.
            if args.as_of and old: c = new_candidate(cik, c['name'])
            c.pop('rank',None);c.pop('points',None);c.pop('total_points',None)
            print(f'Registrant {position}/{total}: CIK {cik}', flush=True)
            try:
                before_errors=len(client.errors)
                identity, own = client.submissions(cik)
                history_complete=len(client.errors)==before_errors
                own = [r for r in own if r.filed <= asof.isoformat()]
                c['name'] = identity.get('name') or c['name']
                # Current ticker metadata is used only to find a symbol, never as a filing fact.
                c['limitations'].append('Only a symbol explicitly read from a filing is used for prices; current metadata is not backdated.')
                rows = {r.path:r for r in plan_filings(registration_rows + index_by_cik[cik] + own,start,asof)}
                docs, complete = [], True
                for number,row in enumerate(sorted(rows.values(),key=lambda r:(r.filed,r.accession)),1):
                    print(f'  Filing {number}/{len(rows)}: {row.form} {row.filed} {row.accession}',flush=True)
                    part, ok = read_folder(client, row); docs.extend(part); complete &= ok
                apply_documents(c, docs, complete=complete)
                # The rule uses the new issuer's own list, not an insider's index row.
                proof = next((r for r in sorted(own,key=lambda r:(r.filed,r.accession)) if r.form in {'10-Q','10-K','4'}),None)
                if proof:
                    part, ok = read_folder(client, proof)
                    if part: apply_documents(c, part, complete=ok)
                resolve_parent(client, c, indexed, asof)
                parent_docs=[]
                for row in parent_filings(client, c, asof, start=start):
                    part, ok = read_folder(client, row);parent_docs.extend(part);apply_documents(c, part, complete=ok, parent=True)
                c['stage'] = stage(c, asof, factors['window_days'])
                c['eligibility'], c['eligibility_reason'] = eligibility(c,start)
                if c['eligibility'] != 'before start' and not c['drop']:
                    distribution = value(c,'distribution_date')
                    if distribution: c['metrics']['days_since_distribution'] = {'value': (asof-date.fromisoformat(distribution)).days, 'source': f'computed: run date {asof} minus filing-established distribution date {distribution}; {c["facts"]["distribution_date"]["filing"]}'}
                    if reader: prices(c,asof,reader,horizon=factors.get('early_performance_trading_days'))
                    else: c['limitations'].append('Prices explicitly disabled for this run.')
                    if c['stage']=='in its window':
                        # Periodic reports can establish share counts and pro-forma inputs.
                        for row in own:
                            if row.form in {'10-Q','10-K'} and start.isoformat()<=row.filed<=asof.isoformat():
                                part,ok=read_folder(client,row);docs.extend(part)
                        if value(c,'parent_cik'):
                            _,parent_rows=client.submissions(value(c,'parent_cik'))
                            periodic=[r for r in parent_rows if r.form in {'10-Q','10-K'} and start.isoformat()<=r.filed<=asof.isoformat()]
                            for row in periodic:
                                part,ok=read_folder(client,row);parent_docs.extend(part)
                        forms=[r for r in own if r.form in {'4','4/A'} and distribution<=r.filed<=asof.isoformat()]
                        form_docs=[];form_complete=history_complete
                        for row in forms:
                            part,ok=read_folder(client,row);form_docs.extend(part);form_complete &= ok
                        populate_factors(c,docs,parent_docs,form_docs,form_complete,asof,reader)
            except Exception as error:
                c['limitations'].append(f'Incomplete candidate read: {error}')
                c['stage'] = stage(c,asof,factors['window_days'])
                c['eligibility'], c['eligibility_reason'] = eligibility(c,start)
            events=diagnostic_events(diagnostics)
            c['price_errors']=events[diagnostic_cursor:]
            diagnostic_cursor=len(events)
            for error in c['price_errors']:
                detail=f"Closes error for {error.get('ticker',cik)} at {error.get('stage','unknown')}: {error.get('message','')}"
                c['limitations'].append(detail)
                print(detail,flush=True)
            c['window_end'] = (date.fromisoformat(value(c,'distribution_date'))+timedelta(days=factors['window_days'])).isoformat() if value(c,'distribution_date') else None
            c['checkpoint']=checkpoint
            registry['candidates'][cik] = c
            completed+=1
            save_json(registry_path,registry)
            save_json(root/'progress.json',{'checkpoint':checkpoint,'total_candidates':total,'processed_this_run':completed,'resumed_candidates':skipped,'last_cik':cik,'updated':datetime.now(EASTERN).isoformat()})
        pending=[cik for cik in registrations if registry['candidates'].get(cik,{}).get('checkpoint')!=checkpoint]
        if pending:limitations.append(f'PARTIAL RUN: {len(pending)} candidates remain unread for this snapshot. Repeat with --resume to continue; this is not a complete screen.')
        shown = [c for c in registry['candidates'].values() if c.get('eligibility') != 'before start' and c.get('checkpoint')==checkpoint]
        pool = [c for c in shown if not c['drop'] and c.get('eligibility')=='included']
        ranked, unranked = rank(pool,factors)
        registry.update(pending_ciks=pending,complete=not pending,last_run=now.isoformat(),start_date=start.isoformat(),as_of=asof.isoformat(),index_date=max(dates) if dates else None,factors=factors)
        save_json(registry_path,registry)
        limitations += client.errors
        limitations.append(f'Closes error log: {diagnostics}; captured errors: {diagnostic_cursor}.')
        text = report(shown,ranked,unranked,asof,registry['index_date'],limitations,run_day=now.date(),factors=factors)
        target = save_report(root,text,now,start)
        save_json(target.with_suffix('.json'), {'run_time':now.isoformat(),'diagnostics_file':str(diagnostics),'diagnostics_count':diagnostic_cursor,'index_urls':urls,'factors':factors,'limitations':limitations,'registry':registry})
        print(f'Report: {target}\nRegistry: {registry_path}')
        return target


def main():
    parser = argparse.ArgumentParser(description='Find filing-established U.S. spinoffs and rank the distribution window.')
    parser.add_argument('--start', required=True, help='Inclusive distribution date, YYYY-MM-DD')
    parser.add_argument('--factors', required=True, help='Factor PDF, JSON factor file, or JSON source_pdf pointer')
    parser.add_argument('--output', default=str(ANALYST/'spinoff_output'))
    parser.add_argument('--index-start', default='1994-07-01', help='Earliest index to scan; a later cutoff is incomplete coverage')
    parser.add_argument('--as-of', help='Use filings and closes no later than this YYYY-MM-DD; history is rebuilt')
    parser.add_argument('--resume',action='store_true',help='Continue the same dated snapshot; skip already processed candidates, not a fresh intraday refresh')
    parser.add_argument('--max-candidates',type=int,help='Process at most this many new candidates; save a clearly labeled partial report')
    parser.add_argument('--no-prices', action='store_true', help='Do not invoke the closes reader; missing-price factors receive zero points')
    args = parser.parse_args()
    if args.max_candidates is not None and args.max_candidates<1:parser.error('--max-candidates must be positive')
    try: run(args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__': main()
