import unittest,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from course_notes.batch import run_batch,plan
from course_notes.config import Settings

class BatchTests(unittest.TestCase):
    def test_dedup_and_same_named_videos_are_separate(self):
        items=plan(['one/lecture.mp4','two/lecture.mp4','one/lecture.mp4'],'out')
        self.assertEqual(len(items),2)
        self.assertNotEqual(items[0][1],items[1][1])
    def test_failure_does_not_cancel_following_video(self):
        with tempfile.TemporaryDirectory() as root:
            parent=threading.Event();calls=[]
            def run(video,output,settings,notify,cancel,**kwargs):
                calls.append((video.name,kwargs['auto_approve_images']))
                if video.name=='bad.mp4':cancel.set();raise RuntimeError('bad')
                self.assertFalse(cancel.is_set());return output/'good.md'
            with patch('course_notes.batch.run_safe',side_effect=run):
                results=run_batch(['bad.mp4','good.mp4'],root,Settings(),lambda *a:None,parent,True)
            self.assertEqual([r['status'] for r in results],['failed','success'])
            self.assertFalse(parent.is_set());self.assertEqual(len(calls),2)
            self.assertTrue((Path(root)/'batch-results.json').exists())
    def test_user_cancel_stops_queue(self):
        from course_notes.process import Cancelled
        with tempfile.TemporaryDirectory() as root:
            parent=threading.Event()
            def run(*args,**kwargs):parent.set();raise Cancelled('cancel')
            with patch('course_notes.batch.run_safe',side_effect=run) as mock:
                with self.assertRaises(Cancelled):run_batch(['a.mp4','b.mp4'],root,Settings(),lambda *a:None,parent)
                self.assertEqual(mock.call_count,1)
