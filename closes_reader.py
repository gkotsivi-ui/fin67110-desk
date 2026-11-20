"""Daily closes, with strict pre-filing selection at 16:00 America/New_York.

LSEG field reference:
https://developers.lseg.com/en/article-catalog/article/the-data-library-for-python-quick-reference-guide-access-layer
Desktop session reference:
https://cdn.refinitiv.com/public/lseg-lib-python-doc/2.0.0.2/book/en/sections/session-layer/session/session-desktop-definition-object.html
No session or file is opened at import time.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo('America/New_York')
NOT_AVAILABLE = 'not available'
ENV_FILE = Path(__file__).with_name('.env')


def filing_time(value: str) -> datetime:
    """A naive command-line timestamp is always Eastern, never machine local."""
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
        raise ValueError('Use YYYY-MM-DDTHH:MM:SS in Eastern time.')
    naive = datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
    aware = naive.replace(tzinfo=EASTERN)
    if aware.utcoffset() != naive.replace(tzinfo=EASTERN, fold=1).utcoffset():
        raise ValueError('Filing time is ambiguous or nonexistent at the Eastern daylight-saving transition.')
    return aware


def _settings():
    # dotenv is deliberately optional in the isolated LSEG worker.
    from dotenv import dotenv_values
    return {**dotenv_values(ENV_FILE), **os.environ}


def _normalize(rows, ticker, start, end, source, include_volume=False):
    result = {}
    for row in rows:
        try:
            day = date.fromisoformat(str(row['date'])[:10])
            price = float(row['close'])
            if start <= day <= end and math.isfinite(price) and price > 0:
                if day in result and result[day]['close'] != price:
                    return NOT_AVAILABLE
                result[day] = {'ticker': ticker, 'date': day.isoformat(), 'close': price,
                               'close_time': datetime.combine(day, time(16), EASTERN).isoformat(),
                               'source': source}
                if row.get('currency'):result[day]['currency']=row['currency']
                if include_volume:
                    try:
                        volume = float(row.get('volume'))
                        if not math.isfinite(volume) or volume < 0: volume = None
                    except (TypeError, ValueError): volume = None
                    result[day].update(volume=volume, currency=row.get('currency') or None,
                                       volume_source=source.replace('TR.PriceClose','TR.Volume'))
        except (KeyError, TypeError, ValueError):
            continue
    return [result[day] for day in sorted(result)] or NOT_AVAILABLE


class ReaderFailure(Exception):
    def __init__(self, stage, error):
        super().__init__(str(error))
        self.stage = stage
        self.error_type = type(error).__name__


def _sanitize(message, config):
    message = str(message)
    for name, value in config.items():
        if re.search(r'key|token|secret|password', name, re.I) and value and len(str(value)) >= 6:
            message = message.replace(str(value), '[REDACTED]')
    message = re.sub(r'(?i)(Bearer\s+)[^\s\"\']+', r'\1[REDACTED]', message)
    message = re.sub(r'''(?i)([\"']?(?:access_token|refresh_token|app[_-]?key|password)[\"']?\s*[:=]\s*[\"']?)[^\s,}\"']+''', r'\1[REDACTED]', message)
    message = re.sub(r'eyJ[A-Za-z0-9_-]+[.][A-Za-z0-9_-]+[.][A-Za-z0-9_-]+', '[REDACTED]', message)
    return message[:6000]


def _diagnostic(config, ticker, start, end, stage, message, **details):
    event = {'time': datetime.now(EASTERN).isoformat(timespec='seconds'),
             'ticker': ticker, 'start': start, 'end': end, 'stage': stage,
             'message': _sanitize(message, config),
             **{key: _sanitize(value, config) for key, value in details.items()}}
    filename = config.get('LSEG_DIAGNOSTICS_FILE') or str(ENV_FILE.parent / 'closes_diagnostics.jsonl')
    try:
        path = Path(filename).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, (json.dumps(event) + '\n').encode())
        finally:
            os.close(descriptor)
    except OSError as error:
        print('Could not save closes diagnostic: ' + _sanitize(error, config), file=sys.stderr)


def _resolve_ticker(ld, ticker):
    conversion = ld.content.symbol_conversion
    response = conversion.Definition(
        symbols=[ticker], from_symbol_type=conversion.SymbolTypes.TICKER_SYMBOL,
        to_symbol_types=[conversion.SymbolTypes.RIC], preferred_country_code='USA',
        asset_class=conversion.AssetClass.EQUITIES,
    ).get_data()
    frame = response.data.df
    columns = {str(column).upper(): column for column in frame.columns}
    if 'RIC' not in columns:
        raise ValueError('LSEG symbol conversion returned no RIC column.')
    choices = {value for value in frame[columns['RIC']] if isinstance(value, str) and value.strip()
               and value.lower() not in {'nan', '<na>'}
               and not re.search(r'_w(?:[.]|$)|[.]WI(?:[.]|$)', value, re.I)}
    if len(choices) != 1:
        raise ValueError(f'LSEG symbol conversion requires one regular U.S. equity RIC for {ticker}; received {sorted(choices)}. Set LSEG_RIC_MAP for an explicit instrument.')
    return choices.pop()


def _lseg_rows(instrument, start, end, app_key, include_volume=False):
    session = None
    stage = 'library_import'
    try:
        import lseg.data as ld
        stage = 'desktop_session'
        session = ld.session.desktop.Definition(app_key=app_key).get_session()
        stage = 'session_open'
        session.open()
        stage = 'session_select'
        ld.session.set_default(session)
        stage = 'data_request'
        fields_requested = ['TR.PriceClose.date', 'TR.PriceClose']
        if include_volume:
            fields_requested += ['TR.Volume', 'TR.PriceClose.currency']
        parameters = {'SDate': start, 'EDate': end, 'Frq': 'D'}
        try:
            frame = ld.get_data(universe=[instrument], fields=fields_requested,
                                parameters=parameters, header_type=ld.HeaderType.NAME)
        except Exception as error:
            if 'unable to resolve' not in str(error).lower() or not re.fullmatch(r'[A-Z][A-Z0-9-]{0,15}', instrument):
                raise
            stage = 'symbol_resolution'
            instrument = _resolve_ticker(ld, instrument)
            stage = 'data_request'
            frame = ld.get_data(universe=[instrument], fields=fields_requested,
                                parameters=parameters, header_type=ld.HeaderType.NAME)
        stage = 'response_parse'
        if frame.empty:
            return {'rows': [], 'instrument': instrument}
        fields = {str(c).lower(): c for c in frame.columns}
        date_field, close_field = fields['tr.priceclose.date'], fields['tr.priceclose']
        rows = []
        for _, row in frame.iterrows():
            try:
                close = float(row[close_field])
                if math.isfinite(close) and close > 0:
                    item = {'date': str(row[date_field])[:10], 'close': close}
                    if include_volume:
                        try:
                            volume = float(row[fields['tr.volume']])
                            if not math.isfinite(volume) or volume < 0: volume = None
                        except (KeyError, TypeError, ValueError): volume = None
                        currency = row.get(fields.get('tr.priceclose.currency'))
                        item.update(volume=volume, currency=str(currency) if currency is not None else None)
                    rows.append(item)
            except (TypeError, ValueError):
                continue
        return {'rows': rows, 'instrument': instrument}
    except Exception as error:
        raise ReaderFailure(stage, error) from error
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def worker_python(config, *, platform=None):
    """Use the explicit interpreter, or this repo's platform-specific LSEG environment."""
    if config.get('LSEG_PYTHON'):
        return config['LSEG_PYTHON']
    platform = os.name if platform is None else platform
    relative = ('Scripts', 'python.exe') if platform == 'nt' else ('bin', 'python')
    return str(Path(__file__).resolve().parent.joinpath('.venv-lseg', *relative))


def daily_closes(ticker: str, start_date: str, end_date: str, *, include_volume=False):
    """Inclusive dates; list of dated closes or the literal 'not available'."""
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError('Start date must not follow end date.')
    ticker = ticker.strip().upper()
    config = {}
    stage = 'configuration'
    try:
        config = _settings()
        filename = (config.get('LSEG_CLOSES_FILE') or '').strip()
        if filename:
            stage = 'file_read'
            path = Path(filename).expanduser()
            if not path.is_absolute():
                path = ENV_FILE.parent / path
            with path.open(newline='', encoding='utf-8-sig') as stream:
                rows = [row for row in csv.DictReader(stream) if row.get('ticker', '').strip().upper() == ticker]
            result = _normalize(rows, ticker, start, end, f'file:{path.resolve()}', include_volume)
            if result == NOT_AVAILABLE:
                _diagnostic(config, ticker, start_date, end_date, 'file_no_valid_closes', 'No valid closes for the requested ticker/dates, or conflicting duplicate dates.')
            return result
        key = (config.get('LSEG_APP_KEY') or '').strip()
        if not key:
            _diagnostic(config, ticker, start_date, end_date, 'configuration', 'LSEG_APP_KEY and LSEG_CLOSES_FILE are both absent or blank.')
            return NOT_AVAILABLE
        instrument = json.loads(config.get('LSEG_RIC_MAP') or '{}').get(ticker, ticker)
        python = worker_python(config)
        stage = 'worker_launch'
        worker = subprocess.run([python, str(Path(__file__).resolve()), '--worker-volume' if include_volume else '--worker', instrument,
                                 start.isoformat(), end.isoformat()],
                                env={**os.environ, 'LSEG_APP_KEY': key, 'PYTHONIOENCODING': 'utf-8'}, capture_output=True, text=True, encoding='utf-8', timeout=180)
        if worker.returncode:
            _diagnostic(config, ticker, start_date, end_date, 'worker_exit', worker.stderr or worker.stdout or 'Worker exited without output.', returncode=worker.returncode, instrument=instrument)
            return NOT_AVAILABLE
        stage = 'worker_response'
        payload = json.loads(worker.stdout.strip().splitlines()[-1])
        if isinstance(payload, dict) and payload.get('error'):
            error = payload['error']
            _diagnostic(config, ticker, start_date, end_date, error.get('stage','worker_error'), error.get('message','Unknown worker error'), error_type=error.get('type',''), instrument=instrument, worker_stderr=worker.stderr)
            return NOT_AVAILABLE
        rows = payload.get('rows', []) if isinstance(payload, dict) else payload
        if not rows:
            _diagnostic(config, ticker, start_date, end_date, 'empty_response', 'LSEG returned no close rows.', instrument=instrument)
            return NOT_AVAILABLE
        source_instrument = payload.get('instrument', instrument) if isinstance(payload, dict) else instrument
        result = _normalize(rows, ticker, start, end, f'LSEG TR.PriceClose ({source_instrument})', include_volume)
        if result == NOT_AVAILABLE:
            _diagnostic(config, ticker, start_date, end_date, 'no_valid_closes', 'Response contained no usable prices/dates or conflicting duplicate dates.', instrument=instrument)
        return result
    except subprocess.TimeoutExpired:
        _diagnostic(config, ticker, start_date, end_date, 'worker_timeout', 'LSEG worker exceeded the 180-second request deadline.')
        return NOT_AVAILABLE
    except Exception as error:
        _diagnostic(config, ticker, start_date, end_date, stage, error, error_type=type(error).__name__)
        return NOT_AVAILABLE


def daily_closes_and_volumes(ticker: str, start_date: str, end_date: str):
    """Dated closes with volume and quote currency; missing fields stay null."""
    return daily_closes(ticker, start_date, end_date, include_volume=True)


def last_close_before(ticker: str, filed: str):
    """Return the most recent available dated close strictly before filing time."""
    cutoff = filing_time(filed)
    end = cutoff.date() if cutoff.time() > time(16) else cutoff.date() - timedelta(days=1)
    # A valid recent close is sufficient; very long vendor requests can fail
    # for an instrument even when its recent history is available.
    rows = daily_closes(ticker, (end-timedelta(days=366)).isoformat(), end.isoformat())
    if rows == NOT_AVAILABLE:
        rows = daily_closes(ticker, '1900-01-01', end.isoformat())
    if rows == NOT_AVAILABLE:
        return NOT_AVAILABLE
    eligible = [row for row in rows if datetime.fromisoformat(row['close_time']) < cutoff]
    return eligible[-1] if eligible else NOT_AVAILABLE


def main():
    if len(sys.argv) == 5 and sys.argv[1] in {'--worker', '--worker-volume'}:
        try:
            print(json.dumps(_lseg_rows(sys.argv[2], sys.argv[3], sys.argv[4], os.environ['LSEG_APP_KEY'], include_volume=sys.argv[1]=='--worker-volume')))
        except Exception as error:
            print(json.dumps({'rows': [], 'error': {'stage': getattr(error, 'stage', 'worker_error'), 'type': getattr(error, 'error_type', type(error).__name__), 'message': _sanitize(error, os.environ)}}))
        return
    parser = argparse.ArgumentParser(description='Print official closes or the last close before filing time.')
    parser.add_argument('ticker')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--filed', help='YYYY-MM-DDTHH:MM:SS, Eastern; strict before')
    group.add_argument('--start', help='Inclusive YYYY-MM-DD')
    parser.add_argument('--end', help='Inclusive YYYY-MM-DD, required with --start')
    args = parser.parse_args()
    if args.start and not args.end:
        parser.error('--end is required with --start')
    print(json.dumps(last_close_before(args.ticker, args.filed) if args.filed else daily_closes(args.ticker, args.start, args.end), indent=2))


if __name__ == '__main__':
    main()
