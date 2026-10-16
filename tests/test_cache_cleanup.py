import json,tempfile,unittest
from pathlib import Path
from course_notes.cache_cleanup import cleanup_batch


class CleanupTests(unittest.TestCase):
    def test_only_audio_is_removed_and_evidence_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);job=root/'video_job';job.mkdir()
            target=root/'notes.md';target.write_text('notes')
            for name in ('audio.wav','speech.json','evidence.json'):(job/name).write_text('source')
            report=[{'status':'success','job':str(job),'target':str(target)}]
            self.assertEqual(len(cleanup_batch(report,root)),1)
            self.assertFalse((job/'audio.wav').exists())
            self.assertTrue((job/'speech.json').exists());self.assertTrue((job/'evidence.json').exists())
    def test_failure_pending_review_and_outside_path_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);job=root/'video_job';job.mkdir()
            target=root/'notes.md';target.touch()
            (job/'audio.wav').touch();(job/'speech.json').touch()
            row={'status':'failed','job':str(job),'target':str(target)}
            self.assertEqual(cleanup_batch([row],root),[])
            row['status']='success'
            (job/'review-requests.json').write_text(json.dumps([{'id':'a','status':'pending'}]))
            with self.assertRaises(ValueError):cleanup_batch([row],root)
            self.assertTrue((job/'audio.wav').exists())
            with self.assertRaises(ValueError):cleanup_batch([row],root/'other')
