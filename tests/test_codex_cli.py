import json,unittest
from course_notes.codex_cli import validate_events,usage_delta

class CliEventsTests(unittest.TestCase):
    def test_resumed_thread_usage_is_not_double_counted(self):
        self.assertEqual(usage_delta({'input_tokens':35210,'output_tokens':116,'cached_input_tokens':1000},{'input_tokens':17553,'output_tokens':58,'cached_input_tokens':0}),{'input_tokens':17657,'output_tokens':58,'cached_input_tokens':1000})
    def events(self,*events): return '\n'.join(json.dumps(e) for e in events)
    def test_success_requires_complete_turn(self):
        with self.assertRaises(RuntimeError): validate_events(self.events({'type':'item.completed','item':{'type':'agent_message','text':'partial'}}))
    def test_tools_are_rejected(self):
        for kind in ('command_execution','mcp_tool_call','web_search','file_change','image_view'):
            with self.assertRaises(RuntimeError): validate_events(self.events({'type':'item.completed','item':{'type':kind}},{'type':'turn.completed'}))
    def test_completed_text_is_accepted(self):
        validate_events(self.events({'type':'item.completed','item':{'type':'agent_message','text':'result'}},{'type':'turn.completed'}))
    def test_reconnected_complete_turn_is_accepted(self):
        validate_events(self.events({'type':'error','message':'Reconnecting... 1/1'},{'type':'item.completed','item':{'type':'agent_message','text':'result'}},{'type':'turn.completed'}))
    def test_failed_final_turn_is_rejected(self):
        with self.assertRaises(RuntimeError): validate_events(self.events({'type':'turn.failed'}))
