import tempfile,unittest,json
from pathlib import Path
import cv2,numpy as np
from course_notes.board_assets import extract_ink,crop_box,materialize,write_image,latex_warnings,display_latex

class BoardTests(unittest.TestCase):
    def test_nested_formula_and_matrix_syntax(self):
        expression=r'\begin{aligned}\mathbf A&=\begin{pmatrix}a&b\\c&d\end{pmatrix}\\f(x)&=\begin{cases}\frac{\sqrt{x^2+1}}{\sum_{k=1}^{n}k^2}&x>0\\0&x\le0\end{cases}\end{aligned}'
        self.assertEqual(latex_warnings(expression),[])
        self.assertEqual(display_latex(r'\sum_i P_i\log P_i\right)'),r'\sum_i P_i\log P_i)')
        self.assertIn(r'\textcircled{1}',display_latex('①'))
        for invalid in [r'\frac{a}{b',r'\begin{cases}x\end{aligned}',r'\input{secret}']:
            self.assertTrue(latex_warnings(invalid))
    def test_ink_geometry_and_transparency_on_dark_and_light_boards(self):
        for background,paper,ink in [('dark',65,220),('light',235,25)]:
            image=np.full((150,240,3),paper,np.uint8)
            cv2.line(image,(30,120),(200,30),(ink,ink,ink),2)
            cv2.circle(image,(90,70),30,(ink,ink,ink),2)
            transparent,white,metadata=extract_ink(image,background)
            self.assertEqual(transparent.shape,(150,240,4))
            self.assertLess(int(transparent[5,5,3]),5)
            self.assertGreater(int(transparent[70,120,3]),180)
            self.assertLess(int(white[70,120,0]),80)
            self.assertGreater(int(white[5,5,0]),250)
    def test_invalid_boxes_never_crop_unrelated_region(self):
        image=np.zeros((100,100,3),np.uint8)
        for box in [[800,0,100,900],[-1,0,900,900],[0,0,float('nan'),900],[0,0,1,1]]:
            with self.assertRaises(ValueError):crop_box(image,box)
    def test_original_crop_and_manifest_survive_materialization(self):
        with tempfile.TemporaryDirectory() as temporary:
            job=Path(temporary);(job/'visuals').mkdir();source=job/'visuals/原图.png'
            image=np.full((180,240,3),60,np.uint8);cv2.circle(image,(100,80),30,(230,230,230),2);write_image(source,image)
            analysis={'formulas':[{'latex':r'\frac{a}{b}','bbox':[0,0,1000,1000],'confidence':'low','uncertainty':'fixture'}],'diagrams':[{'title':'circle','bbox':[0,0,1000,1000],'background':'dark','uncertainty':'fixture'}]}
            text=materialize(job,'C0001-V000001',source,analysis)
            out=job/'board-assets/C0001-V000001'
            self.assertIn(r'\frac{a}{b}',text)
            self.assertTrue((out/'diagram-01-transparent.png').is_file())
            self.assertEqual(len(json.loads((out/'manifest.json').read_text('utf-8'))['source_sha256']),64)
    def test_complex_slide_background_is_preserved(self):
        image=np.arange(1800,dtype=np.uint8).reshape(20,30,3)
        transparent,white,metadata=extract_ink(image,'preserve')
        self.assertTrue(np.array_equal(image,white));self.assertTrue(np.all(transparent[:,:,3]==255))
