import json,tempfile,unittest,threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from course_notes.config import Settings,selected_provider
from course_notes.llm import call


class MessagesTests(unittest.TestCase):
    def events(self,reason='end_turn',stop=True):
        events=[{'type':'message_start','message':{'usage':{'input_tokens':12}}},
                {'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}},
                {'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':'{"markdown":"公式复核"}'}},
                {'type':'message_delta','delta':{'stop_reason':reason},'usage':{'output_tokens':8}}]
        if stop:events.append({'type':'message_stop'})
        return [line for e in events for line in ('data: '+json.dumps(e),'')]

    def invoke(self,lines,images=(),cancel=None,effort='off'):
        response=SimpleNamespace(status_code=200,iter_lines=lambda **kw:iter(lines),close=lambda:None)
        provider=SimpleNamespace(model='deepseek-flash',wire_api='deepseek_messages',base_url='https://api.deepseek.com/anthropic',key='fixture-key')
        with patch('course_notes.llm.selected_provider',return_value=provider),patch('course_notes.deepseek_messages.requests.post',return_value=response) as post,patch('course_notes.usage.record_usage') as usage:
            result=call(Settings(provider='deepseek:direct',deepseek_reasoning_effort=effort),'JSON',images,cancel)
            return result,post.call_args,usage.call_args

    def test_vision_wire_and_actual_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'frame.png';image.write_bytes(b'fixture')
            result,request,usage=self.invoke(self.events(),[image])
        self.assertEqual(json.loads(result)['markdown'],'公式复核')
        self.assertEqual(request.args[0],'https://api.deepseek.com/anthropic/v1/messages')
        self.assertFalse(request.kwargs['allow_redirects'])
        body=request.kwargs['json']
        self.assertEqual(body['thinking'],{'type':'disabled'})
        self.assertNotIn('tools',body)
        self.assertEqual(body['messages'][0]['content'][1]['source']['media_type'],'image/png')
        self.assertEqual(usage.args[-1],{'input_tokens':12,'output_tokens':8})

    def test_incomplete_and_truncated_not_success(self):
        for lines in (self.events(stop=False),self.events(reason='max_tokens')):
            with self.assertRaisesRegex(RuntimeError,'未完整'):self.invoke(lines)

    def test_medium_enables_thinking_with_official_mapping(self):
        result,request,_=self.invoke(self.events(),effort='medium')
        self.assertEqual(request.kwargs['json']['thinking'],{'type':'enabled'})
        self.assertEqual(request.kwargs['json']['output_config'],{'effort':'high'})
        self.assertEqual(json.loads(result)['markdown'],'公式复核')

    def test_unknown_effort_fails_before_network(self):
        with self.assertRaisesRegex(ValueError,'思考强度'):self.invoke(self.events(),effort='unknown')

    def test_error_does_not_return_partial_text(self):
        with self.assertRaisesRegex(RuntimeError,'overloaded'):
            self.invoke(['data: {"type":"error","error":{"type":"overloaded"}}',''])

    def test_cancel_before_request(self):
        cancel=threading.Event();cancel.set()
        with patch('course_notes.deepseek_messages.requests.post') as post:
            with self.assertRaises(Exception):self.invoke(self.events(),cancel=cancel)
            post.assert_not_called()
