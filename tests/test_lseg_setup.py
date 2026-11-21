"""Synthetic setup probes never use credentials or a live desktop session."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
import check_lseg


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
