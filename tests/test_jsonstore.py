import json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from course_notes.jsonstore import transaction

class JsonStoreTests(unittest.TestCase):
    def test_transient_windows_denial_retries_without_losing_update(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';path.write_text('[1]','utf-8')
            original=os.replace;calls=[]
            def replace(source,target):
                calls.append(source)
                if len(calls)<3:raise PermissionError('temporarily open')
                original(source,target)
            with patch('course_notes.jsonstore.os.replace',side_effect=replace),patch('course_notes.jsonstore.time.sleep'):
                with transaction(path) as rows:rows.append(2)
            self.assertEqual(json.loads(path.read_text('utf-8')),[1,2])
            self.assertEqual(len(calls),3)
            self.assertEqual(len(set(calls)),1)
