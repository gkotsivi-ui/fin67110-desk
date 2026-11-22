"""Synthetic setup probes never use credentials or a live desktop session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
import check_lseg

# A stand-in for lseg.data with the parts the probe uses: a desktop session whose open() either opens it or,
# as the real library did with Workspace closed, returns without an error and leaves it closed.
SYNTHETIC_LSEG = '''
import enum, os


class OpenState(enum.Enum):
    Opened = 'opened'
    Pending = 'pending'
    Closed = 'closed'


class _Session:
    def __init__(self):
        self.open_state = OpenState.Closed

    def open(self):
        if os.environ.get('SYNTHETIC_OPENS') == '1':
            self.open_state = OpenState.Opened

    def close(self):
        self.open_state = OpenState.Closed


class _Definition:
    def __init__(self, app_key):
        self.app_key = app_key

    def get_session(self):
        return _Session()


class _Desktop:
    Definition = _Definition


class session:
    desktop = _Desktop
'''


class LsegSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        executable=Path(self.tmp.name)/'python.exe';executable.touch()
        self.config={'LSEG_PYTHON':str(executable)}

    def response(self, **payload):
        return Mock(returncode=0,stdout=json.dumps({'ok':True,'version':'2.1.1',**payload}))

    def test_missing_interpreter_names_setup_without_starting_a_child(self):
        runner=Mock()
        result=check_lseg.check({'LSEG_PYTHON':'missing/synthetic/python'},runner=runner)
        self.assertFalse(result['ok']);self.assertEqual(result['stage'],'interpreter')
        runner.assert_not_called()

    def test_offline_default_never_opens_a_session(self):
        runner=Mock(return_value=self.response())
        self.assertTrue(check_lseg.check(self.config,runner=runner)['ok'])
        self.assertNotIn('--session',runner.call_args.args[0])
        self.assertEqual(runner.call_args.kwargs['encoding'],'utf-8')

    def test_session_requires_key_before_worker_runs(self):
        runner=Mock()
        self.assertEqual(check_lseg.check(self.config,session=True,runner=runner)['stage'],'configuration')
        runner.assert_not_called()

    def test_session_success_passes_key_only_in_environment(self):
        runner=Mock(return_value=self.response(session=True))
        config={**self.config,'LSEG_APP_KEY':'synthetic-test-key'}
        result=check_lseg.check(config,session=True,runner=runner)
        self.assertTrue(result['ok']);self.assertIn('--session',runner.call_args.args[0])
        self.assertEqual(runner.call_args.kwargs['env']['LSEG_APP_KEY'],'synthetic-test-key')
        self.assertNotIn('synthetic-test-key',str(runner.call_args.args))
        self.assertNotIn('synthetic-test-key',str(result))

    def test_sdk_failure_does_not_echo_secrets_or_raw_error(self):
        runner=Mock(return_value=self.response(ok=False,stage='desktop_session',error_type='secret-identity',message='synthetic-test-key'))
        result=check_lseg.check({**self.config,'LSEG_APP_KEY':'synthetic-test-key'},session=True,runner=runner)
        self.assertFalse(result['ok']);self.assertNotIn('synthetic-test-key',str(result));self.assertNotIn('secret-identity',str(result))

    def test_missing_library_wrong_version_and_invalid_response_fail(self):
        for response, stage in [(self.response(ok=False,stage='library_import'),'library_import'),
                                (self.response(version='0.0'),'version'),
                                (Mock(returncode=0,stdout='not JSON'),'worker')]:
            with self.subTest(stage=stage):
                result=check_lseg.check(self.config,runner=Mock(return_value=response))
                self.assertFalse(result['ok']);self.assertEqual(result['stage'],stage)

    def test_timeout_is_bounded_and_does_not_echo_worker_output(self):
        runner=Mock(side_effect=subprocess.TimeoutExpired('synthetic',45,output='secret'))
        result=check_lseg.check(self.config,runner=runner)
        self.assertEqual(result['stage'],'timeout');self.assertNotIn('secret',str(result))


class ProbeSessionStateTests(unittest.TestCase):
    """The probe itself, run on a stand-in library: a desktop session passes only when it reports Opened.

    On 2026-11-21 on Windows, with Workspace closed, the real library's open() returned without an error and
    left the session closed, and check_lseg.py --session printed that the session had opened."""

    def run_probe(self, opens):
        root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root/'lseg'/'data').mkdir(parents=True)
        (root/'lseg'/'__init__.py').write_text('',encoding='utf-8')
        (root/'lseg'/'data'/'__init__.py').write_text(SYNTHETIC_LSEG,encoding='utf-8')
        (root/'lseg_data-2.1.1.dist-info').mkdir()
        (root/'lseg_data-2.1.1.dist-info'/'METADATA').write_text('Metadata-Version: 2.1\nName: lseg-data\nVersion: 2.1.1\n',encoding='utf-8')
        env={**os.environ,'PYTHONPATH':str(root),'LSEG_APP_KEY':'synthetic-test-key','SYNTHETIC_OPENS':'1' if opens else '0'}
        done=subprocess.run([sys.executable,'-c',check_lseg.PROBE,'--session'],env=env,capture_output=True,
                            text=True,encoding='utf-8',timeout=60)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_a_session_left_closed_fails(self):
        result=self.run_probe(opens=False)
        self.assertEqual((result['ok'],result.get('stage')),(False,'desktop_session'))
        self.assertNotIn('synthetic-test-key',json.dumps(result))

    def test_an_opened_session_passes(self):
        result=self.run_probe(opens=True)
        self.assertEqual((result['ok'],result['version'],result['session']),(True,'2.1.1',True))


class LegacyWorkerTests(unittest.TestCase):
    def test_legacy_reader_uses_sdk_worker_and_preserves_query_dates(self):
        from datetime import date
        from unittest.mock import patch
        import closes
        runner=Mock(return_value=Mock(returncode=0,stdout='{"rows":[["2026-01-05",10.0]],"source":"synthetic LSEG"}'))
        with patch.dict('sys.modules',{'lseg':None,'lseg.data':None}), \
             patch('closes_reader._settings',return_value={'LSEG_PYTHON':'synthetic/python'}), \
             patch.object(closes,'setting',return_value='synthetic-secret-key'), \
             patch.object(closes.subprocess,'run',runner):
            result=closes.lseg_closes('EXM',date(2026,1,5),date(2026,1,6))
        self.assertEqual(result,([(date(2026,1,5),10.0)],'synthetic LSEG'))
        argv=runner.call_args.args[0]
        self.assertEqual(argv[0],'synthetic/python');self.assertEqual(argv[-3:],['EXM','2026-01-05','2026-01-06'])
        compile(argv[2],'<legacy worker>','exec')
        self.assertNotIn('synthetic-secret-key',str(argv))
        self.assertEqual(runner.call_args.kwargs['env']['DESK_LSEG_WORKER'],'1')

    def test_legacy_worker_cannot_spawn_itself_when_sdk_is_missing(self):
        from datetime import date
        from unittest.mock import patch
        import closes
        with patch.dict('sys.modules',{'lseg':None,'lseg.data':None}), \
             patch.dict('os.environ',{'DESK_LSEG_WORKER':'1'}), \
             patch.object(closes,'worker_closes') as launch:
            self.assertEqual(closes.lseg_closes('EXM',date(2026,1,5),date(2026,1,6)),([],''))
        launch.assert_not_called()

    def test_failed_legacy_worker_does_not_echo_sdk_errors(self):
        from contextlib import redirect_stderr
        from datetime import date
        from unittest.mock import patch
        import closes,io
        stream=io.StringIO()
        with patch('closes_reader._settings',return_value={}), \
             patch.object(closes,'setting',return_value='synthetic-secret'), \
             patch.object(closes.subprocess,'run',return_value=Mock(returncode=1,stdout='secret identity',stderr='synthetic-secret')), \
             redirect_stderr(stream):
            result=closes.worker_closes('EXM',date(2026,1,5),date(2026,1,6))
        self.assertEqual(result,([],''));self.assertNotIn('synthetic-secret',stream.getvalue())
        self.assertNotIn('identity',stream.getvalue())
