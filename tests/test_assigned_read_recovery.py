"""Recovery asks for missing evidence without relaxing the required-read check."""
import json
from pathlib import Path
import tempfile
import unittest
from desk_files import AssignedFiles
import desk_files


class AssignedReadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.run=Path(self.tmp.name)
        self.paths=[]
        for role in ('Research','Financial','Advisor'):
            for suffix in ('.md','.json'):
                p=self.run/(role+suffix);p.write_text('{}' if suffix=='.json' else 'Synthetic draft',encoding='utf-8')
                self.paths.append(p)
        self.store=AssignedFiles(self.run,self.paths,self.run/'reads.json')

    def test_drafts_only_are_rejected_by_original_check(self):
        for p in self.paths:
            if p.suffix=='.md':self.store.read(p.name)
        with self.assertRaisesRegex(ValueError,'did not read assigned files'):self.store.verify()

    def test_one_missing_read_retry_reads_json_and_preserves_both_replies(self):
        replies=[]
        def request(feedback):
            for p in self.paths:
                if p.suffix==('.md' if feedback is None else '.json'):self.store.read(p.name)
            replies.append(feedback)
            return 'first' if feedback is None else 'corrected'
        result=desk_files.reply_with_required_reads(self.store,request)
        self.assertEqual(result,'corrected')
        self.assertEqual(len(replies),2)
        for p in self.paths:
            if p.suffix=='.json':self.assertIn(p.name,replies[1])
        self.store.verify()
        self.assertEqual(len(json.loads((self.run/'reads.json').read_text(encoding='utf-8'))['reads']),6)

    def test_second_omission_still_stops_after_two_calls(self):
        calls=[]
        def request(feedback):calls.append(feedback);return 'unread'
        with self.assertRaisesRegex(ValueError,'did not read assigned files'):
            desk_files.reply_with_required_reads(self.store,request)
        self.assertEqual(len(calls),2)

    def test_changed_file_is_not_retried(self):
        calls=[]
        def request(feedback):
            calls.append(feedback)
            for p in self.paths:self.store.read(p.name)
            self.paths[0].write_text('Changed after read',encoding='utf-8')
            return 'invalid'
        with self.assertRaisesRegex(ValueError,'changed'):
            desk_files.reply_with_required_reads(self.store,request)
        self.assertEqual(len(calls),1)
