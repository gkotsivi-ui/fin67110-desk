#!/usr/bin/env python3
"""Codex lifecycle adapter. This file is inactive until hooks are installed."""
from __future__ import annotations

try:
    import fcntl
except ImportError:  # Windows has no fcntl. Lock the file's first byte with msvcrt: one owner at a time, as flock does.
    import msvcrt
    import time as _time

    class fcntl:  # noqa: N801 - the names of fcntl this file uses
        LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

        @staticmethod
        def flock(stream, operation):
            stream.flush()
            position = stream.tell()
            stream.seek(0)
            try:
                if operation & fcntl.LOCK_UN:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    return
                while True:
                    try:
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        return
                    except OSError as exc:
                        if operation & fcntl.LOCK_NB:
                            raise BlockingIOError(*exc.args) from exc
                        _time.sleep(0.05)
            finally:
                stream.seek(position)
import hashlib
import json
import os
from pathlib import Path
import sys

from worksheet_numbers import audit_paths, failure_report

WORKSPACE = Path(__file__).resolve().parents[1]
OUTPUT = WORKSPACE / 'runs'
STATE = WORKSPACE / '.worksheet-audit-state'


def snapshot():
    return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in OUTPUT.rglob('Spinoff worksheet*.md')}


def handle(event):
    name = event.get('hook_event_name')
    if name not in ('SessionStart', 'PostToolUse', 'Stop'):
        raise ValueError('Unsupported hook event')
    session = event.get('session_id')
    if not isinstance(session, str) or not session:
        raise ValueError('Hook event is missing session_id')
    STATE.mkdir(parents=True, exist_ok=True)
    session_key = hashlib.sha256(session.encode()).hexdigest()
    path = STATE / (session_key+'.json')
    with (STATE / (session_key+'.lock')).open('a', encoding='utf-8') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = snapshot()
        if path.exists():
            state = json.loads(path.read_text(encoding='utf-8'))
        elif name == 'SessionStart':
            # Existing worksheets are not outputs of this session.
            state = {'observed': current, 'pending': []}
        else:
            # Missing start event cannot silently exempt existing outputs.
            state = {'observed': {}, 'pending': []}
        pending = set(state['pending'])
        pending.update(p for p, digest in current.items() if state['observed'].get(p) != digest)
        state = {'observed': current, 'pending': sorted(pending)}
        # State contains paths and change hashes only, never numerical evidence.
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, indent=2), encoding='utf-8')
        os.replace(temp, path)
        paths = [Path(p) for p in sorted(pending)]
        if any(not p.is_relative_to(OUTPUT.resolve()) for p in paths):
            raise ValueError('Invalid worksheet path in session state')
        # Always reread the actual worksheets and evidence. Never cache PASS.
        failures = audit_paths(paths, WORKSPACE)
    if failures:
        reason = 'Worksheet check failed. Do not report done. Correct each failed line and run the check again.\n'
        reason += failure_report(failures)
        return {'decision': 'block', 'reason': reason}
    return {}


def main():
    try:
        result = handle(json.load(sys.stdin))
    except Exception as error:
        # Exit zero with an explicit block: generic hook errors can fail open.
        result = {'decision':'block', 'reason':'Worksheet hook could not complete. Do not report done: '+str(error)}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
