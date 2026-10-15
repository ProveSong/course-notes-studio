import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from course_notes.config import Settings
from course_notes.formulas import annotate_formulas

class FormulaCacheTests(unittest.TestCase):
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
