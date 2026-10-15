import json,unittest,tempfile,os
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from course_notes.config import Settings,selected_provider,visual_settings
from course_notes.llm import call

class DeepSeekTests(unittest.TestCase):
    def provider(self):return SimpleNamespace(model='deepseek-chat',wire_api='chat_completions',base_url='https://api.deepseek.com',key='secret-test-key')
    def test_chat_endpoint_json_and_usage(self):
        response=SimpleNamespace(status_code=200,json=lambda:{'choices':[{'finish_reason':'stop','message':{'content':'{"markdown":"课程"}'}}],'usage':{'prompt_tokens':10}},text='')
        settings=Settings(provider='deepseek:direct',llm_transport='codex_cli')
        with patch('course_notes.llm.selected_provider',return_value=self.provider()),patch('course_notes.llm.requests.post',return_value=response) as post,patch('course_notes.usage.record_usage') as usage:
            self.assertEqual(json.loads(call(settings,'output JSON'))['markdown'],'课程')
            self.assertEqual(post.call_args.args[0],'https://api.deepseek.com/v1/chat/completions')
            self.assertEqual(post.call_args.kwargs['json']['response_format'],{'type':'json_object'})
            self.assertNotIn('secret-test-key',str(post.call_args.kwargs['json']))
            usage.assert_called_once()
    def test_image_rejected_without_network(self):
        with patch('course_notes.llm.selected_provider',return_value=self.provider()),patch('course_notes.llm.requests.post') as post:
            with self.assertRaisesRegex(ValueError,'不支持截图'):call(Settings(provider='deepseek:direct'),'prompt',['image.png'])
            post.assert_not_called()
    def test_truncation_is_not_accepted(self):
        response=SimpleNamespace(status_code=200,text='',json=lambda:{'choices':[{'finish_reason':'length','message':{'content':'partial'}}]})
        with patch('course_notes.llm.selected_provider',return_value=self.provider()),patch('course_notes.llm.requests.post',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'未完整'):call(Settings(),'prompt')
    def test_visual_configuration_preserves_independent_model(self):
        s=Settings(provider='deepseek:direct',model='deepseek-chat',vision_provider='codex:test',vision_model='vision-model',vision_transport='codex_cli')
        v=visual_settings(s)
        self.assertEqual((v.provider,v.model,v.llm_transport),('codex:test','vision-model','codex_cli'))
        self.assertEqual(s.provider,'deepseek:direct')
        with self.assertRaises(ValueError):visual_settings(Settings(provider='deepseek:direct',deepseek_protocol='chat_completions'))
        self.assertEqual(visual_settings(Settings(provider='deepseek:direct')).model,'deepseek-flash')
    def test_key_not_saved_in_settings(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'secret-test-key'}):
            p=selected_provider(Settings(provider='deepseek:direct'))
            self.assertEqual(p.key,'secret-test-key')
            self.assertEqual(p.wire_api,'deepseek_messages')
            self.assertEqual(p.base_url,'https://api.deepseek.com/anthropic')
    @unittest.skipUnless(os.name=='nt','DPAPI requires Windows')
    def test_dpapi_roundtrip(self):
        from course_notes.credential_store import crypt
        encrypted=crypt(b'local-test-secret')
        self.assertNotIn(b'local-test-secret',encrypted)
        self.assertEqual(crypt(encrypted,True),b'local-test-secret')
