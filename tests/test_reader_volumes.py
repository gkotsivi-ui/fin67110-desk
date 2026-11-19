import sys,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import closes_reader as c
class ReaderVolumesTests(unittest.TestCase):
    def test_csv_volume_is_optional_and_legacy_closes_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'closes.csv';p.write_text('ticker,date,close,volume,currency\nZZZ,2026-01-05,10,100,USD\nZZZ,2026-01-06,11,,USD\n')
            with patch.object(c,'_settings',return_value={'LSEG_CLOSES_FILE':str(p)}):
                legacy=c.daily_closes('ZZZ','2026-01-01','2026-01-10')
                rows=c.daily_closes_and_volumes('ZZZ','2026-01-01','2026-01-10')
            self.assertNotIn('volume',legacy[0]);self.assertEqual(rows[0]['volume'],100)
            self.assertEqual(rows[0]['currency'],'USD');self.assertIsNone(rows[1]['volume'])
    def test_sdk_volume_field_and_currency_are_read_without_a_live_session(self):
        from types import SimpleNamespace,ModuleType
        from unittest.mock import Mock
        package=ModuleType('lseg');sdk=ModuleType('lseg.data');package.data=sdk
        session=Mock();sdk.session=SimpleNamespace(desktop=SimpleNamespace(Definition=lambda **kwargs:SimpleNamespace(get_session=lambda:session)),set_default=Mock());sdk.HeaderType=SimpleNamespace(NAME='names')
        frame=SimpleNamespace(empty=False,columns=['TR.PriceClose.date','TR.PriceClose','TR.Volume','TR.PriceClose.Currency'],iterrows=lambda:iter([(0,{'TR.PriceClose.date':'2026-01-05','TR.PriceClose':10,'TR.Volume':100,'TR.PriceClose.Currency':'USD'})]))
        sdk.get_data=Mock(return_value=frame)
        with patch.dict(sys.modules,{'lseg':package,'lseg.data':sdk}):
            result=c._lseg_rows('ZZZ','2026-01-01','2026-01-10','invented',include_volume=True)
        self.assertEqual(result['rows'][0]['volume'],100);self.assertEqual(result['rows'][0]['currency'],'USD')
        self.assertIn('TR.Volume',sdk.get_data.call_args.kwargs['fields'])
        session.close.assert_called_once()
    def test_last_close_tries_recent_window_before_full_history(self):
        row={'date':'2026-01-05','close':10,'close_time':'2026-01-05T16:00:00-05:00','source':'invented'}
        with patch.object(c,'daily_closes',return_value=[row]) as fetch:
            result=c.last_close_before('ZZZ','2026-01-06T12:00:00')
        self.assertEqual(result['close'],10)
        self.assertNotEqual(fetch.call_args.args[1],'1900-01-01')
        self.assertEqual(fetch.call_count,1)
    def test_old_last_close_uses_full_history_only_if_recent_unavailable(self):
        row={'date':'2024-01-05','close':10,'close_time':'2024-01-05T16:00:00-05:00','source':'invented'}
        with patch.object(c,'daily_closes',side_effect=['not available',[row]]) as fetch:
            self.assertEqual(c.last_close_before('ZZZ','2026-01-06T12:00:00')['close'],10)
        self.assertEqual(fetch.call_args.args[1],'1900-01-01')
