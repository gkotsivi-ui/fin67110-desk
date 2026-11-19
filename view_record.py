"""First saved prediction and its scheduled reaction window. No model calls or market reads."""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import exchange_calendars

EASTERN = ZoneInfo('America/New_York')
DIRECTIONS = {'up', 'down', 'flat', 'not computed'}
LABELS = {'more than the price': 'up', 'less than the price': 'down', 'equal to the price': 'flat'}
WINDOW_DEFINITION = ('Last official close at or before filing acceptance to the first official close '
                     'strictly after filing acceptance; XNYS sessions, including holidays and early closes.')


def close_window(filed):
    calendar = exchange_calendars.get_calendar(
        'XNYS', start=(filed - timedelta(days=30)).date().isoformat(),
        end=(filed + timedelta(days=30)).date().isoformat())
    times = [t.to_pydatetime() for t in calendar.schedule['close']]
    return max(t for t in times if t <= filed), min(t for t in times if t > filed)


def normalize_direction(signal):
    direction = LABELS.get(signal, signal)
    if direction not in DIRECTIONS:
        raise ValueError('Prediction must be up, down, flat, or not computed')
    return direction


def acceptance(run):
    """EDGAR Accepted is Eastern. An explicit price-cutoff override is not an acceptance timestamp."""
    path = run / 'filing_time.json'
    evidence = json.loads(path.read_text()) if path.exists() else {}
    raw = evidence.get('edgar_accepted')
    if not raw or raw == 'not available':
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=EASTERN)
    return parsed.astimezone(EASTERN)


def freeze_view(run, ticker, signal, *, clock=None):
    """Create one atomic record. Existing views and historical worksheet records are never backfilled."""
    run = Path(run)
    path = run / 'view.json'
    if path.exists():
        return json.loads(path.read_text())
    for old in run.glob('Spinoff worksheet*.json'):
        if ', model ' not in old.name and isinstance(json.loads(old.read_text()).get('view'), dict):
            return None
    direction = normalize_direction(signal)
    filed = acceptance(run)
    window = {'definition': WINDOW_DEFINITION, 'calendar': 'XNYS',
              'baseline_close_time': None, 'first_close_after_filing_time': None}
    reason = None
    if filed is None:
        direction = 'not computed'
        reason = 'The saved evidence does not establish the filing acceptance time.'
    else:
        before, after = close_window(filed)
        window.update(baseline_close_time=before.astimezone(EASTERN).isoformat(),
                      first_close_after_filing_time=after.astimezone(EASTERN).isoformat())
    # Read the code clock after window calculation, immediately before publication.
    now = (clock or (lambda: datetime.now(EASTERN)))()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Prediction save time must have a UTC offset')
    saved_time = now.isoformat()
    payload = {'schema_version': 2, 'ticker': ticker,
               'filing_time': filed.isoformat() if filed else None,
               'time': saved_time, 'view_time': saved_time, 'direction': direction,
               'reaction_window': window,
               'prediction_basis': 'Code maps the existing low-value versus price comparison to direction. '
                                   'This is not a statistical price-reaction model.',
               'reason': reason}
    # The atomic link prevents both partial reads and replacement by concurrent publishers.
    with tempfile.NamedTemporaryFile(mode='w', dir=run, prefix='.view-', suffix='.tmp', delete=False) as stream:
        json.dump(payload, stream, indent=2)
        stream.write('\n')
        temp = Path(stream.name)
    try:
        try:
            os.link(temp, path)
        except FileExistsError:
            return json.loads(path.read_text())
    finally:
        temp.unlink(missing_ok=True)
    return payload


def validate_view(data):
    """Validate the new schema while leaving older saved schemas unchanged."""
    if data.get('schema_version') != 2:
        return
    normalize_direction(data.get('direction'))
    if data['direction'] not in DIRECTIONS:
        raise ValueError('New prediction records must use canonical direction labels')
    when = datetime.fromisoformat(data['time'])
    if when.tzinfo is None or data.get('view_time') != data['time']:
        raise ValueError('Saved prediction timestamps differ or lack a UTC offset')
    if not data.get('filing_time'):
        if data['direction'] != 'not computed':
            raise ValueError('A prediction without filing acceptance must be not computed')
        return
    filed = datetime.fromisoformat(data['filing_time'])
    if filed.tzinfo is None:
        raise ValueError('Filing acceptance must have a UTC offset')
    before, after = close_window(filed)
    window = data['reaction_window']
    if (datetime.fromisoformat(window['baseline_close_time']) != before
            or datetime.fromisoformat(window['first_close_after_filing_time']) != after):
        raise ValueError('Saved reaction window differs from the filing session window')
