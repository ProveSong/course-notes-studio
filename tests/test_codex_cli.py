import json,unittest
from course_notes.codex_cli import validate_events

class CliEventsTests(unittest.TestCase):
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
