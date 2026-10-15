import json, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from course_notes.review import register,decide,process_approved,grant_task_consent,apply_task_consent
from course_notes.config import Settings
from course_notes.llm import endpoint

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.job=Path(self.temp.name)
        (self.job/'visuals').mkdir(); (self.job/'chunks').mkdir()
        (self.job/'visuals/a.jpg').write_bytes(b'fixture')
        (self.job/'chunks/C0001.evidence.json').write_text('{}')
        (self.job/'chunks/C0001.md').write_text('content')
        self.s=Settings()
        register(self.job,'C0001',[{'visual_id':'V000001','reason':'unclear symbol'}],[{'id':'V000001','time':5,'image':'visuals/a.jpg'}])
    def tearDown(self): self.temp.cleanup()
    @patch('course_notes.review.call')
    def test_pending_never_uploads(self,call):
        process_approved(self.job,self.s,lambda a,b:None,threading.Event()); call.assert_not_called()
    @patch('course_notes.review.destination',return_value={'provider':'fixture','base_url':'https://example.test','model':'test'})
    @patch('course_notes.review.call',return_value='{"markdown":"verified explanation"}')
    def test_approved_upload_and_changed_file_rejected(self,call,destination):
        decide(self.job,['C0001-V000001'],self.s)
        process_approved(self.job,self.s,lambda a,b:None,threading.Event())
        self.assertEqual(call.call_count,1)
        self.assertEqual(json.loads((self.job/'review-requests.json').read_text('utf-8'))[0]['status'],'reviewed')
        decide(self.job,['C0001-V000001'],self.s)
        (self.job/'visuals/a.jpg').write_bytes(b'changed')
        with self.assertRaises(ValueError): process_approved(self.job,self.s,lambda a,b:None,threading.Event())
        self.assertEqual(call.call_count,1)
    def test_version_prefix_not_duplicated(self):
        self.assertEqual(endpoint('https://example.test/v1','responses'),'https://example.test/v1/responses')
    @patch('course_notes.review.destination',return_value={'provider':'fixture','base_url':'https://example.test','model':'test'})
    def test_later_requests_survive_slow_review(self,destination):
        decide(self.job,['C0001-V000001'],self.s)
        def during_call(*args,**kwargs):
            register(self.job,'C0002',[{'visual_id':'V000002','reason':'new question'}],[{'id':'V000002','time':10,'image':'visuals/a.jpg'}])
            return '{"markdown":"review complete"}'
        with patch('course_notes.review.call',side_effect=during_call):
            process_approved(self.job,self.s,lambda a,b:None,threading.Event())
        records=json.loads((self.job/'review-requests.json').read_text('utf-8'))
        self.assertEqual([(r['id'],r['status']) for r in records],[('C0001-V000001','reviewed'),('C0002-V000002','pending')])
    def task_fixture(self):
        self.s.llm_transport='codex_cli'
        (self.job/'manifest.json').write_text(json.dumps({'signature':{'video':'fixture','size':7}}),'utf-8')
        (self.job/'visuals.json').write_text(json.dumps([{'image':'visuals/a.jpg'}]),'utf-8')
    @patch('course_notes.review.destination',return_value={'provider':'fixture','base_url':'https://example.test','model':'test'})
    def test_task_consent_rejects_changed_frame(self,destination):
        self.task_fixture();grant_task_consent(self.job,self.s)
        (self.job/'visuals/a.jpg').write_bytes(b'new image')
        register(self.job,'C0002',[{'visual_id':'V000002'}],[{'id':'V000002','time':10,'image':'visuals/a.jpg'}])
        apply_task_consent(self.job,self.s)
        records=json.loads((self.job/'review-requests.json').read_text('utf-8'))
        self.assertEqual(records[-1]['status'],'pending')
    @patch('course_notes.review.destination',return_value={'provider':'fixture','base_url':'https://example.test','model':'test'})
    def test_task_consent_is_bound_to_cli(self,destination):
        self.task_fixture();grant_task_consent(self.job,self.s)
        self.s.llm_transport='api'
        with patch('course_notes.review.call') as call:
            with self.assertRaisesRegex(ValueError,'调用方式'):
                process_approved(self.job,self.s,lambda a,b:None,threading.Event())
            call.assert_not_called()

    @patch('course_notes.review.destination',return_value={'provider':'fixture','base_url':'https://example.test','model':'test'})
    def test_explicit_auto_option_supports_api_and_future_requests(self,destination):
        self.task_fixture();self.s.llm_transport='api'
        with self.assertRaises(ValueError):grant_task_consent(self.job,self.s)
        grant_task_consent(self.job,self.s,automatic=True)
        register(self.job,'C0002',[{'visual_id':'V000002'}],[{'id':'V000002','time':10,'image':'visuals/a.jpg'}])
        apply_task_consent(self.job,self.s)
        records=json.loads((self.job/'review-requests.json').read_text('utf-8'))
        self.assertEqual([r['status'] for r in records],['approved','approved'])
        self.assertTrue(all(r['approved_transport']=='api' for r in records))
        self.assertTrue(all(r['approval_source']=='user-auto-checkbox' for r in records))

if __name__=='__main__': unittest.main()
