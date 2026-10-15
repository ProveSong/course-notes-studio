import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from course_notes.llm import call


class StreamTests(unittest.TestCase):
    def request(self,events):
        response=SimpleNamespace(status_code=200,text='\n'.join('data: '+json.dumps(e,ensure_ascii=False) for e in events))
        response.json=lambda: (_ for _ in ()).throw(ValueError())
        provider=SimpleNamespace(model='test',wire_api='responses',base_url='https://example.test',key='test')
        with patch('course_notes.llm.selected_provider',return_value=provider),patch('course_notes.llm.requests.post',return_value=response):
            return call(None,'test')

    def test_text_done_without_completed_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'未完成'):
            self.request([{'type':'response.output_text.done','text':'partial'}])

    def test_completed_keeps_chinese(self):
        self.assertEqual(self.request([{'type':'response.completed','response':{'status':'completed','output_text':'模型补充，非老师原话'}}]),'模型补充，非老师原话')

    def test_failed_stream_does_not_return_partial(self):
        with self.assertRaises(RuntimeError):
            self.request([{'type':'response.output_text.delta','delta':'partial'},{'type':'response.failed'}])
