import io,json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from course_notes.config import Settings
from course_notes.llm import call
from course_notes.codex_cli import call_cli
from course_notes.conversation import Conversation


class ConversationTests(unittest.TestCase):
    def test_compaction_keeps_conversation_identity_and_archives_complete_history(self):
        provider=SimpleNamespace(identity='fixture',base_url='https://example.test',model='test',wire_api='responses')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'conversation.json'
            session=Conversation(path,provider)
            for index in range(7):
                session.commit({'role':'user','content':str(index)*25000},'answer')
                session=Conversation(path,provider)
            identity=session.row['id'];history=session.messages
            with patch('course_notes.llm._call',return_value='{"context_summary":"Existing course context"}') as remote:
                result=Conversation(path,provider,Settings())
            self.assertEqual(result.row['id'],identity)
            self.assertLess(len(result.messages),len(history))
            from course_notes.conversation import text_size,HISTORY_CHARACTER_BUDGET
            self.assertLess(text_size(result.messages),HISTORY_CHARACTER_BUDGET)
            archive=json.loads(next(path.parent.glob('*checkpoint-001.json')).read_text('utf-8'))
            self.assertEqual(archive['messages'],history)
            self.assertEqual(remote.call_args.kwargs['history'],history)
            with patch('course_notes.llm._call') as remote:
                Conversation(path,provider,Settings());remote.assert_not_called()
    def test_same_prefix_across_text_vision_and_restart(self):
        p=SimpleNamespace(identity='deepseek:direct',base_url='https://example.test',model='deepseek-flash',wire_api='deepseek_messages',key='fixture-key')
        captured=[]
        def remote(settings,provider,prompt,images,cancel,history):
            captured.append(json.loads(json.dumps(history)))
            return '{"markdown":"answer"}'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'conversation.json';image=Path(directory)/'frame.png';image.write_bytes(b'fixture')
            s=Settings(provider='deepseek:direct',conversation_file=str(path))
            with patch('course_notes.llm.selected_provider',return_value=p),patch('course_notes.deepseek_messages.call_messages',side_effect=remote):
                call(s,'first JSON')
                call(replace(s),'second JSON',[image])
                call(replace(s),'third JSON')
                self.assertEqual([len(h) for h in captured],[0,2,4])
                self.assertEqual(captured[2][:2],captured[1])
                self.assertNotIn('base64',json.dumps(captured[2]))
                self.assertIn('image/png',path.read_text('utf-8'))
                history=path.read_bytes()
                with patch('course_notes.deepseek_messages.call_messages',side_effect=RuntimeError('offline')):
                    with self.assertRaises(RuntimeError):call(s,'failed')
                self.assertEqual(path.read_bytes(),history)
                p.model='other-model';call(s,'other destination')
                self.assertEqual(captured[-1],[])
                call(replace(s,conversation_file=str(Path(directory)/'other-video.json')),'other video')
                self.assertEqual(captured[-1],[])
                self.assertNotIn('fixture-key',path.read_text('utf-8'))

    def test_rules_sent_once_video_scope_preserved_and_images_not_replayed(self):
        from course_notes.conversation import economical_history
        prefix='讲义规则：不省略推导。'
        messages=[{'role':'user','task_video':'video-1','content':prefix+'\n材料：旧材料'},
                  {'role':'assistant','content':'旧讲义'},
                  {'role':'user','task_video':'video-2','content':[{'type':'text','text':prefix+'\n材料：新材料'},
                      {'type':'image','source':{'data':'private-base64'}}]},
                  {'role':'assistant','content':'新讲义'}]
        result,seen=economical_history(messages)
        serialized=json.dumps(result,ensure_ascii=False)
        self.assertEqual(serialized.count(prefix),1)
        self.assertIn('video-1',serialized);self.assertIn('video-2',serialized)
        self.assertNotIn('private-base64',serialized)
        self.assertNotIn('旧材料',serialized)
        self.assertNotIn('新材料',serialized)
        self.assertIn('旧讲义',serialized);self.assertIn('新讲义',serialized)
        self.assertNotIn('task_video',serialized)
        self.assertIn('private-base64',json.dumps(messages))

    def test_codex_resumes_exact_thread_and_keeps_private_home(self):
        provider=SimpleNamespace(identity='codex:test',base_url='https://example.test',model='test',wire_api='responses',app='codex',key='fixture-key')
        commands=[];homes=[]
        def launch(command,**kwargs):
            commands.append(command);homes.append(kwargs['env']['CODEX_HOME'])
            Path(command[command.index('-o')+1]).write_text('{"markdown":"result"}','utf-8')
            kwargs['stdout'].write(b'{"type":"thread.started","thread_id":"fixture-thread"}\n{"type":"turn.completed","usage":{"cached_input_tokens":20}}\n')
            return SimpleNamespace(stdin=io.BytesIO(),poll=lambda:0,returncode=0)
        with tempfile.TemporaryDirectory() as directory:
            settings=Settings(conversation_file=str(Path(directory)/'conversation.json'),llm_transport='codex_cli')
            with patch('course_notes.codex_cli.selected_provider',return_value=provider),patch('course_notes.codex_cli.executable',return_value='codex.exe'),patch('course_notes.codex_cli.subprocess.Popen',side_effect=launch),patch('course_notes.usage.record_usage'):
                call_cli(settings,'first');call_cli(settings,'second')
        self.assertNotIn('resume',commands[0]);self.assertNotIn('--ephemeral',commands[0])
        self.assertEqual(commands[1][commands[1].index('resume')+1],'fixture-thread')
        self.assertEqual(homes[0],homes[1])
        self.assertNotIn('fixture-key',str(commands))
