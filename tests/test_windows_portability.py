"""Synthetic portability regressions; no LSEG session or external requests."""
import errno
from pathlib import Path
import socket
import unittest
from unittest.mock import Mock, patch

import closes_reader
import portable


class WindowsPortabilityTests(unittest.TestCase):
    def test_default_lseg_interpreter_matches_platform_and_override_wins(self):
        root = Path(closes_reader.__file__).resolve().parent / '.venv-lseg'
        self.assertEqual(Path(closes_reader.worker_python({}, platform='nt')), root/'Scripts/python.exe')
        self.assertEqual(Path(closes_reader.worker_python({}, platform='posix')), root/'bin/python')
        for platform in ('nt', 'posix'):
            self.assertEqual(closes_reader.worker_python({'LSEG_PYTHON': 'custom python'}, platform=platform), 'custom python')

    def test_lseg_worker_receives_selected_interpreter_and_utf8(self):
        response = Mock(returncode=0, stdout='{"rows": []}', stderr='')
        with patch.object(closes_reader, '_settings', return_value={'LSEG_APP_KEY': 'synthetic', 'LSEG_PYTHON': 'custom python'}), \
             patch.object(closes_reader.subprocess, 'run', return_value=response) as run, \
             patch.object(closes_reader, '_diagnostic'):
            closes_reader.daily_closes('EXM', '2026-01-01', '2026-01-02')
        self.assertEqual(run.call_args.args[0][0], 'custom python')
        self.assertEqual(run.call_args.kwargs['encoding'], 'utf-8')
        self.assertEqual(run.call_args.kwargs['env']['PYTHONIOENCODING'], 'utf-8')

    def test_external_addresses_and_hostnames_are_blocked_on_both_socket_methods(self):
        for family, address in [(socket.AF_INET, ('192.0.2.1', 443)),
                                (socket.AF_INET6, ('2001:db8::1', 443)),
                                (socket.AF_INET, ('example.invalid', 443))]:
            with socket.socket(family) as sock, portable.local_sockets_only():
                for method in (sock.connect, sock.connect_ex):
                    with self.assertRaisesRegex(AssertionError, 'external'):
                        method(address)

    def test_loopback_and_asyncio_event_loop_work_under_guard(self):
        import asyncio
        with portable.local_sockets_only():
            with socket.socket() as server:
                server.bind(('127.0.0.1', 0))
                server.listen()
                for method in ('connect', 'connect_ex'):
                    with socket.socket() as client:
                        result = getattr(client, method)(server.getsockname())
                        if method == 'connect_ex':
                            self.assertEqual(result, 0)
                        connection, _ = server.accept()
                        connection.close()
            loop = asyncio.new_event_loop()
            try:
                loop.call_soon_threadsafe(lambda: None)
                loop.run_until_complete(asyncio.sleep(0))
            finally:
                loop.close()

    def test_symlink_permission_failure_skips_but_other_errors_fail(self):
        link, target = Mock(), Path('synthetic')
        link.symlink_to.side_effect = PermissionError(errno.EPERM, 'not permitted')
        with self.assertRaises(unittest.SkipTest):
            portable.symlink_or_skip(self, link, target)
        link.symlink_to.side_effect = FileExistsError(errno.EEXIST, 'already exists')
        with self.assertRaises(FileExistsError):
            portable.symlink_or_skip(self, link, target)
