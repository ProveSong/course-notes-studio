import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from course_notes.config import Settings
from course_notes.formulas import annotate_formulas

class FormulaCacheTests(unittest.TestCase):
    def test_pix2tex_dispatch_is_explicit_and_does_not_relabel_paddle_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Path(directory);model=job/'weights';model.mkdir()
            for name in ('weights.pth','image_resizer.pth'):(model/name).write_bytes(b'fixture')
            settings=Settings(formula_backend='pix2tex',pix2tex_model_dir=str(model),pix2tex_python='isolated-python')
            rows=[{'image':'a.png','formula_regions':[{'bbox':[0,0,1000,1000]}]}]
            def worker(command,*args):
                self.assertEqual(command[0],Path('isolated-python'))
                self.assertEqual(command[1].name,'pix2tex_worker.py')
                (job/'formulas.json').write_text(json.dumps([{'row':0,'latex':'x=1','backend':'pix2tex-0.1.4'}]))
            with patch('course_notes.formulas.run_command',side_effect=worker):
                result=annotate_formulas(rows,job,settings,lambda *a:None)
            self.assertEqual(result[0]['local_formulas'][0]['backend'],'pix2tex-0.1.4')
            self.assertEqual(json.loads((job/'formula-request.json').read_text())['backend'],'pix2tex')
            (job/'formula-request.json').write_text(json.dumps({'backend':'paddle'}))
            with patch('course_notes.formulas.run_command') as run:
                with self.assertRaisesRegex(ValueError,'后端已变化'):annotate_formulas(rows,job,settings,lambda *a:None)
                run.assert_not_called()
    def test_source_matched_review_reused_without_gpu_or_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Path(directory);(job/'visuals').mkdir();(job/'board-assets/item').mkdir(parents=True)
            source=job/'visuals/a.png';source.write_bytes(b'fixture')
            value={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'analysis':{'formulas':[{'latex':'x=1','bbox':[0,0,1000,1000],'confidence':'high'}]}}
            (job/'board-assets/item/manifest.json').write_text(json.dumps(value),'utf-8')
            rows=[{'image':'visuals/a.png','ocr_regions':[{'text':'x=1','bbox':[0,0,1000,1000]}]}]
            with patch('course_notes.formulas.run_command') as run:
                result=annotate_formulas(rows,job,Settings(),lambda *x:None)
            run.assert_not_called()
            self.assertEqual(result[0]['local_formulas'][0]['latex'],'x=1')
            self.assertNotIn('local_formulas',rows[0])
            # A changed source cannot carry old review results forward.
            source.write_bytes(b'changed')
            result=annotate_formulas([{'image':'visuals/a.png','local_formulas':result[0]['local_formulas']}],job,Settings(),lambda *x:None)
            self.assertNotIn('local_formulas',result[0])
