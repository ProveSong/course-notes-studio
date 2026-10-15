import json, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from course_notes.config import Settings
from course_notes.pipeline import run


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.video=self.root/'lecture.mp4'; self.video.write_bytes(b'fixture')
        self.output=self.root/'out'; self.job=self.output/'lecture_job'
        (self.job/'visuals').mkdir(parents=True)
        self.settings=Settings(chunk_seconds=5,sample_seconds=5,compact_notes=False,formula_backend='none')
        speech=[{'start':1,'end':2,'text':'课堂内容'}, {'start':6,'end':7,'text':'课堂闲聊也必须保留'}]
        visuals=[]
        for i in (0,5):
            (self.job/'visuals'/f'{i}.jpg').write_bytes(b'fixture')
            visuals.append({'time':i,'timestamp':f'00:00:0{i}','image':f'visuals/{i}.jpg','ocr_text':'板书','device':'gpu:0'})
        for filename,content in [('speech.json',speech),('visuals.json',visuals),('ocr.json',visuals)]:
            (self.job/filename).write_text(json.dumps(content,ensure_ascii=False),'utf-8')
        cap=SimpleNamespace(get=lambda field:25 if field==5 else 250,release=lambda:None)
        self.capture=patch('course_notes.pipeline.cv2.VideoCapture',return_value=cap); self.capture.start()
        self.destination=patch('course_notes.pipeline.destination',return_value={'provider':'test','base_url':'https://example.test','model':'test'});self.destination.start()
    def tearDown(self):
        self.capture.stop();self.destination.stop();self.temp.cleanup()

    def test_omitted_evidence_is_preserved_and_resume_reuses_cache(self):
        response=json.dumps({'markdown':'老师讲解','covered_speech_ids':[],'covered_visual_ids':[],'image_requests':[]})
        with patch('course_notes.pipeline.generate',return_value=response):
            target=run(self.video,self.output,self.settings)
        text=target.read_text('utf-8')
        self.assertIn('课堂闲聊也必须保留',text)
        self.assertIn('2/2',text)
        results=[json.loads(p.read_text('utf-8'))['result'] for p in (self.job/'chunks').glob('*.result.json')]
        self.assertEqual(sum(len(r['coverage_fallback_speech']) for r in results),2)
        with patch('course_notes.pipeline.generate') as generate:
            run(self.video,self.output,self.settings)
            generate.assert_not_called()

    def test_bad_response_cancels_remaining_futures(self):
        executors=[]
        def executor(**kwargs):
            pool=ThreadPoolExecutor(**kwargs);executors.append(pool);return pool
        cancel=threading.Event()
        with patch('course_notes.pipeline.generate',return_value='{}'),patch('course_notes.pipeline.ThreadPoolExecutor',side_effect=executor):
            with self.assertRaisesRegex(ValueError,'正文为空'):
                run(self.video,self.output,self.settings,cancel=cancel)
        self.assertTrue(cancel.is_set())
        self.assertTrue(executors[0]._shutdown)
        executors[0].shutdown(wait=True,cancel_futures=True)

    def test_compact_output_does_not_append_raw_evidence_and_keeps_sources(self):
        self.settings.compact_notes=True
        response=json.dumps({'markdown':'连续的课程解释','covered_speech_ids':[],'covered_visual_ids':[],'image_requests':[]})
        with patch('course_notes.pipeline.generate',return_value=response):
            target=run(self.video,self.output,self.settings)
        text=target.read_text('utf-8')
        self.assertIn('连续的课程解释',text)
        self.assertNotIn('覆盖检查补入',text)
        self.assertNotIn('完整原始语音',text)
        self.assertNotIn('S000001',text)
        self.assertTrue((self.job/'speech.json').is_file())
        self.assertTrue((self.job/'chunks/C0001.input-audit.json').is_file())
        self.assertTrue(target.name.endswith('—课程讲解.md'))

    def test_cancel_returns_without_waiting_for_remote_reply(self):
        entered=threading.Event(); release=threading.Event(); cancel=threading.Event();errors=[]
        def remote(*args):
            entered.set(); release.wait(5)
            return '{"markdown":"fixture"}'
        def task():
            try: run(self.video,self.output,self.settings,cancel=cancel)
            except Exception as error: errors.append(error)
        with patch('course_notes.pipeline.generate',side_effect=remote):
            thread=threading.Thread(target=task)
            thread.start()
            try:
                self.assertTrue(entered.wait(2));cancel.set();thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertTrue(errors)
            finally:
                release.set();thread.join(6)
                # Wait for already running calls before removing the fixture.
                for worker in list(threading.enumerate()):
                    if worker.name.startswith('ThreadPoolExecutor'): worker.join(6)
