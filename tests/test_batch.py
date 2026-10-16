import unittest,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from course_notes.batch import run_batch,plan
from course_notes.config import Settings

class BatchTests(unittest.TestCase):
    def test_whole_task_and_review_share_session_and_resume_legacy_id(self):
        import json
        from course_notes.config import Settings
        from course_notes.conversation import Conversation
        from course_notes.task_session import for_job
        from types import SimpleNamespace
        provider=SimpleNamespace(identity='deepseek:direct',base_url='https://example.test',model='deepseek-flash',wire_api='deepseek_messages')
        with tempfile.TemporaryDirectory() as root:
            out=Path(root);legacy=out/'b_job'/'deepseek-conversation.json'
            old=Conversation(legacy,provider);old.commit({'role':'user','content':'previous task context'},'answer')
            seen=[]
            def run(video,directory,settings,*args,**kwargs):
                seen.append(settings)
                job=directory/(video.stem+'_job');job.mkdir(exist_ok=True)
                (job/'manifest.json').write_text(json.dumps({'conversation_file':settings.conversation_file,'conversation_video':settings.conversation_video}),'utf-8')
                self.assertEqual(for_job(Settings(),job).conversation_file,settings.conversation_file)
                return directory/'result.md'
            with patch('course_notes.config.selected_provider',return_value=provider),patch('course_notes.batch.run_safe',side_effect=run):
                run_batch(['a.mp4','b.mp4'],out,Settings(),lambda *a:None,threading.Event())
                run_batch(['a.mp4','b.mp4'],out,Settings(),lambda *a:None,threading.Event())
            self.assertEqual(len({s.conversation_file for s in seen}),1)
            self.assertEqual([s.conversation_video for s in seen],['video-1','video-2']*2)
            migrated=Conversation(Path(seen[0].conversation_file),provider)
            self.assertEqual(migrated.row['id'],old.row['id'])
            self.assertTrue(legacy.exists())
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
