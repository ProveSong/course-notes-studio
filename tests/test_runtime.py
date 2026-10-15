import json,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import requests
from course_notes.config import Settings
from course_notes.diagnostics import validate_local_runtime
from course_notes.local_control import serve


class RuntimeTests(unittest.TestCase):
    def test_workers_import_standard_secrets(self):
        worker=Path(__file__).resolve().parents[1]/'course_notes'
        result=subprocess.run([sys.executable,'-c','import secrets; print(secrets.token_hex(8))'],cwd=worker,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(result.stdout.strip()),16)

    def test_preflight_detects_missing_environment_before_asr(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Settings(deepread_root=directory,formula_backend='none')
            with self.assertRaisesRegex(FileNotFoundError,'GPU Python'):validate_local_runtime(s)
            python=Path(directory)/'python.exe';python.touch();s.deepread_python=str(python)
            validate_local_runtime(s)

    def test_control_requires_token_for_status_and_cancel(self):
        app=SimpleNamespace(cancel=threading.Event(),after=lambda *args:None)
        with tempfile.TemporaryDirectory() as directory,patch('course_notes.local_control.ROOT',Path(directory)):
            control=serve(app)
            try:
                self.assertEqual(requests.get(control['url']+'/status',timeout=5).status_code,401)
                self.assertEqual(requests.post(control['url']+'/cancel',timeout=5).status_code,401)
                self.assertFalse(app.cancel.is_set())
                headers={'Authorization':'Bearer '+control['token']}
                self.assertEqual(requests.get(control['url']+'/status',headers=headers,timeout=5).status_code,200)
                self.assertEqual(requests.post(control['url']+'/cancel',headers=headers,timeout=5).status_code,200)
                self.assertTrue(app.cancel.is_set())
            finally:app._control_server.shutdown();app._control_server.server_close()
