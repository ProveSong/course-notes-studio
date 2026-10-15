import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from course_notes.board import enrich
from course_notes.board_assets import write_image
from course_notes.review import register,decide
from course_notes.config import Settings

class BoardConsentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.job=Path(self.temp.name);self.s=Settings()
        (self.job/'visuals').mkdir();(self.job/'chunks').mkdir()
        write_image(self.job/'visuals/frame.png',np.zeros((40,60,3),np.uint8))
        (self.job/'chunks/C0001.evidence.json').write_text('{"speech":[]}','utf-8')
        register(self.job,'C0001',[{'visual_id':'V000001'}],[{'id':'V000001','time':0,'image':'visuals/frame.png'}])
    def tearDown(self):self.temp.cleanup()
    @patch('course_notes.board.call')
    def test_unapproved_board_never_uploads(self,call):
        with self.assertRaisesRegex(ValueError,'批准'):enrich(self.job,self.s,'C0001-V000001',threading.Event())
        call.assert_not_called()
    @patch('course_notes.board.destination',return_value={'provider':'test','base_url':'https://example.test','model':'test'})
    @patch('course_notes.review.destination',return_value={'provider':'test','base_url':'https://example.test','model':'test'})
    @patch('course_notes.board.call',return_value='{"markdown":"fixture","formulas":[],"diagrams":[]}')
    def test_local_cache_reuse_still_checks_image_hash(self,call,*destinations):
        decide(self.job,['C0001-V000001'],self.s)
        enrich(self.job,self.s,'C0001-V000001',threading.Event())
        enrich(self.job,self.s,'C0001-V000001',threading.Event())
        self.assertEqual(call.call_count,1)
        write_image(self.job/'visuals/frame.png',np.ones((40,60,3),np.uint8)*255)
        with self.assertRaisesRegex(ValueError,'变更'):enrich(self.job,self.s,'C0001-V000001',threading.Event())
        self.assertEqual(call.call_count,1)
