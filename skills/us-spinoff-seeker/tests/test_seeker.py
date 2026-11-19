"""Rule contracts. Fixtures contain invented issuers, filings, and prices only."""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/seeker.py'
spec = importlib.util.spec_from_file_location('spinoff_seeker', SCRIPT)
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)


def filing(form='10-12B', day='2026-01-05', cik='101', name='Issuer'):
    return s.Filing(cik, name, form, day, f'edgar/data/{cik}/0000000101-26-000001.txt')


def doc(text, form='10-12B', day='2026-01-05', cik='101'):
    return s.Document(filing(form, day, cik), 'https://www.sec.gov/Archives/edgar/data/101/a/exhibit.htm', [('Distribution information', text)])


def candidate():
    return s.new_candidate('101', 'Issuer')


def fact(c, key, value):
    s.put_fact(c, key, value, doc('The filing explicitly states ' + str(value)), 'Distribution information', 'The filing explicitly states ' + str(value))


class RuleTests(unittest.TestCase):
    def test_record_date_in_today_announcement_is_not_distribution_date(self):
        c=candidate()
        text='The spin-off was completed today following the distribution to shareholders of one share for every one share held on April 6, 2026, the record date for the distribution.'
        s.apply_documents(c,[doc(text,'8-K','2026-04-20')])
        self.assertIsNone(s.value(c,'distribution_date'))
        self.assertEqual(s.value(c,'record_date'),'2026-04-06')

    def test_today_completion_uses_explicit_release_dateline_not_filing_date(self):
        c=candidate()
        text='HARBOR — April 20, 2026 — Issuer announcement. The spin-off was completed today following the distribution of shares held on April 6, 2026, the record date.'
        s.apply_documents(c,[doc(text,'8-K','2026-04-21')])
        self.assertEqual(s.value(c,'distribution_date'),'2026-04-20')
        self.assertEqual(s.value(c,'record_date'),'2026-04-06')

    def test_today_completion_with_conflicting_datelines_stays_blank(self):
        c=candidate()
        text='HARBOR — April 20, 2026 — Release. Other — April 21, 2026 — Release. The spin-off was completed today following the distribution of shares held on April 6, 2026, the record date.'
        s.apply_documents(c,[doc(text,'8-K','2026-04-22')])
        self.assertIsNone(s.value(c,'distribution_date'))

    def test_explicit_completion_date_survives_record_date_in_same_paragraph(self):
        c=candidate();fact(c,'distribution_date','2026-03-02')
        text='On March 22, 2026, the spin-off was consummated by means of a pro rata distribution wherein each shareholder of record on March 22, 2026 (the Record Date) received shares.'
        s.apply_documents(c,[doc(text,'10-Q','2026-04-01')])
        self.assertEqual(s.value(c,'distribution_date'),'2026-03-22')

    def test_incorporation_date_is_not_future_distribution_date(self):
        c=candidate()
        text='Information Statement. Issuer was incorporated on January 23, 2026. Following the future Separation and Distribution, all shares will be distributed to shareholders.'
        s.apply_documents(c,[doc(text,'10-12B','2026-06-01')])
        self.assertIsNone(s.value(c,'distribution_date'))

    def test_form_index_fixed_columns_and_amendments_cert_8k(self):
        header = f'{"Form Type":<12}{"Company Name":<62}{"CIK":<12}{"Date Filed":<12}File Name'
        rows = [f'{form:<12}{"Issuer":<62}{101:<12}{"2026-01-05":<12}edgar/data/101/0000000101-26-000001.txt' for form in ('10-12B', '10-12B/A', '10-12G', '10-12G/A', 'CERT', '8-K', '10-K', '4')]
        parsed = s.parse_form_index('\n'.join([header, '-'*110, *rows]))
        self.assertEqual(len(parsed), 8)
        self.assertEqual(sum(s.is_registration(r.form) for r in parsed), 4)

    def test_index_rows_need_not_align_with_header_columns(self):
        header = 'Form Type   Company Name                                                  CIK         Date Filed  File Name'
        row = f'{"10-12B":<17}{"Registrant":<62}{101:<12}{"2026-01-05":<12}edgar/data/101/0000000101-26-000001.txt'
        result=s.parse_form_index(header+'\n'+'-'*140+'\n'+row)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].cik,'101')
        self.assertTrue(s.is_registration(result[0].form))

    def test_index_can_discard_unneeded_form_objects(self):
        header=f'{"Form Type":<12}{"Company Name":<62}{"CIK":<12}{"Date Filed":<12}File Name'
        text='\n'.join([header,*[f'{form:<17}{"Registrant":<62}{101:<12}{"2026-01-05":<12}edgar/data/101/0000000101-26-000001.txt' for form in ('4','10-12B','8-K')]])
        self.assertEqual([r.form for r in s.parse_form_index(text,forms={'10-12B','8-K'})],['10-12B','8-K'])
        self.assertEqual(s.parse_form_index(text,forms={'CERT'}),[])

    def test_historical_indexes_begin_before_start_distribution(self):
        urls = s.index_urls(date(2026, 2, 1), date(1994, 7, 1))
        self.assertIn('/1994/QTR3/form.idx', urls[0])
        self.assertIn('/2026/QTR1/form.idx', urls[-1])

    def test_every_http_request_has_user_agent_and_rate_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Mock(); fake.get.return_value = Mock(status_code=200, content=b'ok', headers={})
            client = s.Edgar('Research test@example.invalid', Path(tmp), session=fake)
            client.pause = Mock()
            client.get('https://www.sec.gov/a', fresh=True)
            client.get('https://data.sec.gov/b', fresh=True)
            self.assertEqual(client.pause.call_count, 2)
            for call in fake.get.call_args_list:
                self.assertEqual(call.kwargs['headers']['User-Agent'], 'Research test@example.invalid')
            self.assertGreaterEqual(client.interval, .2)

    def test_redirect_is_another_rate_limited_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Mock(); fake.get.side_effect = [Mock(status_code=302, headers={'Location': '/b'}, content=b''), Mock(status_code=200, headers={}, content=b'ok')]
            client = s.Edgar('test@example.invalid', Path(tmp), session=fake); client.pause = Mock()
            self.assertEqual(client.get('https://www.sec.gov/a', fresh=True), 'ok')
            self.assertEqual(client.pause.call_count, 2)

    def test_missing_user_agent_rejected(self):
        with self.assertRaises(ValueError): s.Edgar('', Path('.'))

    def test_non_sec_link_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): s.Edgar('test@example.invalid', Path(tmp)).get('https://example.invalid/a')

    def test_folder_reads_exhibits_not_only_primary(self):
        fake = Mock()
        fake.get.side_effect = [json.dumps({'directory': {'item': [{'name': 'primary.htm'}, {'name': 'info.htm'}]}}), '<h1>Registration</h1><p>Cover.</p>', '<h2>Information Statement</h2><p>Distribution date: February 2, 2026.</p>']
        docs, complete = s.read_folder(fake, filing())
        self.assertTrue(complete)
        self.assertEqual(len(docs), 2)
        self.assertIn('Information Statement', docs[1].text)

    def test_partial_folder_cannot_prove_no_statement(self):
        c = candidate()
        s.apply_documents(c, [doc('Registration of securities.')], complete=False)
        self.assertFalse(c['drop'])

    def test_registry_facts_have_filing_section_quote(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02')
        value = c['facts']['distribution_date']
        self.assertEqual(value['value'], '2026-02-02')
        self.assertTrue(all(value[k] for k in ('filing', 'section', 'quote', 'filed')))

    def test_unknown_facts_stay_blank(self):
        c = candidate(); s.apply_documents(c, [doc('Information Statement. Proposed separation; no dates announced.')])
        self.assertIsNone(c['facts']['distribution_date'])
        self.assertIsNone(c['facts']['distribution_ratio'])

    def test_explicit_dates_ratio_parent_extracted(self):
        c = candidate()
        s.apply_documents(c, [doc('Information Statement. Parent: Parent issuer; Parent CIK: 202. Distribution ratio: one share for every four shares. Record date: January 20, 2026. Distribution date: February 2, 2026.')])
        self.assertEqual(c['facts']['parent_cik']['value'], '202')
        self.assertEqual(c['facts']['parent']['value'], 'Parent issuer')
        self.assertEqual(c['facts']['record_date']['value'], '2026-01-20')
        self.assertEqual(c['facts']['distribution_ratio']['value'], 'one share for every four shares')

    def test_ambiguous_or_placeholder_date_not_estimated(self):
        c = candidate(); s.apply_documents(c, [doc('Information Statement. Distribution date: [ ], 2026. Record date: January 20, 2026 or January 21, 2026.')])
        self.assertIsNone(c['facts']['distribution_date'])
        self.assertIsNone(c['facts']['record_date'])

    def test_amendment_can_change_a_previously_sourced_date(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02')
        s.put_fact(c, 'distribution_date', '2026-02-03', doc('Distribution date: February 3, 2026.', '10-12B/A', '2026-01-06'), 'Distribution', 'Distribution date: February 3, 2026.')
        self.assertEqual(c['facts']['distribution_date']['value'], '2026-02-03')
        self.assertTrue(c['history'])

    def test_equal_date_conflict_stays_blank(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02'); fact(c, 'distribution_date', '2026-02-03')
        self.assertIsNone(c['facts']['distribution_date'])
        self.assertTrue(c['conflicts'])

    def test_drop_three_non_spinoff_classes(self):
        for text, reason in [('Registration only.', 'information statement'), ('Information Statement. We are a closed-end investment fund.', 'fund'), ('Information Statement. We are registering our existing outstanding shares.', 'existing')]:
            c = candidate(); s.apply_documents(c, [doc(text)])
            self.assertIn(reason, c['drop']['reason'])
            self.assertTrue(c['drop']['filing'])

    def test_negative_fund_sentence_not_a_fund(self):
        c = candidate(); s.apply_documents(c, [doc('Information Statement. We are not an investment company.')])
        self.assertFalse(c['drop'])

    def test_later_parent_distribution_restores_candidate(self):
        c = candidate(); s.apply_documents(c, [doc('Registration only.')])
        s.apply_documents(c, [doc('Parent issuer completed the distribution of Issuer to its stockholders on February 2, 2026.', '8-K', '2026-02-02', '202')], parent=True)
        self.assertFalse(c['drop'])
        self.assertTrue(c['distribution_evidence'])

    def test_unrelated_parent_distribution_cannot_restore(self):
        c = candidate(); s.apply_documents(c, [doc('Registration only.')])
        s.apply_documents(c, [doc('Parent issuer completed the distribution of a different business on February 2, 2026.', '8-K', '2026-02-02', '202')], parent=True)
        self.assertTrue(c['drop'])

    def test_parent_filings_use_registry_cik(self):
        c = candidate(); fact(c, 'parent_cik', '202')
        fake = Mock(); fake.submissions.return_value = ({}, [filing('8-K', '2026-02-02', '202')])
        s.parent_filings(fake, c, date(2026, 2, 5))
        fake.submissions.assert_called_once_with('202')

    def test_stage_sequence_and_window_boundaries(self):
        c = candidate(); self.assertEqual(s.stage(c, date(2026, 2, 5), 10), 'registered')
        c['listing_evidence'] = {'filing': 'CERT'}
        self.assertEqual(s.stage(c, date(2026, 2, 5), 10), 'listing approved')
        c['trading_evidence'] = {'filing': '10-Q'}
        self.assertEqual(s.stage(c, date(2026, 2, 5), 10), 'trading')
        fact(c, 'distribution_date', '2026-02-02')
        self.assertEqual(s.stage(c, date(2026, 2, 2), 10), 'trading')
        self.assertEqual(s.stage(c, date(2026, 2, 3), 10), 'in its window')
        self.assertEqual(s.stage(c, date(2026, 2, 12), 10), 'in its window')
        self.assertEqual(s.stage(c, date(2026, 2, 13), 10), 'past it')

    def test_own_10q_10k_form4_prove_trading_cert_does_not(self):
        for form in ('10-Q', '10-K', '4'):
            c = candidate(); s.apply_documents(c, [doc('Issuer report.', form)])
            self.assertTrue(c['trading_evidence'])
        c = candidate(); s.apply_documents(c, [doc('Exchange certifies approval for listing.', 'CERT')])
        self.assertTrue(c['listing_evidence']); self.assertFalse(c['trading_evidence'])

    def test_first_close_strictly_after_distribution_and_dates_printed(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02'); fact(c, 'ticker', 'ZZZ')
        c['trading_evidence'] = {'filing': '10-Q'}
        reader = Mock(return_value=[{'ticker': 'ZZZ', 'date': '2026-02-02', 'close': 9}, {'ticker': 'ZZZ', 'date': '2026-02-03', 'close': 10}, {'ticker': 'ZZZ', 'date': '2026-02-05', 'close': 12}])
        s.prices(c, date(2026, 2, 5), reader)
        self.assertEqual(c['prices']['first']['date'], '2026-02-03')
        self.assertIn('2026-02-03', s.price_text(c['prices']['first']))
        self.assertEqual(c['metrics']['return_since_first_close']['value'], .2)

    def test_when_issued_ticker_is_never_requested(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02'); fact(c, 'ticker', 'ZZZ.WI'); c['trading_evidence'] = {'filing': '10-Q'}
        reader = Mock(); s.prices(c, date(2026, 2, 5), reader); reader.assert_not_called()

    def test_unavailable_close_does_not_abort(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02'); fact(c, 'ticker', 'ZZZ'); c['trading_evidence'] = {'filing': '10-Q'}
        s.prices(c, date(2026, 2, 5), Mock(return_value='not available'))
        self.assertIsNone(c['prices']['first'])

    def test_date_filter_is_inclusive_and_missing_date_unranked(self):
        c = candidate(); self.assertEqual(s.eligibility(c, date(2026, 2, 2))[0], 'unknown')
        fact(c, 'distribution_date', '2026-02-02'); self.assertEqual(s.eligibility(c, date(2026, 2, 2))[0], 'included')
        self.assertEqual(s.eligibility(c, date(2026, 2, 3))[0], 'before start')

    def test_weights_directions_points_and_ties(self):
        a, b = candidate(), s.new_candidate('102', 'Registrant')
        for c, v in ((a, .1), (b, .2)):
            c['stage'] = 'in its window'; c['metrics']['return_since_first_close'] = {'value': v, 'source': 'dated closes'}
            fact(c,'distribution_date','2026-02-02')
        config = {'window_days': 30, 'factors': [{'name': 'return_since_first_close', 'weight': 3, 'direction': 'higher'}]}
        ranked, unranked = s.rank([a, b], config)
        self.assertEqual(ranked[0]['cik'], '102'); self.assertEqual(ranked[0]['points']['return_since_first_close'], 3)
        self.assertEqual(ranked[1]['points']['return_since_first_close'], 0)
        config['factors'][0]['direction'] = 'lower'
        self.assertEqual(s.rank([a, b], config)[0][0]['cik'], '101')
        a['metrics']['return_since_first_close']['value'] = .2
        self.assertEqual(s.rank([a, b], config)[0][0]['points']['return_since_first_close'], 1.5)

    def test_missing_factor_no_imputation(self):
        c=candidate();fact(c,'distribution_date','2026-02-02');c['stage']='in its window'
        config={'window_days':30,'factors':[{'name':'unknown_metric','weight':1,'direction':'higher'}]}
        ranked,unranked=s.rank([c],config)
        self.assertEqual(len(ranked),1);self.assertFalse(unranked)
        self.assertEqual(c['points']['unknown_metric'],0)
        self.assertNotIn('unknown_metric',c['metrics'])
        text=s.report([c],ranked,unranked,date(2026,2,5),'2026-02-04',[],factors=config)
        self.assertIn('blank',text);self.assertIn('unknown_metric',text)

    def test_only_missing_distribution_date_blocks_window_ranking(self):
        a=candidate();a['stage']='in its window'
        b=candidate();b['cik']='102';b['stage']='in its window';fact(b,'distribution_date','2026-02-02')
        ranked,unranked=s.rank([a,b],{'window_days':30,'factors':[{'name':'x','weight':1,'direction':'higher'}]})
        self.assertEqual([c['cik'] for c in ranked],['102'])
        self.assertEqual([c['cik'] for c in unranked],['101'])
        self.assertIn('Distribution date',a['unranked_reason'])

    def test_blank_factor_is_not_an_estimated_zero_in_peer_comparisons(self):
        a,b,c=[s.new_candidate(str(i),'Issuer') for i in (101,102,103)]
        for item in [a,b,c]:
            fact(item,'distribution_date','2026-02-02');item['stage']='in its window'
        a['metrics']['x']={'value':-5,'source':'filing'}
        b['metrics']['x']={'value':0,'source':'filing'}
        c['factor_missing_reasons']={'x':'ownership table has an unresolved footnote'}
        config={'window_days':30,'factors':[{'name':'x','weight':1,'direction':'higher'}]}
        ranked,unranked=s.rank([a,b,c],config)
        self.assertFalse(unranked)
        self.assertEqual(a['points']['x'],0);self.assertEqual(b['points']['x'],1);self.assertEqual(c['points']['x'],0)
        self.assertNotIn('x',c['metrics'])
        text=s.report([a,b,c],ranked,[],date(2026,2,5),'2026-02-04',[],factors=config)
        self.assertIn('0 (blank: ownership table has an unresolved footnote)',text)

    def test_zero_weights_in_user_file_and_report_limits(self):
        config=s.load_factors(Path(__file__).resolve().parents[3]/'spinoff_factors.json')
        factors={f['configured_name']:f for f in config['factors']}
        self.assertEqual(factors['analyst_count']['weight'],0)
        self.assertEqual(factors['unwanted_selling']['weight'],0)
        text=s.report([],[],[],date(2026,2,5),'2026-02-04',config['limitations'],factors=config)
        limits=text.split('## What the data cannot show')[1]
        self.assertIn('analyst_count',limits);self.assertIn('unwanted_selling',limits)

    def test_invalid_factor_config_rejected(self):
        for config in ({'window_days': 0, 'factors': []}, {'window_days': 3, 'factors': [{'name': 'a', 'weight': -1, 'direction': 'up'}]}):
            with self.assertRaises(ValueError): s.validate_factors(config)

    def test_report_header_sections_disclaimer_and_blanks(self):
        c = candidate(); c['stage'] = 'registered'
        output = s.report([c], [], [], date(2026, 2, 2), '2026-02-01', ['Coverage incomplete'])
        first = output.splitlines()[0]
        self.assertIn('Run date:', first); self.assertIn('Price date:', first); self.assertIn('Index date:', first)
        for phrase in ('Watch list', 'Dropped', 'cannot show', 'distribution_date', 'Coverage incomplete'):
            self.assertIn(phrase, output)
        self.assertTrue(output.rstrip().endswith('screens, not recommendations'))

    def test_parent_name_before_distribution_is_not_child_identification(self):
        c = candidate(); s.apply_documents(c, [doc('Registration only.')])
        s.apply_documents(c, [doc('Parent issuer completed the distribution of another entity to stockholders on February 2, 2026.', '8-K', '2026-02-02', '202')], parent=True)
        self.assertTrue(c['drop'])

    def test_decimal_distribution_ratio_is_not_truncated(self):
        c = candidate(); s.apply_documents(c, [doc('Information Statement. Distribution ratio: 0.5 shares for every one share. Record date: January 20, 2026.')])
        self.assertEqual(c['facts']['distribution_ratio']['value'], '0.5 shares for every one share')

    def test_pdf_cannot_be_silently_treated_as_absent_statement(self):
        fake = Mock(); fake.get.side_effect = [json.dumps({'directory': {'item': [{'name': 'primary.htm'}, {'name': 'statement.pdf'}]}}), '<p>Registration only.</p>']
        docs, complete = s.read_folder(fake, filing())
        self.assertFalse(complete)
        c = candidate(); s.apply_documents(c, docs, complete=complete)
        self.assertFalse(c['drop'])

    def test_us_listing_needs_filing_evidence(self):
        c = candidate()
        s.apply_documents(c, [doc('The exchange certifies approval for listing on the Nasdaq Stock Market.', 'CERT')])
        self.assertTrue(c.get('us_listing_evidence'))
        other = candidate(); s.apply_documents(other, [doc('A foreign exchange certifies listing approval.', 'CERT')])
        self.assertFalse(other.get('us_listing_evidence'))

    def test_index_date_is_header_not_run_date(self):
        self.assertEqual(s.index_date('Last Data Received: January 30, 2026'), '2026-01-30')
        self.assertIsNone(s.index_date('No update date supplied.'))

    def test_missing_record_date_does_not_block_distribution_window(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02'); c['trading_evidence'] = {'filing': '10-Q'}
        self.assertEqual(s.stage(c, date(2026,2,5), 10), 'in its window')
        self.assertIsNone(c['facts']['record_date'])

    def test_natural_parent_and_scheduled_date(self):
        c = candidate()
        s.apply_documents(c, [doc('Information Statement. We are a wholly owned subsidiary of Parent registrant. The distribution will occur on February 2, 2026. The record date is January 20, 2026.')])
        self.assertEqual(c['facts']['parent']['value'], 'Parent registrant')
        self.assertEqual(c['facts']['distribution_date']['value'], '2026-02-02')

    def test_inline_xbrl_symbol_is_a_filing_fact(self):
        blocks = s.html_blocks('<p>Information Statement.</p><ix:nonNumeric name="dei:TradingSymbol">ZZZ</ix:nonNumeric><ix:nonNumeric name="dei:SecurityExchangeName">Nasdaq Stock Market</ix:nonNumeric>')
        c = candidate(); d = doc(''); d.blocks = blocks
        s.apply_documents(c, [d])
        self.assertEqual(c['facts']['ticker']['value'], 'ZZZ')
        self.assertEqual(c['facts']['ticker']['quote'], 'ZZZ')
        self.assertTrue(c['us_listing_evidence'])

    def test_bounded_throttle_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Mock(); fake.get.return_value = Mock(status_code=429, content=b'', headers={})
            client = s.Edgar('test@example.invalid', Path(tmp), session=fake); client.pause = Mock()
            with patch.object(s.time, 'sleep'), self.assertRaises(RuntimeError):
                client.get('https://www.sec.gov/a', fresh=True)
            self.assertEqual(fake.get.call_count, 4)
            self.assertEqual(client.pause.call_count, 4)

    def test_actual_rate_gate_spaces_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = s.Edgar('test@example.invalid', Path(tmp))
            with patch.object(s, 'ANALYST', Path(tmp)), patch.object(s.time, 'time', return_value=100), patch.object(s.time, 'sleep') as sleep:
                client.pause(); client.pause()
                self.assertGreaterEqual(sleep.call_args_list[1].args[0], .20)

    def test_end_to_end_with_invented_edgar_and_closes(self):
        header = f'{"Form Type":<12}{"Company Name":<62}{"CIK":<12}{"Date Filed":<12}File Name'
        index = '\n'.join(['Last Data Received: February 5, 2026', header, '-'*110,
            f'{"10-12B":<12}{"Issuer":<62}{101:<12}{"2026-01-05":<12}edgar/data/101/0000000101-26-000001.txt'])
        registration = doc('Information Statement. Parent: Parent registrant; Parent CIK: 202. Distribution date: February 2, 2026. Record date: January 20, 2026. Distribution ratio: one share for every four shares. Trading symbol: ZZZ. Registered on Nasdaq.')
        proof = doc('Issuer quarterly report.', '10-Q', '2026-02-04')
        parent_doc = doc('Parent registrant completed the distribution of Issuer to stockholders on February 2, 2026.', '8-K', '2026-02-02', '202')
        fake = Mock(); fake.get.return_value = index; fake.errors = []
        fake.submissions.side_effect = lambda cik: ({'name': 'Issuer'}, [registration.filing, proof.filing]) if cik=='101' else ({'name': 'Parent registrant'}, [parent_doc.filing])
        def folders(client, row):
            return ([parent_doc] if row.cik=='202' else [proof] if row.form=='10-Q' else [registration]), True
        reader = Mock(return_value=[{'ticker':'ZZZ','date':'2026-02-03','close':10}, {'ticker':'ZZZ','date':'2026-02-05','close':12}])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); factors=root/'factors.json'
            factors.write_text(json.dumps({'window_days':30,'factors':[{'name':'return_since_first_close','weight':1,'direction':'higher'}]}))
            args = type('Args', (), {'as_of':'2026-02-05','start':'2026-02-02','factors':str(factors),'output':str(root/'out'),'index_start':'1994-07-01','no_prices':False})()
            with patch.object(s,'dotenv_values',return_value={'SEC_USER_AGENT':'test@example.invalid'}), patch.object(s,'Edgar',return_value=fake), patch.object(s,'index_urls',return_value=['https://www.sec.gov/fake/form.idx']), patch.object(s,'read_folder',side_effect=folders), patch.object(s,'load_reader',return_value=reader):
                target = s.run(args)
            report = target.read_text()
            self.assertTrue(report.rstrip().endswith('screens, not recommendations'))
            self.assertIn('2026-02-03', report)
            registry = json.loads((root/'out/registry.json').read_text())
            self.assertEqual(registry['candidates']['101']['stage'], 'in its window')
            self.assertEqual(registry['candidates']['101']['rank'], 1)
            self.assertTrue(target.with_suffix('.json').exists())

    def test_vendor_when_issued_mapping_and_tag_are_rejected(self):
        c = candidate(); fact(c, 'distribution_date', '2026-02-02'); fact(c, 'ticker', 'ZZZ'); c['trading_evidence']={'filing':'10-Q'}
        rows = [
            {'ticker':'ZZZ','date':'2026-02-03','close':10,'source':'LSEG TR.PriceClose (ZZZ_w.N)'},
            {'ticker':'ZZZ','date':'2026-02-04','close':11,'when_issued':True},
            {'ticker':'ZZZ','date':'2026-02-05','close':12,'source':'LSEG TR.PriceClose (ZZZ.N)'}]
        s.prices(c,date(2026,2,5),Mock(return_value=rows))
        self.assertEqual(c['prices']['first']['date'],'2026-02-05')

    def test_redirects_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Mock(); fake.get.return_value = Mock(status_code=302,headers={'Location':'/again'},content=b'')
            client = s.Edgar('test@example.invalid',Path(tmp),session=fake); client.pause=Mock()
            with self.assertRaises(RuntimeError): client.get('https://www.sec.gov/again',fresh=True)
            self.assertLessEqual(fake.get.call_count,6)

    def test_report_ranking_table_rows_are_contiguous(self):
        a,b=candidate(),s.new_candidate('102','Registrant')
        for c,v in ((a,1),(b,2)):
            c['stage']='in its window'; c['metrics']['days_since_distribution']={'value':v,'source':'dated filing'}
            fact(c,'distribution_date','2026-02-02')
        ranked,_=s.rank([a,b],{'window_days':30,'factors':[{'name':'days_since_distribution','weight':1,'direction':'lower'}]})
        lines=s.report([a,b],ranked,[],date(2026,2,5),'2026-02-04',[]).splitlines()
        first=next(i for i,line in enumerate(lines) if line.startswith('| Rank'))
        self.assertTrue(all(line.startswith('|') for line in lines[first:first+4]))

    def test_placeholder_symbol_is_not_a_ticker(self):
        for text in ('Information Statement. Trading symbol will be determined later.', 'Information Statement. Trading symbol: TBD.'):
            c=candidate(); s.apply_documents(c,[doc(text)])
            self.assertIsNone(c['facts']['ticker'])

    def test_future_information_statement_is_not_a_present_one(self):
        c=candidate(); s.apply_documents(c,[doc('This registration contains no information statement. An information statement will be filed in a future amendment.')])
        self.assertIn('information statement',c['drop']['reason'])

    def test_later_filing_resolves_prior_date_conflict(self):
        c=candidate(); fact(c,'distribution_date','2026-02-02'); fact(c,'distribution_date','2026-02-03')
        s.put_fact(c,'distribution_date','2026-02-04',doc('Distribution date: February 4, 2026.',day='2026-01-06'),'Distribution','Distribution date: February 4, 2026.')
        self.assertEqual(c['facts']['distribution_date']['value'],'2026-02-04')
        self.assertTrue(c['conflicts'][0].get('resolved_by'))

    def test_parent_label_does_not_consume_other_facts(self):
        c=candidate(); s.apply_documents(c,[doc('Information Statement. Parent: Parent registrant. Record date: January 20, 2026.')])
        self.assertEqual(c['facts']['parent']['value'],'Parent registrant')

    def test_parent_cik_resolution_requires_filing_index_identity(self):
        c=candidate(); fact(c,'parent','Parent registrant')
        parent=filing('8-K','2026-01-06','202',name='Parent registrant')
        fake=Mock(); fake.submissions.return_value=({},[parent]); fake.get.return_value='<div>Parent registrant (Filer) CIK: 0000000202</div>'
        s.resolve_parent(fake,c,[parent],date(2026,2,5))
        self.assertEqual(c['facts']['parent_cik']['value'],'202')
        self.assertIn('-index.html',c['facts']['parent_cik']['filing'])

    def test_ambiguous_parent_cik_is_not_guessed(self):
        c=candidate(); fact(c,'parent','Parent registrant')
        fake=Mock()
        s.resolve_parent(fake,c,[filing(cik='202',name='Parent registrant'),filing(cik='203',name='Parent registrant')],date(2026,2,5))
        self.assertIsNone(c['facts']['parent_cik']); fake.submissions.assert_not_called()

    def test_historical_asof_is_not_mislabeled_as_run_date(self):
        text=s.report([],[],[],date(2026,2,5),'2026-02-04',[],run_day=date(2026,2,7))
        self.assertIn('Run date: 2026-02-07',text.splitlines()[0])
        self.assertIn('As-of date: 2026-02-05',text)

    def test_pdf_is_authoritative_for_weights_window_and_horizon(self):
        rows=[['Factor','Direction','Weight','Measured as','Why this weight'],
              ['Insider ownership / incentives','higher','0.25','% owned by officers and directors',''],
              ['Size relative to parent','lower','0.20','Spinoff market cap / parent market cap',''],
              ['Insider buying','higher','0.15','Count of code P purchases',''],
              ['Early price performance','lower','0.15','Return after N trading days',''],
              ['Debt transferred','lower','0.15','Debt / total assets',''],
              ['Absolute market cap','lower','0.10','Shares outstanding times first close',''],
              ['Analyst recommendations','lower','0.00','No source',''],
              ['Unwanted selling pressure','higher','0.00','Covered by relative size',''],
              ['Total','','1.00','','']]
        config=s.parse_pdf_factors(rows,'Window length: 365 days after distribution (180 days for a focus). Early-performance horizon: 20 trading days from the first close after distribution.')
        self.assertEqual(config['window_days'],365)
        self.assertEqual(config['early_performance_trading_days'],20)
        self.assertEqual(len(config['factors']),8)
        self.assertAlmostEqual(sum(f['weight'] for f in config['factors']),1)
        self.assertEqual(config['factors'][0]['name'],'insider_ownership_pct')
        self.assertEqual(config['factors'][1]['direction'],'lower')

    def test_json_can_point_to_source_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config.json';p.write_text(json.dumps({'source_pdf':'weights.pdf'}))
            expected={'window_days':365,'factors':[{'name':'a','weight':1,'direction':'higher'}]}
            with patch.object(s,'load_pdf_factors',return_value=expected) as loader:
                self.assertEqual(s.load_factors(p),expected)
            self.assertEqual(loader.call_args.args[0].resolve(),(Path(tmp)/'weights.pdf').resolve())

    def test_zero_weight_factors_do_not_require_data(self):
        c=candidate();c['stage']='in its window';c['metrics']['size']={'value':2,'source':'filing'}
        fact(c,'distribution_date','2026-02-02')
        config={'window_days':365,'factors':[{'name':'size','weight':1,'direction':'lower'},{'name':'analyst_recommendations','weight':0,'direction':'lower'}]}
        ranked,unranked=s.rank([c],config)
        self.assertEqual(len(ranked),1);self.assertFalse(unranked)
        self.assertEqual(ranked[0]['points']['analyst_recommendations'],0)

    def test_form4_uses_xml_not_index_headers_or_submission_wrapper(self):
        client=Mock();client.errors=[]
        names=['0000000101-26-000001-index-headers.html','0000000101-26-000001.txt','ownership.xml']
        xml='<ownershipDocument><issuer><issuerCik>101</issuerCik></issuer></ownershipDocument>'
        client.get.side_effect=[json.dumps({'directory':{'item':[{'name':name} for name in names]}}),xml]
        docs,complete=s.read_folder(client,filing('4'))
        self.assertTrue(complete)
        self.assertEqual([d.url.rsplit('/',1)[-1] for d in docs],['ownership.xml'])
        self.assertEqual(s.factor_engine().insider_purchases(docs,'101','2026-01-01','2026-02-01',True)['value'],0)

    def test_form4_without_xml_has_incomplete_factor_coverage(self):
        client=Mock();client.errors=[]
        client.get.return_value=json.dumps({'directory':{'item':[{'name':'ownership.htm'}]}})
        docs,complete=s.read_folder(client,filing('4'))
        self.assertFalse(complete);self.assertEqual(docs,[])

    def test_missing_reason_and_report_distinguish_zero_weight_from_required(self):
        c=candidate();c['stage']='in its window'
        fact(c,'distribution_date','2026-02-02')
        config={'window_days':365,'factors':[
            {'name':'size','configured_name':'relative_size','weight':1,'direction':'lower'},
            {'name':'analyst_recommendations','configured_name':'analyst_count','weight':0,'direction':'lower'},
            {'name':'unwanted_selling_pressure','configured_name':'unwanted_selling','weight':0,'direction':'higher'}]}
        ranked,unranked=s.rank([c],config)
        self.assertFalse(unranked);self.assertEqual(c['points']['size'],0)
        text=s.report([c],ranked,unranked,date(2026,2,5),'2026-02-04',[],factors=config)
        section=text.split('## Unranked / missing dates')[1].split('## Watch list')[0]
        self.assertNotIn('analyst_count',section)
        self.assertNotIn('unwanted_selling',section)
        self.assertIn('analyst_count: weight 0; not required for ranking',text)
        self.assertIn('unwanted_selling: weight 0; not required for ranking',text)
        self.assertIn('Blank extraction results do not prove that a fact is absent from a filing.',text)

    def test_positive_weights_are_reported_as_required_without_override(self):
        c=candidate();c['stage']='in its window'
        fact(c,'distribution_date','2026-02-02')
        config={'window_days':365,'factors':[{'name':'analyst_recommendations','configured_name':'analyst_count','weight':.025,'direction':'lower'}]}
        ranked,unranked=s.rank([c],config)
        self.assertFalse(unranked);self.assertEqual(c['points']['analyst_recommendations'],0)
        text=s.report([c],ranked,unranked,date(2026,2,5),'2026-02-04',[],factors=config)
        self.assertIn('analyst_count: weight 0.025; blank values receive 0 points',text)

    def test_early_return_requires_twenty_later_trading_closes(self):
        c=candidate();fact(c,'distribution_date','2026-02-02');fact(c,'ticker','ZZZ');c['trading_evidence']={'filing':'10-Q'}
        rows=[{'date':(date(2026,2,3)+s.timedelta(days=i)).isoformat(),'close':10+i,'ticker':'ZZZ'} for i in range(21)]
        s.prices(c,date(2026,3,10),Mock(return_value=rows),horizon=20)
        self.assertEqual(c['metrics']['early_price_performance']['value'],2)
        s.prices(c,date(2026,3,10),Mock(return_value=rows[:20]),horizon=20)
        self.assertNotIn('early_price_performance',c['metrics'])

    def test_window_row_contains_parent_distribution_and_end_date(self):
        c=candidate();fact(c,'parent','Parent registrant');fact(c,'distribution_date','2026-02-02')
        c.update(stage='in its window',window_end='2027-02-02');c['metrics']['size']={'value':2,'source':'filing'}
        fact(c,'distribution_date','2026-02-02')
        ranked,_=s.rank([c],{'window_days':365,'factors':[{'name':'size','weight':1,'direction':'lower'}]})
        text=s.report([c],ranked,[],date(2026,2,5),'2026-02-04',[])
        self.assertIn('| Parent | Distribution date | Window ends |',text)
        self.assertIn('Parent registrant | 2026-02-02 | 2027-02-02',text)

    def test_named_factor_dictionary_and_early_return_days(self):
        config={'window_days':365,'early_return_days':20,'factors':{'insider_ownership':{'weight':.25,'direction':'higher'},'early_return':{'weight':.15,'direction':'lower'},'analyst_count':{'weight':0,'direction':'lower'}}}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'factors.json';path.write_text(json.dumps(config))
            loaded=s.load_factors(path)
        self.assertEqual(loaded['early_performance_trading_days'],20)
        self.assertEqual([f['name'] for f in loaded['factors']],['insider_ownership_pct','early_price_performance','analyst_recommendations'])
        self.assertEqual([f['weight'] for f in loaded['factors']],[.25,.15,0])

    def test_early_return_horizon_must_be_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'factors.json';path.write_text(json.dumps({'window_days':365,'early_return_days':0,'factors':{'early_return':{'weight':1,'direction':'lower'}}}))
            with self.assertRaises(ValueError):s.load_factors(path)

    def test_filing_plan_limits_8k_history_but_keeps_registrations(self):
        old_reg=filing('10-12B','2020-01-01');old_8k=filing('8-K','2020-01-01');new_8k=filing('8-K','2026-02-02')
        result=s.plan_filings([old_reg,old_8k,new_8k],date(2026,1,1),date(2026,2,5))
        self.assertEqual(result,[old_reg,new_8k])

    def test_factor_metrics_and_parent_close_integrated(self):
        c=candidate();fact(c,'distribution_date','2026-02-02')
        c['prices']['first']={'ticker':'ZZZ','date':'2026-02-03','close':10}
        d=doc('');d.raw='<h2>Beneficial ownership</h2><table><tr><th>Owner</th><th>Percent</th></tr><tr><td>All directors and executive officers as a group</td><td>10%</td></tr></table><h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>1000</td></tr></table><h2>Pro forma balance sheet</h2><table><tr><th>Line</th><th>Pro forma</th></tr><tr><td>Total debt</td><td>20</td></tr><tr><td>Total assets</td><td>100</td></tr></table>'
        parent=doc('',form='10-K',cik='202');parent.raw='<ix:nonNumeric name="dei:TradingSymbol">PPP</ix:nonNumeric><h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>10000</td></tr></table>'
        reader=Mock(return_value=[{'ticker':'PPP','date':'2026-02-03','close':20}])
        s.populate_factors(c,[d],[parent],[],True,date(2026,2,5),reader)
        self.assertEqual(c['metrics']['insider_ownership_pct']['value'],10)
        self.assertEqual(c['metrics']['debt_to_assets']['value'],.2)
        self.assertEqual(c['metrics']['absolute_market_cap']['value'],10000)
        self.assertEqual(c['metrics']['size_relative_to_parent']['value'],.05)
        self.assertEqual(c['metrics']['insider_buying']['value'],0)
        reader.assert_called_once_with('PPP','2026-02-03','2026-02-03')

    def test_resume_key_changes_with_factor_rules_or_dates(self):
        one=s.checkpoint_key(date(2026,1,1),date(2026,2,5),{'window_days':365},False)
        self.assertNotEqual(one,s.checkpoint_key(date(2026,1,1),date(2026,2,6),{'window_days':365},False))
        self.assertNotEqual(one,s.checkpoint_key(date(2026,1,1),date(2026,2,5),{'window_days':180},False))

    def test_rules_change_invalidates_resume_snapshot(self):
        with patch.object(s,'rules_digest',return_value='one'):
            first=s.checkpoint_key(date(2026,1,1),date(2026,3,5),{'window_days':365},False)
        with patch.object(s,'rules_digest',return_value='two'):
            second=s.checkpoint_key(date(2026,1,1),date(2026,3,5),{'window_days':365},False)
        self.assertNotEqual(first,second)

    def test_complete_six_factor_run_with_filing_quotes_and_fake_closes(self):
        header=f'{"Form Type":<12}{"Company Name":<62}{"CIK":<12}{"Date Filed":<12}File Name'
        index='\n'.join(['Last Data Received: March 5, 2026',header,f'{"10-12B":<17}{"Issuer":<62}{101:<12}{"2026-01-05":<12}edgar/data/101/0000000101-26-000001.txt'])
        registration=doc('Information Statement. Parent: Parent registrant; Parent CIK: 202. Distribution date: February 2, 2026. Trading symbol: ZZZ. Registered on Nasdaq.')
        registration.raw='<h2>Beneficial ownership</h2><table><tr><th>Owner</th><th>Percent</th></tr><tr><td>All directors and executive officers as a group</td><td>10%</td></tr></table><h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>1000</td></tr></table><h2>Pro forma balance sheet</h2><table><tr><th>Line</th><th>Pro forma</th></tr><tr><td>Total debt</td><td>20</td></tr><tr><td>Total assets</td><td>100</td></tr></table>'
        proof=doc('Issuer quarterly report.','10-Q','2026-02-04')
        parent=doc('','10-K','2026-02-03','202');parent.raw='<ix:nonNumeric name="dei:TradingSymbol">PPP</ix:nonNumeric><h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>10000</td></tr></table>'
        fake=Mock();fake.get.return_value=index;fake.errors=[]
        fake.submissions.side_effect=lambda cik: ({'name':'Issuer'},[registration.filing,proof.filing]) if cik=='101' else ({'name':'Parent registrant'},[parent.filing])
        def folders(client,row):return ([parent] if row.cik=='202' else [proof] if row.form=='10-Q' else [registration]),True
        days=[];day=date(2026,2,3)
        while len(days)<21:
            if day.weekday()<5:days.append(day.isoformat())
            day+=s.timedelta(days=1)
        reader=Mock(side_effect=lambda ticker,start,end: [{'ticker':'PPP','date':'2026-02-03','close':20}] if ticker=='PPP' else [{'ticker':'ZZZ','date':day,'close':10+i} for i,day in enumerate(days)])
        weights={'insider_ownership':(.25,'higher'),'relative_size':(.20,'lower'),'insider_buying':(.15,'higher'),'early_return':(.15,'lower'),'debt_to_assets':(.15,'lower'),'market_cap':(.10,'lower'),'analyst_count':(0,'lower'),'unwanted_selling':(0,'higher')}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);factor_file=root/'factors.json';factor_file.write_text(json.dumps({'window_days':365,'early_return_days':20,'factors':{k:{'weight':w,'direction':d} for k,(w,d) in weights.items()}}))
            args=type('Args',(),{'as_of':'2026-03-05','start':'2026-01-01','factors':str(factor_file),'output':str(root/'out'),'index_start':'1994-07-01','no_prices':False})()
            with patch.object(s,'dotenv_values',return_value={'SEC_USER_AGENT':'test@example.invalid'}),patch.object(s,'Edgar',return_value=fake),patch.object(s,'index_urls',return_value=['https://www.sec.gov/fake/form.idx']),patch.object(s,'read_folder',side_effect=folders),patch.object(s,'load_reader',return_value=reader):
                target=s.run(args)
            saved=json.loads(target.with_suffix('.json').read_text())['registry']['candidates']['101']
            self.assertEqual(saved['rank'],1);self.assertAlmostEqual(saved['total_points'],1)
            self.assertEqual(len(saved['points']),8)
            self.assertTrue(all(saved['metrics'][key]['source'] for key in ('insider_ownership_pct','size_relative_to_parent','insider_buying','early_price_performance','debt_to_assets','absolute_market_cap')))
            text=target.read_text();self.assertIn('relative_size points',text)
            self.assertTrue(text.rstrip().endswith('screens, not recommendations'))

    def test_bounded_batches_resume_without_repeating_processed_candidate(self):
        header=f'{"Form Type":<12}{"Company Name":<62}{"CIK":<12}{"Date Filed":<12}File Name'
        index='\n'.join(['Last Data Received: March 5, 2026',header,*[f'{"10-12B":<17}{"Registrant":<62}{cik:<12}{"2026-01-05":<12}edgar/data/{cik}/0000000101-26-000001.txt' for cik in (101,102)]])
        fake=Mock();fake.get.return_value=index;fake.errors=[];fake.submissions.side_effect=lambda cik:({'name':'Registrant'},[])
        def folder(client,row):return [s.Document(row,row.folder+'doc.htm',[('Information Statement','Information Statement. Dates not supplied.')])],True
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);factors=root/'factors.json';factors.write_text(json.dumps({'window_days':365,'factors':[{'name':'days_since_distribution','weight':1,'direction':'lower'}]}))
            args=type('Args',(),{'as_of':'2026-03-05','start':'2026-01-01','factors':str(factors),'output':str(root/'out'),'index_start':'1994-07-01','no_prices':True,'max_candidates':1,'resume':False})()
            with patch.object(s,'dotenv_values',return_value={'SEC_USER_AGENT':'test@example.invalid'}),patch.object(s,'Edgar',return_value=fake),patch.object(s,'index_urls',return_value=['https://www.sec.gov/fake/form.idx']),patch.object(s,'read_folder',side_effect=folder):
                first=s.run(args)
                self.assertIn('Coverage: PARTIAL','\n'.join(first.read_text().splitlines()[:12]))
                self.assertFalse(json.loads((root/'out/registry.json').read_text())['complete'])
                args.resume=True;s.run(args)
            self.assertEqual(fake.submissions.call_count,2)
            self.assertTrue(json.loads((root/'out/registry.json').read_text())['complete'])

    def test_xml_only_form4_folder_is_read(self):
        client=Mock();client.get.side_effect=[json.dumps({'directory':{'item':[{'name':'report.xml'}]}}),'<ownershipDocument><issuer><issuerCik>101</issuerCik></issuer></ownershipDocument>']
        docs,complete=s.read_folder(client,filing('4'))
        self.assertTrue(complete);self.assertEqual(len(docs),1)
        self.assertIn('ownershipDocument',docs[0].raw)

    def test_parent_when_issued_vendor_close_is_not_used(self):
        c=candidate();fact(c,'distribution_date','2026-02-02');c['prices']['first']={'ticker':'ZZZ','date':'2026-02-03','close':10}
        own=doc('');own.raw='<h2>As of February 3, 2026</h2><table><tr><td>Total common shares outstanding</td><td>1000</td></tr></table>'
        parent=doc('',cik='202');parent.raw='<ix:nonNumeric name="dei:TradingSymbol">PPP</ix:nonNumeric>'+own.raw
        s.populate_factors(c,[own],[parent],[],True,date(2026,3,5),Mock(return_value=[{'ticker':'PPP','date':'2026-02-03','close':20,'source':'LSEG TR.PriceClose (PPP.WI)'}]))
        self.assertNotIn('size_relative_to_parent',c['metrics'])

    def test_readable_positive_exclusion_survives_unreadable_other_exhibit(self):
        c=candidate();s.apply_documents(c,[doc('Information Statement. We are a closed-end investment fund.')],complete=False)
        self.assertIn('fund',c['drop']['reason'])

    def test_document_text_is_not_rebuilt_for_each_paragraph(self):
        class Blocks(list):
            passes = 0
            def __iter__(self):
                self.passes += 1
                return super().__iter__()
        d = doc('Information Statement.')
        d.blocks = Blocks([('Information Statement', 'Separation discussion.')]*40)
        s.apply_documents(candidate(), [d])
        self.assertLessEqual(d.blocks.passes, 3)

    def test_diagnostics_path_is_restored_after_run_scope(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'errors.jsonl'
            previous=os.environ.get('LSEG_DIAGNOSTICS_FILE')
            with s.diagnostics_output(path):
                self.assertEqual(os.environ['LSEG_DIAGNOSTICS_FILE'],str(path))
                self.assertTrue(path.exists())
            self.assertEqual(os.environ.get('LSEG_DIAGNOSTICS_FILE'),previous)

    def test_atomic_registry_roundtrip_and_timestamped_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); registry = root/'registry.json'
            s.save_json(registry, {'candidates': {'101': candidate()}})
            self.assertIn('101', json.loads(registry.read_text())['candidates'])
            p = s.save_report(root, 'screens, not recommendations\n', datetime(2026,2,2,12,30,1,123456,tzinfo=timezone.utc), date(2026,1,1))
            self.assertEqual(p.name,'Spinoffs, 2026-02-02, 12-30-01.123456, start 2026-01-01.md')
            s.save_json(p.with_suffix('.json'),{'run_time':'2026-02-02T12:30:01.123456+00:00'})
            self.assertEqual(p.stem,p.with_suffix('.json').stem)
            self.assertNotEqual(s.report_stem(datetime(2026,2,2,12,30,1,123457),date(2026,1,1)),p.stem)


if __name__ == '__main__': unittest.main()
