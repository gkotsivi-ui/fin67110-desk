"""desk_sources.Sources on a stand-in transport: what is sent to SEC EDGAR, to which host, and how fast.

Proposed by the mutation audit of 2026-11-22. No network: the transport is a stand-in and the clock is made up.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desk_sources
from desk_sources import Sources, canonical_url

AGENT = 'Made Up Student made.up@example.edu'
URL = 'https://www.sec.gov/Archives/edgar/data/12345/000000000026000001/a.htm'


class Transport:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = requests.Response()
        response.status_code, response._content = self.status, b'made up'
        return response


class SourcesRequests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.transport = Transport()
        self.sources = Sources(self.folder.name, AGENT, transport=self.transport)

    def test_every_request_carries_the_user_agent(self):
        self.sources.text(URL)
        self.assertEqual(self.transport.calls[0][1]['headers']['User-Agent'], AGENT)

    def test_a_missing_user_agent_stops_before_any_request(self):
        sources = Sources(self.folder.name, '', transport=self.transport)
        with self.assertRaisesRegex(ValueError, 'SEC_USER_AGENT'):
            sources.text(URL)
        self.assertEqual(self.transport.calls, [])

    def test_requests_are_at_least_0_23_seconds_apart(self):
        now, slept = [1000.0], []

        def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds
        with patch.object(desk_sources.time, 'monotonic', lambda: now[0]), patch.object(desk_sources.time, 'sleep', sleep):
            self.sources.text(URL)
            now[0] += 0.05
            self.sources.text(URL.replace('a.htm', 'b.htm'))
        self.assertAlmostEqual(slept[-1], 0.18)

    def test_plain_http_is_refused(self):
        with self.assertRaises(ValueError):
            canonical_url('http://www.sec.gov/Archives/edgar/data/12345/a.htm')

    def test_another_host_is_refused(self):
        for url in ('https://example.com/filing', 'https://www.sec.gov.example.com/a', 'https://sec.gov/a'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical_url(url)

    def test_a_redirect_is_refused_and_never_followed(self):
        transport = Transport(status=302)
        sources = Sources(self.folder.name, AGENT, transport=transport)
        with self.assertRaisesRegex(ValueError, 'redirect'):
            sources.text(URL)
        self.assertIs(transport.calls[0][1]['allow_redirects'], False)


if __name__ == '__main__':
    unittest.main()
