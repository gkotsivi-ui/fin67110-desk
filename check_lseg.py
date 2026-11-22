"""Check the selected LSEG worker; session checks are explicit and never request prices."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from closes_reader import _settings, worker_python

ROOT = Path(__file__).resolve().parent
EXPECTED_VERSION = '2.1.1'
PROBE = r'''
import contextlib, io, json, os, sys
from importlib.metadata import version
from zoneinfo import ZoneInfo
stage = 'library_import'
session = None
try:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import lseg.data as ld
        installed = version('lseg-data')
        stage = 'timezone'
        ZoneInfo('America/New_York')
        if '--session' in sys.argv:
            stage = 'desktop_session'
            session = ld.session.desktop.Definition(app_key=os.environ['LSEG_APP_KEY']).get_session()
            session.open()
            # On 2026-11-21, with Workspace closed, open() returned without an error and left the session
            # closed, and this check printed that the session had opened. Only an opened session passes.
            if session.open_state != ld.OpenState.Opened:
                raise RuntimeError('desktop session not opened')
    result = {'ok': True, 'version': installed, 'session': '--session' in sys.argv}
except Exception as error:
    # Do not print SDK errors: they can contain credentials or account identifiers.
    result = {'ok': False, 'stage': stage, 'error_type': type(error).__name__}
finally:
    if session is not None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                session.close()
            except Exception:
                pass
print(json.dumps(result))
'''


def check(config=None, *, session=False, runner=None):
    """Return a safe status object. Default checks never open an LSEG session."""
    config = _settings() if config is None else config
    runner = subprocess.run if runner is None else runner
    executable = Path(worker_python(config)).expanduser()
    if not executable.is_absolute():
        executable = ROOT / executable
    if not executable.is_file():
        return {'ok': False, 'stage': 'interpreter', 'message':
                'Selected interpreter is missing. Create .venv-lseg or correct LSEG_PYTHON.'}
    key = (config.get('LSEG_APP_KEY') or '').strip()
    if session and (not key or key.startswith(('YOUR_', 'FILL'))):
        return {'ok': False, 'stage': 'configuration', 'message':
                'Set LSEG_APP_KEY in this repository\'s .env before a session check.'}
    try:
        response = runner([str(executable), '-c', PROBE, *(['--session'] if session else [])],
                          cwd=ROOT, env={**os.environ, 'LSEG_APP_KEY': key,
                                         'PYTHONIOENCODING': 'utf-8'},
                          capture_output=True, text=True, encoding='utf-8', timeout=45)
        if response.returncode:
            return {'ok': False, 'stage': 'worker', 'message': 'Worker failed. Reinstall requirements-lseg.txt.'}
        result = json.loads(response.stdout.strip())
        if not isinstance(result, dict) or type(result.get('ok')) is not bool:
            raise ValueError('Invalid probe result')
        if not result['ok']:
            stage = result.get('stage')
            if stage not in {'library_import', 'timezone', 'desktop_session'}:
                stage = 'worker'
            return {'ok': False, 'stage': stage, 'message':
                    'Import/timezone check failed. Install requirements-lseg.txt.' if stage != 'desktop_session' else
                    'Desktop connection failed. Open Workspace, sign in, and check your local App Key and access.'}
        if result.get('version') != EXPECTED_VERSION:
            return {'ok': False, 'stage': 'version', 'message': 'Install the pinned requirements-lseg.txt version.'}
        return {'ok': True, 'stage': 'desktop_session' if session else 'imports', 'message':
                'LSEG 2.1.1 and timezone imports passed.' +
                (' Desktop session opened and closed; no prices requested.' if session else
                 ' Session not tested; use --session with Workspace open.')}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'stage': 'timeout', 'message': 'Worker exceeded 45 seconds. Check Workspace and local setup.'}
    except (OSError, ValueError, TypeError):
        return {'ok': False, 'stage': 'worker', 'message': 'Worker could not run or returned an invalid response.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', action='store_true', help='Open and close a desktop session; no market data request.')
    result = check(session=parser.parse_args().session)
    print(('ok    ' if result['ok'] else 'FIX   ') + result['message'])
    return int(not result['ok'])


if __name__ == '__main__':
    raise SystemExit(main())
